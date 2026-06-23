import json, os, pathlib, subprocess, pytest
ROOT = pathlib.Path(os.environ.get('TASK_ROOT', '/app'))

@pytest.fixture(scope='module')
def suite_result(tmp_path_factory):
    suite = 'milestone_4'
    tmp_path = tmp_path_factory.mktemp('suite')
    out = tmp_path / f'{suite}.json'
    subprocess.run(['python3', str(ROOT / 'src' / 'document_rollout_simulator.py'), '--suite', suite, '--out', str(out)], check=True, env={**os.environ, 'TASK_ROOT': str(ROOT)})
    return json.loads(out.read_text())

def by_case(result, case_id):
    for row in result['results']:
        if row['case'] == case_id:
            return row
    raise AssertionError(f'missing case {case_id}')

class TestMilestone4:

    def test_1_rolling_update_keeps_availability(self, suite_result):
        """rolling update keeps availability."""
        row = by_case(suite_result, 'm4_failover')
        assert row["status"] == 'ALLOW'

    def test_2_pdb_protects_api_and_workers(self, suite_result):
        """PDB protects API and workers."""
        row = by_case(suite_result, 'm4_gap')
        assert row["status"] == 'ANOMALY'

    def test_3_hpa_metrics_and_bounds_are_valid(self, suite_result):
        """HPA metrics and bounds are valid."""
        row = by_case(suite_result, 'm4_badseq')
        assert row["status"] == 'ANOMALY'

    def test_4_network_policy_denies_unrelated_egress(self, suite_result):
        """network policy denies unrelated egress."""
        row = by_case(suite_result, 'm4_conflict')
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
