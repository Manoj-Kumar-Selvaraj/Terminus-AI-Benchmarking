require 'csv'
require 'json'
require 'minitest/autorun'

APP = '/app'
SOURCES = File.join(APP, 'data', 'sources.csv')
ACTIONS = File.join(APP, 'data', 'actions.csv')
REPORT = File.join(APP, 'out', 'resolution_report.csv')
SUMMARY = File.join(APP, 'out', 'resolution_summary.json')
AUDIT = File.join(APP, 'out', 'resolution_audit.json')

class TestMilestone2 < Minitest::Test
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

  def test_elite_and_std_aliases_normalize_and_match
    write_inputs(
      [
        ['SRC-101','ACC-1','LOC-1','VIP','1500','20260530100000','ACTIVE','L1'],
        ['SRC-102','ACC-2','LOC-1','STD','1900','20260530100100','ACTIVE','L2']
      ],
      [
        ['ACT-101','SRC-101','ACC-1','LOC-1','ELITE','1500','20260530100500','RETURN','L1'],
        ['ACT-102','SRC-102','ACC-2','LOC-1','STANDARD','1900','20260530100600','CREDIT','L2']
      ]
    )
    rows, summary = run_batch
    assert_equal ['MATCHED','MATCHED'], rows.map { |r| r['status'] }
    assert_equal ['VIP','STANDARD'], rows.map { |r| r['kind'] }
    assert_equal 2, summary['matched_count']
    assert_equal 3400, summary['matched_amount_cents']
    assert_equal 0, summary['unmatched_count']
    assert_equal 0, summary['unmatched_amount_cents']
  end

  def test_prem_alias_normalizes_to_premium
    write_inputs(
      [['SRC-200','ACC-3','LOC-1','PREM','2000','20260530100000','ACTIVE','L1']],
      [['ACT-200','SRC-200','ACC-3','LOC-1','PREMIUM','2000','20260530100500','CREDIT','L1']]
    )
    rows, summary = run_batch
    assert_equal ['MATCHED'], rows.map { |r| r['status'] }
    assert_equal ['PREMIUM'], rows.map { |r| r['kind'] }
    assert_equal 1, summary['matched_count']
    assert_equal 2000, summary['matched_amount_cents']
  end

  def test_alias_normalization_with_varied_data
    write_inputs(
      [
        ['SRC-300','ACC-5','LOC-2','PREM','5000','20260530110000','ACTIVE','L3'],
        ['SRC-301','ACC-6','LOC-2','STANDARD','3000','20260530110100','ACTIVE','L3']
      ],
      [
        ['ACT-300','SRC-300','ACC-5','LOC-2','PREMIUM','5000','20260530110500','ADJUST','L3'],
        ['ACT-301','SRC-301','ACC-6','LOC-2','STD','3000','20260530110600','RETURN','L3']
      ]
    )
    rows, summary = run_batch
    assert_equal ['MATCHED','MATCHED'], rows.map { |r| r['status'] }
    assert_equal ['PREMIUM','STANDARD'], rows.map { |r| r['kind'] }
    assert_equal 2, summary['matched_count']
    assert_equal 8000, summary['matched_amount_cents']
  end

  def test_inactive_source_with_alias_kind_remains_unmatched
    write_inputs(
      [['SRC-400','ACC-7','LOC-1','STD','1000','20260530100000','INACTIVE','L1']],
      [['ACT-400','SRC-400','ACC-7','LOC-1','STANDARD','1000','20260530100500','CREDIT','L1']]
    )
    rows, summary = run_batch
    assert_equal ['UNMATCHED'], rows.map { |r| r['status'] }
    assert_equal [''], rows.map { |r| r['kind'] }
    assert_equal 0, summary['matched_count']
    assert_equal 1000, summary['unmatched_amount_cents']
  end

  def test_milestone_one_reason_filter_still_applies_with_aliases
    write_inputs(
      [['SRC-500','ACC-8','LOC-1','STD','1200','20260530100000','ACTIVE','L1']],
      [['ACT-500','SRC-500','ACC-8','LOC-1','STANDARD','1200','20260530100500','VOID','L1']]
    )
    rows, summary = run_batch
    assert_equal 'UNMATCHED', rows[0]['status']
    assert_equal '', rows[0]['kind']
    assert_equal 0, summary['matched_count']
  end
end
