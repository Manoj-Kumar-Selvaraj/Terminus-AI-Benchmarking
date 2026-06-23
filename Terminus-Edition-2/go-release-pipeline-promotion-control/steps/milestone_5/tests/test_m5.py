import hashlib
import hmac
import json
import shutil
import subprocess
from pathlib import Path

APP = Path("/app")
KEYS = APP / "config" / "release_history_keys.json"

KEY_CONFIG = {
    "schema_version": "release-history-keys/v1",
    "keys_by_env": {
        "prod": {"key_id": "prod-rollback-2026", "secret": "prod-history-secret"},
        "staging": {
            "key_id": "staging-rollback-2026",
            "secret": "staging-history-secret",
        },
    },
}

FIELDS = [
    "environment",
    "build_number",
    "commit_sha",
    "artifact_hash",
    "promoted_artifact_hash",
    "package_hash",
    "promotion_status",
    "release_contract_version",
]

UNIT_FIELDS = [
    "name",
    "artifact_hash",
    "package_hash",
    "release_contract_version",
]


def write_json(path: Path, value: dict) -> Path:
    """Write a JSON fixture and return its path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")
    return path


def read_json(path: Path) -> dict:
    """Read a generated JSON artifact."""
    return json.loads(path.read_text())


def canonical_parts(history: dict) -> list[str]:
    """Return the signed release-history canonical part sequence."""
    parts = ["release-history/v1", str(history.get("schema_version", ""))]
    for rec in history.get("releases", []):
        for field in FIELDS:
            parts.append(str(rec.get(field, "")))
        units = rec.get("deployment_units", [])
        parts.append(str(len(units)))
        for unit in units:
            for field in UNIT_FIELDS:
                parts.append(str(unit.get(field, "")))
    return parts


def canonical_bytes(history: dict) -> bytes:
    """Return the zero-delimited canonical history payload."""
    payload = bytearray()
    for part in canonical_parts(history):
        payload.extend(part.encode())
        payload.append(0)
    return bytes(payload)


def history_digest(history: dict) -> str:
    """Return the unsigned digest bound into the release-history signature."""
    return hashlib.sha256(canonical_bytes(history)).hexdigest()


def sign_history(
    history: dict,
    env: str = "prod",
    key_id: str | None = None,
    secret: str | None = None,
) -> dict:
    """Build a release-history signature fixture."""
    key = KEY_CONFIG["keys_by_env"][env]
    submitted_key_id = key_id if key_id is not None else key["key_id"]
    submitted_secret = secret if secret is not None else key["secret"]
    mac = hmac.new(submitted_secret.encode(), digestmod=hashlib.sha256)
    mac.update(canonical_bytes(history))
    return {
        "schema_version": "release-history-signature/v1",
        "algorithm": "HMAC-SHA256",
        "environment": env,
        "key_id": submitted_key_id,
        "history_digest": history_digest(history),
        "signature": mac.hexdigest(),
    }


def run_rollback(
    tmp_path: Path,
    history: dict,
    env: str = "prod",
    target_build: str = "",
    signature: dict | None = None,
    expect_ok: bool = True,
    signature_text: str | None = None,
    key_config: dict | None = None,
    preexisting_manifest: bool = False,
):
    """Run the rollback command with a signed temporary history fixture."""
    KEYS.write_text(
        json.dumps(KEY_CONFIG if key_config is None else key_config, indent=2) + "\n"
    )
    out_dir = tmp_path / "rollback"
    history_path = tmp_path / "release_history.json"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    write_json(history_path, history)
    if preexisting_manifest:
        write_json(
            out_dir / "rollback_manifest.json",
            {
                "schema_version": "rollback-manifest/v1",
                "target_build_number": "stale-success",
            },
        )
    if signature_text is not None:
        Path(str(history_path) + ".sig").write_text(signature_text)
    elif signature is not None:
        write_json(Path(str(history_path) + ".sig"), signature)
    cmd = [
        "go",
        "run",
        "./cmd/pipelinesim",
        "rollback",
        "--history",
        str(history_path),
        "--env",
        env,
        "--out",
        str(out_dir),
    ]
    if target_build:
        cmd.extend(["--target-build", target_build])
    result = subprocess.run(cmd, cwd=APP, text=True, capture_output=True, timeout=30)
    if expect_ok:
        assert result.returncode == 0, result.stderr + result.stdout
    else:
        assert result.returncode != 0, (
            "rollback unexpectedly succeeded\nSTDOUT="
            + result.stdout
            + "\nSTDERR="
            + result.stderr
        )
    return result, out_dir


def prod_history() -> dict:
    """Return a baseline compatible promoted history with distinct hash fields."""
    return {
        "schema_version": "release-history/v1",
        "releases": [
            {
                "environment": "prod",
                "build_number": "9100",
                "commit_sha": "prod-9100",
                "artifact_hash": "artifact-9100",
                "promoted_artifact_hash": "promoted-9100",
                "package_hash": "pkg-9100",
                "promotion_status": "promoted",
                "release_contract_version": "2024.10",
            },
            {
                "environment": "prod",
                "build_number": "9101",
                "commit_sha": "prod-9101",
                "artifact_hash": "artifact-9101",
                "promoted_artifact_hash": "promoted-9101",
                "package_hash": "pkg-9101",
                "promotion_status": "promoted",
                "release_contract_version": "2024.11",
            },
            {
                "environment": "prod",
                "build_number": "9102",
                "commit_sha": "prod-9102",
                "artifact_hash": "artifact-9102",
                "promoted_artifact_hash": "promoted-9102",
                "package_hash": "pkg-9102",
                "promotion_status": "failed",
            },
        ],
    }


def prod_bundle_history() -> dict:
    """Return promoted history records with signed multi-artifact deployment bundles."""
    return {
        "schema_version": "release-history/v1",
        "releases": [
            {
                "environment": "prod",
                "build_number": "9300",
                "commit_sha": "prod-9300",
                "artifact_hash": "artifact-9300",
                "promoted_artifact_hash": "promoted-9300",
                "package_hash": "pkg-9300",
                "promotion_status": "promoted",
                "release_contract_version": "2024.10",
                "deployment_units": [
                    {
                        "name": "api",
                        "artifact_hash": "api-artifact-9300",
                        "package_hash": "api-package-9300",
                        "release_contract_version": "2024.10",
                    },
                    {
                        "name": "worker",
                        "artifact_hash": "worker-artifact-9300",
                        "package_hash": "worker-package-9300",
                        "release_contract_version": "2024.11",
                    },
                ],
            },
            {
                "environment": "prod",
                "build_number": "9301",
                "commit_sha": "prod-9301",
                "artifact_hash": "artifact-9301",
                "promoted_artifact_hash": "promoted-9301",
                "package_hash": "pkg-9301",
                "promotion_status": "promoted",
                "release_contract_version": "2024.11",
                "deployment_units": [
                    {
                        "name": "api",
                        "artifact_hash": "api-artifact-9301",
                        "package_hash": "api-package-9301",
                        "release_contract_version": "2024.11",
                    },
                    {
                        "name": "worker",
                        "artifact_hash": "worker-artifact-9301",
                        "package_hash": "worker-package-9301",
                        "release_contract_version": "2024.11",
                    },
                ],
            },
        ],
    }


class TestMilestone5:
    def test_signed_default_rollback_preserves_milestone4_selection(self, tmp_path):
        """A valid signature enables normal previous-promoted rollback selection."""
        history = prod_history()
        _, out_dir = run_rollback(tmp_path, history, signature=sign_history(history))
        manifest = read_json(out_dir / "rollback_manifest.json")

        assert manifest["target_build_number"] == "9100"
        assert manifest["artifact_hash"] == "artifact-9100"
        assert manifest["promoted_artifact_hash"] == "promoted-9100"
        assert manifest["rollback_source"] == "release_history"

    def test_tampering_with_any_history_record_invalidates_signature(self, tmp_path):
        """The signature covers the full history, including records not selected for rollback."""
        signed = prod_history()
        tampered = json.loads(json.dumps(signed))
        tampered["releases"][2]["promotion_status"] = "promoted"
        _, out_dir = run_rollback(
            tmp_path, tampered, signature=sign_history(signed), expect_ok=False
        )

        assert not (out_dir / "rollback_manifest.json").exists()

    def test_stale_history_digest_rejects_replayed_signature_metadata(
        self, tmp_path
    ):
        """The signature envelope must bind to the exact canonical history digest."""
        history = prod_history()
        signature = sign_history(history)
        signature["history_digest"] = history_digest(
            {"schema_version": "release-history/v1", "releases": []}
        )

        _, out_dir = run_rollback(
            tmp_path, history, signature=signature, expect_ok=False
        )

        assert not (out_dir / "rollback_manifest.json").exists()

    def test_signature_hex_comparison_is_case_insensitive(self, tmp_path):
        """Uppercase digest and HMAC hex strings are valid for the same signed history."""
        history = prod_history()
        signature = sign_history(history)
        signature["history_digest"] = signature["history_digest"].upper()
        signature["signature"] = signature["signature"].upper()

        _, out_dir = run_rollback(tmp_path, history, signature=signature)
        manifest = read_json(out_dir / "rollback_manifest.json")

        assert manifest["target_build_number"] == "9100"

    def test_signed_rollback_copies_selected_deployment_bundle(self, tmp_path):
        """Rollback manifests preserve the selected multi-artifact bundle exactly."""
        history = prod_bundle_history()
        _, out_dir = run_rollback(tmp_path, history, signature=sign_history(history))
        manifest = read_json(out_dir / "rollback_manifest.json")

        assert manifest["target_build_number"] == "9300"
        assert manifest["artifact_hash"] == "artifact-9300"
        assert manifest["promoted_artifact_hash"] == "promoted-9300"
        assert (
            manifest["deployment_units"] == history["releases"][0]["deployment_units"]
        )

    def test_deployment_units_are_part_of_signed_history(self, tmp_path):
        """Tampering with a deployment unit invalidates the full-history signature."""
        signed = prod_bundle_history()
        tampered = json.loads(json.dumps(signed))
        tampered["releases"][0]["deployment_units"][1]["package_hash"] = (
            "worker-package-tampered"
        )

        _, out_dir = run_rollback(
            tmp_path, tampered, signature=sign_history(signed), expect_ok=False
        )

        assert not (out_dir / "rollback_manifest.json").exists()

    def test_deployment_unit_contract_floor_is_enforced(self, tmp_path):
        """Every selected deployment unit must satisfy the environment compatibility floor."""
        history = prod_bundle_history()
        history["releases"][0]["deployment_units"][1]["release_contract_version"] = (
            "2024.09"
        )

        _, out_dir = run_rollback(
            tmp_path, history, signature=sign_history(history), expect_ok=False
        )

        assert not (out_dir / "rollback_manifest.json").exists()

    def test_deployment_unit_required_fields_are_enforced(self, tmp_path):
        """A selected deployment unit with an empty required field is incompatible."""
        history = prod_bundle_history()
        history["releases"][0]["deployment_units"][0]["package_hash"] = ""

        _, out_dir = run_rollback(
            tmp_path, history, signature=sign_history(history), expect_ok=False
        )

        assert not (out_dir / "rollback_manifest.json").exists()

    def test_missing_signature_fails_closed_before_selection(self, tmp_path):
        """Rollback must not proceed when the sibling signature file is absent."""
        history = prod_history()
        _, out_dir = run_rollback(tmp_path, history, signature=None, expect_ok=False)

        assert not (out_dir / "rollback_manifest.json").exists()

    def test_failed_signed_rollback_clears_stale_success_manifest(self, tmp_path):
        """A failed signed rollback must not leave a previous success manifest behind."""
        history = prod_history()
        _, out_dir = run_rollback(
            tmp_path,
            history,
            signature=None,
            expect_ok=False,
            preexisting_manifest=True,
        )

        assert not (out_dir / "rollback_manifest.json").exists()

    def test_malformed_signature_json_fails_closed_before_selection(self, tmp_path):
        """Malformed signature JSON is rejected before any rollback target is selected."""
        history = prod_history()
        _, out_dir = run_rollback(
            tmp_path, history, signature_text="{not-json", expect_ok=False
        )

        assert not (out_dir / "rollback_manifest.json").exists()

    def test_unsupported_signature_schema_fails_closed_before_selection(self, tmp_path):
        """Only the documented release-history signature schema may authorize rollback."""
        history = prod_history()
        signature = sign_history(history)
        signature["schema_version"] = "release-history-signature/v0"
        _, out_dir = run_rollback(
            tmp_path, history, signature=signature, expect_ok=False
        )

        assert not (out_dir / "rollback_manifest.json").exists()

    def test_unsupported_signature_algorithm_fails_closed_before_selection(
        self, tmp_path
    ):
        """Only HMAC-SHA256 signatures may authorize rollback."""
        history = prod_history()
        signature = sign_history(history)
        signature["algorithm"] = "SHA256"
        _, out_dir = run_rollback(
            tmp_path, history, signature=signature, expect_ok=False
        )

        assert not (out_dir / "rollback_manifest.json").exists()

    def test_missing_key_config_entry_fails_closed_before_selection(self, tmp_path):
        """Rollback fails closed when the requested environment has no configured signing key."""
        history = prod_history()
        key_config = {
            "schema_version": "release-history-keys/v1",
            "keys_by_env": {
                "staging": KEY_CONFIG["keys_by_env"]["staging"],
            },
        }
        _, out_dir = run_rollback(
            tmp_path,
            history,
            env="prod",
            signature=sign_history(history),
            key_config=key_config,
            expect_ok=False,
        )

        assert not (out_dir / "rollback_manifest.json").exists()

    def test_signature_environment_and_key_id_must_match_requested_env(self, tmp_path):
        """A valid HMAC under a different environment key must not authorize prod rollback."""
        history = prod_history()
        wrong_env_sig = sign_history(history, env="staging")
        _, out_dir = run_rollback(
            tmp_path, history, env="prod", signature=wrong_env_sig, expect_ok=False
        )
        assert not (out_dir / "rollback_manifest.json").exists()

        wrong_key_sig = sign_history(history, env="prod", key_id="retired-prod-key")
        _, out_dir = run_rollback(
            tmp_path, history, env="prod", signature=wrong_key_sig, expect_ok=False
        )
        assert not (out_dir / "rollback_manifest.json").exists()

    def test_explicit_signed_target_still_requires_compatible_promoted_record(
        self, tmp_path
    ):
        """Signature verification composes with explicit target and compatibility-floor checks."""
        history = {
            "schema_version": "release-history/v1",
            "releases": [
                {
                    "environment": "prod",
                    "build_number": "9200",
                    "commit_sha": "prod-9200",
                    "artifact_hash": "artifact-9200",
                    "promoted_artifact_hash": "promoted-9200",
                    "package_hash": "pkg-9200",
                    "promotion_status": "promoted",
                    "release_contract_version": "2024.09",
                },
                {
                    "environment": "prod",
                    "build_number": "9201",
                    "commit_sha": "prod-9201",
                    "artifact_hash": "artifact-9201",
                    "promoted_artifact_hash": "promoted-9201",
                    "package_hash": "pkg-9201",
                    "promotion_status": "promoted",
                    "release_contract_version": "2024.11",
                },
            ],
        }

        _, out_dir = run_rollback(
            tmp_path, history, target_build="9201", signature=sign_history(history)
        )
        assert (
            read_json(out_dir / "rollback_manifest.json")["target_build_number"]
            == "9201"
        )

        _, out_dir = run_rollback(
            tmp_path,
            history,
            target_build="9200",
            signature=sign_history(history),
            expect_ok=False,
        )
        assert not (out_dir / "rollback_manifest.json").exists()
