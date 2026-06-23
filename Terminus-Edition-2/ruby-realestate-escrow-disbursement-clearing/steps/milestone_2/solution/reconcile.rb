
require 'csv'
require 'fileutils'

APP = '/app'
OUT = File.join(APP, 'out')
FileUtils.mkdir_p(OUT)

def csv_rows(path)
  return [] unless File.exist?(path)
  CSV.read(path, headers: true).map { |r| r.to_h.transform_values { |v| v.nil? ? '' : v.to_s.strip } }
end

def write_csv(path, header, rows)
  CSV.open(path, 'w') do |csv|
    csv << header
    rows.each { |row| csv << header.map { |h| row[h] } }
  end
end

def int_string?(v)
  v.to_s.match?(/\A\d+\z/)
end

def ts_string?(v)
  v.to_s.match?(/\A\d{14}\z/)
end

def canonical_kind(v, aliases: false)
  s = v.to_s.strip.upcase
  if aliases
    return 'SELLER' if ['SELLER', 'SLR'].include?(s)
    return 'BROKER' if ['BROKER', 'BRK'].include?(s)
    return 'TAX' if ['TAX', 'TAXAUTH'].include?(s)
  end
  s
end

def reason_ok?(v)
  ['CLOSE', 'CORRECT', 'RELEASE'].include?(v.to_s.strip.upcase)
end

def load_windows
  csv_rows(File.join(APP, 'config', 'windows.csv')).map do |r|
    { trust_id: r['trust_id'], open_ts: r['open_ts'], close_ts: r['close_ts'], state: r['state'].to_s.strip.upcase }
  end
end

def window_ok?(src, act, windows)
  return false unless ts_string?(src[:source_ts]) && ts_string?(act[:action_ts])
  src_ts = src[:source_ts].to_i
  act_ts = act[:action_ts].to_i
  windows.any? do |w|
    next false unless w[:trust_id] == src[:trust_id] && w[:state] == 'OPEN'
    next false unless ts_string?(w[:open_ts]) && ts_string?(w[:close_ts])
    open_ts = w[:open_ts].to_i
    close_ts = w[:close_ts].to_i
    src_ts >= open_ts && src_ts <= close_ts && act_ts > src_ts && act_ts <= close_ts
  end
end

def load_holds(aliases: false)
  csv_rows(File.join(APP, 'data', 'holds.csv')).map.with_index do |r, i|
    {
      escrow_id: r['escrow_id'], payee_id: r['payee_id'], trust_id: r['trust_id'], location: r['location'],
      kind: canonical_kind(r['kind'], aliases: aliases), amount: r['amount'], source_ts: r['source_ts'],
      status: r['status'].to_s.strip.upcase, row: i, used: false
    }
  end
end

def load_actions(aliases: false)
  csv_rows(File.join(APP, 'data', 'disbursements.csv')).map do |r|
    {
      action_id: r['action_id'], closing_id: r['closing_id'], escrow_id: r['escrow_id'], payee_id: r['payee_id'],
      trust_id: r['trust_id'], location: r['location'], kind: canonical_kind(r['kind'], aliases: aliases),
      amount: r['amount'], action_ts: r['action_ts'], reason: r['reason'].to_s.strip.upcase
    }
  end
end

def eligible_kind?(kind, aliases: false)
  allowed = aliases ? ['SELLER', 'BROKER', 'TAX'] : ['SELLER', 'BROKER']
  allowed.include?(kind)
end

def candidate?(src, act, windows, aliases: false)
  return false if src[:used]
  return false unless src[:escrow_id] == act[:escrow_id] && src[:payee_id] == act[:payee_id]
  return false unless src[:trust_id] == act[:trust_id] && src[:location] == act[:location]
  return false unless src[:amount] == act[:amount] && int_string?(src[:amount]) && int_string?(act[:amount])
  return false unless src[:status] == 'HELD' && reason_ok?(act[:reason])
  return false unless eligible_kind?(src[:kind], aliases: aliases) && src[:kind] == act[:kind]
  window_ok?(src, act, windows)
end

def match_rows(aliases: false)
  holds = load_holds(aliases: aliases)
  actions = load_actions(aliases: aliases)
  windows = load_windows
  report = []
  summary = { 'matched_count' => 0, 'matched_amount' => 0, 'unmatched_count' => 0, 'unmatched_amount' => 0 }
  matches = {}

  actions.each do |act|
    candidates = holds.each_with_index.select { |src, _idx| candidate?(src, act, windows, aliases: aliases) }
    candidates.sort_by! { |src, _idx| [-src[:source_ts].to_i, src[:row]] }
    best, idx = candidates.first
    amount = int_string?(act[:amount]) ? act[:amount].to_i : 0
    if best
      holds[idx][:used] = true
      matches[act[:action_id]] = { action: act, source: best }
      summary['matched_count'] += 1
      summary['matched_amount'] += amount
      report << { 'action_id' => act[:action_id], 'escrow_id' => act[:escrow_id], 'payee_id' => act[:payee_id], 'trust_id' => act[:trust_id], 'kind' => best[:kind], 'amount' => act[:amount], 'reason' => act[:reason], 'status' => 'MATCHED' }
    else
      summary['unmatched_count'] += 1
      summary['unmatched_amount'] += amount
      report << { 'action_id' => act[:action_id], 'escrow_id' => act[:escrow_id], 'payee_id' => act[:payee_id], 'trust_id' => act[:trust_id], 'kind' => '', 'amount' => act[:amount], 'reason' => act[:reason], 'status' => 'UNMATCHED' }
    end
  end

  write_csv(File.join(OUT, 'disbursement_report.csv'), ['action_id','escrow_id','payee_id','trust_id','kind','amount','reason','status'], report)
  File.write(File.join(OUT, 'disbursement_summary.txt'), summary.map { |k, v| "#{k}=#{v}" }.join("\n") + "\n")
  [matches, actions]
end

def packages
  csv_rows(File.join(APP, 'config', 'closing_packages.csv')).map do |r|
    req = r['required_kinds'].to_s.split(/[|;]/).map { |x| canonical_kind(x, aliases: true) }.reject(&:empty?)
    { closing_id: r['closing_id'], escrow_id: r['escrow_id'], trust_id: r['trust_id'], expected_total: r['expected_total'].to_i, required_kinds: req, package_state: r['package_state'].to_s.strip.upcase }
  end
end

def build_groups(matches, actions)
  package_map = packages.each_with_object({}) { |p, h| h[p[:closing_id]] = p }
  action_status = actions.each_with_object({}) { |a, h| h[a[:action_id]] = matches.key?(a[:action_id]) }
  groups = []

  package_map.each_value do |pkg|
    related = actions.select { |a| a[:closing_id] == pkg[:closing_id] }
    matched = related.select { |a| action_status[a[:action_id]] }
    matched_kinds = matched.map { |a| a[:kind] }
    matched_amount = matched.map { |a| a[:amount].to_i }.sum
    missing = pkg[:required_kinds] - matched_kinds
    reason = 'OK'
    status = 'CLEARED'
    if pkg[:package_state] != 'OPEN'
      status = 'HELD'; reason = 'PACKAGE_NOT_OPEN'
    elsif related.empty?
      status = 'HELD'; reason = 'NO_MATCHED_ROWS'
    elsif related.any? { |a| !action_status[a[:action_id]] }
      status = 'HELD'; reason = 'UNMATCHED_ACTION'
    elsif matched.empty?
      status = 'HELD'; reason = 'NO_MATCHED_ROWS'
    elsif !missing.empty?
      status = 'HELD'; reason = "MISSING_KIND:#{missing.first}"
    elsif matched_amount != pkg[:expected_total]
      status = 'HELD'; reason = 'TOTAL_MISMATCH'
    end
    groups << {
      'closing_id' => pkg[:closing_id], 'escrow_id' => pkg[:escrow_id], 'trust_id' => pkg[:trust_id],
      'required_kinds' => pkg[:required_kinds].sort.join('|'), 'matched_kinds' => matched_kinds.sort.join('|'),
      'matched_amount' => matched_amount.to_s, 'expected_amount' => pkg[:expected_total].to_s,
      'status' => status, 'reason' => reason
    }
  end
  groups
end

def write_groups(groups)
  write_csv(File.join(OUT, 'closing_group_report.csv'), ['closing_id','escrow_id','trust_id','required_kinds','matched_kinds','matched_amount','expected_amount','status','reason'], groups)
end

def load_balances
  csv_rows(File.join(APP, 'data', 'trust_balances.csv')).each_with_object({}) { |r, h| h[r['trust_id']] = r['opening_balance'].to_i }
end

def load_control_totals
  csv_rows(File.join(APP, 'config', 'control_totals.csv')).each_with_object({}) do |r, h|
    h[r['trust_id']] = { count: r['expected_group_count'].to_i, amount: r['expected_amount'].to_i }
  end
end

def apply_funding(groups)
  balances = load_balances
  controls = load_control_totals
  valid = groups.select { |g| g['status'] == 'CLEARED' }
  valid_by_trust = valid.group_by { |g| g['trust_id'] }
  valid_by_trust.each do |trust, gs|
    if controls[trust]
      actual_count = gs.length
      actual_amount = gs.sum { |g| g['expected_amount'].to_i }
      if actual_count != controls[trust][:count] || actual_amount != controls[trust][:amount]
        gs.each { |g| g['status'] = 'HELD'; g['reason'] = 'CONTROL_TOTAL_MISMATCH' }
      end
    end
  end
  groups.each do |g|
    next unless g['status'] == 'CLEARED'
    trust = g['trust_id']
    amount = g['expected_amount'].to_i
    balances[trust] ||= 0
    if balances[trust] < amount
      g['status'] = 'HELD'
      g['reason'] = 'INSUFFICIENT_FUNDS'
    else
      balances[trust] -= amount
    end
  end
  write_csv(File.join(OUT, 'trust_balance_after.csv'), ['trust_id','balance'], balances.keys.sort.map { |k| { 'trust_id' => k, 'balance' => balances[k].to_s } })
  groups
end

def ledger_path
  File.join(OUT, 'escrow_commit_ledger.csv')
end

def read_commits
  return [] unless File.exist?(ledger_path)
  csv_rows(ledger_path)
end

def write_commits(rows)
  write_csv(ledger_path, ['commit_id','closing_id','trust_id','amount','committed_at'], rows)
end

def commit_groups(groups)
  committed = read_commits
  committed_ids = committed.map { |r| r['closing_id'] }.to_set
  limit = ENV['ABEND_AFTER_GROUPS'].to_s.empty? ? nil : ENV['ABEND_AFTER_GROUPS'].to_i
  new_commits = 0
  groups.each do |g|
    next unless g['status'] == 'CLEARED'
    next if committed_ids.include?(g['closing_id'])
    committed << { 'commit_id' => "COMMIT-#{g['closing_id']}", 'closing_id' => g['closing_id'], 'trust_id' => g['trust_id'], 'amount' => g['expected_amount'], 'committed_at' => '20260613000000' }
    committed_ids.add(g['closing_id'])
    write_commits(committed)
    new_commits += 1
    if limit && new_commits >= limit
      File.write(File.join(OUT, 'restart_checkpoint.txt'), "last_committed_closing_id=#{g['closing_id']}\ncommitted_count=#{committed.length}\nstatus=ABENDED\n")
      abort('simulated ABEND after committed group boundary')
    end
  end
  write_commits(committed)
  File.write(File.join(OUT, 'restart_checkpoint.txt'), "last_committed_closing_id=#{committed.last && committed.last['closing_id']}\ncommitted_count=#{committed.length}\nstatus=COMPLETE\n")
end

matches, actions = match_rows(aliases: true)
groups = build_groups(matches, actions)
write_groups(groups)
