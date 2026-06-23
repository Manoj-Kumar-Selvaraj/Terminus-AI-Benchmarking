import json, os, pathlib, subprocess, pytest
ROOT = pathlib.Path(os.environ.get('TASK_ROOT', '/app'))

@pytest.fixture(scope='module')
def suite_result(tmp_path_factory):
    suite = 'milestone_1'
    tmp_path = tmp_path_factory.mktemp('suite')
    out = tmp_path / f'{suite}.json'
    subprocess.run(['python3', str(ROOT / 'src' / 'document_rollout_simulator.py'), '--suite', suite, '--out', str(out)], check=True, env={**os.environ, 'TASK_ROOT': str(ROOT)})
    return json.loads(out.read_text())

def by_case(result, case_id):
    for row in result['results']:
        if row['case'] == case_id:
            return row
    raise AssertionError(f'missing case {case_id}')

class TestMilestone1:

    def test_1_api_service_selects_only_api_pods(self, suite_result):
        """API service selects only API pods."""
        row = by_case(suite_result, 'm1_positive')
        assert row["status"] == 'ALLOW'

    def test_2_worker_queue_selector_excludes_api_pods(self, suite_result):
        """worker queue selector excludes API pods."""
        row = by_case(suite_result, 'm1_old_reference')
        assert row["status"] == 'DENY'

    def test_3_migration_job_is_not_selected(self, suite_result):
        """migration job is not selected."""
        row = by_case(suite_result, 'm1_disabled')
        assert row["status"] == 'DENY'

    def test_4_stable_labels_and_service_names_remain(self, suite_result):
        """stable labels and service names remain."""
        row = by_case(suite_result, 'm1_schema')
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
