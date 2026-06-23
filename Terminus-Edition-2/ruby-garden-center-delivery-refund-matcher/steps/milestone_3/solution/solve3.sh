#!/usr/bin/env bash
set -euo pipefail
cat > /app/lib/reconcile.rb <<'RUBY'
#!/usr/bin/env ruby
require "csv"
require "json"
require "fileutils"

SOURCE = "/app/data/deliveries.csv"
ACTIONS = "/app/data/refunds.csv"
REPORT = "/app/out/refund_report.csv"
SUMMARY = "/app/out/refund_summary.json"
CALENDAR = "/app/config/cutoff_calendar.txt"
ALLOWED = ["SOIL", "MULCH", "PLANTS"]
ALIASES = { "SOL" => "SOIL", "MUL" => "MULCH", "PLT" => "PLANTS" }

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
  source_headers.include?("delivery_date") || action_headers.include?("refund_date")
end

def date_match?(source, action, dates, enabled)
  return true unless enabled
  return false if source.due_date.empty? || action.action_date.empty?
  return false unless dates[action.action_date]
  action.action_date <= source.due_date
end

def load_sources
  CSV.read(SOURCE, headers: true).map do |row|
    SourceRow.new(
      id: clean(row["delivery_id"]),
      customer: clean(row["customer_id"]),
      amount: parse_amount(row["amount_cents"]),
      status: clean(row["status"]).upcase,
      dim: canonical_dim(row["load_type"]),
      due_date: clean(row["delivery_date"])
    )
  end
end

def load_actions
  CSV.read(ACTIONS, headers: true).map do |row|
    ActionRow.new(
      id: clean(row["delivery_id"]),
      customer: clean(row["customer_id"]),
      amount: parse_amount(row["amount_cents"]),
      dim: canonical_dim(row["load_type"]),
      action_date: clean(row["refund_date"]),
      raw_amount: clean(row["amount_cents"])
    )
  end
end

def base_match?(source, action)
  source.id == action.id &&
    source.customer == action.customer &&
    source.amount == action.amount &&
    source.status == "DROPPED" &&
    allowed?(action.dim) &&
    source.dim == action.dim
end

def find_match(sources, action, used, dates, dates_enabled)
  best = nil
  sources.each_with_index do |source, index|
    next if used[index]
    next unless base_match?(source, action)
    next unless date_match?(source, action, dates, dates_enabled)
    if best.nil? || source.due_date > sources[best].due_date
      best = index
    end
  end
  best
end

sources = load_sources
actions = load_actions
dates_enabled = date_mode?
dates = dates_enabled ? open_dates : {}
used = Array.new(sources.length, false)
FileUtils.mkdir_p(File.dirname(REPORT))
matched_count = 0
matched_amount = 0
unmatched_count = 0
unmatched_amount = 0
CSV.open(REPORT, "w") do |csv|
  csv << ["delivery_id", "customer_id", "load_type", "amount_cents", "status"]
  actions.each do |action|
    idx = find_match(sources, action, used, dates, dates_enabled)
    if idx
      used[idx] = true
      matched_count += 1
      matched_amount += action.amount
      csv << [action.id, action.customer, action.dim, action.raw_amount, "MATCHED"]
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
