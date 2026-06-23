#!/usr/bin/env bash
set -euo pipefail
cat > /app/lib/reconcile.rb <<'RUBY'
#!/usr/bin/env ruby
require "csv"
require "json"
require "fileutils"

SOURCE = "/app/data/kegs.csv"
ACTIONS = "/app/data/deposits.csv"
REPORT = "/app/out/deposit_report.csv"
SUMMARY = "/app/out/deposit_summary.json"
CALENDAR = "/app/config/cutoff_calendar.txt"
METHODS = "/app/config/methods.csv"
PROFILE = "/app/config/run_profile.ini"
ALLOWED = ["HALF", "SIXTH", "CORNELIUS"]
ALIASES = { "HLF" => "HALF", "SIX" => "SIXTH", "COR" => "CORNELIUS" }

SourceRow = Struct.new(:id, :customer, :amount, :status, :dim, :due_date, keyword_init: true)
ActionRow = Struct.new(:id, :customer, :amount, :dim, :action_date, :raw_amount, keyword_init: true)

def clean(value)
  value.to_s.strip
end

def canonical_dim(value)
  token = clean(value).upcase
  ALIASES.fetch(token, token)
end

def allowed?(value)
  ALLOWED.include?(canonical_dim(value))
end

def truthy?(value)
  clean(value).upcase == "TRUE"
end

def keg_policy
  policy = {}
  if File.exist?(METHODS)
    CSV.read(METHODS, headers: true).each_with_index do |row, index|
      dim = canonical_dim(row["keg_type"])
      next if dim.empty?
      raw_priority = clean(row["priority"])
      priority = raw_priority.match?(/\A\d+\z/) ? raw_priority.to_i : 10_000 + index
      policy[dim] = { enabled: truthy?(row["enabled"]), priority: priority }
    end
  end
  if policy.empty?
    ALLOWED.each_with_index { |dim, index| policy[dim] = { enabled: true, priority: index + 1 } }
  end
  policy
end

def enabled_type?(value, policy)
  entry = policy[canonical_dim(value)]
  !entry.nil? && entry[:enabled]
end

def type_priority(value, policy)
  policy.fetch(canonical_dim(value), { priority: 99_999 })[:priority]
end

def deposit_open_window_days
  return 2 unless File.exist?(PROFILE)
  File.readlines(PROFILE).each do |line|
    key, val = line.split("=", 2)
    return clean(val).to_i if clean(key) == "deposit_open_window_days" && clean(val).match?(/\A\d+\z/)
  end
  2
end

def open_days_in_window?(deposit_date, return_date)
  max_days = deposit_open_window_days
  return false if deposit_date.empty? || return_date.empty?
  return false if deposit_date > return_date
  count = 0
  return true unless File.exist?(CALENDAR)
  File.readlines(CALENDAR).each do |line|
    day, status = line.split
    day = clean(day)
    next unless clean(status).upcase == "OPEN"
    if day > deposit_date && (day < return_date || day == return_date)
      count += 1
    end
  end
  count <= max_days
end

def parse_amount(value)
  clean(value).to_i
end

def open_dates
  return {} unless File.exist?(CALENDAR)
  File.readlines(CALENDAR).each_with_object({}) do |line, memo|
    date, status = line.split
    memo[clean(date)] = true if status.to_s.strip.upcase == "OPEN"
  end
end

def date_mode?
  source_headers = CSV.read(SOURCE, headers: true).headers
  action_headers = CSV.read(ACTIONS, headers: true).headers
  source_headers.include?("return_date") || action_headers.include?("deposit_date")
end

def date_match?(source, action, dates, enabled)
  return true unless enabled
  return false if source.due_date.empty? || action.action_date.empty?
  return false unless dates[action.action_date]
  return false unless action.action_date <= source.due_date
  open_days_in_window?(action.action_date, source.due_date)
end

def load_sources
  CSV.read(SOURCE, headers: true).map do |row|
    SourceRow.new(
      id: clean(row["keg_id"]),
      customer: clean(row["distributor_id"]),
      amount: parse_amount(row["amount_cents"]),
      status: clean(row["status"]).upcase,
      dim: canonical_dim(row["keg_type"]),
      due_date: clean(row["return_date"])
    )
  end
end

def load_actions
  CSV.read(ACTIONS, headers: true).map do |row|
    ActionRow.new(
      id: clean(row["keg_id"]),
      customer: clean(row["distributor_id"]),
      amount: parse_amount(row["amount_cents"]),
      dim: canonical_dim(row["keg_type"]),
      action_date: clean(row["deposit_date"]),
      raw_amount: clean(row["amount_cents"])
    )
  end
end

def base_match?(source, action)
  source.id == action.id &&
    source.customer == action.customer &&
    source.amount == action.amount &&
    source.status == "RETURNED"
end

def type_match?(source, action, policy)
  return enabled_type?(source.dim, policy) if action.dim == "ANY"
  enabled_type?(action.dim, policy) && source.dim == action.dim
end

def better_candidate?(source, best_source, index, best_index, policy)
  return true if best_source.nil?
  return source.due_date > best_source.due_date if source.due_date != best_source.due_date
  source_priority = type_priority(source.dim, policy)
  best_priority = type_priority(best_source.dim, policy)
  return source_priority < best_priority if source_priority != best_priority
  index < best_index
end

def find_match(sources, action, used, dates, dates_enabled, policy)
  best = nil
  sources.each_with_index do |source, index|
    next if used[index]
    next unless base_match?(source, action)
    next unless type_match?(source, action, policy)
    next unless date_match?(source, action, dates, dates_enabled)
    if better_candidate?(source, best && sources[best], index, best, policy)
      best = index
    end
  end
  best
end

sources = load_sources
actions = load_actions
dates_enabled = date_mode?
dates = dates_enabled ? open_dates : {}
policy = keg_policy
used = Array.new(sources.length, false)
FileUtils.mkdir_p(File.dirname(REPORT))
matched_count = 0
matched_amount = 0
unmatched_count = 0
unmatched_amount = 0
CSV.open(REPORT, "w") do |csv|
  csv << ["keg_id", "distributor_id", "keg_type", "amount_cents", "status"]
  actions.each do |action|
    idx = find_match(sources, action, used, dates, dates_enabled, policy)
    if idx
      used[idx] = true
      matched_count += 1
      matched_amount += action.amount
      csv << [action.id, action.customer, sources[idx].dim, action.raw_amount, "MATCHED"]
    else
      unmatched_count += 1
      unmatched_amount += action.amount
      csv << [action.id, action.customer, "", action.raw_amount, "UNMATCHED"]
    end
  end
end
File.write(SUMMARY, JSON.pretty_generate({matched_count: matched_count, matched_amount_cents: matched_amount, unmatched_count: unmatched_count, unmatched_amount_cents: unmatched_amount}))
RUBY
chmod +x /app/lib/reconcile.rb
/app/scripts/run_batch.sh
