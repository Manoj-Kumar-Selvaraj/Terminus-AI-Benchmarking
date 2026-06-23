require 'csv'
require 'json'
require 'minitest/autorun'

APP = '/app'
SOURCES = File.join(APP, 'data', 'sources.csv')
ACTIONS = File.join(APP, 'data', 'actions.csv')
REPORT = File.join(APP, 'out', 'resolution_report.csv')
SUMMARY = File.join(APP, 'out', 'resolution_summary.json')
AUDIT = File.join(APP, 'out', 'resolution_audit.json')

class TestMilestone4 < Minitest::Test
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

  def test_any_uses_enabled_policy_priority_and_disabled_kind_stays_unmatched
    write_inputs(
      [
        ['SRC-301','ACC-1','LOC-1','PREMIUM','1000','20260530100100','ACTIVE','L1'],
        ['SRC-301','ACC-1','LOC-1','VIP','1000','20260530100200','ACTIVE','L1'],
        ['SRC-302','ACC-2','LOC-1','VIP','2000','20260530100300','ACTIVE','L2']
      ],
      [
        ['ACT-301','SRC-301','ACC-1','LOC-1','ANY','1000','20260530101000','CREDIT','L1'],
        ['ACT-302','SRC-302','ACC-2','LOC-1','VIP','2000','20260530101000','CREDIT','L2']
      ],
      policy: [['STANDARD','Y','3'], ['PREMIUM','Y','1'], ['VIP','N','2']]
    )
    rows, _summary = run_batch
    assert_equal ['MATCHED','UNMATCHED'], rows.map { |r| r['status'] }
    assert_equal 'PREMIUM', rows[0]['kind']
  end
end