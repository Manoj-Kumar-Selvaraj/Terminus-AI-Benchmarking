#!/usr/bin/env ruby
require 'csv'
require 'fileutils'
require 'set'

APP = '/app'
OUT = File.join(APP, 'out')
FileUtils.mkdir_p(OUT)

def canon(value)
  value.to_s.strip.upcase
end

def numeric_ts?(value)
  value.to_s.match?(/\A\d{14}\z/)
end

def int_text?(value)
  value.to_s.match?(/\A\d+\z/)
end

def load_csv(path)
  return [] unless File.exist?(path)
  CSV.read(path, headers: true).map { |row| row.to_h }
end

def write_csv(path, header, rows)
  CSV.open(path, 'w') do |csv|
    csv << header
    rows.each { |row| csv << header.map { |key| row[key] } }
  end
end

def parse_windows
  load_csv(File.join(APP, 'config', 'windows.csv')).map do |row|
    { reservation_id: row['reservation_id'].to_s.strip, open_ts: row['open_ts'].to_s.strip, close_ts: row['close_ts'].to_s.strip, state: canon(row['state']) }
  end
end

def window_ok?(source, action, windows)
  return false unless numeric_ts?(source[:reserve_ts]) && numeric_ts?(action[:credit_ts])
  windows.any? do |window|
    window[:reservation_id] == source[:reservation_id] &&
      window[:state] == 'OPEN' &&
      numeric_ts?(window[:open_ts]) && numeric_ts?(window[:close_ts]) &&
      source[:reserve_ts] >= window[:open_ts] && source[:reserve_ts] <= window[:close_ts] &&
      action[:credit_ts] >= source[:reserve_ts] && action[:credit_ts] <= window[:close_ts]
  end
end

def load_aliases(enabled)
  aliases = {}
  return aliases unless enabled
  load_csv(File.join(APP, 'config', 'kind_aliases.csv')).each do |row|
    aliases[canon(row['alias'])] = canon(row['canonical'])
  end
  aliases
end

def normalize_sku(value, aliases)
  raw = canon(value)
  aliases.fetch(raw, raw)
end

def source_rows(aliases)
  load_csv(File.join(APP, 'data', 'seat_events.csv')).map.with_index do |row, idx|
    {
      event_id: row['event_id'].to_s.strip,
      account_id: row['account_id'].to_s.strip,
      reservation_id: row['reservation_id'].to_s.strip,
      sku_type: normalize_sku(row['sku_type'], aliases),
      amount: row['amount'].to_s.strip,
      reserve_ts: row['reserve_ts'].to_s.strip,
      status: row['status'].to_s.strip,
      region: row['region'].to_s.strip,
      row_index: idx,
      used: false
    }
  end
end

def credit_rows(aliases)
  load_csv(File.join(APP, 'data', 'credits.csv')).map do |row|
    {
      credit_id: row['credit_id'].to_s.strip,
      event_id: row['event_id'].to_s.strip,
      account_id: row['account_id'].to_s.strip,
      reservation_id: row['reservation_id'].to_s.strip,
      sku_type: normalize_sku(row['sku_type'], aliases),
      raw_sku_type: canon(row['sku_type']),
      amount: row['amount'].to_s.strip,
      credit_ts: row['credit_ts'].to_s.strip,
      reason: canon(row['reason']),
      region: row['region'].to_s.strip
    }
  end
end

def load_policies(aliases)
  rows = load_csv(File.join(APP, 'config', 'sku_policy.csv'))
  rows.each_with_object([]) do |row, policies|
    next unless int_text?(row['min_amount'].to_s.strip) && int_text?(row['max_amount'].to_s.strip) && int_text?(row['priority'].to_s.strip)
    enabled = %w[TRUE YES Y 1 ENABLED].include?(canon(row['enabled']))
    policies << {
      region: canon(row['region']),
      sku_type: normalize_sku(row['sku_type'], aliases),
      enabled: enabled,
      min_amount: row['min_amount'].to_i,
      max_amount: row['max_amount'].to_i,
      priority: row['priority'].to_i
    }
  end
end

def applicable_policy(source, policies)
  return nil if policies.empty?
  amount = source[:amount].to_i
  exact = policies.select { |p| p[:region] == canon(source[:region]) && p[:sku_type] == source[:sku_type] }
  chosen = exact.empty? ? policies.select { |p| p[:region] == '*' && p[:sku_type] == source[:sku_type] } : exact
  chosen.select { |p| p[:enabled] && amount >= p[:min_amount] && amount <= p[:max_amount] }.max_by { |p| p[:priority] }
end

def eligible_reason?(reason)
  %w[BURST RECLAIM CORRECT].include?(canon(reason))
end

def run_row_reconciliation(alias_enabled:, policy_enabled: false, allow_any: false)
  aliases = load_aliases(alias_enabled)
  sources = source_rows(aliases)
  credits = credit_rows(aliases)
  windows = parse_windows
  policies = policy_enabled ? load_policies(aliases) : []
  eligible_skus = alias_enabled ? %w[CPU GPU MEM] : %w[CPU GPU]
  rows = []
  matched_count = 0
  matched_amount = 0
  unmatched_count = 0
  unmatched_amount = 0
  credits.each do |credit|
    candidates = []
    sources.each_with_index do |source, index|
      next if source[:used]
      next unless source[:event_id] == credit[:event_id]
      next unless source[:account_id] == credit[:account_id]
      next unless source[:reservation_id] == credit[:reservation_id]
      next unless source[:region] == credit[:region]
      next unless source[:amount] == credit[:amount] && int_text?(source[:amount]) && int_text?(credit[:amount])
      next unless source[:status] == 'ALLOCATED'
      next unless eligible_reason?(credit[:reason])
      next unless eligible_skus.include?(source[:sku_type])
      next unless allow_any && credit[:raw_sku_type] == 'ANY' || eligible_skus.include?(credit[:sku_type])
      next unless window_ok?(source, credit, windows)
      policy = nil
      if policy_enabled
        policy = applicable_policy(source, policies)
        next unless policy
        unless credit[:raw_sku_type] == 'ANY'
          next unless credit[:sku_type] == source[:sku_type]
        end
      end
      candidates << [index, policy]
    end
    candidates.sort_by! do |index, policy|
      [-sources[index][:reserve_ts].to_i, -(policy ? policy[:priority] : 0), sources[index][:row_index]]
    end
    if candidates.any?
      index, _policy = candidates.first
      source = sources[index]
      source[:used] = true
      matched_count += 1
      matched_amount += credit[:amount].to_i
      rows << {
        'credit_id' => credit[:credit_id], 'event_id' => credit[:event_id], 'account_id' => credit[:account_id],
        'reservation_id' => credit[:reservation_id], 'sku_type' => source[:sku_type], 'amount' => credit[:amount],
        'reason' => credit[:reason], 'status' => 'MATCHED'
      }.merge('__matched_sku' => source[:sku_type], '__region' => source[:region])
    else
      unmatched_count += 1
      unmatched_amount += credit[:amount].to_i if int_text?(credit[:amount])
      rows << {
        'credit_id' => credit[:credit_id], 'event_id' => credit[:event_id], 'account_id' => credit[:account_id],
        'reservation_id' => credit[:reservation_id], 'sku_type' => '', 'amount' => credit[:amount],
        'reason' => credit[:reason], 'status' => 'UNMATCHED'
      }.merge('__matched_sku' => '', '__region' => credit[:region])
    end
  end
  write_csv(File.join(OUT, 'seat_credit_report.csv'), %w[credit_id event_id account_id reservation_id sku_type amount reason status], rows)
  File.write(File.join(OUT, 'seat_credit_summary.txt'), "matched_count=#{matched_count}\nmatched_amount=#{matched_amount}\nunmatched_count=#{unmatched_count}\nunmatched_amount=#{unmatched_amount}\n")
  [rows, { matched_count: matched_count, matched_amount: matched_amount, unmatched_count: unmatched_count, unmatched_amount: unmatched_amount }]
end


def load_cycles
  load_csv(File.join(APP, 'config', 'reservation_cycles.csv')).map do |row|
    {
      group_id: row['group_id'].to_s.strip,
      reservation_id: row['reservation_id'].to_s.strip,
      account_id: row['account_id'].to_s.strip,
      region: row['region'].to_s.strip,
      billing_cycle: row['billing_cycle'].to_s.strip,
      required_sku_types: row['required_sku_types'].to_s.split('|').map { |v| canon(v) }.reject(&:empty?),
      expected_amount: row['expected_amount'].to_s.strip,
      allow_partial: %w[TRUE YES Y 1].include?(canon(row['allow_partial']))
    }
  end
end

def build_groups(row_results)
  cycles = load_cycles
  cycles.map do |cycle|
    members = row_results.select do |row|
      row['reservation_id'] == cycle[:reservation_id] && row['account_id'] == cycle[:account_id] && row['__region'] == cycle[:region]
    end
    matched_members = members.select { |row| row['status'] == 'MATCHED' }
    matched_amount = matched_members.sum { |row| row['amount'].to_i }
    present = matched_members.map { |row| row['sku_type'] }.to_set
    required = cycle[:required_sku_types].to_set
    status = 'CLEARABLE'
    reason = 'OK'
    if members.empty? || matched_members.empty?
      status = 'HELD'; reason = 'NO_MATCHED_CREDITS'
    elsif matched_members.length != members.length
      status = 'HELD'; reason = 'MEMBER_UNMATCHED'
    elsif !(required - present).empty?
      status = 'HELD'; reason = 'MISSING_REQUIRED_SKU'
    elsif !int_text?(cycle[:expected_amount]) || matched_amount != cycle[:expected_amount].to_i
      status = 'HELD'; reason = 'GROUP_TOTAL_MISMATCH'
    end
    {
      'group_id' => cycle[:group_id], 'reservation_id' => cycle[:reservation_id], 'account_id' => cycle[:account_id],
      'region' => cycle[:region], 'billing_cycle' => cycle[:billing_cycle], 'required_sku_types' => cycle[:required_sku_types].join('|'),
      'expected_amount' => cycle[:expected_amount], 'matched_amount' => matched_amount.to_s, 'status' => status, 'reason' => reason,
      '__primary_sku' => matched_members.first ? matched_members.first['sku_type'] : (cycle[:required_sku_types].first || '')
    }
  end
end

def apply_capacity_and_controls(groups)
  capacities = {}
  load_csv(File.join(APP, 'data', 'capacity_pools.csv')).each do |row|
    next unless int_text?(row['capacity'].to_s.strip)
    capacities[[row['region'].to_s.strip, canon(row['sku_type'])]] = row['capacity'].to_i
  end
  expected = {}
  load_csv(File.join(APP, 'config', 'control_totals.csv')).each do |row|
    next unless int_text?(row['expected_committed_amount'].to_s.strip)
    expected[[row['region'].to_s.strip, canon(row['sku_type']), row['billing_cycle'].to_s.strip]] = row['expected_committed_amount'].to_i
  end
  clearable = groups.select { |g| g['status'] == 'CLEARABLE' }
  by_key = clearable.group_by { |g| [g['region'], g['__primary_sku'], g['billing_cycle']] }
  groups.each do |g|
    next unless g['status'] == 'CLEARABLE'
    key = [g['region'], g['__primary_sku'], g['billing_cycle']]
    total_for_key = by_key.fetch(key, []).sum { |x| x['matched_amount'].to_i }
    if capacities.fetch([g['region'], g['__primary_sku']], 0) < g['matched_amount'].to_i
      g['status'] = 'HELD'; g['reason'] = 'CAPACITY_EXCEEDED'
    elsif expected.key?(key) && expected[key] != total_for_key
      g['status'] = 'HELD'; g['reason'] = 'CONTROL_TOTAL_MISMATCH'
    end
  end
  usage = Hash.new(0)
  groups.select { |g| g['status'] == 'CLEARABLE' }.each do |g|
    usage[[g['region'], g['__primary_sku']]] += g['matched_amount'].to_i
  end
  [groups, capacities, usage]
end

def prior_commits
  path = File.join(OUT, 'credit_commit_ledger.csv')
  return {} unless File.exist?(path)
  load_csv(path).each_with_object({}) do |row, memo|
    memo[row['group_id']] = row if row['commit_status'] == 'COMMITTED'
  end
end

def commit_groups(groups, capacities, usage)
  committed = prior_commits
  commit_rows = committed.values.map(&:dup)
  clearable = groups.select { |g| g['status'] == 'CLEARABLE' }.sort_by { |g| [g['billing_cycle'], g['region'], g['group_id']] }
  abend_after = ENV['ABEND_AFTER_GROUPS'].to_s
  limit = int_text?(abend_after) ? abend_after.to_i : nil
  newly = 0
  clearable.each do |g|
    next if committed.key?(g['group_id'])
    commit_rows << {
      'group_id' => g['group_id'], 'reservation_id' => g['reservation_id'], 'account_id' => g['account_id'],
      'region' => g['region'], 'billing_cycle' => g['billing_cycle'], 'sku_type' => g['__primary_sku'],
      'committed_amount' => g['matched_amount'], 'commit_status' => 'COMMITTED'
    }
    committed[g['group_id']] = commit_rows.last
    newly += 1
    write_csv(File.join(OUT, 'credit_commit_ledger.csv'), %w[group_id reservation_id account_id region billing_cycle sku_type committed_amount commit_status], commit_rows)
    File.write(File.join(OUT, 'restart_checkpoint.txt'), "last_committed_group=#{g['group_id']}\ncommitted_count=#{committed.length}\n")
    if limit && newly >= limit
      warn "simulated ABEND after #{newly} new groups"
      exit 17
    end
  end
  write_csv(File.join(OUT, 'credit_commit_ledger.csv'), %w[group_id reservation_id account_id region billing_cycle sku_type committed_amount commit_status], commit_rows)
  File.write(File.join(OUT, 'restart_checkpoint.txt'), "last_committed_group=#{commit_rows.last ? commit_rows.last['group_id'] : ''}\ncommitted_count=#{committed.length}\n")
  committed_usage = Hash.new(0)
  commit_rows.each { |r| committed_usage[[r['region'], r['sku_type']]] += r['committed_amount'].to_i }
  pool_rows = capacities.keys.sort.map do |region, sku|
    committed_amount = committed_usage[[region, sku]]
    {
      'region' => region, 'sku_type' => sku, 'starting_capacity' => capacities[[region, sku]].to_s,
      'committed_amount' => committed_amount.to_s, 'remaining_capacity' => (capacities[[region, sku]] - committed_amount).to_s,
      'status' => capacities[[region, sku]] - committed_amount >= 0 ? 'OK' : 'NEGATIVE'
    }
  end
  write_csv(File.join(OUT, 'capacity_pool_after.csv'), %w[region sku_type starting_capacity committed_amount remaining_capacity status], pool_rows)
end

rows, _summary = run_row_reconciliation(alias_enabled: true, policy_enabled: true, allow_any: true)
groups, capacities, usage = apply_capacity_and_controls(build_groups(rows))
write_csv(File.join(OUT, 'reservation_credit_groups.csv'), %w[group_id reservation_id account_id region billing_cycle required_sku_types expected_amount matched_amount status reason], groups)
commit_groups(groups, capacities, usage)
