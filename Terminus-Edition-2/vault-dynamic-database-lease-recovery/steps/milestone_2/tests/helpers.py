# ruff: noqa
import concurrent.futures
import datetime as dt
import json
import os
import shutil
import signal
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest

APP_ROOT = Path(os.environ.get("TASK_APP_ROOT", "/app"))
RUNTIME_BIN = os.environ.get("VAULT_DB_RUNTIME_BIN", "/opt/task-tools/vault-db-runtime")
NOW = dt.datetime(2026, 6, 23, 10, 0, 0, tzinfo=dt.timezone.utc)

@dataclass
class Result:
    process: subprocess.CompletedProcess
    payload: dict
    @property
    def ok(self): return self.payload.get("ok") is True and self.process.returncode == 0
    @property
    def result(self): return self.payload.get("result", self.payload)
    @property
    def code(self): return self.payload.get("error", {}).get("code")

class Workspace:
    def __init__(self, root: Path, binaries: dict[str, Path]):
        self.root = root
        self.state = root / "state"
        self.runtime = root / "runtime"
        self.config = root / "config"
        self.log = root / "logs" / "lease-agent.jsonl"
        self.binaries = binaries
        shutil.copytree(APP_ROOT / "state", self.state)
        shutil.copytree(APP_ROOT / "config", self.config)
        self.runtime.mkdir(parents=True)
        self.log.parent.mkdir(parents=True)
        self.runtime_cmd("reset")

    @property
    def env(self):
        env = os.environ.copy()
        env.update({
            "LEASE_AGENT_STATE_DIR": str(self.state),
            "LEASE_AGENT_CONFIG_DIR": str(self.config),
            "LEASE_AGENT_LOG": str(self.log),
            "VAULT_DB_RUNTIME_DIR": str(self.runtime),
            "VAULT_DB_RUNTIME_BIN": RUNTIME_BIN,
        })
        return env

    def _run(self, command, *, check=False, timeout=90):
        proc = subprocess.Popen(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env, start_new_session=True)
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            stdout, stderr = proc.communicate()
            raise AssertionError(f"command timed out after {timeout}s: {command}\nstdout={stdout}\nstderr={stderr}")
        p = subprocess.CompletedProcess(command, proc.returncode, stdout, stderr)
        if check and p.returncode != 0:
            raise AssertionError(f"command failed {command}: rc={p.returncode}\nstdout={p.stdout}\nstderr={p.stderr}")
        try:
            payload = json.loads(p.stdout.strip().splitlines()[-1]) if p.stdout.strip() else {}
        except json.JSONDecodeError as exc:
            raise AssertionError(f"non-JSON output from {command}: {p.stdout!r} {p.stderr!r}") from exc
        return Result(p, payload)

    def runtime_cmd(self, *args, check=True): return self._run([RUNTIME_BIN, *map(str,args)], check=check)
    def agent(self, *args, check=False): return self._run([str(self.binaries["lease-agent"]), *map(str,args)], check=check)
    def payment(self, *args, check=False): return self._run([str(self.binaries["payment-api"]), *map(str,args)], check=check)

    def write_json(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, sort_keys=True))
        return path

    def claims(self, *, pod_uid=None, issuer="https://kubernetes.default.svc.cluster.local",
               subject="system:serviceaccount:payments:payment-ledger-api",
               audience=None, namespace="payments", service_account="payment-ledger-api",
               exp=None, nbf=None, extra=None):
        pod_uid = pod_uid or f"pod-{uuid.uuid4().hex[:12]}"
        if audience is None: audience = ["vault.payment-ledger.internal"]
        value = {
            "iss": issuer, "sub": subject, "aud": audience,
            "namespace": namespace, "service_account": service_account,
            "pod_uid": pod_uid, "iat": int(NOW.timestamp()) - 10,
            "nbf": int(NOW.timestamp()) - 10 if nbf is None else nbf,
            "exp": int(NOW.timestamp()) + 3600 if exp is None else exp,
        }
        if extra: value.update(extra)
        return value

    def token(self, claims=None, *, name=None):
        claims = claims or self.claims()
        cpath = self.write_json(f"claims/{name or uuid.uuid4().hex}.json", claims)
        minted = self.runtime_cmd("mint-token", "--claims", cpath).payload["token"]
        tpath = self.root / "tokens" / f"{name or uuid.uuid4().hex}.jwt"
        tpath.parent.mkdir(parents=True, exist_ok=True)
        tpath.write_text(minted)
        return tpath, claims

    def request(self, claims, *, request_id=None, pod_uid=None, role="payment-ledger",
                vault_role="payment-ledger-k8s", protocol=2, generation=1, name=None):
        value = {
            "request_id": request_id or f"req-{uuid.uuid4().hex}",
            "pod_uid": pod_uid if pod_uid is not None else claims.get("pod_uid", ""),
            "vault_role": vault_role, "database_role": role,
            "requested_at": "2026-06-23T10:00:00Z",
            "protocol_version": protocol, "generation": generation,
        }
        return self.write_json(f"requests/{name or uuid.uuid4().hex}.json", value), value

    def login(self, token): return self.agent("login", "--token", token)
    def issue(self, token, request, protocol=None):
        args = ["issue", "--token", token, "--request", request]
        if protocol is not None: args += ["--protocol", str(protocol)]
        return self.agent(*args)
    def renew(self, token, lease_id, protocol=2): return self.agent("renew", "--token", token, "--lease-id", lease_id, "--protocol", protocol)
    def rotate(self, token, request, protocol=2): return self.agent("rotate", "--token", token, "--request", request, "--protocol", protocol)
    def revoke(self, token, lease_id): return self.agent("revoke", "--token", token, "--lease-id", lease_id)
    def cleanup(self): return self.agent("cleanup")
    def reconcile(self): return self.agent("reconcile")
    def shutdown(self, token): return self.agent("shutdown", "--token", token)

    def issue_lease(self, *, pod_uid=None, protocol=2, request_id=None):
        token, claims = self.token(self.claims(pod_uid=pod_uid))
        request, request_value = self.request(claims, request_id=request_id, protocol=protocol)
        result = self.issue(token, request, protocol)
        assert result.ok, (result.process.stdout, result.process.stderr)
        return token, claims, request, request_value, result.result

    def inspect(self, kind): return self.runtime_cmd("inspect", kind).payload
    def fail(self, point, *, count=1, request_id=None, lease_id=None, pod_uid=None):
        args = ["inject-failure", "--point", point, "--count", str(count)]
        if request_id: args += ["--request-id", request_id]
        if lease_id: args += ["--lease-id", lease_id]
        if pod_uid: args += ["--pod-uid", pod_uid]
        return self.runtime_cmd(*args)
    def advance(self, duration): return self.runtime_cmd("clock", "advance", duration)
    def set_clock(self, value): return self.runtime_cmd("clock", "set", value)

    def dbop(self, pod_uid, operation="SELECT_PAYMENT_STATUS", tenant="payments", generation=0):
        req = {"pod_uid": pod_uid, "operation": operation, "tenant": tenant}
        if generation: req["generation"] = generation
        path = self.write_json(f"dbops/{uuid.uuid4().hex}.json", req)
        return self.payment("db-op", "--request", path)

    def session_open(self, pod_uid, operation="SELECT_PAYMENT_STATUS", tenant="payments"):
        path = self.write_json(f"sessions/{uuid.uuid4().hex}.json", {"pod_uid":pod_uid,"operation":operation,"tenant":tenant})
        return self.payment("session-open", "--request", path)
    def session_exec(self, session_id, operation="SELECT_PAYMENT_STATUS", tenant="payments"):
        path = self.write_json(f"sessions/{uuid.uuid4().hex}.json", {"session_id":session_id,"operation":operation,"tenant":tenant})
        return self.payment("session-exec", "--request", path)

    def app_json(self, name): return json.loads((self.state / name).read_text())
    def app_text(self, name): return (self.state / name).read_text()

@pytest.fixture(scope="session", autouse=True)
def protected_integrity():
    """Reject edits to the trusted runtime and incident evidence used by the verifier."""
    import hashlib
    manifest = json.loads(Path(__file__).with_name("protected-integrity.json").read_text())
    for key, expected in manifest.items():
        path = Path(RUNTIME_BIN) if key == "runtime" else APP_ROOT / key.removeprefix("app:")
        assert path.is_file(), f"protected file missing: {key}"
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == expected, f"protected file changed: {key}"

@pytest.fixture(scope="session")
def binaries():
    lease = Path(os.environ.get("LEASE_AGENT_TEST_BIN", str(APP_ROOT / "build" / "lease-agent")))
    payment = Path(os.environ.get("PAYMENT_API_TEST_BIN", str(APP_ROOT / "build" / "payment-api")))
    if not lease.exists() or not payment.exists():
        raise AssertionError("verifier binaries were not built before pytest")
    return {"lease-agent": lease, "payment-api": payment}

@pytest.fixture
def ws(tmp_path, binaries): return Workspace(tmp_path, binaries)

def assert_denied(result, code):
    assert not result.ok
    assert result.code == code, result.payload

def runtime_user_count(ws, *, active_only=False):
    users = ws.inspect("database-users")["database_users"]
    return sum(1 for u in users if not active_only or u["active"])

def runtime_lease_count(ws, *, active_only=False):
    leases = ws.inspect("leases")["leases"]
    return sum(1 for l in leases if not active_only or l["status"] == "ACTIVE")

def source_text(): return "\n".join(p.read_text() for p in (APP_ROOT/"internal").rglob("*.go"))
