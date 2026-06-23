#!/usr/bin/env bash
set -euo pipefail
cat > /app/lib/reconcile.rb <<'RUBY'
#!/usr/bin/env ruby
require "csv"
require "json"
require "fileutils"

SOURCE = "/app/data/pledges.csv"
ACTIONS = "/app/data/adjustments.csv"
REPORT = "/app/out/adjustment_report.csv"
SUMMARY = "/app/out/adjustment_summary.json"
CALENDAR = "/app/config/cutoff_calendar.txt"
METHODS = "/app/config/methods.csv"
ALLOWED = ["GENERAL", "CAPITAL", "RELIEF"]
ALIASES = { "GEN" => "GENERAL", "CAP" => "CAPITAL", "REL" => "RELIEF" }

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

def enabled_funds
  return {} unless File.exist?(METHODS)
  CSV.read(METHODS, headers: true).each_with_object({}) do |row, memo|
    fund = canonical_dim(row["fund"])
    next unless allowed?(fund)
    memo[fund] = true if clean(row["enabled"]).casecmp("true").zero?
  end
end

def load_sources
  CSV.read(SOURCE, headers: true).map do |row|
    SourceRow.new(
      id: clean(row["pledge_id"]),
      customer: clean(row["donor_id"]),
      amount: parse_amount(row["amount_cents"]),
      status: clean(row["status"]).upcase,
      dim: canonical_dim(row["fund"]),
      due_date: clean(row["pledge_due"])
    )
  end
end

def load_actions
  CSV.read(ACTIONS, headers: true).map do |row|
    ActionRow.new(
      id: clean(row["pledge_id"]),
      customer: clean(row["donor_id"]),
      amount: parse_amount(row["amount_cents"]),
      dim: canonical_dim(row["fund"]),
      action_date: clean(row["adjustment_date"]),
      raw_amount: clean(row["amount_cents"])
    )
  end
end

def dated_mode?
  source_headers = CSV.read(SOURCE, headers: true).headers
  action_headers = CSV.read(ACTIONS, headers: true).headers
  source_headers.include?("pledge_due") || action_headers.include?("adjustment_date")
end

def base_match?(source, action, fund_enabled)
  source.id == action.id &&
    source.customer == action.customer &&
    source.amount == action.amount &&
    source.status == "BOOKED" &&
    allowed?(action.dim) &&
    source.dim == action.dim &&
    fund_enabled[source.dim]
end

def date_match?(source, action, dates, use_dates)
  return true unless use_dates
  return false if source.due_date.empty? || action.action_date.empty?
  return false unless dates[action.action_date]
  action.action_date <= source.due_date
end

def find_match(sources, action, used, dates, fund_enabled, use_dates)
  best = nil
  sources.each_with_index do |source, index|
    next if used[index]
    next unless base_match?(source, action, fund_enabled)
    next unless date_match?(source, action, dates, use_dates)
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
fund_enabled = enabled_funds
use_dates = dated_mode?
used = Array.new(sources.length, false)
FileUtils.mkdir_p(File.dirname(REPORT))
matched_count = 0
matched_amount = 0
unmatched_count = 0
unmatched_amount = 0
CSV.open(REPORT, "w") do |csv|
  csv << ["pledge_id", "donor_id", "fund", "amount_cents", "status"]
  actions.each do |action|
    idx = find_match(sources, action, used, dates, fund_enabled, use_dates)
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
File.write(
  SUMMARY,
  JSON.pretty_generate(
    {
      matched_count: matched_count,
      matched_amount_cents: matched_amount,
      unmatched_count: unmatched_count,
      unmatched_amount_cents: unmatched_amount
    }
  )
)
RUBY
chmod +x /app/lib/reconcile.rb
/app/scripts/run_batch.sh
