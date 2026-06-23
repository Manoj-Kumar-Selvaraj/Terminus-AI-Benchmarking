#!/bin/bash
set -euo pipefail
cat > /app/app/reconcile.rb <<'RUBY'
require 'csv'
require 'fileutils'
def canon(v)
  v = v.to_s.strip.upcase
  return "LOAD" if v == "LD" || v == "LOAD"
  return "SOLAR" if v == "QR" || v == "SOLAR"
  return "BATTERY" if v == "CC" || v == "BATTERY"
  v
end
def digits?(v) = v.to_s.match?(/\A\d{14}\z/)
def resource_type_ok?(v) = ['LOAD', 'SOLAR', 'BATTERY'].include?(v)
def reason_ok?(v) = ["CURTAIL", "BONUS", "CORRECT"].include?(v)
# Milestone 2: timestamp ordering only; window eligibility is milestone 3.
def ts_ok?(src, act)
  return false unless digits?(src[:ts]) && digits?(act[:ts])
  act[:ts] >= src[:ts]
end
sources = CSV.read('/app/data/events.csv', headers: true).map.with_index { |r,i| {id:r['parcel_id'].strip, party:r['meter_id'].strip, scope:r['station_id'].strip, resource_type:canon(r['resource_type']), amount:r['amount'].strip, ts:r['event_ts'].strip, status:r['status'].strip, loc:r['feeder'].strip, row:i, used:false} }
actions = CSV.read('/app/data/settlements.csv', headers: true).map { |r| {aid:r['settlement_id'].strip, id:r['parcel_id'].strip, party:r['meter_id'].strip, scope:r['station_id'].strip, resource_type:canon(r['resource_type']), amount:r['amount'].strip, ts:r['settle_ts'].strip, reason:r['reason'].strip, loc:r['feeder'].strip} }
FileUtils.mkdir_p('/app/out')
mc=uc=ma=ua=0
CSV.open('/app/out/cod_demand_response_report.csv', 'w') do |csv|
  csv << ['settlement_id','parcel_id','meter_id','station_id','resource_type','amount','reason','status']
  actions.each do |act|
    candidates = []
    sources.each_with_index do |src,i|
      candidates << i if (src[:id] == act[:id]) && src[:amount] == act[:amount] && !src[:used] && src[:party] == act[:party] && src[:scope] == act[:scope] && src[:loc] == act[:loc] && resource_type_ok?(src[:resource_type]) && src[:status] == "CONFIRMED" && src[:resource_type] == act[:resource_type] && reason_ok?(act[:reason]) && ts_ok?(src, act)
    end
    candidates.sort_by! { |i| [-sources[i][:ts].to_i, sources[i][:row]] }
    best = candidates.first
    amt = act[:amount].to_i
    if best
      sources[best][:used] = true
      mc += 1; ma += amt
      csv << [act[:aid], act[:id], act[:party], act[:scope], sources[best][:resource_type], act[:amount], act[:reason], 'MATCHED']
    else
      uc += 1; ua += amt
      csv << [act[:aid], act[:id], act[:party], act[:scope], '', act[:amount], act[:reason], 'UNMATCHED']
    end
  end
end
File.write('/app/out/cod_demand_response_summary.txt', "matched_count=#{mc}
matched_amount=#{ma}
unmatched_count=#{uc}
unmatched_amount=#{ua}
")
RUBY
/app/scripts/run_batch.sh
