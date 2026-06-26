# ruff: noqa
import json
import socket
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Optional

import pytest

APP = Path('/app')
ROLLOUTCTL = APP / 'bin' / 'rolloutctl'
GATEWAYD = APP / 'bin' / 'gatewayd'


def run_ctl(*args: str, check: bool = True, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    result = subprocess.run([str(ROLLOUTCTL), *args], cwd=APP, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
    if check and result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    return result


def spawn_ctl(*args: str) -> subprocess.Popen[str]:
    return subprocess.Popen([str(ROLLOUTCTL), *args], cwd=APP, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])


class Gateway:
    def __init__(self, root: Path, region: str, hold_generation: int = 0, started: Optional[Path] = None, release: Optional[Path] = None):
        self.region = region
        self.port = free_port()
        self.url = f'http://127.0.0.1:{self.port}'
        self.state_path = root / f'gateway-{region}.json'
        args = [str(GATEWAYD), '--region', region, '--state', str(self.state_path), '--listen', f'127.0.0.1:{self.port}']
        if hold_generation:
            args += ['--hold-generation', str(hold_generation), '--started-file', str(started), '--release-file', str(release)]
        self.proc = subprocess.Popen(args, cwd=APP, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
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


def wait_for_file(path: Path, timeout: float = 5) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists() and path.stat().st_size > 0:
            return
        time.sleep(0.02)
    raise AssertionError(f'timed out waiting for {path}')


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


class TestMilestone3:
    def test_competing_processes_issue_only_one_live_request(self, tmp_path: Path) -> None:
        """A durable unexpired claim prevents two controller processes from concurrently sending the same delivery."""
        started = tmp_path / 'started.log'
        release = tmp_path / 'release'
        gateway = Gateway(tmp_path, 'us-east', hold_generation=210, started=started, release=release)
        try:
            state = tmp_path / 'controller'
            enqueue(state, policy(tmp_path / 'p.json', '{"deny_mcc":[7995]}'), 'fr-210', 210)
            mapping = gateway_map(tmp_path / 'gateways.json', {'us-east': gateway.url})
            first = spawn_ctl('dispatch', '--state', str(state), '--gateways', str(mapping), '--worker-id', 'drain-a', '--now-unix', '1000')
            wait_for_file(started)
            second = spawn_ctl('dispatch', '--state', str(state), '--gateways', str(mapping), '--worker-id', 'drain-b', '--now-unix', '1000')
            second_exited_before_release = False
            try:
                second.wait(timeout=2)
                second_exited_before_release = True
            except subprocess.TimeoutExpired:
                pass
            release.write_text('release\n', encoding='utf-8')
            first.wait(timeout=5)
            if second.poll() is None:
                second.wait(timeout=5)
            assert first.returncode == 0
            assert second.returncode == 0
            remote = gateway.state()
            command_id = delivery(status(state), 'fr-210', 'us-east')['command_id']
            assert second_exited_before_release, 'competing worker remained blocked in a duplicate gateway request'
            assert remote['request_attempts'][command_id] == 1
            assert len(remote['audits']) == 1
        finally:
            gateway.close()

    def test_unexpired_claim_blocks_takeover_and_expired_claim_is_recovered(self, tmp_path: Path) -> None:
        """The 30-second logical lease survives a worker stop and takeover increments the token without changing identity."""
        gateway = Gateway(tmp_path, 'eu-west')
        try:
            state = tmp_path / 'controller'
            enqueue(state, policy(tmp_path / 'p.json', '{"velocity":{"max_attempts":5}}'), 'fr-211', 211, 'eu-west')
            mapping = gateway_map(tmp_path / 'gateways.json', {'eu-west': gateway.url})
            stopped = run_ctl('dispatch', '--state', str(state), '--gateways', str(mapping), '--worker-id', 'owner', '--now-unix', '500', '--failpoint', 'after-claim:eu-west', check=False)
            assert stopped.returncode == 85
            first = delivery(status(state), 'fr-211', 'eu-west')
            assert first['status'] == 'claimed'
            assert first['lease_until'] == 530
            assert first['claim_token'] == 1
            command_id = first['command_id']

            run_ctl('dispatch', '--state', str(state), '--gateways', str(mapping), '--worker-id', 'early', '--now-unix', '530')
            assert gateway.state()['request_attempts'] == {}
            assert delivery(status(state), 'fr-211', 'eu-west')['status'] == 'claimed'

            run_ctl('dispatch', '--state', str(state), '--gateways', str(mapping), '--worker-id', 'takeover', '--now-unix', '531')
            final = delivery(status(state), 'fr-211', 'eu-west')
            assert final['status'] == 'acked'
            assert final['claim_token'] == 2
            assert final['command_id'] == command_id
            assert gateway.state()['request_attempts'][command_id] == 1
        finally:
            gateway.close()

    def test_delayed_older_generation_becomes_superseded_after_newer_apply(self, tmp_path: Path) -> None:
        """An older in-flight request cannot regress regional policy when a newer generation completes first."""
        started = tmp_path / 'old-started'
        release = tmp_path / 'release-old'
        gateway = Gateway(tmp_path, 'ap-south', hold_generation=220, started=started, release=release)
        try:
            state = tmp_path / 'controller'
            old_policy = policy(tmp_path / 'old.json', '{"deny_mcc":[7995]}')
            new_policy = policy(tmp_path / 'new.json', '{"deny_mcc":[4829,7995]}')
            mapping = gateway_map(tmp_path / 'gateways.json', {'ap-south': gateway.url})
            enqueue(state, old_policy, 'fr-220', 220, 'ap-south')
            old = spawn_ctl('dispatch', '--state', str(state), '--gateways', str(mapping), '--worker-id', 'old', '--now-unix', '1000')
            wait_for_file(started)
            enqueue(state, new_policy, 'fr-221', 221, 'ap-south')
            run_ctl('dispatch', '--state', str(state), '--gateways', str(mapping), '--worker-id', 'new', '--now-unix', '1001')
            assert gateway.state()['active_generation'] == 221
            release.write_text('release\n', encoding='utf-8')
            old.wait(timeout=5)
            assert old.returncode == 0
            doc = status(state)
            assert delivery(doc, 'fr-220', 'ap-south')['status'] == 'superseded'
            assert delivery(doc, 'fr-221', 'ap-south')['status'] == 'acked'
            assert doc['active_generation']['ap-south'] == 221
            assert [entry['generation'] for entry in gateway.state()['audits']] == [221]
        finally:
            gateway.close()

    def test_locally_obsolete_pending_rollout_is_superseded_without_request(self, tmp_path: Path) -> None:
        """Once the durable regional fence is newer, an older pending rollout is resolved locally rather than sent."""
        gateway = Gateway(tmp_path, 'us-east')
        try:
            state = tmp_path / 'controller'
            mapping = gateway_map(tmp_path / 'gateways.json', {'us-east': gateway.url})
            enqueue(state, policy(tmp_path / 'new.json', '{"deny_mcc":[4829]}'), 'fr-231', 231)
            run_ctl('dispatch', '--state', str(state), '--gateways', str(mapping), '--worker-id', 'new', '--now-unix', '2000')
            attempts_before = sum(gateway.state()['request_attempts'].values())
            enqueue(state, policy(tmp_path / 'old.json', '{"deny_mcc":[7995]}'), 'fr-230', 230)
            run_ctl('dispatch', '--state', str(state), '--gateways', str(mapping), '--worker-id', 'old', '--now-unix', '2001')
            doc = status(state)
            assert delivery(doc, 'fr-230', 'us-east')['status'] == 'superseded'
            assert sum(gateway.state()['request_attempts'].values()) == attempts_before
        finally:
            gateway.close()

    def test_unmapped_region_stays_pending_while_mapped_region_progresses(self, tmp_path: Path) -> None:
        """Concurrency repair preserves partial gateway-map behavior instead of failing or dropping unmapped work."""
        gateway = Gateway(tmp_path, 'us-east')
        try:
            state = tmp_path / 'controller'
            enqueue(state, policy(tmp_path / 'p.json', '{"deny_mcc":[7995]}'), 'fr-240', 240, 'us-east,eu-west')
            mapping = gateway_map(tmp_path / 'gateways.json', {'us-east': gateway.url})
            run_ctl('dispatch', '--state', str(state), '--gateways', str(mapping), '--workers', '2', '--worker-id', 'partial', '--now-unix', '3000')
            doc = status(state)
            assert delivery(doc, 'fr-240', 'us-east')['status'] == 'acked'
            assert delivery(doc, 'fr-240', 'eu-west')['status'] == 'pending'
        finally:
            gateway.close()
