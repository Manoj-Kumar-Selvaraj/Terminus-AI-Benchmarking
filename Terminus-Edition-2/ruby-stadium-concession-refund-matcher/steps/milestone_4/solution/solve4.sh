#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cat > /app/app/reconcile.rb <<'RUBY'
require 'csv'
require 'fileutils'

def canon(v)
  v = v.to_s.strip.upcase
  return 'FOOD' if v == 'FD' || v == 'FOOD'
  return 'DRINK' if v == 'DR' || v == 'DRINK'
  return 'MERCH' if v == 'MR' || v == 'MERCH'

  v
end

def digits?(v)
  v.to_s.match?(/\A\d{14}\z/)
end

def item_type_ok?(v)
  %w[FOOD DRINK MERCH].include?(v)
end

def load_reason_policy
  path = '/app/config/reasons.csv'
  return {} unless File.exist?(path)

  CSV.read(path, headers: true).each_with_object({}) do |row, memo|
    code = row['reason'].to_s.strip.upcase
    next if code.empty?

    memo[code] = true if row['eligible'].to_s.strip.upcase == 'Y'
  end
end

def reason_ok?(value, policy)
  policy.fetch(value.to_s.strip.upcase, false)
end

def window_ok?(src, act, windows)
  return false unless digits?(src[:ts]) && digits?(act[:ts])

  windows.any? do |w|
    w[:scope] == src[:scope] &&
      w[:state].to_s.strip.upcase == 'OPEN' &&
      digits?(w[:open]) &&
      digits?(w[:close]) &&
      src[:ts] >= w[:open] &&
      src[:ts] <= w[:close] &&
      act[:ts] >= src[:ts] &&
      act[:ts] <= w[:close]
  end
end

reason_policy = load_reason_policy
sources = CSV.read('/app/data/folios.csv', headers: true).map.with_index do |r, i|
  {
    id: r['folio_id'].strip,
    party: r['fan_id'].strip,
    scope: r['property_id'].strip,
    item_type: canon(r['item_type']),
    amount: r['amount'].strip,
    ts: r['sale_ts'].strip,
    status: r['status'].strip.upcase,
    loc: r['stand'].strip,
    row: i,
    used: false
  }
end
actions = CSV.read('/app/data/refunds.csv', headers: true).map do |r|
  {
    aid: r['refund_id'].strip,
    id: r['folio_id'].strip,
    party: r['fan_id'].strip,
    scope: r['property_id'].strip,
    item_type: canon(r['item_type']),
    amount: r['amount'].strip,
    ts: r['refund_ts'].strip,
    reason: r['reason'].strip,
    loc: r['stand'].strip
  }
end
windows = CSV.read('/app/config/windows.csv', headers: true).map do |r|
  {
    scope: r['property_id'].strip,
    open: r['open_ts'].strip,
    close: r['close_ts'].strip,
    state: r['state'].strip
  }
end

FileUtils.mkdir_p('/app/out')
mc = uc = ma = ua = 0
CSV.open('/app/out/concession_refund_report.csv', 'w') do |csv|
  csv << %w[refund_id folio_id fan_id property_id item_type amount reason status]
  actions.each do |act|
    candidates = []
    sources.each_with_index do |src, i|
      next if src[:used]
      next unless src[:id] == act[:id]
      next unless src[:party] == act[:party]
      next unless src[:scope] == act[:scope]
      next unless src[:loc] == act[:loc]
      next unless src[:amount] == act[:amount]
      next unless src[:status] == 'SOLD'
      next unless item_type_ok?(src[:item_type])
      next unless src[:item_type] == act[:item_type]
      next unless reason_ok?(act[:reason], reason_policy)
      next unless window_ok?(src, act, windows)

      candidates << i
    end
    candidates.sort_by! { |i| [-sources[i][:ts].to_i, sources[i][:row]] }
    best = candidates.first
    amt = act[:amount].to_i
    if best
      sources[best][:used] = true
      mc += 1
      ma += amt
      csv << [act[:aid], act[:id], act[:party], act[:scope], sources[best][:item_type], act[:amount], act[:reason], 'MATCHED']
    else
      uc += 1
      ua += amt
      csv << [act[:aid], act[:id], act[:party], act[:scope], '', act[:amount], act[:reason], 'UNMATCHED']
    end
  end
end
File.write(
  '/app/out/concession_refund_summary.txt',
  "matched_count=#{mc}\nmatched_amount=#{ma}\nunmatched_count=#{uc}\nunmatched_amount=#{ua}\n"
)
RUBY

/app/scripts/run_batch.sh
test -s /app/out/concession_refund_report.csv
test -s /app/out/concession_refund_summary.txt
