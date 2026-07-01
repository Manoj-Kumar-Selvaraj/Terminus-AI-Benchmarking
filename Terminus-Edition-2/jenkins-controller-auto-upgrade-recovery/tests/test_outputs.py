# ruff: noqa: E402, F811

import json

from helpers import file_digest, fresh_root, journal_records, read_json, run_recover, write_json


def make_target_compatible(root, target):
    """Extend backup manifests so later cumulative solutions can plan the target."""
    for manifest_path in (root / "backups").glob("*/manifest.json"):
        manifest = read_json(manifest_path)
        values = list(manifest.get("compatible_targets", []))
        if target not in values:
            values.append(target)
        manifest["compatible_targets"] = values
        write_json(manifest_path, manifest)



def test_plan_derives_runtime_without_mutating_state(tmp_path):
    """Plan must derive Java from the contract and leave deployment unchanged."""
    root = fresh_root(tmp_path)
    dep_path = root / "cluster" / "controller_deployment.json"
    contract_path = root / "config" / "version_contract.json"
    target = f"2.5{sum(map(ord, tmp_path.name)) % 40 + 10}.1"
    dep = read_json(dep_path)
    dep["jenkins_version"] = target
    dep["controller_image"] = f"registry.local/controller:{target}-jdk11"
    dep["java_major"] = 11
    dep["annotations"]["random_marker"] = "keep-me"
    write_json(dep_path, dep)
    contract = read_json(contract_path)
    contract["versions"][target] = {"required_java": 21, "supported_java": [21]}
    write_json(contract_path, contract)
    make_target_compatible(root, target)
    before = file_digest(dep_path)

    result = run_recover(root, "plan", "--json", check=True)
    plan = json.loads(result.stdout)

    assert plan["actions"][0]["required_java"] == 21
    assert plan["actions"][0]["target_version"] == target
    assert file_digest(dep_path) == before


def test_apply_updates_only_runtime_fields_and_preserves_metadata(tmp_path):
    """Apply must derive Java from the active contract, not a fixture constant."""
    root = fresh_root(tmp_path)
    dep_path = root / "cluster" / "controller_deployment.json"
    dep = read_json(dep_path)
    target = f"2.7{sum(map(ord, tmp_path.name)) % 30 + 10}.1"
    dep["jenkins_version"] = target
    dep["controller_image"] = f"registry.local/controller:{target}-jdk11"
    dep["java_major"] = 11
    dep["future_field"] = {"ticket": "RND-728", "enabled": True}
    write_json(dep_path, dep)
    contract_path = root / "config" / "version_contract.json"
    contract = read_json(contract_path)
    contract["versions"][target] = {"required_java": 21, "supported_java": [21]}
    write_json(contract_path, contract)
    make_target_compatible(root, target)
    old_inode = dep_path.stat().st_ino

    run_recover(root, "apply", "--owner", "operator-a", check=True)
    updated = read_json(dep_path)

    assert dep_path.stat().st_ino != old_inode
    assert updated["java_major"] == 21
    assert "jdk21" in updated["controller_image"]
    assert updated["future_field"] == dep["future_field"]
    assert updated["cluster"] == dep["cluster"]
    assert updated["home_claim"] == dep["home_claim"]


def test_missing_target_contract_fails_before_any_mutation(tmp_path):
    """An unknown target must fail closed before the deployment is changed."""
    root = fresh_root(tmp_path)
    dep_path = root / "cluster" / "controller_deployment.json"
    dep = read_json(dep_path)
    dep["jenkins_version"] = "9.9.9"
    write_json(dep_path, dep)
    before = dep_path.read_bytes()

    result = run_recover(root, "apply", "--owner", "operator-a")

    assert result.returncode != 0
    assert "absent from version contract" in result.stderr
    assert dep_path.read_bytes() == before
    assert not (root / "recovery_state" / "journal.jsonl").exists()


def test_fault_before_runtime_commit_is_atomic(tmp_path):
    """A pre-commit failure must leave the deployment byte-for-byte unchanged."""
    root = fresh_root(tmp_path)
    dep_path = root / "cluster" / "controller_deployment.json"
    before = dep_path.read_bytes()

    result = run_recover(
        root,
        "apply",
        "--owner",
        "operator-a",
        "--fault",
        "before_runtime_commit",
    )

    assert result.returncode != 0
    assert dep_path.read_bytes() == before
    assert journal_records(root) == []
    assert not list(dep_path.parent.glob(".recover-*"))


def test_verify_reports_runtime_recovery_progress(tmp_path):
    """Verify must run diagnostics and show that runtime incompatibility is fixed."""
    root = fresh_root(tmp_path)
    run_recover(root, "apply", "--owner", "operator-a", check=True)

    result = run_recover(root, "verify", "--json")
    data = json.loads(result.stdout)
    runtime = next(check for check in data["checks"] if check["name"] == "runtime")

    assert result.returncode != 0
    assert runtime["ok"] is True
    assert data["phase"] != "RUNTIME_INCOMPATIBLE"


def test_lost_response_resumes_without_repeating_runtime_commit(tmp_path):
    """A committed runtime update must be recognized after a lost response."""
    root = fresh_root(tmp_path)
    first = run_recover(
        root,
        "apply",
        "--owner",
        "operator-a",
        "--fault",
        "after_runtime_commit_response_lost",
    )
    assert first.returncode != 0
    assert read_json(root / "cluster" / "controller_deployment.json")["java_major"] == 17

    fenced = run_recover(root, "resume", "--owner", "operator-b")
    assert fenced.returncode != 0
    assert "fenced by owner operator-a" in fenced.stderr

    run_recover(root, "resume", "--owner", "operator-a", check=True)
    records = journal_records(root)
    for record in records:
        assert "operation_id" in record
        assert "owner" in record
        assert record["owner"] == "operator-a"
    events = [record["event"] for record in records]
    assert events.count("runtime_committed") == 1
    assert events.count("operation_completed") == 1


def test_repeated_apply_is_idempotent(tmp_path):
    """Running the same completed recovery twice must not add duplicate events."""
    root = fresh_root(tmp_path)
    run_recover(root, "apply", "--owner", "operator-a", check=True)
    first_dep = (root / "cluster" / "controller_deployment.json").read_bytes()
    first_records = journal_records(root)

    run_recover(root, "apply", "--owner", "operator-a", check=True)

    assert (root / "cluster" / "controller_deployment.json").read_bytes() == first_dep
    assert journal_records(root) == first_records


def test_operation_identity_changes_with_target_and_cluster(tmp_path):
    """Operation identity must include deployment identity and target version."""
    root = fresh_root(tmp_path)
    base = json.loads(run_recover(root, "plan", "--json", check=True).stdout)["operation_id"]
    dep_path = root / "cluster" / "controller_deployment.json"
    dep = read_json(dep_path)
    target = f"2.6{sum(map(ord, tmp_path.name)) % 30 + 10}.1"
    contract = read_json(root / "config" / "version_contract.json")
    contract["versions"][target] = {"required_java": 21, "supported_java": [21]}
    write_json(root / "config" / "version_contract.json", contract)
    make_target_compatible(root, target)
    dep["jenkins_version"] = target
    write_json(dep_path, dep)
    changed_target = json.loads(run_recover(root, "plan", "--json", check=True).stdout)["operation_id"]
    dep["cluster"] = "prod-ci-west"
    write_json(dep_path, dep)
    changed_cluster = json.loads(run_recover(root, "plan", "--json", check=True).stdout)["operation_id"]

    assert len({base, changed_target, changed_cluster}) == 3


def test_inspect_reports_lease_and_journal_state(tmp_path):
    """Inspect must report durable recovery state rather than static fixture answers."""
    root = fresh_root(tmp_path)
    run_recover(root, "apply", "--owner", "operator-a", check=True)

    result = run_recover(root, "inspect", "--json", check=True)
    data = json.loads(result.stdout)

    assert "operation_id" in data
    assert "milestone" in data
    assert data["milestone"] not in ("", None)
    assert data["journal_records"] >= 2
    events = [record["event"] for record in journal_records(root)]
    assert events.count("runtime_committed") == 1
    assert events.count("operation_completed") == 1
    assert data["lease"]["owner"] == "operator-a"
    assert data["lease"]["status"] == "completed"
    lease = read_json(root / "recovery_state" / "lease.json")
    assert lease["owner"] == "operator-a"
    assert lease["status"] == "completed"
    assert isinstance(lease["generation"], int)
    assert lease["generation"] >= 1


import json
import hashlib

from helpers import (
    create_snapshot,
    fresh_root,
    journal_records,
    read_json,
    run_recover,
    tree_digest,
    write_json,
)


def test_recovery_selects_newest_complete_compatible_snapshot(tmp_path):
    """Recovery must skip a newer corrupt snapshot and select the newest valid one."""
    root = fresh_root(tmp_path)

    run_recover(root, "apply", "--owner", "restore-a", check=True)
    state = read_json(root / "jenkins_home" / "controller_state.json")

    assert state["restored_from_snapshot"] == "pre-upgrade-20260618"
    assert state["home_schema"] == "recovered-target"
    assert state["previous_version"] == "2.426.3"


def test_snapshot_selection_is_dynamic_not_name_hardcoded(tmp_path):
    """A newly added later valid snapshot must be selected without code changes."""
    root = fresh_root(tmp_path)
    snapshot_name = f"verified-{tmp_path.name}"
    create_snapshot(root, snapshot_name, "2026-06-21T10:00:00Z")

    plan = json.loads(run_recover(root, "plan", "--json", check=True).stdout)
    run_recover(root, "apply", "--owner", "restore-a", check=True)
    state = read_json(root / "jenkins_home" / "controller_state.json")

    assert isinstance(plan["selected_snapshot"], str)
    assert plan["selected_snapshot"] == snapshot_name
    assert state["restored_from_snapshot"] == snapshot_name


def test_plan_does_not_mutate_filesystem(tmp_path):
    """Plan must report snapshot selection without writing recovery state."""
    root = fresh_root(tmp_path)
    before = tree_digest(root)

    data = json.loads(run_recover(root, "plan", "--json", check=True).stdout)

    assert isinstance(data["selected_snapshot"], str)
    assert data["selected_snapshot"] == "pre-upgrade-20260618"
    assert tree_digest(root) == before
    assert not (root / "recovery_state").exists()


def test_restore_preserves_unrelated_home_files_and_additional_jobs(tmp_path):
    """Restore must merge validated backup data without replacing unrelated home content."""
    root = fresh_root(tmp_path)
    marker = root / "jenkins_home" / "userContent" / "random-preserve.txt"
    marker.write_text("operator note 91\n", encoding="utf-8")
    jobs = read_json(root / "jenkins_home" / "jobs.json")
    jobs["jobs"].append("ad-hoc-check/run")
    write_json(root / "jenkins_home" / "jobs.json", jobs)
    job_config = root / "jenkins_home" / "jobs" / "ad-hoc-check" / "config.xml"
    job_config.parent.mkdir(parents=True)
    job_config.write_text("<project><description>keep</description></project>\n")

    run_recover(root, "apply", "--owner", "restore-a", check=True)
    restored_jobs = read_json(root / "jenkins_home" / "jobs.json")["jobs"]

    assert marker.read_text() == "operator note 91\n"
    assert "ad-hoc-check/run" in restored_jobs
    assert "<description>keep</description>" in job_config.read_text()


def test_upgrade_lock_removed_after_restore(tmp_path):
    """A successful restore must remove the failed upgrade lock only."""
    root = fresh_root(tmp_path)
    lock = root / "jenkins_home" / "UPGRADE.lock"
    assert lock.exists()

    run_recover(root, "apply", "--owner", "restore-a", check=True)

    assert not lock.exists()


def test_home_stage_fault_does_not_modify_live_home(tmp_path):
    """A crash after staging must leave the live Jenkins home unchanged."""
    root = fresh_root(tmp_path)
    before = tree_digest(root / "jenkins_home")

    result = run_recover(
        root,
        "apply",
        "--owner",
        "restore-a",
        "--fault",
        "after_home_stage",
    )

    assert result.returncode != 0
    assert tree_digest(root / "jenkins_home") == before
    assert [r["event"] for r in journal_records(root)] == ["runtime_committed", "home_staged"]
    staging = root / "recovery_state" / "staging"
    assert staging.exists()
    assert any(path.relative_to(staging).as_posix().endswith("config.xml") for path in staging.rglob("config.xml"))
    assert any(path.relative_to(staging).as_posix().endswith("jobs.json") for path in staging.rglob("jobs.json"))


def test_different_owner_fenced_after_home_stage_fault(tmp_path):
    """A staged restore lease must reject resume attempts from a different owner."""
    root = fresh_root(tmp_path)
    run_recover(
        root,
        "apply",
        "--owner",
        "restore-a",
        "--fault",
        "after_home_stage",
    )
    before = tree_digest(root / "jenkins_home")

    result = run_recover(root, "resume", "--owner", "restore-b")

    assert result.returncode != 0
    assert "fenced by owner restore-a" in result.stderr
    assert tree_digest(root / "jenkins_home") == before
    assert [r["event"] for r in journal_records(root)] == ["runtime_committed", "home_staged"]


def test_resume_commits_existing_stage_only_once(tmp_path):
    """Resume must reuse the durable stage and not duplicate restore events."""
    root = fresh_root(tmp_path)
    run_recover(
        root,
        "apply",
        "--owner",
        "restore-a",
        "--fault",
        "after_home_stage",
    )

    run_recover(root, "resume", "--owner", "restore-a", check=True)
    events = [r["event"] for r in journal_records(root)]

    assert events.count("home_staged") == 1
    assert events.count("home_committed") == 1
    assert read_json(root / "jenkins_home" / "controller_state.json")["upgrade_status"] == "RESTORED"


def test_no_valid_snapshot_fails_before_any_live_mutation(tmp_path):
    """Preflight must fail before runtime or home changes when no snapshot is valid."""
    root = fresh_root(tmp_path)
    for manifest in (root / "backups").glob("*/manifest.json"):
        data = read_json(manifest)
        data["compatible_targets"] = ["0.0.0"]
        write_json(manifest, data)
    before_cluster = tree_digest(root / "cluster")
    before_home = tree_digest(root / "jenkins_home")

    result = run_recover(root, "apply", "--owner", "restore-a")

    assert result.returncode != 0
    assert "no complete compatible backup" in result.stderr
    assert tree_digest(root / "cluster") == before_cluster
    assert tree_digest(root / "jenkins_home") == before_home
    assert not (root / "recovery_state").exists()


def test_duplicate_job_inventory_is_rejected_before_mutation(tmp_path):
    """A snapshot with duplicate logical jobs must not be activated."""
    root = fresh_root(tmp_path)
    snap = create_snapshot(root, "duplicate-jobs", "2026-06-22T10:00:00Z")
    jobs_path = snap / "jobs.json"
    jobs = read_json(jobs_path)
    jobs["jobs"].append(jobs["jobs"][0])
    write_json(jobs_path, jobs)
    manifest = read_json(snap / "manifest.json")
    import hashlib
    manifest["checksums"]["jobs.json"] = hashlib.sha256(jobs_path.read_bytes()).hexdigest()
    write_json(snap / "manifest.json", manifest)
    before = tree_digest(root / "jenkins_home")

    result = run_recover(root, "apply", "--owner", "restore-a")

    # duplicate-jobs is invalid, so the next valid snapshot is used rather than activating it
    assert result.returncode == 0
    assert read_json(root / "jenkins_home" / "controller_state.json")["restored_from_snapshot"] == "pre-upgrade-20260618"
    assert tree_digest(root / "jenkins_home") != before


def test_unparseable_xml_snapshot_is_rejected(tmp_path):
    """Checksum-valid but malformed XML must not be selected for restore."""
    root = fresh_root(tmp_path)
    snap = create_snapshot(root, "bad-xml", "2026-06-22T10:00:00Z")
    config_path = snap / "config.xml"
    content = b"<jenkins><broken>"
    config_path.write_bytes(content)
    manifest = read_json(snap / "manifest.json")
    manifest["checksums"]["config.xml"] = hashlib.sha256(content).hexdigest()
    write_json(snap / "manifest.json", manifest)

    run_recover(root, "apply", "--owner", "restore-a", check=True)
    state = read_json(root / "jenkins_home" / "controller_state.json")

    assert state["restored_from_snapshot"] == "pre-upgrade-20260618"


def test_restore_preserves_controller_audit_fields(tmp_path):
    """Controller state fields unrelated to recovery must survive the restore."""
    root = fresh_root(tmp_path)
    state_path = root / "jenkins_home" / "controller_state.json"
    state = read_json(state_path)
    state["random_audit"] = {"ticket": "INC-7281", "operator": "night-shift"}
    write_json(state_path, state)

    run_recover(root, "apply", "--owner", "restore-a", check=True)
    restored = read_json(state_path)

    assert restored["random_audit"] == state["random_audit"]
    assert restored["last_successful_boot"] == state["last_successful_boot"]


def test_recovered_xml_and_job_inventory_are_valid(tmp_path):
    """The activated home must contain parseable XML and unique backed-up jobs."""
    root = fresh_root(tmp_path)
    run_recover(root, "apply", "--owner", "restore-a", check=True)

    import xml.etree.ElementTree as ET
    for name in ("config.xml", "credentials.xml", "queue.xml"):
        ET.parse(root / "jenkins_home" / name)
    jobs = read_json(root / "jenkins_home" / "jobs.json")["jobs"]
    assert len(jobs) == len(set(jobs))
    for job in jobs:
        assert (root / "jenkins_home" / "jobs" / job.split("/")[0] / "config.xml").exists()


import json

from helpers import fresh_root, journal_records, read_json, run_recover, run_sim, tree_digest, write_json


def resolved_plugins(plan):
    """Return the plugin resolution map from any plan action that reports it."""
    for action in plan["actions"]:
        if isinstance(action.get("resolved"), dict):
            return action["resolved"]
    raise AssertionError(f"plan does not contain a resolved plugin action: {plan}")


def test_resolves_essential_plugins_and_dependency_closure(tmp_path):
    """Recovery must resolve essential plugins and their compatible dependencies."""
    root = fresh_root(tmp_path)
    run_recover(root, "apply", "--owner", "plugins-a", check=True)
    plugins = read_json(root / "jenkins_home" / "plugins" / "plugins.json")

    expected = {
        "workflow-job": "1400.v7fd111b_ec82f",
        "workflow-api": "1283.v99c10937efcb_",
        "credentials-binding": "687.v619cb_15e923f",
        "plain-credentials": "182.v468b_97b_9dcb_8",
        "matrix-auth": "3.2.2",
        "git": "5.2.2",
        "scm-api": "690.vfc8b_54395023",
    }
    assert {name: plugins[name]["version"] for name in expected} == expected
    assert all(plugins[name]["enabled"] is True for name in expected)
    events = [record["event"] for record in journal_records(root)]
    assert events.count("plugins_committed") == 1


def test_incident_progresses_beyond_plugin_incompatible(tmp_path):
    """Simulator diagnostics must advance beyond the plugin incompatibility phase."""
    root = fresh_root(tmp_path)
    run_recover(root, "apply", "--owner", "plugins-a", check=True)

    result = run_sim(root, "diagnose", "--json")
    diag = json.loads(result.stdout)

    assert diag["phase"] != "PLUGIN_INCOMPATIBLE"


def test_plugin_selection_follows_mutated_catalog_and_baseline(tmp_path):
    """Changing the offline catalog and contract must change the selected version."""
    root = fresh_root(tmp_path)
    catalog_path = root / "config" / "plugin_catalog.json"
    contract_path = root / "config" / "version_contract.json"
    version = f"3.9.{sum(map(ord, tmp_path.name)) % 40 + 10}"
    catalog = read_json(catalog_path)
    catalog["plugins"]["matrix-auth"].append(
        {"version": version, "min_core": "2.462.3", "min_java": 17, "dependencies": {}}
    )
    write_json(catalog_path, catalog)
    contract = read_json(contract_path)
    contract["target_plugin_baseline"]["matrix-auth"]["min_version"] = version
    write_json(contract_path, contract)

    plan = json.loads(run_recover(root, "plan", "--json", check=True).stdout)
    run_recover(root, "apply", "--owner", "plugins-a", check=True)

    assert resolved_plugins(plan)["matrix-auth"] == version
    assert read_json(root / "jenkins_home" / "plugins" / "plugins.json")["matrix-auth"]["version"] == version


def test_lowest_compatible_plugin_version_wins_when_multiple_candidates_match(tmp_path):
    """When multiple candidates satisfy the contract, the resolver must choose the lowest compatible version."""
    root = fresh_root(tmp_path)
    catalog_path = root / "config" / "plugin_catalog.json"
    catalog = read_json(catalog_path)
    catalog["plugins"]["matrix-auth"].append(
        {"version": "3.3.0", "min_core": "2.462.3", "min_java": 17, "dependencies": {}}
    )
    write_json(catalog_path, catalog)

    plan = json.loads(run_recover(root, "plan", "--json", check=True).stdout)
    run_recover(root, "apply", "--owner", "plugins-a", check=True)
    plugins = read_json(root / "jenkins_home" / "plugins" / "plugins.json")

    assert resolved_plugins(plan)["matrix-auth"] == "3.2.2"
    assert plugins["matrix-auth"]["version"] == "3.2.2"


def test_optional_plugins_and_metadata_are_preserved(tmp_path):
    """Recovery must not replace the plugin inventory with only required entries."""
    root = fresh_root(tmp_path)
    path = root / "jenkins_home" / "plugins" / "plugins.json"
    plugins = read_json(path)
    plugins["random-optional-728"] = {
        "version": "9.1",
        "enabled": False,
        "optional": True,
        "metadata": {"owner": "team-x"},
    }
    plugins["git"]["pin_reason"] = "security-review"
    write_json(path, plugins)

    run_recover(root, "apply", "--owner", "plugins-a", check=True)
    updated = read_json(path)

    assert updated["random-optional-728"] == plugins["random-optional-728"]
    assert updated["git"]["pin_reason"] == "security-review"


def test_no_compatible_candidate_fails_before_any_mutation(tmp_path):
    """An impossible plugin contract must fail during planning before state changes."""
    root = fresh_root(tmp_path)
    contract_path = root / "config" / "version_contract.json"
    contract = read_json(contract_path)
    contract["target_plugin_baseline"]["git"]["min_version"] = "99.0.0"
    write_json(contract_path, contract)
    before_cluster = tree_digest(root / "cluster")
    before_home = tree_digest(root / "jenkins_home")

    result = run_recover(root, "apply", "--owner", "plugins-a")

    assert result.returncode != 0
    assert "no compatible plugin candidate for git" in result.stderr
    assert tree_digest(root / "cluster") == before_cluster
    assert tree_digest(root / "jenkins_home") == before_home


def test_dependency_cycle_is_rejected(tmp_path):
    """The resolver must reject a catalog cycle instead of partially updating plugins."""
    root = fresh_root(tmp_path)
    catalog_path = root / "config" / "plugin_catalog.json"
    catalog = read_json(catalog_path)
    catalog["plugins"]["workflow-api"][-1]["dependencies"] = {
        "workflow-job": "1400.v7fd111b_ec82f"
    }
    write_json(catalog_path, catalog)

    result = run_recover(root, "plan", "--json")

    assert result.returncode != 0
    assert "dependency cycle" in result.stderr


def test_plugin_fault_before_commit_preserves_inventory(tmp_path):
    """A pre-commit plugin failure must leave the original plugin file unchanged."""
    root = fresh_root(tmp_path)
    path = root / "jenkins_home" / "plugins" / "plugins.json"
    before = path.read_bytes()

    result = run_recover(
        root,
        "apply",
        "--owner",
        "plugins-a",
        "--fault",
        "before_plugins_commit",
    )

    assert result.returncode != 0
    assert path.read_bytes() == before
    assert "plugins_committed" not in [r["event"] for r in journal_records(root)]


def test_lost_plugin_response_resumes_without_second_update(tmp_path):
    """A lost response after plugin commit must resume without duplicate commits."""
    root = fresh_root(tmp_path)
    first = run_recover(
        root,
        "apply",
        "--owner",
        "plugins-a",
        "--fault",
        "after_plugins_commit_response_lost",
    )
    assert first.returncode != 0
    before = (root / "jenkins_home" / "plugins" / "plugins.json").read_bytes()

    run_recover(root, "resume", "--owner", "plugins-a", check=True)
    events = [r["event"] for r in journal_records(root)]

    assert events.count("plugins_committed") == 1
    assert (root / "jenkins_home" / "plugins" / "plugins.json").read_bytes() == before


def test_plan_is_non_mutating_and_reports_dependency_changes(tmp_path):
    """Plan must expose the resolved closure without writing recovery state."""
    root = fresh_root(tmp_path)
    before = tree_digest(root)

    result = run_recover(root, "plan", "--json", check=True)
    data = json.loads(result.stdout)
    resolved = resolved_plugins(data)

    assert "workflow-api" in resolved
    assert "scm-api" in resolved
    assert tree_digest(root) == before
    assert not (root / "recovery_state").exists()


import json
import subprocess
import time

from helpers import fresh_root, journal_records, read_json, run_recover, run_sim, tree_digest, write_json


def test_policy_is_derived_and_preserves_audit_fields(tmp_path):
    """Policy recovery must add safety guards without replacing audit metadata."""
    root = fresh_root(tmp_path)
    path = root / "cluster" / "auto_upgrade_policy.json"
    policy = read_json(path)
    policy["future_control"] = {"approval_group": "platform-cab", "sequence": 728}
    write_json(path, policy)

    run_recover(root, "apply", "--owner", "policy-a", check=True)
    updated = read_json(path)

    assert updated["auto_upgrade_enabled"] is False
    assert updated["channel"] == "pinned-lts"
    assert updated["target_version"] == "2.462.3"
    assert updated["pin_target_version"] is True
    assert updated["java_preflight_required"] is True
    assert updated["backup_required"] is True
    assert updated["abort_on_failed_preflight"] is True
    assert updated["lock_strategy"] == "clear-after-verified-restore"
    assert updated["future_control"] == policy["future_control"]
    assert updated["audit"] == policy["audit"]
    assert updated["source_version"] == policy["source_version"]
    assert updated["change_ticket"] == policy["change_ticket"]
    assert updated["last_upgrade_id"] == policy["last_upgrade_id"]


def test_policy_uses_dynamically_selected_snapshot(tmp_path):
    """Policy must reference the snapshot selected by validated recovery planning."""
    from helpers import create_snapshot
    root = fresh_root(tmp_path)
    snapshot_name = f"cab-{tmp_path.name}"
    create_snapshot(root, snapshot_name, "2026-06-23T00:00:00Z")

    run_recover(root, "apply", "--owner", "policy-a", check=True)
    policy = read_json(root / "cluster" / "auto_upgrade_policy.json")

    assert policy["required_backup_snapshot"] == snapshot_name


def test_lost_policy_response_is_reconciled_by_same_owner(tmp_path):
    """A committed policy update must be resumed without applying it twice."""
    root = fresh_root(tmp_path)
    first = run_recover(
        root,
        "apply",
        "--owner",
        "policy-a",
        "--fault",
        "after_policy_commit_response_lost",
    )
    assert first.returncode != 0
    policy_after_commit = (root / "cluster" / "auto_upgrade_policy.json").read_bytes()

    other = run_recover(root, "resume", "--owner", "policy-b")
    assert other.returncode != 0
    assert "fenced by owner policy-a" in other.stderr

    run_recover(root, "resume", "--owner", "policy-a", check=True)
    events = [r["event"] for r in journal_records(root)]
    assert events.count("policy_committed") == 1
    assert (root / "cluster" / "auto_upgrade_policy.json").read_bytes() == policy_after_commit


def test_journal_records_ordered_recovery_state_machine(tmp_path):
    """The journal must record the ordered durable recovery phases."""
    root = fresh_root(tmp_path)
    run_recover(root, "apply", "--owner", "policy-a", check=True)

    events = [r["event"] for r in journal_records(root)]

    required = [
        "runtime_committed",
        "home_staged",
        "home_committed",
        "plugins_committed",
        "preflight_completed",
        "policy_committed",
    ]
    assert events[: len(required)] == required
    assert events[-1] == "operation_completed"
    assert events.count("policy_committed") == 1


def test_inspect_reports_journal_count_and_lease(tmp_path):
    """Inspect must report journal count and current lease details after policy recovery."""
    root = fresh_root(tmp_path)
    run_recover(root, "apply", "--owner", "policy-a", check=True)

    result = run_recover(root, "inspect", "--json", check=True)
    data = json.loads(result.stdout)
    lease = data["lease"]

    assert "operation_id" in data
    assert isinstance(data["journal_records"], int)
    assert data["journal_records"] >= 7
    assert lease["owner"] == "policy-a"
    assert lease["status"] == "completed"
    assert isinstance(lease["generation"], int)
    assert lease["operation_id"]


def test_incident_progresses_beyond_unsafe_automation(tmp_path):
    """Diagnose must pass the unsafe automation phase after policy recovery."""
    root = fresh_root(tmp_path)
    run_recover(root, "apply", "--owner", "policy-a", check=True)

    result = run_sim(root, "diagnose", "--json")
    data = json.loads(result.stdout)
    policy_check = next(check for check in data["checks"] if check["name"] == "upgrade_policy")

    assert result.returncode != 0
    assert policy_check["ok"] is True
    assert data["phase"] != "UNSAFE_AUTOMATION"


def test_preflight_failure_does_not_partially_modify_state(tmp_path):
    """Invalid backup evidence must stop the operation before any cumulative write."""
    root = fresh_root(tmp_path)
    for manifest in (root / "backups").glob("*/manifest.json"):
        data = read_json(manifest)
        data["compatible_targets"] = ["not-this-target"]
        write_json(manifest, data)
    before = tree_digest(root)

    result = run_recover(root, "apply", "--owner", "policy-a")

    assert result.returncode != 0
    assert tree_digest(root) == before


def test_process_lock_blocks_concurrent_recovery(tmp_path):
    """Only one recovery process may mutate an incident root at a time."""
    root = fresh_root(tmp_path)
    import os
    from helpers import RECOVER, SOURCE, SIM
    env = os.environ.copy()
    env.update({"APP_ROOT": str(root), "JENKINS_RECOVERY_SOURCE": str(SOURCE), "JENKINS_SIM_BIN": str(SIM)})
    first = subprocess.Popen(
        [str(RECOVER), "apply", "--owner", "policy-a", "--hold-ms", "900"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    for _ in range(50):
        if (root / "recovery_state" / "lease.json").exists():
            break
        time.sleep(0.1)
    assert (root / "recovery_state" / "lease.json").exists(), "Lease not created in time"
    lease = read_json(root / "recovery_state" / "lease.json")
    assert lease["owner"] == "policy-a"
    assert lease["status"] == "active"
    assert isinstance(lease["generation"], int)
    assert "operation_id" in lease and lease["operation_id"]
    second = run_recover(root, "apply", "--owner", "policy-b")
    out, err = first.communicate(timeout=20)

    assert first.returncode == 0, err
    assert second.returncode != 0
    assert "local lock" in second.stderr or "fenced" in second.stderr


def test_repeated_completed_apply_does_not_duplicate_journal(tmp_path):
    """A completed policy recovery must remain idempotent on replay."""
    root = fresh_root(tmp_path)
    run_recover(root, "apply", "--owner", "policy-a", check=True)
    records = journal_records(root)

    run_recover(root, "apply", "--owner", "policy-a", check=True)

    assert journal_records(root) == records


def test_plan_lists_guards_and_does_not_write_policy(tmp_path):
    """Plan must expose guard decisions without changing the incident."""
    root = fresh_root(tmp_path)
    path = root / "cluster" / "auto_upgrade_policy.json"
    before = path.read_bytes()

    data = json.loads(run_recover(root, "plan", "--json", check=True).stdout)

    assert "guards" in data
    assert isinstance(data["guards"], list)
    assert all(isinstance(guard, str) for guard in data["guards"])
    guards = set(data["guards"])
    assert any("java" in guard and "preflight" in guard for guard in guards)
    assert any("backup" in guard and "verified" in guard for guard in guards)
    assert any("lease" in guard or "owner" in guard for guard in guards)
    assert len(guards) >= 3
    assert path.read_bytes() == before


import json
import shlex

from helpers import SIM, fresh_root, journal_records, read_json, run_recover, tree_digest, write_json


def test_dynamic_controller_election_uses_priority_not_fixed_name(tmp_path):
    """Recovery must elect the highest-priority eligible controller dynamically."""
    root = fresh_root(tmp_path)
    path = root / "cluster" / "topology.json"
    topo = read_json(path)
    winner = f"controller-{tmp_path.name}-winner"
    loser = f"controller-{tmp_path.name}-loser"
    topo["pods"][0]["name"] = loser
    topo["pods"][0]["metadata"]["recovery_priority"] = 50
    topo["pods"][1]["name"] = winner
    topo["pods"][1]["metadata"]["recovery_eligible"] = True
    topo["pods"][1]["metadata"]["recovery_priority"] = 900
    topo["service"]["routes_to"] = "broken-route"
    write_json(path, topo)

    before = tree_digest(root)
    plan = json.loads(run_recover(root, "plan", "--json", check=True).stdout)
    assert tree_digest(root) == before

    assert isinstance(plan["elected_controller"], str)
    run_recover(root, "apply", "--owner", "cluster-a", check=True)
    updated = read_json(path)

    assert plan["elected_controller"] == winner
    assert updated["service"]["routes_to"] == winner
    elected = [p for p in updated["pods"] if p["elected"]]
    assert [p["name"] for p in elected] == [winner]


def test_controller_election_tie_breaks_by_name(tmp_path):
    """Equal-priority eligible controllers must be ordered by controller name."""
    root = fresh_root(tmp_path)
    path = root / "cluster" / "topology.json"
    topo = read_json(path)
    topo["pods"][0]["name"] = "zulu-controller"
    topo["pods"][0]["metadata"]["recovery_eligible"] = True
    topo["pods"][0]["metadata"]["recovery_priority"] = 300
    topo["pods"][1]["name"] = "alpha-controller"
    topo["pods"][1]["metadata"]["recovery_eligible"] = True
    topo["pods"][1]["metadata"]["recovery_priority"] = 300
    topo["service"]["routes_to"] = "stale-controller"
    write_json(path, topo)

    plan = json.loads(run_recover(root, "plan", "--json", check=True).stdout)
    assert isinstance(plan["elected_controller"], str)
    run_recover(root, "apply", "--owner", "cluster-a", check=True)
    updated = read_json(path)

    assert plan["elected_controller"] == "alpha-controller"
    assert updated["service"]["routes_to"] == "alpha-controller"
    elected = [p["name"] for p in updated["pods"] if p["elected"]]
    assert elected == ["alpha-controller"]


def test_missing_priority_loses_to_any_explicit_priority(tmp_path):
    """A missing recovery priority must rank below every explicit numeric priority."""
    root = fresh_root(tmp_path)
    path = root / "cluster" / "topology.json"
    topo = read_json(path)
    topo["pods"][0]["name"] = "has-priority"
    topo["pods"][0]["metadata"]["recovery_eligible"] = True
    topo["pods"][0]["metadata"]["recovery_priority"] = 1
    topo["pods"][1]["name"] = "no-priority"
    topo["pods"][1]["metadata"]["recovery_eligible"] = True
    topo["pods"][1]["metadata"].pop("recovery_priority", None)
    topo["service"]["routes_to"] = "stale-controller"
    write_json(path, topo)

    plan = json.loads(run_recover(root, "plan", "--json", check=True).stdout)

    assert plan["elected_controller"] == "has-priority"


def test_fencing_preserves_pod_metadata_and_safe_observers(tmp_path):
    """Fencing must change ownership fields only and preserve unrelated pod data."""
    root = fresh_root(tmp_path)
    path = root / "cluster" / "topology.json"
    before = read_json(path)

    run_recover(root, "apply", "--owner", "cluster-a", check=True)
    after = read_json(path)

    by_name_before = {p["name"]: p for p in before["pods"]}
    by_name_after = {p["name"]: p for p in after["pods"]}
    assert after["topology_revision"] == before["topology_revision"]
    assert after["home_claim"] == before["home_claim"]
    assert set(by_name_after) == set(by_name_before)
    for name in by_name_before:
        assert by_name_after[name]["metadata"] == by_name_before[name]["metadata"]
    observer = by_name_after["jenkins-observer-0"]
    assert observer["role"] == "observer"
    assert observer["mounts_home"] is False
    for name, pod in by_name_after.items():
        if pod["mounts_home"] and not pod["elected"]:
            assert pod["read_write"] is False, name


def test_agents_follow_dynamic_contract_and_offline_agents_are_unchanged(tmp_path):
    """Online agents must be upgraded to the contract while offline agents remain untouched."""
    root = fresh_root(tmp_path)
    contract_path = root / "config" / "version_contract.json"
    contract = read_json(contract_path)
    contract["required_agent_java"] = 21
    write_json(contract_path, contract)
    topo_path = root / "cluster" / "topology.json"
    topo = read_json(topo_path)
    topo["agents"].append(
        {
            "name": "already-compatible",
            "online": True,
            "remoting_java_major": 21,
            "labels": ["compat"],
            "metadata": {"owner": "platform-ci", "ticket": "AGENT-21"},
        }
    )
    write_json(topo_path, topo)
    before = read_json(topo_path)

    run_recover(root, "apply", "--owner", "cluster-a", check=True)
    after = read_json(topo_path)

    by_name_before = {a["name"]: a for a in before["agents"] if a["online"]}
    by_name_after = {a["name"]: a for a in after["agents"] if a["online"]}
    assert set(by_name_after) == set(by_name_before)
    for agent in after["agents"]:
        if agent["online"]:
            assert agent["remoting_java_major"] >= 21
    for name in by_name_before:
        assert by_name_after[name]["labels"] == by_name_before[name]["labels"]
    old_offline = next(a for a in before["agents"] if not a["online"])
    new_offline = next(a for a in after["agents"] if a["name"] == old_offline["name"])
    assert new_offline == old_offline
    compat = next(a for a in after["agents"] if a["name"] == "already-compatible")
    assert compat["remoting_java_major"] == 21
    assert compat["labels"] == ["compat"]
    assert compat["metadata"] == {"owner": "platform-ci", "ticket": "AGENT-21"}


def test_queue_dedup_preserves_first_record_order_and_unknown_fields(tmp_path):
    """Queue reconciliation must keep the first full record for each dynamic ID."""
    root = fresh_root(tmp_path)
    path = root / "jenkins_home" / "queue.json"
    queue = read_json(path)
    duplicate_id = f"dup-{tmp_path.name}"
    unique_id = f"unique-{tmp_path.name}"
    queue["items"] = [
        {"id": duplicate_id, "job": "alpha/run", "state": "waiting", "marker": "first"},
        {"id": "q-1001", "job": "payments-ledger/main", "state": "waiting", "cause": "SCM"},
        {"id": duplicate_id, "job": "wrong/replay", "state": "blocked", "marker": "second"},
        {"id": "q-1002", "job": "shared-library/test", "state": "blocked", "cause": "timer"},
        {"id": unique_id, "job": "omega/run", "state": "waiting", "future": {"x": 1}},
    ]
    queue["future_queue_field"] = "preserve"
    write_json(path, queue)

    run_recover(root, "apply", "--owner", "cluster-a", check=True)
    updated = read_json(path)

    assert [item["id"] for item in updated["items"]] == [duplicate_id, "q-1001", "q-1002", unique_id]
    assert updated["items"][0]["marker"] == "first"
    assert updated["items"][-1]["future"] == {"x": 1}
    assert updated["future_queue_field"] == "preserve"


def test_final_apply_generates_ready_outputs_through_simulator(tmp_path):
    """The recovery controller must finish by invoking the simulator start workflow."""
    root = fresh_root(tmp_path)
    run_recover(root, "apply", "--owner", "cluster-a", check=True)

    diagnostics = read_json(root / "out" / "controller_diagnostics.json")
    status = read_json(root / "out" / "controller_status.json")

    assert diagnostics["phase"] == "READY"
    assert diagnostics["ready"] is True
    assert status["status"] == "READY"
    assert status["cluster"] == "prod-ci-east"


def test_final_apply_uses_configured_simulator_binary(tmp_path):
    """Recovery must honor JENKINS_SIM_BIN when a non-default simulator path is configured."""
    root = fresh_root(tmp_path)
    log = tmp_path / "custom-sim.log"
    custom_sim = tmp_path / "custom-sim.sh"
    custom_sim.write_text(
        "#!/usr/bin/env bash\n"
        f"echo invoked >> {shlex.quote(str(log))}\n"
        f"exec {shlex.quote(str(SIM))} \"$@\"\n",
        encoding="utf-8",
    )
    custom_sim.chmod(0o755)

    run_recover(
        root,
        "apply",
        "--owner",
        "cluster-a",
        check=True,
        extra_env={"JENKINS_SIM_BIN": custom_sim},
    )

    assert log.read_text(encoding="utf-8").strip() == "invoked"


def test_final_apply_uses_default_simulator_when_env_bin_absent(tmp_path):
    """Recovery must fall back to /app/scripts/jenkins_cluster_sim when no env override is set."""
    root = fresh_root(tmp_path)

    run_recover(root, "apply", "--owner", "cluster-a", check=True, extra_env={"JENKINS_SIM_BIN": None})

    diagnostics = read_json(root / "out" / "controller_diagnostics.json")
    status = read_json(root / "out" / "controller_status.json")
    assert diagnostics["phase"] == "READY"
    assert status["status"] == "READY"


def test_cluster_lost_response_resumes_without_duplicate_mutations(tmp_path):
    """A lost response after cluster commit must be reconciled by the same owner."""
    root = fresh_root(tmp_path)
    first = run_recover(
        root,
        "apply",
        "--owner",
        "cluster-a",
        "--fault",
        "after_cluster_commit_response_lost",
    )
    assert first.returncode != 0
    topo_after_commit = (root / "cluster" / "topology.json").read_bytes()
    queue_after_commit = (root / "jenkins_home" / "queue.json").read_bytes()

    other = run_recover(root, "resume", "--owner", "cluster-b")
    assert other.returncode != 0
    run_recover(root, "resume", "--owner", "cluster-a", check=True)
    events = [r["event"] for r in journal_records(root)]

    assert events.count("cluster_committed") == 1
    assert events.count("operation_completed") == 1
    assert events.index("cluster_committed") < events.index("operation_completed")
    assert (root / "cluster" / "topology.json").read_bytes() == topo_after_commit
    assert (root / "jenkins_home" / "queue.json").read_bytes() == queue_after_commit
    assert read_json(root / "out" / "controller_status.json")["status"] == "READY"


def test_no_eligible_controller_fails_before_any_mutation(tmp_path):
    """A topology without an eligible home owner must fail closed during planning."""
    root = fresh_root(tmp_path)
    path = root / "cluster" / "topology.json"
    topo = read_json(path)
    for pod in topo["pods"]:
        pod.setdefault("metadata", {})["recovery_eligible"] = False
    write_json(path, topo)
    before = tree_digest(root)

    result = run_recover(root, "apply", "--owner", "cluster-a")

    assert result.returncode != 0
    assert "no eligible controller" in result.stderr
    assert tree_digest(root) == before


def test_completed_recovery_is_idempotent_including_outputs(tmp_path):
    """Replaying a completed recovery must not change durable state or outputs."""
    root = fresh_root(tmp_path)
    run_recover(root, "apply", "--owner", "cluster-a", check=True)
    before = tree_digest(root)
    records = journal_records(root)

    run_recover(root, "apply", "--owner", "cluster-a", check=True)

    assert tree_digest(root) == before
    assert journal_records(root) == records


def test_verify_reports_ready_without_writing_new_outputs(tmp_path):
    """Verify must use diagnostics and must not act as another mutation path."""
    root = fresh_root(tmp_path)
    run_recover(root, "apply", "--owner", "cluster-a", check=True)
    out_before = tree_digest(root / "out")

    result = run_recover(root, "verify", "--json", check=True)

    assert json.loads(result.stdout)["phase"] == "READY"
    assert tree_digest(root / "out") == out_before


def test_verify_uses_diagnostics_without_starting_simulator(tmp_path):
    """Verify must not invoke simulator start after recovery is already ready."""
    root = fresh_root(tmp_path)
    log_path = tmp_path / "sim-invocations.log"
    wrapper = tmp_path / "sim-wrapper.sh"
    wrapper.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$1\" >> {json.dumps(str(log_path))}\n"
        f"exec {json.dumps(str(SIM))} \"$@\"\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    env = {"JENKINS_SIM_BIN": wrapper}
    run_recover(root, "apply", "--owner", "cluster-a", check=True, extra_env=env)
    log_path.write_text("", encoding="utf-8")
    out_before = tree_digest(root / "out")

    result = run_recover(root, "verify", "--json", check=True, extra_env=env)

    assert json.loads(result.stdout)["phase"] == "READY"
    assert tree_digest(root / "out") == out_before
    assert "start" not in log_path.read_text(encoding="utf-8").splitlines()


def test_full_recovery_preserves_cumulative_runtime_home_plugin_and_policy_state(tmp_path):
    """Final recovery must keep all earlier runtime, home, plugin, and policy guarantees intact."""
    root = fresh_root(tmp_path)
    run_recover(root, "apply", "--owner", "cluster-a", check=True)

    dep = read_json(root / "cluster" / "controller_deployment.json")
    state = read_json(root / "jenkins_home" / "controller_state.json")
    plugins = read_json(root / "jenkins_home" / "plugins" / "plugins.json")
    policy = read_json(root / "cluster" / "auto_upgrade_policy.json")

    assert dep["java_major"] == 17 and "jdk17" in dep["controller_image"]
    assert state["home_schema"] == "recovered-target"
    assert plugins["workflow-job"]["enabled"] is True
    assert policy["auto_upgrade_enabled"] is False
    assert policy["required_backup_snapshot"] == state["restored_from_snapshot"]
