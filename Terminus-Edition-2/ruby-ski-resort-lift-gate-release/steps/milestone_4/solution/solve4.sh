#!/bin/bash
set -euo pipefail
cat > /app/app/reconcile.rb <<'RUBY'
require 'csv'
require 'fileutils'

def load_alias_map
  map = {}
  CSV.foreach('/app/config/kind_aliases.csv', headers: true) do |r|
    key = r['alias'].to_s.strip.upcase
    next if key.empty? || map.key?(key)
    map[key] = r['canonical'].to_s.strip.upcase
  end
  map
end

def load_reason_eligible
  eligible = {}
  CSV.foreach('/app/config/reasons.csv', headers: true) do |r|
    reason = r['reason'].to_s.strip.upcase
    eligible[reason] = (r['eligible'].to_s.strip.upcase == 'Y')
  end
  eligible
end

def load_reason_tiers
  tiers = {}
  CSV.foreach('/app/config/reason_tiers.csv', headers: true) do |r|
    reason = r['reason'].to_s.strip.upcase
    tiers[reason] = r['pass_tiers'].to_s.split('|').map { |t| t.strip.upcase }.reject(&:empty?)
  end
  tiers
end

ALIAS_MAP = load_alias_map
REASON_ELIGIBLE = load_reason_eligible
REASON_TIERS = load_reason_tiers

def canon(v)
  normalized = v.to_s.strip.upcase
  ALIAS_MAP.fetch(normalized, normalized)
end

def digits?(v)
  v.to_s.match?(/\A\d{14}\z/)
end

def rate_type_ok?(v)
  ['DAY', 'SEASON', 'VIP'].include?(v)
end

def reason_eligible?(reason)
  REASON_ELIGIBLE.fetch(reason, false)
end

def tier_reason_ok?(reason, tier)
  allowed = REASON_TIERS[reason]
  return false unless allowed
  allowed.include?(tier)
end

def pick_window(src, act, windows)
  eligible = windows.select do |w|
    w[:scope] == src[:scope] &&
      w[:state] == 'OPEN' &&
      digits?(w[:open]) &&
      digits?(w[:close]) &&
      digits?(src[:ts]) &&
      digits?(act[:ts]) &&
      src[:ts] >= w[:open] &&
      src[:ts] <= w[:close] &&
      act[:ts] >= src[:ts] &&
      act[:ts] <= w[:close]
  end
  return nil if eligible.empty?
  eligible.min_by { |w| [-w[:open], w[:close]] }
end

def identity_match?(src, act)
  src[:id] == act[:id] &&
    src[:party] == act[:party] &&
    src[:scope] == act[:scope] &&
    src[:loc] == act[:loc] &&
    src[:amount] == act[:amount]
end

def reject_code(act, sources, windows)
  return 'REASON_INELIGIBLE' unless reason_eligible?(act[:reason])

  identity = []
  sources.each_with_index do |src, i|
    next if src[:used]
    next unless identity_match?(src, act)
    next unless src[:status] == 'SCANNED'
    next unless rate_type_ok?(src[:rate_type])
    next unless src[:rate_type] == act[:rate_type]
    identity << [i, src]
  end
  return 'NO_CANDIDATE' if identity.empty?

  tier_ok = identity.select { |_, src| tier_reason_ok?(act[:reason], src[:rate_type]) }
  return 'TIER_REASON' if tier_ok.empty?

  window_ok = tier_ok.select { |_, src| !pick_window(src, act, windows).nil? }
  return 'WINDOW' if window_ok.empty?

  'NO_CANDIDATE'
end

sources = CSV.read('/app/data/lift_sessions.csv', headers: true).map.with_index do |r, i|
  {
    id: r['pass_id'].strip,
    party: r['skier_id'].strip,
    scope: r['lift_id'].strip,
    rate_type: canon(r['pass_tier']),
    amount: r['amount'].strip,
    ts: r['scan_ts'].strip,
    status: r['status'].strip.upcase,
    loc: r['slope'].strip,
    row: i,
    used: false
  }
end

actions = CSV.read('/app/data/gate_releases.csv', headers: true).map do |r|
  {
    aid: r['release_id'].strip,
    id: r['pass_id'].strip,
    party: r['skier_id'].strip,
    scope: r['lift_id'].strip,
    rate_type: canon(r['pass_tier']),
    amount: r['amount'].strip,
    ts: r['release_ts'].strip,
    reason: r['reason'].strip.upcase,
    loc: r['slope'].strip
  }
end

windows = CSV.read('/app/config/windows.csv', headers: true).map do |r|
  {
    scope: r['lift_id'].strip,
    open: r['open_ts'].strip,
    close: r['close_ts'].strip,
    state: r['state'].strip.upcase
  }
end

FileUtils.mkdir_p('/app/out')
mc = uc = ma = ua = 0
audit_rows = []

CSV.open('/app/out/lift_gate_release_report.csv', 'w') do |csv|
  csv << %w[release_id pass_id skier_id lift_id pass_tier amount reason status]
  actions.each do |act|
    candidates = []
    sources.each_with_index do |src, i|
      next if src[:used]
      next unless identity_match?(src, act)
      next unless src[:status] == 'SCANNED'
      next unless rate_type_ok?(src[:rate_type])
      next unless src[:rate_type] == act[:rate_type]
      next unless reason_eligible?(act[:reason])
      next unless tier_reason_ok?(act[:reason], src[:rate_type])
      next if pick_window(src, act, windows).nil?
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
      audit_rows << [act[:aid], reject_code(act, sources, windows)]
    end
  end
end

File.write('/app/out/lift_gate_release_summary.txt', <<~SUMMARY)
matched_count=#{mc}
matched_amount=#{ma}
unmatched_count=#{uc}
unmatched_amount=#{ua}
SUMMARY

CSV.open('/app/out/lift_gate_release_audit.csv', 'w') do |csv|
  csv << %w[release_id reject_code]
  audit_rows.each { |row| csv << row }
end
RUBY
