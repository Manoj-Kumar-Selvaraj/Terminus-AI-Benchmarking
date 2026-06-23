#!/bin/bash
set -euo pipefail
cat > /app/app/reconcile.rb <<'RUBY'
require 'csv'
require 'fileutils'
def canon(v)
  v = v.to_s.strip.upcase
  return "ENGINE" if v == "PRIMARY" || v == "ENGINE"
  return "BRAKE" if v == "BRAKEIAL" || v == "BRAKE"
  return "TIRE" if v == "TIREORATORY" || v == "TIRE"
  v
end
def digits?(v) = v.to_s.match?(/\A\d{14}\z/)
def repair_type_ok?(v) = ['ENGINE', 'BRAKE', 'TIRE'].include?(v)
def reason_ok?(v) = ["PARTS", "TIREOR", "TOW"].include?(v)
def window_ok?(src, act, windows)
  return false unless digits?(src[:ts]) && digits?(act[:ts])
  windows.any? { |w| w[:scope] == src[:scope] && w[:state] == 'OPEN' && digits?(w[:open]) && digits?(w[:close]) && src[:ts] >= w[:open] && src[:ts] <= w[:close] && act[:ts] >= src[:ts] && act[:ts] <= w[:close] }
end
sources = CSV.read('/app/data/appointments.csv', headers: true).map.with_index { |r,i| {id:r['repair_id'].strip, party:r['member_id'].strip, scope:r['site_id'].strip, repair_type:canon(r['repair_type']), amount:r['amount'].strip, ts:r['repair_ts'].strip, status:r['status'].strip, loc:r['bay'].strip, row:i, used:false} }
actions = CSV.read('/app/data/warranty_claims.csv', headers: true).map { |r| {aid:r['claim_id'].strip, id:r['repair_id'].strip, party:r['member_id'].strip, scope:r['site_id'].strip, repair_type:canon(r['repair_type']), amount:r['amount'].strip, ts:r['claim_ts'].strip, reason:r['reason'].strip, loc:r['bay'].strip} }
windows = CSV.read('/app/config/windows.csv', headers: true).map { |r| {scope:r['site_id'].strip, open:r['open_ts'].strip, close:r['close_ts'].strip, state:r['state'].strip} }
FileUtils.mkdir_p('/app/out')
mc=uc=ma=ua=0
CSV.open('/app/out/claim_route_report.csv', 'w') do |csv|
  csv << ['claim_id','repair_id','member_id','site_id','repair_type','amount','reason','status']
  actions.each do |act|
    candidates = []
    sources.each_with_index do |src,i|
      candidates << i if (src[:id] == act[:id]) && src[:amount] == act[:amount] && !src[:used] && src[:party] == act[:party] && src[:scope] == act[:scope] && src[:loc] == act[:loc] && repair_type_ok?(src[:repair_type]) && src[:status] == "CLOSED" && src[:repair_type] == act[:repair_type] && reason_ok?(act[:reason]) && window_ok?(src, act, windows)
    end
    candidates.sort_by! { |i| [-sources[i][:ts].to_i, sources[i][:row]] }
    best = candidates.first
    amt = act[:amount].to_i
    if best
      sources[best][:used] = true
      mc += 1; ma += amt
      csv << [act[:aid], act[:id], act[:party], act[:scope], sources[best][:repair_type], act[:amount], act[:reason], 'MATCHED']
    else
      uc += 1; ua += amt
      csv << [act[:aid], act[:id], act[:party], act[:scope], '', act[:amount], act[:reason], 'UNMATCHED']
    end
  end
end
File.write('/app/out/claim_route_summary.txt', "matched_count=#{mc}
matched_amount=#{ma}
unmatched_count=#{uc}
unmatched_amount=#{ua}
")
RUBY
/app/scripts/run_batch.sh
