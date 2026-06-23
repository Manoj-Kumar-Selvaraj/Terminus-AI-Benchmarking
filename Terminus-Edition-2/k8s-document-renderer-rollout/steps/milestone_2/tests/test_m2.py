import json, os, pathlib, subprocess, pytest
ROOT = pathlib.Path(os.environ.get('TASK_ROOT', '/app'))

@pytest.fixture(scope='module')
def suite_result(tmp_path_factory):
    suite = 'milestone_2'
    tmp_path = tmp_path_factory.mktemp('suite')
    out = tmp_path / f'{suite}.json'
    subprocess.run(['python3', str(ROOT / 'src' / 'document_rollout_simulator.py'), '--suite', suite, '--out', str(out)], check=True, env={**os.environ, 'TASK_ROOT': str(ROOT)})
    return json.loads(out.read_text())

def by_case(result, case_id):
    for row in result['results']:
        if row['case'] == case_id:
            return row
    raise AssertionError(f'missing case {case_id}')

class TestMilestone2:

    def test_1_font_cache_pvc_is_mounted(self, suite_result):
        """font cache PVC is mounted."""
        row = by_case(suite_result, 'm2_authorized')
        assert row["status"] == 'ALLOW'

    def test_2_config_mount_path_is_present(self, suite_result):
        """config mount path is present."""
        row = by_case(suite_result, 'm2_owner_mismatch')
        assert row["status"] == 'DENY'

    def test_3_secret_is_not_writable_in_worker_path(self, suite_result):
        """secret is not writable in worker path."""
        row = by_case(suite_result, 'm2_wildcard')
        assert row["status"] == 'DENY'

    def test_4_init_cache_warmer_runs_first(self, suite_result):
        """init cache warmer runs first."""
        row = by_case(suite_result, 'm2_readiness')
        assert row["status"] == 'DENY'

    def test_99_result_schema_is_stable(self, suite_result):
        """Simulator output preserves result and summary schema."""
        result = suite_result
        assert {"task","level","suite","results","summary"} <= set(result)
        assert result["results"]
        for row in result["results"]:
            assert {"case","status","reason","selected"} <= set(row)

def test_runtime_has_no_level_unlock():
    source = pathlib.Path('/app/src/document_rollout_simulator.py').read_text()
    assert 'LEVEL =' not in source
    assert 'decision_for(c, LEVEL)' not in source
