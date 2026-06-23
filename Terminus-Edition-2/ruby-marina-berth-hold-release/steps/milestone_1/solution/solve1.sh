#!/bin/bash
set -euo pipefail
cat > /app/app/reconcile.rb <<'RUBY'
require 'csv'
require 'fileutils'

def canon(v)
  v.to_s.strip.upcase
end

def digits?(v)
  v.to_s.match?(/\A\d{14}\z/)
end

def rate_type_ok?(v)
  ['SLIP', 'DRY'].include?(v)
end

def reason_ok?(v)
  ['DEPART', 'TRANSFER', 'OVERRIDE'].include?(v)
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

def time_ok?(src, act, windows)
  return false unless digits?(src[:ts]) && digits?(act[:ts])
  act[:ts] >= src[:ts]
end

sources = CSV.read('/app/data/berth_holds.csv', headers: true).map.with_index do |r, i|
  {
    id: r['hold_id'].strip,
    party: r['vessel_id'].strip,
    scope: r['dock_id'].strip,
    rate_type: canon(r['berth_type']),
    amount: r['amount'].strip,
    ts: r['hold_ts'].strip,
    status: r['status'].strip.upcase,
    loc: r['slip'].strip,
    row: i,
    used: false
  }
end

actions = CSV.read('/app/data/berth_releases.csv', headers: true).map do |r|
  {
    aid: r['release_id'].strip,
    id: r['hold_id'].strip,
    party: r['vessel_id'].strip,
    scope: r['dock_id'].strip,
    rate_type: canon(r['berth_type']),
    amount: r['amount'].strip,
    ts: r['release_ts'].strip,
    reason: r['reason'].strip.upcase,
    loc: r['slip'].strip
  }
end

windows = CSV.read('/app/config/windows.csv', headers: true).map do |r|
  {
    scope: r['dock_id'].strip,
    open: r['open_ts'].strip,
    close: r['close_ts'].strip,
    state: r['state'].strip.upcase
  }
end

FileUtils.mkdir_p('/app/out')
mc = uc = ma = ua = 0

CSV.open('/app/out/berth_release_report.csv', 'w') do |csv|
  csv << %w[release_id hold_id vessel_id dock_id berth_type amount reason status]
  actions.each do |act|
    candidates = []
    sources.each_with_index do |src, i|
      next if src[:used]
      next unless src[:id] == act[:id]
      next unless src[:party] == act[:party]
      next unless src[:scope] == act[:scope]
      next unless src[:loc] == act[:loc]
      next unless src[:amount] == act[:amount]
      next unless src[:status] == 'MOORED'
      next unless rate_type_ok?(src[:rate_type])
      next unless src[:rate_type] == act[:rate_type]
      next unless reason_ok?(act[:reason])
      next unless time_ok?(src, act, windows)
      candidates << i
    end
    candidates.sort_by! { |i| sources[i][:row] }
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

File.write('/app/out/berth_release_summary.txt', <<~SUMMARY)
  matched_count=#{mc}
  matched_amount=#{ma}
  unmatched_count=#{uc}
  unmatched_amount=#{ua}
SUMMARY

RUBY
