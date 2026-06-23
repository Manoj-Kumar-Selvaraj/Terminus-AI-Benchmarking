require 'csv'
require 'fileutils'

CANONICAL_SKUS = ['CPU', 'GPU', 'MEM'].freeze
ENABLED_STATES = ['TRUE', 'YES', 'Y', '1', 'ENABLED'].freeze

def clean(v)
  v.to_s.strip
end

def canon(v)
  value = clean(v).upcase
  return 'CPU' if value == 'C' || value == 'CPU'
  return 'GPU' if value == 'GPUF' || value == 'GPU'
  return 'MEM' if value == 'MEMORY' || value == 'MEM'
  value
end

def digits?(v)
  clean(v).match?(/\A\d{14}\z/)
end

def int_string?(v)
  clean(v).match?(/\A\d+\z/)
end

def sku_type_ok?(v)
  CANONICAL_SKUS.include?(v)
end

def reason_ok?(v)
  ['BURST', 'RECLAIM', 'CORRECT'].include?(clean(v).upcase)
end

def window_ok?(src, act, windows)
  return false unless digits?(src[:ts]) && digits?(act[:ts])

  windows.any? do |w|
    w[:scope] == src[:scope] &&
      w[:state].upcase == 'OPEN' &&
      digits?(w[:open]) &&
      digits?(w[:close]) &&
      src[:ts] >= w[:open] &&
      src[:ts] <= w[:close] &&
      act[:ts] >= src[:ts] &&
      act[:ts] <= w[:close]
  end
end

def policy_priority(src, policies)
  exact = policies.select { |p| p[:region] == src[:loc].upcase && p[:sku_type] == src[:sku_type] }
  candidates = exact.empty? ? policies.select { |p| p[:region] == '*' && p[:sku_type] == src[:sku_type] } : exact
  eligible = candidates.select do |p|
    p[:enabled] &&
      int_string?(p[:min]) &&
      int_string?(p[:max]) &&
      int_string?(p[:priority]) &&
      src[:amount].to_i >= p[:min].to_i &&
      src[:amount].to_i <= p[:max].to_i
  end
  return nil if eligible.empty?

  eligible.map { |p| p[:priority].to_i }.max
end

sources = CSV.read('/app/data/seat_events.csv', headers: true).map.with_index do |r, i|
  {
    id: clean(r['event_id']),
    party: clean(r['account_id']),
    scope: clean(r['reservation_id']),
    sku_type: canon(r['sku_type']),
    amount: clean(r['amount']),
    ts: clean(r['reserve_ts']),
    status: clean(r['status']).upcase,
    loc: clean(r['region']),
    row: i,
    used: false
  }
end

actions = CSV.read('/app/data/credits.csv', headers: true).map do |r|
  {
    aid: clean(r['credit_id']),
    id: clean(r['event_id']),
    party: clean(r['account_id']),
    scope: clean(r['reservation_id']),
    sku_type: canon(r['sku_type']),
    amount: clean(r['amount']),
    ts: clean(r['credit_ts']),
    reason: clean(r['reason']).upcase,
    loc: clean(r['region'])
  }
end

windows = CSV.read('/app/config/windows.csv', headers: true).map do |r|
  { scope: clean(r['reservation_id']), open: clean(r['open_ts']), close: clean(r['close_ts']), state: clean(r['state']) }
end

policies = CSV.read('/app/config/sku_policy.csv', headers: true).map do |r|
  {
    region: clean(r['region']).upcase,
    sku_type: canon(r['sku_type']),
    enabled: ENABLED_STATES.include?(clean(r['enabled']).upcase),
    min: clean(r['min_amount']),
    max: clean(r['max_amount']),
    priority: clean(r['priority'])
  }
end

FileUtils.mkdir_p('/app/out')
matched_count = 0
unmatched_count = 0
matched_amount = 0
unmatched_amount = 0

CSV.open('/app/out/seat_credit_report.csv', 'w') do |csv|
  csv << ['credit_id', 'event_id', 'account_id', 'reservation_id', 'sku_type', 'amount', 'reason', 'status']
  actions.each do |act|
    candidates = []
    sources.each_with_index do |src, i|
      priority = policy_priority(src, policies)
      sku_matches = act[:sku_type] == 'ANY' || src[:sku_type] == act[:sku_type]
      next unless src[:id] == act[:id] &&
                  src[:party] == act[:party] &&
                  src[:scope] == act[:scope] &&
                  src[:loc] == act[:loc] &&
                  int_string?(src[:amount]) &&
                  int_string?(act[:amount]) &&
                  src[:amount].to_i == act[:amount].to_i &&
                  !src[:used] &&
                  sku_type_ok?(src[:sku_type]) &&
                  sku_matches &&
                  !priority.nil? &&
                  src[:status] == 'ALLOCATED' &&
                  reason_ok?(act[:reason]) &&
                  window_ok?(src, act, windows)

      candidates << [i, priority]
    end

    candidates.sort_by! { |i, priority| [-sources[i][:ts].to_i, -priority, sources[i][:row]] }
    best = candidates.first&.first
    amount = act[:amount].to_i
    if best
      sources[best][:used] = true
      matched_count += 1
      matched_amount += amount
      csv << [act[:aid], act[:id], act[:party], act[:scope], sources[best][:sku_type], act[:amount], act[:reason], 'MATCHED']
    else
      unmatched_count += 1
      unmatched_amount += amount
      csv << [act[:aid], act[:id], act[:party], act[:scope], '', act[:amount], act[:reason], 'UNMATCHED']
    end
  end
end

File.write('/app/out/seat_credit_summary.txt', "matched_count=#{matched_count}
matched_amount=#{matched_amount}
unmatched_count=#{unmatched_count}
unmatched_amount=#{unmatched_amount}
")
