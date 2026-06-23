#!/bin/bash
set -euo pipefail
cat > /app/app/reconcile.rb <<'RUBY'
require 'csv'
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

def policy_enabled?(kind, policy)
  row = policy[kind]
  row && row[:enabled]
end

sources = CSV.read('/app/data/seat_events.csv', headers: true).map.with_index do |r, i|
  { id: r['event_id'].strip, account: r['account_id'].strip, scope: r['subscription_id'].strip,
    kind: canon(r['kind']), amount: r['amount'].strip, ts: r['source_ts'].strip,
    status: r['status'].strip, loc: r['location'].strip, row: i, used: false }
end
actions = CSV.read('/app/data/credits.csv', headers: true).map do |r|
  { aid: r['action_id'].strip, id: r['event_id'].strip, account: r['account_id'].strip,
    scope: r['subscription_id'].strip, kind: canon(r['kind']), amount: r['amount'].strip,
    ts: r['action_ts'].strip, reason: r['reason'].strip, loc: r['location'].strip }
end
windows = CSV.read('/app/config/windows.csv', headers: true).map do |r|
  { scope: r['subscription_id'].strip, open: r['open_ts'].strip, close: r['close_ts'].strip, state: r['state'].strip.upcase }
end
policy = load_policy

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
        status_ok?(src[:status]) && reason_ok?(act[:reason]) && window_ok?(src, act, windows)
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
