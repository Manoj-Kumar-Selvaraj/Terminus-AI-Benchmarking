#!/bin/bash
set -euo pipefail
cat > /app/app/reconcile.rb <<'RUBY'
require 'csv'
require 'fileutils'

def canon(v)
  value = v.to_s.strip.upcase
  return 'LOAD' if value == 'LD' || value == 'LOAD'
  return 'SOLAR' if value == 'QR' || value == 'SOLAR'
  return 'BATTERY' if value == 'CC' || value == 'BATTERY'
  return 'ANY' if value == 'ANY'
  value
end

def digits14?(v)
  v.to_s.match?(/\A\d{14}\z/)
end

def digits?(v)
  v.to_s.match?(/\A\d+\z/)
end

def resource_type_ok?(v)
  ['LOAD', 'SOLAR', 'BATTERY'].include?(v)
end

def reason_ok?(v)
  ['CURTAIL', 'BONUS', 'CORRECT'].include?(v.to_s.strip.upcase)
end

def window_ok?(src, act, windows)
  return false unless digits14?(src[:ts]) && digits14?(act[:ts])
  windows.any? do |w|
    w[:scope] == src[:scope] &&
      w[:state] == 'OPEN' &&
      digits14?(w[:open]) &&
      digits14?(w[:close]) &&
      src[:ts] >= w[:open] &&
      src[:ts] <= w[:close] &&
      act[:ts] >= src[:ts] &&
      act[:ts] <= w[:close]
  end
end

def read_policy(path)
  policy = {}
  CSV.read(path, headers: true).each do |r|
    station = r['station_id'].to_s.strip
    resource_type = canon(r['resource_type'])
    enabled = r['enabled'].to_s.strip.upcase
    priority = r['priority'].to_s.strip
    cap = r['max_station_amount'].to_s.strip
    next unless station != '' && resource_type_ok?(resource_type)
    next unless enabled == 'TRUE' && digits?(priority) && digits?(cap)
    policy[[station, resource_type]] = { priority: priority.to_i, cap: cap.to_i }
  end
  policy
end

def read_overrides(path)
  overrides = Hash.new { |h, k| h[k] = [] }
  return overrides unless File.exist?(path)
  CSV.read(path, headers: true).each_with_index do |r, i|
    settlement_id = r['settlement_id'].to_s.strip
    next if settlement_id == ''
    overrides[settlement_id] << {
      mode: r['mode'].to_s.strip.upcase,
      resource_type: canon(r['resource_type']),
      expires: r['expires_ts'].to_s.strip,
      row: i
    }
  end
  overrides
end

def override_for(act, overrides)
  valid = overrides[act[:aid]].select { |o| digits14?(o[:expires]) && o[:expires] >= act[:ts] }
  return { deny: true } if valid.any? { |o| o[:mode] == 'DENY' }
  forced = valid.select { |o| o[:mode] == 'FORCE_RESOURCE' && resource_type_ok?(o[:resource_type]) }
                .sort_by { |o| [-o[:expires].to_i, o[:row]] }
                .first
  forced ? { deny: false, resource_type: forced[:resource_type] } : { deny: false }
end

sources = CSV.read('/app/data/events.csv', headers: true).map.with_index do |r, i|
  {
    id: r['parcel_id'].to_s.strip,
    party: r['meter_id'].to_s.strip,
    scope: r['station_id'].to_s.strip,
    resource_type: canon(r['resource_type']),
    amount: r['amount'].to_s.strip,
    ts: r['event_ts'].to_s.strip,
    status: r['status'].to_s.strip.upcase,
    loc: r['feeder'].to_s.strip,
    row: i,
    used: false
  }
end

actions = CSV.read('/app/data/settlements.csv', headers: true).map do |r|
  {
    aid: r['settlement_id'].to_s.strip,
    id: r['parcel_id'].to_s.strip,
    party: r['meter_id'].to_s.strip,
    scope: r['station_id'].to_s.strip,
    resource_type: canon(r['resource_type']),
    amount: r['amount'].to_s.strip,
    ts: r['settle_ts'].to_s.strip,
    reason: r['reason'].to_s.strip.upcase,
    loc: r['feeder'].to_s.strip
  }
end

windows = CSV.read('/app/config/windows.csv', headers: true).map do |r|
  {
    scope: r['station_id'].to_s.strip,
    open: r['open_ts'].to_s.strip,
    close: r['close_ts'].to_s.strip,
    state: r['state'].to_s.strip.upcase
  }
end

policy = read_policy('/app/config/resource_policy.csv')
overrides = read_overrides('/app/config/settlement_overrides.csv')
matched_by_station_resource = Hash.new(0)
consumption = []

FileUtils.mkdir_p('/app/out')
matched_count = unmatched_count = matched_amount = unmatched_amount = 0

CSV.open('/app/out/cod_demand_response_report.csv', 'w') do |csv|
  csv << ['settlement_id', 'parcel_id', 'meter_id', 'station_id', 'resource_type', 'amount', 'reason', 'status']
  actions.each do |act|
    amount = act[:amount].to_i
    override = override_for(act, overrides)

    if override[:deny]
      unmatched_count += 1
      unmatched_amount += amount
      csv << [act[:aid], act[:id], act[:party], act[:scope], '', act[:amount], act[:reason], 'UNMATCHED']
      next
    end

    effective_resource_type = override[:resource_type] || act[:resource_type]
    candidates = []
    sources.each_with_index do |src, i|
      next if src[:used]
      next unless src[:id] == act[:id] &&
                  src[:amount] == act[:amount] &&
                  src[:party] == act[:party] &&
                  src[:scope] == act[:scope] &&
                  src[:loc] == act[:loc] &&
                  src[:status] == 'CONFIRMED' &&
                  resource_type_ok?(src[:resource_type]) &&
                  reason_ok?(act[:reason]) &&
                  window_ok?(src, act, windows)

      if effective_resource_type == 'ANY'
      elsif src[:resource_type] != effective_resource_type
        next
      end

      rule = policy[[src[:scope], src[:resource_type]]]
      next unless rule
      bucket = [src[:scope], src[:resource_type]]
      next if matched_by_station_resource[bucket] + amount > rule[:cap]
      candidates << [i, rule]
    end

    if effective_resource_type == 'ANY'
      candidates.sort_by! { |i, rule| [-sources[i][:ts].to_i, rule[:priority], sources[i][:row]] }
    else
      candidates.sort_by! { |i, _rule| [-sources[i][:ts].to_i, sources[i][:row]] }
    end
    best_pair = candidates.first

    if best_pair
      best = best_pair[0]
      sources[best][:used] = true
      consumption << [act[:aid], sources[best][:row]]
      matched_by_station_resource[[sources[best][:scope], sources[best][:resource_type]]] += amount
      matched_count += 1
      matched_amount += amount
      csv << [act[:aid], act[:id], act[:party], act[:scope], sources[best][:resource_type], act[:amount], act[:reason], 'MATCHED']
    else
      unmatched_count += 1
      unmatched_amount += amount
      csv << [act[:aid], act[:id], act[:party], act[:scope], '', act[:amount], act[:reason], 'UNMATCHED']
    end
  end
end

CSV.open('/app/out/event_consumption.csv', 'w') do |csv|
  csv << ['settlement_id', 'event_row']
  consumption.each { |row| csv << row }
end

File.write('/app/out/cod_demand_response_summary.txt', "matched_count=#{matched_count}
matched_amount=#{matched_amount}
unmatched_count=#{unmatched_count}
unmatched_amount=#{unmatched_amount}
")
RUBY
/app/scripts/run_batch.sh
