require 'csv'
require 'json'
require 'minitest/autorun'

APP = '/app'
SOURCES = File.join(APP, 'data', 'sources.csv')
ACTIONS = File.join(APP, 'data', 'actions.csv')
REPORT = File.join(APP, 'out', 'resolution_report.csv')
SUMMARY = File.join(APP, 'out', 'resolution_summary.json')
AUDIT = File.join(APP, 'out', 'resolution_audit.json')

class TestMilestone6 < Minitest::Test
  def write_csv(path, header, rows)
    CSV.open(path, 'w') { |csv| csv << header; rows.each { |row| csv << row } }
  end

  def write_inputs(sources, actions, windows: [['LOC-1','20260530090000','20260602235959','OPEN'], ['LOC-2','20260530090000','20260602235959','OPEN']], policy: [['STANDARD','Y','2'], ['PREMIUM','Y','1'], ['VIP','Y','3']], calendar: [['20260530','OPEN'], ['20260531','OPEN'], ['20260601','OPEN'], ['20260602','OPEN']], tolerance: 'max_delta_cents=0', blocked: [], replay: [])
    write_csv(SOURCES, %w[source_id account_id location_id kind amount_cents source_ts status lane], sources)
    write_csv(ACTIONS, %w[action_id source_id account_id location_id kind amount_cents action_ts reason lane], actions)
    write_csv(File.join(APP, 'config', 'windows.csv'), %w[location_id open_ts close_ts state], windows)
    write_csv(File.join(APP, 'config', 'policy.csv'), %w[kind enabled priority], policy)
    File.write(File.join(APP, 'config', 'calendar.txt'), calendar.map { |r| r.join(' ') }.join("\n") + "\n")
    File.write(File.join(APP, 'config', 'tolerance.conf'), tolerance + "\n")
    File.write(File.join(APP, 'config', 'blocked_accounts.txt'), blocked.join("\n") + "\n")
    write_csv(File.join(APP, 'config', 'replay_ledger.csv'), %w[action_id], replay)
    [REPORT, SUMMARY, AUDIT].each { |path| File.delete(path) if File.exist?(path) }
  end

  def run_batch
    assert system('/app/scripts/run_batch.sh')
    [CSV.read(REPORT, headers: true), JSON.parse(File.read(SUMMARY))]
  end

  def test_amount_tolerance_allows_small_delta_but_not_large_delta
    write_inputs(
      [
        ['SRC-501','ACC-1','LOC-1','STANDARD','1000','20260530100000','ACTIVE','L1'],
        ['SRC-502','ACC-2','LOC-1','STANDARD','2000','20260530100000','ACTIVE','L2'],
        ['SRC-503','ACC-3','LOC-1','STANDARD','3000','20260530100000','ACTIVE','L3']
      ],
      [
        ['ACT-501','SRC-501','ACC-1','LOC-1','STANDARD','1004','20260530101000','CREDIT','L1'],
        ['ACT-502','SRC-502','ACC-2','LOC-1','STANDARD','2010','20260530101000','CREDIT','L2'],
        ['ACT-503','SRC-503','ACC-3','LOC-1','STANDARD','3005','20260530101000','CREDIT','L3']
      ],
      tolerance: 'max_delta_cents=5'
    )
    rows, summary = run_batch
    assert_equal ['MATCHED','UNMATCHED','MATCHED'], rows.map { |r| r['status'] }
    assert_equal 2, summary['matched_count']
    assert_equal 4009, summary['matched_amount_cents']
    assert_equal 1, summary['unmatched_count']
    assert_equal 2010, summary['unmatched_amount_cents']
  end

  def test_zero_tolerance_requires_exact_match
    write_inputs(
      [['SRC-600','ACC-1','LOC-1','STANDARD','1000','20260530100000','ACTIVE','L1']],
      [['ACT-600','SRC-600','ACC-1','LOC-1','STANDARD','1001','20260530101000','CREDIT','L1']],
      tolerance: 'max_delta_cents=0'
    )
    rows, summary = run_batch
    assert_equal ['UNMATCHED'], rows.map { |r| r['status'] }
    assert_equal 0, summary['matched_count']
    assert_equal 1001, summary['unmatched_amount_cents']
  end

  def test_tolerance_does_not_override_window_close
    write_inputs(
      [['SRC-700','ACC-1','LOC-1','STANDARD','1000','20260530100000','ACTIVE','L1']],
      [['ACT-700','SRC-700','ACC-1','LOC-1','STANDARD','1003','20260530110000','CREDIT','L1']],
      windows: [['LOC-1','20260530100000','20260530103000','OPEN']],
      tolerance: 'max_delta_cents=5'
    )
    rows, summary = run_batch
    assert_equal 'UNMATCHED', rows[0]['status']
    assert_equal 0, summary['matched_count']
  end
end
