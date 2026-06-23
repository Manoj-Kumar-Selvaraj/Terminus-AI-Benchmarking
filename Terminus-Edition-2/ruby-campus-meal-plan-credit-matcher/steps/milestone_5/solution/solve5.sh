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
METHODS = "/app/config/methods.csv"
LIMITS = "/app/config/student_limits.csv"
ALLOWED = ["DINING", "CAFE", "MARKET"]
ALIASES = { "DIN" => "DINING", "CAF" => "CAFE", "MKT" => "MARKET" }

SourceRow = Struct.new(:id, :student, :amount, :status, :location, :cycle_end, keyword_init: true)
CreditRow = Struct.new(:id, :student, :amount, :location, :credit_date, :raw_amount, keyword_init: true)
LimitRow = Struct.new(:student, :location, :effective_date, :max_amount, :row, keyword_init: true)

def clean(value)
  value.to_s.strip
end

def canonical_location(value)
  token = clean(value).upcase
  ALIASES.fetch(token, token)
end

def allowed_location?(value)
  ALLOWED.include?(canonical_location(value))
end

def amount(value)
  clean(value).to_i
end

def numeric?(value)
  clean(value).match?(/\A\d+\z/)
end

def date?(value)
  clean(value).match?(/\A\d{4}-\d{2}-\d{2}\z/)
end

def read_headers(path)
  CSV.read(path, headers: true).headers
end

def open_dates
  return {} unless File.exist?(CALENDAR)
  File.readlines(CALENDAR).each_with_object({}) do |line, dates|
    date, state = line.split
    dates[clean(date)] = true if clean(state).upcase == "OPEN"
  end
end

def enabled_methods
  methods = {}
  return methods unless File.exist?(METHODS)
  CSV.foreach(METHODS, headers: true) do |row|
    location = canonical_location(row["location"])
    next unless allowed_location?(location)
    methods[location] = clean(row["enabled"]).casecmp?("true")
  end
  methods
end

def load_limits
  return [] unless File.exist?(LIMITS)
  CSV.read(LIMITS, headers: true).map.with_index do |row, index|
    location = canonical_location(row["location"])
    next unless allowed_location?(location)
    next unless clean(row["status"]).upcase == "ACTIVE"
    next unless date?(row["effective_date"])
    next unless numeric?(row["max_daily_amount"])
    LimitRow.new(
      student: clean(row["student_id"]),
      location: location,
      effective_date: clean(row["effective_date"]),
      max_amount: clean(row["max_daily_amount"]).to_i,
      row: index
    )
  end.compact
end

def load_sources(headers)
  CSV.read(SOURCE, headers: true).map do |row|
    SourceRow.new(
      id: clean(row["plan_id"]),
      student: clean(row["student_id"]),
      amount: amount(row["amount_cents"]),
      status: clean(row["status"]).upcase,
      location: canonical_location(row["location"]),
      cycle_end: headers.include?("cycle_end") ? clean(row["cycle_end"]) : ""
    )
  end
end

def load_credits(headers)
  CSV.read(ACTIONS, headers: true).map do |row|
    CreditRow.new(
      id: clean(row["plan_id"]),
      student: clean(row["student_id"]),
      amount: amount(row["amount_cents"]),
      location: canonical_location(row["location"]),
      credit_date: headers.include?("credit_date") ? clean(row["credit_date"]) : "",
      raw_amount: clean(row["amount_cents"])
    )
  end
end

def base_match?(source, credit, methods)
  source.id == credit.id &&
    source.student == credit.student &&
    source.amount == credit.amount &&
    source.status == "ACTIVE" &&
    allowed_location?(credit.location) &&
    source.location == credit.location &&
    methods[source.location]
end

def date_match?(source, credit, dates, dated_mode)
  if dated_mode[:credit_date]
    return false if credit.credit_date.empty?
    return false unless dates[credit.credit_date]
  end
  if dated_mode[:cycle_end]
    return false if source.cycle_end.empty?
  end
  if dated_mode[:cycle_end] && dated_mode[:credit_date]
    return false if credit.credit_date > source.cycle_end
  end
  true
end

def best_limit(credit, limits)
  best = nil
  limits.each do |limit|
    next unless limit.student == credit.student
    next unless limit.location == credit.location
    next if limit.effective_date > credit.credit_date
    if best.nil? || limit.effective_date > best.effective_date || (limit.effective_date == best.effective_date && limit.row < best.row)
      best = limit
    end
  end
  best
end

def find_match(sources, credit, used, dates, dated_mode, methods)
  best = nil
  sources.each_with_index do |source, index|
    next if used[index]
    next unless base_match?(source, credit, methods)
    next unless date_match?(source, credit, dates, dated_mode)
    if best.nil?
      best = index
    elsif dated_mode[:cycle_end] && dated_mode[:credit_date]
      best = index if source.cycle_end > sources[best].cycle_end
    end
  end
  best
end

plan_headers = read_headers(SOURCE)
credit_headers = read_headers(ACTIONS)
dated_mode = { cycle_end: plan_headers.include?("cycle_end"), credit_date: credit_headers.include?("credit_date") }
sources = load_sources(plan_headers)
credits = load_credits(credit_headers)
dates = dated_mode[:credit_date] ? open_dates : {}
methods = enabled_methods
limits = dated_mode[:credit_date] ? load_limits : []
budget_used = Hash.new(0)
used = Array.new(sources.length, false)
FileUtils.mkdir_p(File.dirname(REPORT))
matched_count = matched_amount = unmatched_count = unmatched_amount = 0
consumption_rows = []
CSV.open(REPORT, "w") do |csv|
  csv << ["plan_id", "student_id", "location", "amount_cents", "status"]
  credits.each_with_index do |credit, credit_row|
    idx = find_match(sources, credit, used, dates, dated_mode, methods)
    budget_ok = true
    budget_key = nil
    if idx && dated_mode[:credit_date]
      limit = best_limit(credit, limits)
      budget_key = [credit.student, credit.location, credit.credit_date]
      budget_ok = limit && budget_used[budget_key] + credit.amount <= limit.max_amount
    end
    if idx && budget_ok
      used[idx] = true
      consumption_rows << [credit_row, idx, sources[idx].cycle_end]
      budget_used[budget_key] += credit.amount if budget_key
      matched_count += 1
      matched_amount += credit.amount
      csv << [credit.id, credit.student, sources[idx].location, credit.raw_amount, "MATCHED"]
    else
      unmatched_count += 1
      unmatched_amount += credit.amount
      csv << [credit.id, credit.student, "", credit.raw_amount, "UNMATCHED"]
    end
  end
end
CSV.open(CONSUMPTION, "w") do |csv|
  csv << ["credit_row", "plan_row", "cycle_end"]
  consumption_rows.each { |row| csv << row }
end
File.write(SUMMARY, JSON.pretty_generate({ matched_count: matched_count, matched_amount_cents: matched_amount, unmatched_count: unmatched_count, unmatched_amount_cents: unmatched_amount }))
RUBY

chmod +x /app/lib/reconcile.rb
/app/scripts/run_batch.sh
