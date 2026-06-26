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
        output = self.proc.stdout.read() if self.proc.stdout else ''
        raise AssertionError(f'gateway did not start: {output}')

    def state(self) -> dict:
        with urllib.request.urlopen(self.url + '/debug/state', timeout=2) as response:
            return json.load(response)

    def close(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=3)


def write_policy(path: Path, body: str) -> None:
    path.write_text(body, encoding='utf-8')


def enqueue(state: Path, policy: Path, rollout: str, generation: int, regions: str) -> None:
    run_ctl('enqueue', '--state', str(state), '--rollout', rollout, '--generation', str(generation), '--policy', str(policy), '--regions', regions)


def gateways_file(path: Path, mapping: dict[str, str]) -> Path:
    path.write_text(json.dumps(mapping), encoding='utf-8')
    return path


def status(state: Path) -> dict:
    return json.loads(run_ctl('status', '--state', str(state)).stdout)


@pytest.fixture(scope='session', autouse=True)
def build_binaries() -> None:
    result = subprocess.run(['/app/scripts/build.sh'], cwd=APP, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=90)
    assert result.returncode == 0, result.stdout


class TestMilestone2:
    def test_crash_after_remote_apply_reuses_one_delivery_identity(self, tmp_path: Path) -> None:
        """A remote success followed by process death replays with the same command and one activation audit."""
        gateway = Gateway(tmp_path, 'us-east')
        try:
            controller = tmp_path / 'controller'
            policy = tmp_path / 'policy.json'
            write_policy(policy, '{"deny_mcc":[4829,7995]}')
            enqueue(controller, policy, 'fr-184', 184, 'us-east')
            mapping = gateways_file(tmp_path / 'gateways.json', {'us-east': gateway.url})

            crashed = run_ctl('dispatch', '--state', str(controller), '--gateways', str(mapping), '--workers', '1', '--worker-id', 'first', '--now-unix', '1000', '--failpoint', 'after-apply:us-east', check=False)
            assert crashed.returncode == 86
            first_remote = gateway.state()
            assert len(first_remote['audits']) == 1
            assert len(first_remote['seen']) == 1
            assert status(controller)['rollouts'][0]['deliveries'][0]['status'] in {'pending', 'claimed'}

            run_ctl('dispatch', '--state', str(controller), '--gateways', str(mapping), '--workers', '1', '--worker-id', 'retry', '--now-unix', '1031')
            remote = gateway.state()
            delivery = status(controller)['rollouts'][0]['deliveries'][0]
            assert delivery['status'] == 'acked'
            assert len(remote['audits']) == 1
            assert list(remote['seen']) == [delivery['command_id']]
            assert remote['request_attempts'][delivery['command_id']] == 2
        finally:
            gateway.close()

    def test_acked_delivery_is_not_sent_again_on_later_dispatch(self, tmp_path: Path) -> None:
        """Normal repeated dispatch after acknowledgement is a no-op on both persistent sides."""
        gateway = Gateway(tmp_path, 'eu-west')
        try:
            controller = tmp_path / 'controller'
            policy = tmp_path / 'policy.json'
            write_policy(policy, '{"velocity":{"window_seconds":60,"max_attempts":5}}')
            enqueue(controller, policy, 'fr-185', 185, 'eu-west')
            mapping = gateways_file(tmp_path / 'gateways.json', {'eu-west': gateway.url})
            run_ctl('dispatch', '--state', str(controller), '--gateways', str(mapping), '--worker-id', 'one', '--now-unix', '2000')
            before = gateway.state()
            run_ctl('dispatch', '--state', str(controller), '--gateways', str(mapping), '--worker-id', 'two', '--now-unix', '2001')
            assert gateway.state() == before
        finally:
            gateway.close()

    def test_multi_region_restart_converges_without_duplicate_activation(self, tmp_path: Path) -> None:
        """A crash in one region preserves stable identities and one activation per region across the full rollout."""
        us = Gateway(tmp_path, 'us-east')
        eu = Gateway(tmp_path, 'eu-west')
        try:
            controller = tmp_path / 'controller'
            policy = tmp_path / 'policy.json'
            write_policy(policy, '{"deny_mcc":[7995],"velocity":{"max_attempts":4}}')
            enqueue(controller, policy, 'fr-186', 186, 'us-east,eu-west')
            mapping = gateways_file(tmp_path / 'gateways.json', {'us-east': us.url, 'eu-west': eu.url})
            crashed = run_ctl('dispatch', '--state', str(controller), '--gateways', str(mapping), '--worker-id', 'first', '--now-unix', '3000', '--failpoint', 'after-apply:us-east', check=False)
            assert crashed.returncode == 86
            run_ctl('dispatch', '--state', str(controller), '--gateways', str(mapping), '--worker-id', 'retry', '--now-unix', '3031')
            doc = status(controller)
            assert {d['region']: d['status'] for d in doc['rollouts'][0]['deliveries']} == {'eu-west': 'acked', 'us-east': 'acked'}
            for remote in (us.state(), eu.state()):
                assert len(remote['audits']) == 1
                assert len(remote['seen']) == 1
        finally:
            us.close()
            eu.close()

    def test_same_generation_different_policy_is_rejected(self, tmp_path: Path) -> None:
        """The retry repair does not weaken gateway conflict handling for a reused generation with different bytes."""
        gateway = Gateway(tmp_path, 'ap-south')
        try:
            controller = tmp_path / 'controller'
            p1 = tmp_path / 'p1.json'
            p2 = tmp_path / 'p2.json'
            write_policy(p1, '{"deny_mcc":[7995]}')
            write_policy(p2, '{"deny_mcc":[4829]}')
            mapping = gateways_file(tmp_path / 'gateways.json', {'ap-south': gateway.url})
            enqueue(controller, p1, 'fr-a', 190, 'ap-south')
            run_ctl('dispatch', '--state', str(controller), '--gateways', str(mapping), '--worker-id', 'a', '--now-unix', '4000')
            enqueue(controller, p2, 'fr-b', 190, 'ap-south')
            run_ctl('dispatch', '--state', str(controller), '--gateways', str(mapping), '--worker-id', 'b', '--now-unix', '4001')
            doc = status(controller)
            by_id = {r['id']: r for r in doc['rollouts']}
            assert by_id['fr-a']['deliveries'][0]['status'] == 'acked'
            assert by_id['fr-b']['deliveries'][0]['status'] == 'failed'
            assert gateway.state()['active_generation'] == 190
            assert len(gateway.state()['audits']) == 1
        finally:
            gateway.close()

    def test_enqueue_replay_is_idempotent_but_conflicting_redefinition_is_rejected(self, tmp_path: Path) -> None:
        """Stable delivery work preserves the existing enqueue identity and non-destructive conflict contract."""
        controller = tmp_path / 'controller'
        p1 = tmp_path / 'p1.json'
        p2 = tmp_path / 'p2.json'
        write_policy(p1, '{"deny_mcc":[7995]}')
        write_policy(p2, '{"deny_mcc":[4829]}')
        enqueue(controller, p1, 'fr-191', 191, 'us-east')
        journal = controller / 'journal.jsonl'
        before = journal.read_bytes()
        enqueue(controller, p1, 'fr-191', 191, 'us-east')
        assert journal.read_bytes() == before
        conflict = run_ctl('enqueue', '--state', str(controller), '--rollout', 'fr-191', '--generation', '191', '--policy', str(p2), '--regions', 'us-east', check=False)
        assert conflict.returncode != 0
        assert journal.read_bytes() == before
