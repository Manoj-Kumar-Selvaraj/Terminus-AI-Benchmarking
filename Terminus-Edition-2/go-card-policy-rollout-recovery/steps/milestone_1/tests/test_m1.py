# ruff: noqa
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
ROLLOUTCTL = APP / "bin" / "rolloutctl"


def run_ctl(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [str(ROLLOUTCTL), *args],
        cwd=APP,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    return result


def enqueue(state: Path, policy: Path, rollout: str, generation: int, regions: str = "us-east") -> None:
    run_ctl(
        "enqueue",
        "--state",
        str(state),
        "--rollout",
        rollout,
        "--generation",
        str(generation),
        "--policy",
        str(policy),
        "--regions",
        regions,
    )


def read_status(state: Path) -> dict:
    return json.loads(run_ctl("status", "--state", str(state)).stdout)


@pytest.fixture(scope="session", autouse=True)
def build_binaries() -> None:
    result = subprocess.run(
        ["/app/scripts/build.sh"], cwd=APP, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=90
    )
    assert result.returncode == 0, result.stdout


class TestMilestone1:
    def test_torn_final_record_is_quarantined_without_losing_valid_prefix(self, tmp_path: Path) -> None:
        """A malformed non-newline suffix is saved byte-for-byte while earlier accepted rollouts remain visible."""
        state = tmp_path / "state"
        policy_a = tmp_path / "a.json"
        policy_b = tmp_path / "b.json"
        policy_a.write_text('{"deny_mcc":[7995]}', encoding="utf-8")
        policy_b.write_text('{"deny_mcc":[4829,7995]}', encoding="utf-8")
        enqueue(state, policy_a, "fr-183", 183)
        enqueue(state, policy_b, "fr-184", 184)

        journal = state / "journal.jsonl"
        valid_prefix = journal.read_bytes()
        tail = b'{"version":2,"type":"claimed","rollout_id":"fr-184","reg'
        with journal.open("ab") as handle:
            handle.write(tail)

        status = read_status(state)
        assert [item["id"] for item in status["rollouts"]] == ["fr-183", "fr-184"]
        assert journal.read_bytes() == valid_prefix
        assert (state / "recovery" / "torn-tail.bin").read_bytes() == tail

    def test_recovery_is_idempotent_across_repeated_restarts(self, tmp_path: Path) -> None:
        """Once a torn suffix is recovered, repeated status loads do not mutate the journal or create extra artifacts."""
        state = tmp_path / "state"
        policy = tmp_path / "policy.json"
        policy.write_text('{"velocity":{"window_seconds":60,"max_attempts":5}}', encoding="utf-8")
        enqueue(state, policy, "fr-200", 200)
        journal = state / "journal.jsonl"
        tail = b'{"version":2'
        with journal.open("ab") as handle:
            handle.write(tail)

        first = read_status(state)
        journal_after = journal.read_bytes()
        artifact_after = (state / "recovery" / "torn-tail.bin").read_bytes()
        second = read_status(state)

        assert first == second
        assert journal.read_bytes() == journal_after
        assert artifact_after == tail
        assert [p.name for p in (state / "recovery").iterdir()] == ["torn-tail.bin"]

    def test_complete_malformed_line_is_rejected_without_mutation(self, tmp_path: Path) -> None:
        """A newline-terminated corrupt record remains an operator-visible hard error and is never silently truncated."""
        state = tmp_path / "state"
        policy = tmp_path / "policy.json"
        policy.write_text('{"deny_mcc":[7995]}', encoding="utf-8")
        enqueue(state, policy, "fr-201", 201)
        journal = state / "journal.jsonl"
        with journal.open("ab") as handle:
            handle.write(b"{not-json}\n")
        before = journal.read_bytes()

        result = run_ctl("status", "--state", str(state), check=False)
        assert result.returncode != 0
        assert journal.read_bytes() == before
        assert not (state / "recovery").exists()

    def test_valid_final_record_without_newline_is_accepted(self, tmp_path: Path) -> None:
        """A syntactically valid last JSON record is replayed even when the writer omitted the trailing newline."""
        state = tmp_path / "state"
        state.mkdir()
        event = {
            "version": 2,
            "type": "queued",
            "rollout_id": "fr-202",
            "generation": 202,
            "policy": '{"deny_mcc":[4829]}',
            "regions": ["eu-west"],
        }
        raw = json.dumps(event, separators=(",", ":")).encode()
        (state / "journal.jsonl").write_bytes(raw)

        status = read_status(state)
        assert status["rollouts"][0]["id"] == "fr-202"
        assert (state / "journal.jsonl").read_bytes() == raw
        assert not (state / "recovery").exists()

    def test_invalid_policy_is_rejected_without_creating_journal_state(self, tmp_path: Path) -> None:
        """The existing enqueue validation remains intact while journal recovery is repaired."""
        state = tmp_path / "state"
        invalid = tmp_path / "invalid.json"
        invalid.write_text('{"deny_mcc":', encoding="utf-8")
        result = run_ctl(
            "enqueue",
            "--state",
            str(state),
            "--rollout",
            "bad",
            "--generation",
            "1",
            "--policy",
            str(invalid),
            "--regions",
            "us-east",
            check=False,
        )
        assert result.returncode != 0
        assert not (state / "journal.jsonl").exists()
