# ruff: noqa
import json
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

APP = Path('/app')
ROLLOUTCTL = APP / 'bin' / 'rolloutctl'
GATEWAYD = APP / 'bin' / 'gatewayd'


def run_ctl(*args: str, check: bool = True, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    result = subprocess.run([str(ROLLOUTCTL), *args], cwd=APP, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
    if check and result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    return result


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])


class Gateway:
    def __init__(self, root: Path, region: str):
        self.port = free_port()
        self.url = f'http://127.0.0.1:{self.port}'
        self.state_path = root / f'gateway-{region}.json'
        self.proc = subprocess.Popen([str(GATEWAYD), '--region', region, '--state', str(self.state_path), '--listen', f'127.0.0.1:{self.port}'], cwd=APP, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(self.url + '/healthz', timeout=0.2) as response:
                    if response.status == 200:
                        return
            except Exception:
                time.sleep(0.02)
        raise AssertionError('gateway did not start')

    def state(self) -> dict:
        with urllib.request.urlopen(self.url + '/debug/state', timeout=2) as response:
            return json.load(response)

    def close(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.proc.kill(); self.proc.wait(timeout=3)


def policy(path: Path, body: str) -> Path:
    path.write_text(body, encoding='utf-8')
    return path


def enqueue(state: Path, policy_path: Path, rollout: str, generation: int, regions: str = 'us-east') -> None:
    run_ctl('enqueue', '--state', str(state), '--rollout', rollout, '--generation', str(generation), '--policy', str(policy_path), '--regions', regions)


def gateway_map(path: Path, mapping: dict[str, str]) -> Path:
    path.write_text(json.dumps(mapping), encoding='utf-8')
    return path


def status(state: Path) -> dict:
    return json.loads(run_ctl('status', '--state', str(state)).stdout)


def delivery(doc: dict, rollout_id: str, region: str) -> dict:
    rollout = next(item for item in doc['rollouts'] if item['id'] == rollout_id)
    return next(item for item in rollout['deliveries'] if item['region'] == region)


@pytest.fixture(scope='session', autouse=True)
def build_binaries() -> None:
    result = subprocess.run(['/app/scripts/build.sh'], cwd=APP, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=90)
    assert result.returncode == 0, result.stdout


class TestMilestone4:
    def test_legacy_v1_queue_record_dispatches_and_survives_compaction(self, tmp_path: Path) -> None:
        """The documented rollback-node record shape is normalized, delivered, and retained in the current snapshot model."""
        gateway = Gateway(tmp_path, 'us-east')
        try:
            state = tmp_path / 'controller'
            state.mkdir()
            legacy = {
                'version': 1,
                'type': 'queued',
                'id': 'legacy-250',
                'revision': 250,
                'policy': '{"deny_mcc":[7995]}',
                'regions': ['us-east'],
            }
            (state / 'journal.jsonl').write_text(json.dumps(legacy) + '\n', encoding='utf-8')
            before = status(state)
            item = delivery(before, 'legacy-250', 'us-east')
            assert item['status'] == 'pending'
            assert item['command_id'].startswith('cmd-')
            mapping = gateway_map(tmp_path / 'gateways.json', {'us-east': gateway.url})
            run_ctl('dispatch', '--state', str(state), '--gateways', str(mapping), '--worker-id', 'legacy', '--now-unix', '1000')
            run_ctl('compact', '--state', str(state))
            after = status(state)
            assert delivery(after, 'legacy-250', 'us-east')['status'] == 'acked'
            assert after['active_generation']['us-east'] == 250
            assert len(gateway.state()['audits']) == 1
            assert (state / 'journal.jsonl').read_bytes() == b''
        finally:
            gateway.close()

    def test_compaction_preserves_completed_history_and_active_generation_fence(self, tmp_path: Path) -> None:
        """Acknowledged and superseded deliveries remain terminal after compaction and are not sent again."""
        gateway = Gateway(tmp_path, 'eu-west')
        try:
            state = tmp_path / 'controller'
            mapping = gateway_map(tmp_path / 'gateways.json', {'eu-west': gateway.url})
            enqueue(state, policy(tmp_path / 'new.json', '{"deny_mcc":[4829]}'), 'fr-261', 261, 'eu-west')
            run_ctl('dispatch', '--state', str(state), '--gateways', str(mapping), '--worker-id', 'new', '--now-unix', '2000')
            enqueue(state, policy(tmp_path / 'old.json', '{"deny_mcc":[7995]}'), 'fr-260', 260, 'eu-west')
            run_ctl('dispatch', '--state', str(state), '--gateways', str(mapping), '--worker-id', 'old', '--now-unix', '2001')
            before = status(state)
            attempts_before = dict(gateway.state()['request_attempts'])
            run_ctl('compact', '--state', str(state))
            after = status(state)
            assert after == before
            run_ctl('dispatch', '--state', str(state), '--gateways', str(mapping), '--worker-id', 'post-compact', '--now-unix', '2002')
            assert status(state) == before
            assert gateway.state()['request_attempts'] == attempts_before
            assert delivery(after, 'fr-260', 'eu-west')['status'] == 'superseded'
            assert delivery(after, 'fr-261', 'eu-west')['status'] == 'acked'
        finally:
            gateway.close()

    def test_compaction_preserves_claim_lease_token_and_command_identity(self, tmp_path: Path) -> None:
        """A claimed delivery remains unavailable until its original lease expires even when the journal is compacted."""
        gateway = Gateway(tmp_path, 'ap-south')
        try:
            state = tmp_path / 'controller'
            mapping = gateway_map(tmp_path / 'gateways.json', {'ap-south': gateway.url})
            enqueue(state, policy(tmp_path / 'p.json', '{"velocity":{"max_attempts":5}}'), 'fr-270', 270, 'ap-south')
            stopped = run_ctl('dispatch', '--state', str(state), '--gateways', str(mapping), '--worker-id', 'owner', '--now-unix', '500', '--failpoint', 'after-claim:ap-south', check=False)
            assert stopped.returncode == 85
            claimed = delivery(status(state), 'fr-270', 'ap-south')
            run_ctl('compact', '--state', str(state))
            compacted = delivery(status(state), 'fr-270', 'ap-south')
            assert compacted == claimed
            run_ctl('dispatch', '--state', str(state), '--gateways', str(mapping), '--worker-id', 'early', '--now-unix', '530')
            assert gateway.state()['request_attempts'] == {}
            run_ctl('dispatch', '--state', str(state), '--gateways', str(mapping), '--worker-id', 'late', '--now-unix', '531')
            final = delivery(status(state), 'fr-270', 'ap-south')
            assert final['status'] == 'acked'
            assert final['command_id'] == claimed['command_id']
            assert final['claim_token'] == 2
        finally:
            gateway.close()

    def test_interrupted_compaction_records_replay_offset_and_restart_is_exact(self, tmp_path: Path) -> None:
        """A stop after snapshot rename leaves the old journal intact but represented exactly once through its byte offset."""
        state = tmp_path / 'controller'
        enqueue(state, policy(tmp_path / 'a.json', '{"deny_mcc":[7995]}'), 'fr-280', 280)
        enqueue(state, policy(tmp_path / 'b.json', '{"deny_mcc":[4829]}'), 'fr-281', 281)
        journal = state / 'journal.jsonl'
        old_bytes = journal.read_bytes()
        before = status(state)
        stopped = run_ctl('compact', '--state', str(state), '--failpoint', 'after-snapshot-rename', check=False)
        assert stopped.returncode == 87
        assert journal.read_bytes() == old_bytes
        snapshot = json.loads((state / 'snapshot.json').read_text(encoding='utf-8'))
        assert snapshot['journal_offset'] == len(old_bytes)
        assert status(state) == before

        enqueue(state, policy(tmp_path / 'c.json', '{"deny_mcc":[6011]}'), 'fr-282', 282)
        ids = [item['id'] for item in status(state)['rollouts']]
        assert ids == ['fr-280', 'fr-281', 'fr-282']
        run_ctl('compact', '--state', str(state))
        assert [item['id'] for item in status(state)['rollouts']] == ids
        assert (state / 'journal.jsonl').read_bytes() == b''
        assert json.loads((state / 'snapshot.json').read_text(encoding='utf-8'))['journal_offset'] == 0

    def test_unknown_or_complete_malformed_records_remain_non_destructive_errors(self, tmp_path: Path) -> None:
        """Compatibility is limited to the documented legacy shape and does not turn other corruption into silent recovery."""
        for name, raw in (
            ('unknown', b'{"version":9,"type":"queued"}\n'),
            ('malformed', b'{not-json}\n'),
        ):
            state = tmp_path / name
            state.mkdir()
            journal = state / 'journal.jsonl'
            journal.write_bytes(raw)
            result = run_ctl('status', '--state', str(state), check=False)
            assert result.returncode != 0
            assert journal.read_bytes() == raw
            assert not (state / 'recovery').exists()
