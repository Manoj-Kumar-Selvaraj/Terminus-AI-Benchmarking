#!/bin/bash
set -euo pipefail
cat > /app/app/reconcile.rb <<'RUBY'
require 'csv'
require 'fileutils'
def canon(v)
  v = v.to_s.strip.upcase
  return "CARD" if v == "CC" || v == "CARD"
  return "CASH" if v == "CSH" || v == "CASH"
  return "POINTS" if v == "PTS" || v == "POINTS"
  v
end
def digits?(v) = v.to_s.match?(/\A\d{14}\z/)
def kind_ok?(v) = ['CARD', 'CASH', 'POINTS'].include?(v)
def reason_ok?(v) = ["DISPUTE", "DUPLICATE", "NOAUTH"].include?(v)
def window_ok?(src, act, windows)
  return false unless digits?(src[:ts]) && digits?(act[:ts])
  windows.any? { |w| w[:scope] == src[:scope] && w[:state] == 'OPEN' && digits?(w[:open]) && digits?(w[:close]) && src[:ts] >= w[:open] && src[:ts] <= w[:close] && act[:ts] >= src[:ts] && act[:ts] <= w[:close] }
end
sources = CSV.read('/app/data/folios.csv', headers: true).map.with_index { |r,i| {id:r['folio_id'].strip, party:r['guest_id'].strip, scope:r['property_id'].strip, kind:canon(r['kind']), amount:r['amount'].strip, ts:r['source_ts'].strip, status:r['status'].strip, loc:r['location'].strip, row:i, used:false} }
actions = CSV.read('/app/data/chargebacks.csv', headers: true).map { |r| {aid:r['action_id'].strip, id:r['folio_id'].strip, party:r['guest_id'].strip, scope:r['property_id'].strip, kind:canon(r['kind']), amount:r['amount'].strip, ts:r['action_ts'].strip, reason:r['reason'].strip, loc:r['location'].strip} }
windows = CSV.read('/app/config/windows.csv', headers: true).map { |r| {scope:r['property_id'].strip, open:r['open_ts'].strip, close:r['close_ts'].strip, state:r['state'].strip} }
FileUtils.mkdir_p('/app/out')
mc=uc=ma=ua=0
CSV.open('/app/out/chargeback_report.csv', 'w') do |csv|
  csv << ['action_id','folio_id','guest_id','property_id','kind','amount','reason','status']
  actions.each do |act|
    candidates = []
    sources.each_with_index do |src,i|
      candidates << i if (src[:id] == act[:id]) && src[:amount] == act[:amount] && !src[:used] && src[:party] == act[:party] && src[:scope] == act[:scope] && src[:loc] == act[:loc] && kind_ok?(src[:kind]) && src[:status] == "POSTED" && src[:kind] == act[:kind] && reason_ok?(act[:reason]) && window_ok?(src, act, windows)
    end
    candidates.sort_by! { |i| [-sources[i][:ts].to_i, sources[i][:row]] }
    best = candidates.first
    amt = act[:amount].to_i
    if best
      sources[best][:used] = true
      mc += 1; ma += amt
      csv << [act[:aid], act[:id], act[:party], act[:scope], sources[best][:kind], act[:amount], act[:reason], 'MATCHED']
    else
      uc += 1; ua += amt
      csv << [act[:aid], act[:id], act[:party], act[:scope], '', act[:amount], act[:reason], 'UNMATCHED']
    end
  end
end
File.write('/app/out/chargeback_summary.txt', "matched_count=#{mc}
matched_amount=#{ma}
unmatched_count=#{uc}
unmatched_amount=#{ua}
")
RUBY
/app/scripts/run_batch.sh
