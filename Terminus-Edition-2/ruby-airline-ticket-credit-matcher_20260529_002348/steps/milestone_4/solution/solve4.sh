#!/usr/bin/env bash
set -euo pipefail
cat > /app/lib/reconcile.rb <<'RUBY'
#!/usr/bin/env ruby
require "csv"
require "json"
require "fileutils"

SOURCE = "/app/data/tickets.csv"
ACTIONS = "/app/data/credits.csv"
REPORT = "/app/out/credit_report.csv"
SUMMARY = "/app/out/credit_summary.json"
CALENDAR = "/app/config/cutoff_calendar.txt"
METHODS = "/app/config/methods.csv"
ALLOWED = ["ECONOMY", "BUSINESS", "FIRST"]
ALIASES = { "ECO" => "ECONOMY", "BIZ" => "BUSINESS", "FST" => "FIRST" }

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

def enabled_methods
  return {} unless File.exist?(METHODS)
  CSV.read(METHODS, headers: true).each_with_object({}) do |row, memo|
    next if row["fare_class"].nil? || row["enabled"].nil?
    klass = canonical_dim(row["fare_class"])
    next if klass.empty?
    enabled = clean(row["enabled"]).downcase
    memo[klass] = (enabled == "true")
  end
end

def open_dates
  return {} unless File.exist?(CALENDAR)
  File.readlines(CALENDAR).each_with_object({}) do |line, memo|
    date, status = line.split
    memo[clean(date)] = true if status.to_s.strip.upcase == "OPEN"
  end
end

def load_sources
  CSV.read(SOURCE, headers: true).map do |row|
    SourceRow.new(
      id: clean(row["ticket_id"]),
      customer: clean(row["traveler_id"]),
      amount: parse_amount(row["amount_cents"]),
      status: clean(row["status"]).upcase,
      dim: canonical_dim(row["fare_class"]),
      due_date: clean(row["flight_date"])
    )
  end
end

def load_actions
  CSV.read(ACTIONS, headers: true).map do |row|
    ActionRow.new(
      id: clean(row["ticket_id"]),
      customer: clean(row["traveler_id"]),
      amount: parse_amount(row["amount_cents"]),
      dim: canonical_dim(row["fare_class"]),
      action_date: clean(row["credit_date"]),
      raw_amount: clean(row["amount_cents"])
    )
  end
end

def method_enabled?(methods, dim)
  methods.fetch(dim, false)
end

def base_match?(source, action, methods)
  source.id == action.id &&
    source.customer == action.customer &&
    source.amount == action.amount &&
    source.status == "FLOWN" &&
    allowed?(action.dim) &&
    method_enabled?(methods, source.dim) &&
    source.dim == action.dim
end

def date_match?(source, action, dates)
  return true if !CSV.read(SOURCE, headers: true).headers.include?("flight_date") && !CSV.read(ACTIONS, headers: true).headers.include?("credit_date")
  return false if source.due_date.empty? || action.action_date.empty?
  return false unless dates[action.action_date]
  action.action_date <= source.due_date
end

def find_match(sources, action, used, dates, methods)
  best = nil
  sources.each_with_index do |source, index|
    next if used[index]
    next unless base_match?(source, action, methods)
    next unless date_match?(source, action, dates)
    if best.nil?
      best = index
    elsif source.due_date > sources[best].due_date
      best = index
    elsif source.due_date == sources[best].due_date && index < best
      best = index
    end
  end
  best
end

sources = load_sources
actions = load_actions
dates = open_dates
methods = enabled_methods
used = Array.new(sources.length, false)
FileUtils.mkdir_p(File.dirname(REPORT))
matched_count = 0
matched_amount = 0
unmatched_count = 0
unmatched_amount = 0
CSV.open(REPORT, "w") do |csv|
  csv << ["ticket_id", "traveler_id", "fare_class", "amount_cents", "status"]
  actions.each do |action|
    idx = find_match(sources, action, used, dates, methods)
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
