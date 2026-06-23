#!/bin/bash
set -euo pipefail
cat > /app/app/reconcile.rb <<'RUBY'
require 'csv'
require 'fileutils'

def canon(v)
  v = v.to_s.strip.upcase
  return 'HOURLY' if v == 'HR' || v == 'HOURLY'
  return 'DAILY' if v == 'QR' || v == 'DAILY'
  return 'EVENT' if v == 'CC' || v == 'EVENT'
  v
end

def digits?(v)
  v.to_s.match?(/\A\d{14}\z/)
end

def rate_type_ok?(v)
  ['HOURLY', 'DAILY', 'EVENT'].include?(v)
end

def reason_ok?(v)
  ['REFUND', 'SHORT', 'WAIVE'].include?(v)
end

def window_ok?(src, act, windows)
  return false unless digits?(src[:ts]) && digits?(act[:ts])
  windows.any? do |w|
    w[:scope] == src[:scope] &&
      w[:state] == 'OPEN' &&
      digits?(w[:open]) &&
      digits?(w[:close]) &&
      src[:ts] >= w[:open] &&
      src[:ts] <= w[:close] &&
      act[:ts] >= src[:ts] &&
      act[:ts] <= w[:close]
  end
end

sources = CSV.read('/app/data/sessions.csv', headers: true).map.with_index do |r, i|
  {
    id: r['parcel_id'].strip,
    party: r['plate_id'].strip,
    scope: r['station_id'].strip,
    rate_type: canon(r['rate_type']),
    amount: r['amount'].strip,
    ts: r['entry_ts'].strip,
    status: r['status'].strip.upcase,
    loc: r['level'].strip,
    row: i,
    used: false
  }
end

actions = CSV.read('/app/data/adjustments.csv', headers: true).map do |r|
  {
    aid: r['adjustment_id'].strip,
    id: r['parcel_id'].strip,
    party: r['plate_id'].strip,
    scope: r['station_id'].strip,
    rate_type: canon(r['rate_type']),
    amount: r['amount'].strip,
    ts: r['adjust_ts'].strip,
    reason: r['reason'].strip.upcase,
    loc: r['level'].strip
  }
end

windows = CSV.read('/app/config/windows.csv', headers: true).map do |r|
  {
    scope: r['station_id'].strip,
    open: r['open_ts'].strip,
    close: r['close_ts'].strip,
    state: r['state'].strip.upcase
  }
end

FileUtils.mkdir_p('/app/out')
mc = uc = ma = ua = 0

CSV.open('/app/out/cod_parking_adjustment_report.csv', 'w') do |csv|
  csv << %w[adjustment_id parcel_id plate_id station_id rate_type amount reason status]
  actions.each do |act|
    candidates = []
    sources.each_with_index do |src, i|
      next if src[:used]
      next unless src[:id] == act[:id]
      next unless src[:party] == act[:party]
      next unless src[:scope] == act[:scope]
      next unless src[:loc] == act[:loc]
      next unless src[:amount] == act[:amount]
      next unless src[:status] == 'CLOSED'
      next unless rate_type_ok?(src[:rate_type])
      next unless src[:rate_type] == act[:rate_type]
      next unless reason_ok?(act[:reason])
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
      csv << [act[:aid], act[:id], act[:party], act[:scope], sources[best][:rate_type], act[:amount], act[:reason], 'MATCHED']
    else
      uc += 1
      ua += amt
      csv << [act[:aid], act[:id], act[:party], act[:scope], '', act[:amount], act[:reason], 'UNMATCHED']
    end
  end
end

File.write('/app/out/cod_parking_adjustment_summary.txt', <<~SUMMARY)
  matched_count=#{mc}
  matched_amount=#{ma}
  unmatched_count=#{uc}
  unmatched_amount=#{ua}
SUMMARY
RUBY
/app/scripts/run_batch.sh
