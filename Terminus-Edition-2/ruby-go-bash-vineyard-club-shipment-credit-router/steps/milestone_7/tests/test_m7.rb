require 'csv'
require 'json'
require 'minitest/autorun'

APP = '/app'
SOURCES = File.join(APP, 'data', 'sources.csv')
ACTIONS = File.join(APP, 'data', 'actions.csv')
REPORT = File.join(APP, 'out', 'resolution_report.csv')
SUMMARY = File.join(APP, 'out', 'resolution_summary.json')
AUDIT = File.join(APP, 'out', 'resolution_audit.json')

class TestMilestone7 < Minitest::Test
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

  def test_blocklist_replay_and_audit_output
    write_inputs(
      [
        ['SRC-601','ACC-BLOCK','LOC-1','STANDARD','1000','20260530100000','ACTIVE','L1'],
        ['SRC-602','ACC-2','LOC-1','STANDARD','2000','20260530100000','ACTIVE','L2'],
        ['SRC-603','ACC-3','LOC-1','STANDARD','3000','20260530100000','ACTIVE','L3'],
        ['SRC-604','ACC-2','LOC-1','STANDARD','4000','20260530100000','ACTIVE','L4']
      ],
      [
        ['ACT-601','SRC-601','ACC-BLOCK','LOC-1','STANDARD','1000','20260530101000','CREDIT','L1'],
        ['ACT-602','SRC-602','ACC-2','LOC-1','STANDARD','2000','20260530101000','CREDIT','L2'],
        ['ACT-603','SRC-603','ACC-3','LOC-1','STANDARD','3000','20260530101000','CREDIT','L3'],
        ['ACT-604','SRC-604','ACC-2','LOC-1','STANDARD','4000','20260530101000','CREDIT','L4']
      ],
      blocked: ['ACC-BLOCK'], replay: [['ACT-602']]
    )
    rows, summary = run_batch
    audit = JSON.parse(File.read(AUDIT))
    assert_equal ['UNMATCHED','UNMATCHED','MATCHED','MATCHED'], rows.map { |r| r['status'] }
    assert_equal 'MATCHED', rows.find { |r| r['action_id'] == 'ACT-604' }['status']
    assert_equal ['ACT-603', 'ACT-604'].sort, audit['matched_action_ids'].sort
    assert_equal ['ACT-601', 'ACT-602'].sort, audit['unmatched_action_ids'].sort
    assert_equal 2, summary['matched_count']
    assert_equal 7000, summary['matched_amount_cents']
    assert_equal 2, summary['unmatched_count']
    assert_equal 3000, summary['unmatched_amount_cents']
  end

  def test_blocked_account_alone
    write_inputs(
      [['SRC-801','ACC-X','LOC-1','STANDARD','1500','20260530100000','ACTIVE','L1']],
      [['ACT-801','SRC-801','ACC-X','LOC-1','STANDARD','1500','20260530101000','CREDIT','L1']],
      blocked: ['ACC-X'], replay: []
    )
    rows, summary = run_batch
    assert_equal 'UNMATCHED', rows[0]['status']
    assert_equal 0, summary['matched_count']
    assert_equal 1500, summary['unmatched_amount_cents']
  end
end
