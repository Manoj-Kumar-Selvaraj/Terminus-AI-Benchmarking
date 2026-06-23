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
def time_ok?(src, act)
  digits?(src[:ts]) && digits?(act[:ts]) && act[:ts] >= src[:ts]
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

FileUtils.mkdir_p('/app/out')
mc = uc = ma = ua = 0
CSV.open('/app/out/seat_credit_report.csv', 'w') do |csv|
  csv << ['action_id', 'event_id', 'account_id', 'subscription_id', 'kind', 'amount', 'reason', 'status']
  actions.each do |act|
    best = sources.find do |src|
      src[:id] == act[:id] && src[:amount].to_i == act[:amount].to_i && !src[:used] &&
        src[:account] == act[:account] && src[:scope] == act[:scope] && src[:loc] == act[:loc] &&
        kind_ok?(src[:kind]) && kind_ok?(act[:kind]) && src[:kind] == act[:kind] && status_ok?(src[:status]) &&
        reason_ok?(act[:reason]) && time_ok?(src, act)
    end
    amt = act[:amount].to_i
    if best
      best[:used] = true
      mc += 1
      ma += amt
      csv << [act[:aid], act[:id], act[:account], act[:scope], best[:kind], act[:amount], act[:reason], 'MATCHED']
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
