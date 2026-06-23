#!/bin/bash
set -euo pipefail
cat > /app/app/reconcile.rb <<'RUBY'
require 'csv'
require 'date'
require 'fileutils'

def load_aliases
  CSV.read('/app/config/kind_aliases.csv', headers: true).each_with_object({}) do |r, aliases|
    key = r['alias'].to_s.strip.upcase
    val = r['canonical'].to_s.strip.upcase
    aliases[key] = val unless key.empty?
  end
rescue Errno::ENOENT
  {}
end

def load_reasons
  CSV.read('/app/config/reasons.csv', headers: true).each_with_object({}) do |r, reasons|
    reason = r['reason'].to_s.strip.upcase
    reasons[reason] = r['eligible'].to_s.strip.upcase == 'Y'
  end
rescue Errno::ENOENT
  {}
end

ALIASES = load_aliases
REASONS = load_reasons

def canon(v)
  v = v.to_s.strip.upcase
  return 'ANY' if v == 'ANY'
  ALIASES.fetch(v, v)
end

def digits?(v) = v.to_s.match?(/\A\d{14}\z/)
def kind_ok?(v) = ['BASIC', 'PRO', 'ENT'].include?(v)
def reason_ok?(v) = REASONS[v.to_s.strip.upcase]
def status_ok?(v) = v.to_s.strip.upcase == 'ACTIVE'

def enabled_ok?(v)
  val = v.to_s.strip.upcase
  val == 'Y' || val == 'YES' || val == '1'
end

def parse_ymd(value)
  return nil unless value.to_s.match?(/\A\d{8}\z/)
  Date.strptime(value, '%Y%m%d')
rescue ArgumentError
  nil
end

def round_proration(numerator, denominator, mode)
  case mode
  when 'FLOOR'
    numerator / denominator
  when 'CEIL'
    (numerator + denominator - 1) / denominator
  when 'NEAREST'
    (numerator * 2 + denominator) / (2 * denominator)
  end
end

def window_ok?(src, act, windows)
  return false unless digits?(src[:ts]) && digits?(act[:ts])
  windows.any? do |w|
    w[:scope] == src[:scope] && w[:state] == 'OPEN' && digits?(w[:open]) && digits?(w[:close]) &&
      src[:ts] >= w[:open] && src[:ts] <= w[:close] && act[:ts] >= src[:ts] && act[:ts] <= w[:close]
  end
end

def load_policy
  CSV.read('/app/config/kind_policy.csv', headers: true).each_with_object({}) do |r, policy|
    kind = r['kind'].to_s.strip.upcase
    priority = r['priority'].to_s.strip
    next unless kind_ok?(kind) && priority.match?(/\A\d+\z/)
    policy[kind] = { enabled: enabled_ok?(r['enabled']), priority: priority.to_i }
  end
rescue Errno::ENOENT
  {}
end

def load_release_calendar
  calendar = {}
  File.readlines('/app/config/release_calendar.txt', chomp: true).each do |line|
    next if line.strip.empty?
    parts = line.split(',', 2).map { |v| v.to_s.strip }
    next unless parts.length == 2 && parse_ymd(parts[0])
    calendar[parts[0]] = parts[1].upcase
  end
  calendar
rescue Errno::ENOENT
  {}
end

def load_seat_ledger(calendar)
  capacity = Hash.new(0)
  CSV.read('/app/config/seat_ledger.csv', headers: true).each do |r|
    scope = r['subscription_id'].to_s.strip
    day = r['ledger_date'].to_s.strip
    delta = r['seat_delta'].to_s.strip
    next if scope.empty? || !parse_ymd(day) || calendar[day] != 'OPEN'
    next unless delta.match?(/\A[+-]?\d+\z/)
    seats = delta.to_i
    next unless seats < 0
    capacity[[scope, day]] += -seats
  end
  capacity
rescue Errno::ENOENT
  Hash.new(0)
end

def load_contracts
  contracts = []
  CSV.read('/app/config/proration_contracts.csv', headers: true).each_with_index do |r, idx|
    scope = r['subscription_id'].to_s.strip
    kind = canon(r['kind'])
    start_s = r['period_start'].to_s.strip
    finish_s = r['period_end'].to_s.strip
    cutover_s = r['cutover_date'].to_s.strip
    rate_s = r['rate_cents'].to_s.strip
    mode = r['rounding_mode'].to_s.strip.upcase
    next if scope.empty? || !kind_ok?(kind) || !enabled_ok?(r['enabled'])
    start_d = parse_ymd(start_s)
    finish_d = parse_ymd(finish_s)
    cutover_d = parse_ymd(cutover_s)
    next unless start_d && finish_d && cutover_d && start_d <= finish_d && cutover_d >= start_d && cutover_d <= finish_d
    next unless rate_s.match?(/\A\d+\z/) && ['FLOOR', 'CEIL', 'NEAREST'].include?(mode)
    contracts << {
      scope: scope, kind: kind, start_s: start_s, finish_s: finish_s, cutover_s: cutover_s,
      start_d: start_d, finish_d: finish_d, cutover_d: cutover_d,
      rate: rate_s.to_i, mode: mode, row: idx
    }
  end
  contracts
rescue Errno::ENOENT
  []
end

def policy_enabled?(kind, policy)
  row = policy[kind]
  row && row[:enabled]
end

def calendar_ok?(src, act, calendar)
  return false unless digits?(src[:ts]) && digits?(act[:ts])
  src_day = src[:ts][0, 8]
  act_day = act[:ts][0, 8]
  return false unless calendar[src_day] == 'OPEN' && calendar[act_day] == 'OPEN'
  src_date = parse_ymd(src_day)
  act_date = parse_ymd(act_day)
  return false unless src_date && act_date
  delta = (act_date - src_date).to_i
  delta >= 0 && delta <= 2
end

def ledger_capacity_ok?(src, capacity, used)
  return false unless digits?(src[:ts])
  key = [src[:scope], src[:ts][0, 8]]
  used[key] < capacity[key]
end

def contract_amount_ok?(src, contracts)
  return false unless digits?(src[:ts])
  source_day = src[:ts][0, 8]
  source_date = parse_ymd(source_day)
  return false unless source_date
  chosen = contracts.select do |c|
    c[:scope] == src[:scope] && c[:kind] == src[:kind] && source_date >= c[:start_d] && source_date <= c[:finish_d] &&
      c[:cutover_d] <= source_date
  end.max_by { |c| [c[:cutover_s], c[:row]] }
  return false unless chosen
  period_days = (chosen[:finish_d] - chosen[:start_d]).to_i + 1
  remaining_days = (chosen[:finish_d] - source_date).to_i + 1
  expected = round_proration(chosen[:rate] * remaining_days, period_days, chosen[:mode])
  src[:amount].to_i == expected
end

sources = CSV.read('/app/data/seat_events.csv', headers: true).map.with_index do |r, i|
  { id: r['event_id'].to_s.strip, account: r['account_id'].to_s.strip, scope: r['subscription_id'].to_s.strip,
    kind: canon(r['kind']), amount: r['amount'].to_s.strip, ts: r['source_ts'].to_s.strip,
    status: r['status'].to_s.strip, loc: r['location'].to_s.strip, row: i, used: false }
end
actions = CSV.read('/app/data/credits.csv', headers: true).map do |r|
  { aid: r['action_id'].to_s.strip, id: r['event_id'].to_s.strip, account: r['account_id'].to_s.strip,
    scope: r['subscription_id'].to_s.strip, kind: canon(r['kind']), amount: r['amount'].to_s.strip,
    ts: r['action_ts'].to_s.strip, reason: r['reason'].to_s.strip, loc: r['location'].to_s.strip }
end
windows = CSV.read('/app/config/windows.csv', headers: true).map do |r|
  { scope: r['subscription_id'].to_s.strip, open: r['open_ts'].to_s.strip, close: r['close_ts'].to_s.strip, state: r['state'].to_s.strip.upcase }
end
policy = load_policy
calendar = load_release_calendar
seat_capacity = load_seat_ledger(calendar)
contracts = load_contracts
seat_used = Hash.new(0)

FileUtils.mkdir_p('/app/out')
mc = uc = ma = ua = 0
CSV.open('/app/out/seat_credit_report.csv', 'w') do |csv|
  csv << ['action_id', 'event_id', 'account_id', 'subscription_id', 'kind', 'amount', 'reason', 'status']
  actions.each do |act|
    candidates = []
    sources.each_with_index do |src, i|
      kind_matches = act[:kind] == 'ANY' || src[:kind] == act[:kind]
      concrete_kind_ok = act[:kind] == 'ANY' || kind_ok?(act[:kind])
      candidates << i if src[:id] == act[:id] && src[:amount].to_i == act[:amount].to_i && !src[:used] &&
        src[:account] == act[:account] && src[:scope] == act[:scope] && src[:loc] == act[:loc] &&
        kind_ok?(src[:kind]) && concrete_kind_ok && kind_matches && policy_enabled?(src[:kind], policy) &&
        status_ok?(src[:status]) && reason_ok?(act[:reason]) &&
        window_ok?(src, act, windows) && calendar_ok?(src, act, calendar) &&
        ledger_capacity_ok?(src, seat_capacity, seat_used) && contract_amount_ok?(src, contracts)
    end
    candidates.sort_by! do |i|
      if act[:kind] == 'ANY'
        [-sources[i][:ts].to_i, policy[sources[i][:kind]][:priority], sources[i][:row]]
      else
        [-sources[i][:ts].to_i, sources[i][:row]]
      end
    end
    best_idx = candidates.first
    amt = act[:amount].to_i
    if best_idx
      sources[best_idx][:used] = true
      seat_used[[sources[best_idx][:scope], sources[best_idx][:ts][0, 8]]] += 1
      mc += 1
      ma += amt
      csv << [act[:aid], act[:id], act[:account], act[:scope], sources[best_idx][:kind], act[:amount], act[:reason], 'MATCHED']
    else
      uc += 1
      ua += amt
      csv << [act[:aid], act[:id], act[:account], act[:scope], '', act[:amount], act[:reason], 'UNMATCHED']
    end
  end
end
File.write('/app/out/seat_credit_summary.txt', "matched_count=#{mc}\nmatched_amount=#{ma}\nunmatched_count=#{uc}\nunmatched_amount=#{ua}\n")
RUBY
/app/scripts/run_batch.sh
