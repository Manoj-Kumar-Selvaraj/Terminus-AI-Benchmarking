#!/usr/bin/env bash
set -euo pipefail
# Install the cumulative Ruby implementation required through milestone 4.
cat > /app/lib/reconcile.rb <<'RUBY'
#!/usr/bin/env ruby
require "csv"
require "json"
require "fileutils"

SOURCE = "/app/data/sessions.csv"
ACTIONS = "/app/data/refunds.csv"
REPORT = "/app/out/refund_report.csv"
SUMMARY = "/app/out/refund_summary.json"
CALENDAR = "/app/config/cutoff_calendar.txt"
METHODS = "/app/config/methods.csv"
ALLOWED = ["MINI", "STANDARD", "PREMIUM"]
ALIASES = { "MIN" => "MINI", "STD" => "STANDARD", "PRM" => "PREMIUM" }

SourceRow = Struct.new(:id, :customer, :amount, :status, :dim, :due_date, :row_number, keyword_init: true)
ActionRow = Struct.new(:id, :customer, :amount, :dim, :action_date, :raw_amount, keyword_init: true)

def clean(value)
  value.to_s.strip
end

def canonical_dim(value)
  token = clean(value).upcase
  ALIASES.fetch(token, token)
end

def truthy?(value)
  clean(value).upcase == "TRUE"
end

def parse_amount(value)
  text = clean(value)
  return nil unless text.match?(/\A[1-9]\d*\z/)
  text.to_i
end

def valid_date?(value)
  clean(value).match?(/\A\d{4}-\d{2}-\d{2}\z/)
end

def headers_for(path)
  CSV.read(path, headers: true).headers || []
end

def package_policy
  unless File.exist?(METHODS)
    return ALLOWED.each_with_index.to_h { |dim, idx| [dim, { enabled: true, priority: idx }] }
  end
  table = CSV.read(METHODS, headers: true)
  has_priority = table.headers.include?("priority")
  policy = {}
  table.each_with_index do |row, index|
    dim = canonical_dim(row["package"])
    next unless ALLOWED.include?(dim)
    raw_priority = clean(row["priority"])
    priority = if has_priority
      raw_priority.match?(/\A\d+\z/) ? raw_priority.to_i : 1_000_000 + index
    else
      0
    end
    policy[dim] = { enabled: truthy?(row["enabled"]), priority: priority }
  end
  policy
end

def enabled_type?(value, policy)
  entry = policy[canonical_dim(value)]
  !entry.nil? && entry[:enabled]
end

def type_priority(value, policy)
  policy.fetch(canonical_dim(value), { priority: 9_999_999 })[:priority]
end

def open_dates
  return {} unless File.exist?(CALENDAR)
  File.readlines(CALENDAR).each_with_object({}) do |line, memo|
    date, status = line.split
    memo[clean(date)] = true if valid_date?(date) && clean(status).upcase == "OPEN"
  end
end

def date_mode?
  headers_for(SOURCE).include?("session_date") || headers_for(ACTIONS).include?("refund_date")
end

def date_match?(source, action, dates, enabled)
  return true unless enabled
  return false unless valid_date?(source.due_date) && valid_date?(action.action_date)
  return false unless dates[action.action_date]
  action.action_date <= source.due_date
end

def load_sources
  CSV.read(SOURCE, headers: true).each_with_index.map do |row, index|
    SourceRow.new(
      id: clean(row["session_id"]),
      customer: clean(row["client_id"]),
      amount: parse_amount(row["amount_cents"]),
      status: clean(row["status"]).upcase,
      dim: canonical_dim(row["package"]),
      due_date: clean(row["session_date"]),
      row_number: index + 1
    )
  end
end

def load_actions
  CSV.read(ACTIONS, headers: true).map do |row|
    ActionRow.new(
      id: clean(row["session_id"]),
      customer: clean(row["client_id"]),
      amount: parse_amount(row["amount_cents"]),
      dim: canonical_dim(row["package"]),
      action_date: clean(row["refund_date"]),
      raw_amount: clean(row["amount_cents"])
    )
  end
end

def base_match?(source, action)
  !source.amount.nil? && !action.amount.nil? &&
    source.id == action.id &&
    source.customer == action.customer &&
    source.amount == action.amount &&
    source.status == "SHOT"
end

def type_match?(source, action, policy)
  return enabled_type?(source.dim, policy) if action.dim == "ANY"
  enabled_type?(action.dim, policy) && source.dim == action.dim
end

def better_candidate?(source, best_source, index, best_index, policy, dates_enabled)
  return true if best_source.nil?
  if dates_enabled && source.due_date != best_source.due_date
    return source.due_date > best_source.due_date
  end
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
    best = index if better_candidate?(source, best && sources[best], index, best, policy, dates_enabled)
  end
  best
end

sources = load_sources
actions = load_actions
dates_enabled = date_mode?
dates = dates_enabled ? open_dates : {}
policy = package_policy
used = Array.new(sources.length, false)
FileUtils.mkdir_p(File.dirname(REPORT))
matched_count = 0
matched_amount = 0
unmatched_count = 0
unmatched_amount = 0
CSV.open(REPORT, "w") do |csv|
  csv << ["session_id", "client_id", "package", "amount_cents", "matched_session_row", "status"]
  actions.each do |action|
    idx = find_match(sources, action, used, dates, dates_enabled, policy)
    if idx
      used[idx] = true
      matched_count += 1
      matched_amount += action.amount || 0
      csv << [action.id, action.customer, sources[idx].dim, action.raw_amount, sources[idx].row_number.to_s, "MATCHED"]
    else
      unmatched_count += 1
      unmatched_amount += action.amount || 0
      csv << [action.id, action.customer, "", action.raw_amount, "", "UNMATCHED"]
    end
  end
end
File.write(SUMMARY, JSON.pretty_generate({matched_count: matched_count, matched_amount_cents: matched_amount, unmatched_count: unmatched_count, unmatched_amount_cents: unmatched_amount}))

RUBY
chmod +x /app/lib/reconcile.rb
/app/scripts/run_batch.sh
