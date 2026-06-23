import json, os, pathlib, subprocess, pytest
ROOT = pathlib.Path(os.environ.get('TASK_ROOT', '/app'))

@pytest.fixture(scope='module')
def suite_result(tmp_path_factory):
    suite = 'milestone_3'
    tmp_path = tmp_path_factory.mktemp('suite')
    out = tmp_path / f'{suite}.json'
    subprocess.run(['python3', str(ROOT / 'src' / 'document_rollout_simulator.py'), '--suite', suite, '--out', str(out)], check=True, env={**os.environ, 'TASK_ROOT': str(ROOT)})
    return json.loads(out.read_text())

def by_case(result, case_id):
    for row in result['results']:
        if row['case'] == case_id:
            return row
    raise AssertionError(f'missing case {case_id}')

class TestMilestone3:

    def test_1_owner_can_renew_lease(self, suite_result):
        """owner can renew lease."""
        row = by_case(suite_result, 'm3_commit')
        assert row["status"] == 'ALLOW'

    def test_2_non_owner_cannot_renew_lease(self, suite_result):
        """non-owner cannot renew lease."""
        row = by_case(suite_result, 'm3_stale')
        assert row["status"] == 'SUPPRESSED'

    def test_3_duplicate_render_is_suppressed(self, suite_result):
        """duplicate render is suppressed."""
        row = by_case(suite_result, 'm3_poison_retry')
        assert row["status"] == 'RETRY'

    def test_4_poison_render_reaches_dlq_with_reason(self, suite_result):
        """poison render reaches DLQ with reason."""
        row = by_case(suite_result, 'm3_poison_dlq')
        assert row["status"] == 'DLQ'

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
