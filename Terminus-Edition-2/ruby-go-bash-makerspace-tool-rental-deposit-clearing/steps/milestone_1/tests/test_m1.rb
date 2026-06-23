require 'csv'
require 'json'
require 'minitest/autorun'

APP = '/app'
SOURCES = File.join(APP, 'data', 'sources.csv')
ACTIONS = File.join(APP, 'data', 'actions.csv')
REPORT = File.join(APP, 'out', 'resolution_report.csv')
SUMMARY = File.join(APP, 'out', 'resolution_summary.json')
AUDIT = File.join(APP, 'out', 'resolution_audit.json')

class TestMilestone1 < Minitest::Test
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

  def test_exact_matching_consumption_and_blank_unmatched_kind
    write_inputs(
      [
        ['SRC-001','ACC-1','LOC-1','STANDARD','1000','20260530100000','ACTIVE','L1'],
        ['SRC-002','ACC-2','LOC-1','PREMIUM','2000','20260530100100','CANCELLED','L2']
      ],
      [
        ['ACT-1','SRC-001','ACC-1','LOC-1','STANDARD','1000','20260530100500','CREDIT','L1'],
        ['ACT-2','SRC-001','ACC-1','LOC-1','STANDARD','1000','20260530100600','CREDIT','L1'],
        ['ACT-3','SRC-002','ACC-2','LOC-1','PREMIUM','2000','20260530100600','CREDIT','L2']
      ]
    )
    rows, summary = run_batch
    assert_equal ['MATCHED','UNMATCHED','UNMATCHED'], rows.map { |r| r['status'] }
    assert_equal '', rows[1]['kind']
    assert_equal 1, summary['matched_count']
    assert_equal 3000, summary['unmatched_amount_cents']
  end
end