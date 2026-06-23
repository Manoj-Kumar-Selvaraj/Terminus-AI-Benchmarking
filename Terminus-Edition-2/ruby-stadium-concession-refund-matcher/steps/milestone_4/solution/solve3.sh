#!/bin/bash
set -euo pipefail
cat > /app/app/reconcile.rb <<'RUBY'
require 'csv'
require 'fileutils'
def canon(v)
  v = v.to_s.strip.upcase
  return "FOOD" if v == "FD" || v == "FOOD"
  return "DRINK" if v == "DR" || v == "DRINK"
  return "MERCH" if v == "MR" || v == "MERCH"
  v
end
def digits?(v) = v.to_s.match?(/\A\d{14}\z/)
def item_type_ok?(v) = ['FOOD', 'DRINK', 'MERCH'].include?(v)
def reason_ok?(v) = %w[SPOIL DUP VOID].include?(v.to_s.strip.upcase)
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
sources = CSV.read('/app/data/folios.csv', headers: true).map.with_index { |r,i| {id:r['folio_id'].strip, party:r['fan_id'].strip, scope:r['property_id'].strip, item_type:canon(r['item_type']), amount:r['amount'].strip, ts:r['sale_ts'].strip, status:r['status'].strip, loc:r['stand'].strip, row:i, used:false} }
actions = CSV.read('/app/data/refunds.csv', headers: true).map { |r| {aid:r['refund_id'].strip, id:r['folio_id'].strip, party:r['fan_id'].strip, scope:r['property_id'].strip, item_type:canon(r['item_type']), amount:r['amount'].strip, ts:r['refund_ts'].strip, reason:r['reason'].strip, loc:r['stand'].strip} }
windows = CSV.read('/app/config/windows.csv', headers: true).map { |r| {scope:r['property_id'].strip, open:r['open_ts'].strip, close:r['close_ts'].strip, state:r['state'].strip} }
FileUtils.mkdir_p('/app/out')
mc=uc=ma=ua=0
CSV.open('/app/out/concession_refund_report.csv', 'w') do |csv|
  csv << ['refund_id','folio_id','fan_id','property_id','item_type','amount','reason','status']
  actions.each do |act|
    candidates = []
    sources.each_with_index do |src,i|
      next if src[:used]
      next unless src[:id] == act[:id]
      next unless src[:party] == act[:party]
      next unless src[:scope] == act[:scope]
      next unless src[:loc] == act[:loc]
      next unless src[:amount] == act[:amount]
      next unless src[:status] == 'SOLD'
      next unless item_type_ok?(src[:item_type])
      next unless src[:item_type] == act[:item_type]
      next unless reason_ok?(act[:reason])
      next unless window_ok?(src, act, windows)
      candidates << i
    end
    candidates.sort_by! { |i| [-sources[i][:ts].to_i, sources[i][:row]] }
    best = candidates.first
    amt = act[:amount].to_i
    if best
      sources[best][:used] = true
      mc += 1; ma += amt
      csv << [act[:aid], act[:id], act[:party], act[:scope], sources[best][:item_type], act[:amount], act[:reason], 'MATCHED']
    else
      uc += 1; ua += amt
      csv << [act[:aid], act[:id], act[:party], act[:scope], '', act[:amount], act[:reason], 'UNMATCHED']
    end
  end
end
File.write('/app/out/concession_refund_summary.txt', "matched_count=#{mc}
matched_amount=#{ma}
unmatched_count=#{uc}
unmatched_amount=#{ua}
")
RUBY
/app/scripts/run_batch.sh
