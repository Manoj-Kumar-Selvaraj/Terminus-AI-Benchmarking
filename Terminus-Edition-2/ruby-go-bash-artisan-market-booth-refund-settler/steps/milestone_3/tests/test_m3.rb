require 'csv'
require 'json'
require 'minitest/autorun'

APP = '/app'
SOURCES = File.join(APP, 'data', 'sources.csv')
ACTIONS = File.join(APP, 'data', 'actions.csv')
REPORT = File.join(APP, 'out', 'resolution_report.csv')
SUMMARY = File.join(APP, 'out', 'resolution_summary.json')
AUDIT = File.join(APP, 'out', 'resolution_audit.json')

class TestMilestone3 < Minitest::Test
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

  def test_open_window_close_bound_and_latest_source_timestamp
    write_inputs(
      [
        ['SRC-201','ACC-1','LOC-1','STANDARD','1000','20260530100100','ACTIVE','L1'],
        ['SRC-201','ACC-1','LOC-1','STANDARD','1000','20260530101000','ACTIVE','L1'],
        ['SRC-202','ACC-2','LOC-2','STANDARD','2000','20260530100100','ACTIVE','L2']
      ],
      [
        ['ACT-201','SRC-201','ACC-1','LOC-1','STANDARD','1000','20260530101500','CREDIT','L1'],
        ['ACT-202','SRC-202','ACC-2','LOC-2','STANDARD','2000','20260530110000','CREDIT','L2']
      ],
      windows: [['LOC-1','20260530100000','20260530103000','OPEN'], ['LOC-2','20260530100000','20260530103000','OPEN']]
    )
    rows, summary = run_batch
    assert_equal ['MATCHED','UNMATCHED'], rows.map { |r| r['status'] }
    assert_equal 1, summary['matched_count']
    assert_equal 2000, summary['unmatched_amount_cents']
  end
end