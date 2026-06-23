#!/usr/bin/env bash
set -euo pipefail
cat > /app/lib/reconcile.rb <<'RUBY'
#!/usr/bin/env ruby
require "csv"
require "json"
require "fileutils"

SOURCE = "/app/data/plans.csv"
ACTIONS = "/app/data/credits.csv"
REPORT = "/app/out/credit_report.csv"
SUMMARY = "/app/out/credit_summary.json"
CONSUMPTION = "/app/out/plan_consumption.csv"
CALENDAR = "/app/config/cutoff_calendar.txt"
ALLOWED = ["DINING", "CAFE", "MARKET"]
ALIASES = { "DIN" => "DINING", "CAF" => "CAFE", "MKT" => "MARKET" }

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

def load_sources
  headers = CSV.read(SOURCE, headers: true).headers
  CSV.read(SOURCE, headers: true).map do |row|
    SourceRow.new(
      id: clean(row["plan_id"]),
      customer: clean(row["student_id"]),
      amount: parse_amount(row["amount_cents"]),
      status: clean(row["status"]).upcase,
      dim: canonical_dim(row["location"]),
      due_date: headers.include?("cycle_end") ? clean(row["cycle_end"]) : ""
    )
  end
end

def load_actions
  headers = CSV.read(ACTIONS, headers: true).headers
  CSV.read(ACTIONS, headers: true).map do |row|
    ActionRow.new(
      id: clean(row["plan_id"]),
      customer: clean(row["student_id"]),
      amount: parse_amount(row["amount_cents"]),
      dim: canonical_dim(row["location"]),
      action_date: headers.include?("credit_date") ? clean(row["credit_date"]) : "",
      raw_amount: clean(row["amount_cents"])
    )
  end
end

def base_match?(source, action)
  source.id == action.id &&
    source.customer == action.customer &&
    source.amount == action.amount &&
    source.status == "ACTIVE" &&
    allowed?(action.dim) &&
    source.dim == action.dim
end

def date_match?(source, action, dates, has_cycle_end, has_credit_date)
  if has_credit_date
    return false if action.action_date.empty?
    return false unless dates[action.action_date]
  end
  if has_cycle_end
    return false if source.due_date.empty?
  end
  if has_cycle_end && has_credit_date
    return false if action.action_date > source.due_date
  end
  true
end

def find_match(sources, action, used, dates, dated_mode)
  best = nil
  sources.each_with_index do |source, index|
    next if used[index]
    next unless base_match?(source, action)
    next unless date_match?(source, action, dates, dated_mode[:cycle_end], dated_mode[:credit_date])
    if best.nil?
      best = index
    elsif dated_mode[:cycle_end] && dated_mode[:credit_date]
      if source.due_date > sources[best].due_date
        best = index
      elsif source.due_date == sources[best].due_date && index < best
        best = index
      end
    end
  end
  best
end

plan_headers = CSV.read(SOURCE, headers: true).headers
credit_headers = CSV.read(ACTIONS, headers: true).headers
dated_mode = {
  cycle_end: plan_headers.include?("cycle_end"),
  credit_date: credit_headers.include?("credit_date")
}
sources = load_sources
actions = load_actions
dates = dated_mode[:credit_date] ? open_dates : {}
used = Array.new(sources.length, false)
FileUtils.mkdir_p(File.dirname(REPORT))
matched_count = 0
matched_amount = 0
unmatched_count = 0
unmatched_amount = 0
consumption_rows = []
CSV.open(REPORT, "w") do |csv|
  csv << ["plan_id", "student_id", "location", "amount_cents", "status"]
  actions.each_with_index do |action, credit_row|
    idx = find_match(sources, action, used, dates, dated_mode)
    if idx
      used[idx] = true
      consumption_rows << [credit_row, idx, sources[idx].due_date]
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
CSV.open(CONSUMPTION, "w") do |csv|
  csv << ["credit_row", "plan_row", "cycle_end"]
  consumption_rows.each { |row| csv << row }
end
File.write(SUMMARY, JSON.pretty_generate({matched_count: matched_count, matched_amount_cents: matched_amount, unmatched_count: unmatched_count, unmatched_amount_cents: unmatched_amount}))
RUBY
chmod +x /app/lib/reconcile.rb
/app/scripts/run_batch.sh
