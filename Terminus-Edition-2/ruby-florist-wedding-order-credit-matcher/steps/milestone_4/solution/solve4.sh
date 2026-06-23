#!/usr/bin/env bash
set -euo pipefail

cat > /app/lib/reconcile.rb <<'RUBY'
#!/usr/bin/env ruby
require "csv"
require "json"
require "fileutils"

SOURCE = "/app/data/orders.csv"
ACTIONS = "/app/data/credits.csv"
REPORT = "/app/out/credit_report.csv"
SUMMARY = "/app/out/credit_summary.json"
CALENDAR = "/app/config/cutoff_calendar.txt"
METHODS = "/app/config/methods.csv"
ALLOWED = ["BOUQUET", "CENTERPIECE", "ARCH"]
ALIASES = { "BQT" => "BOUQUET", "CTR" => "CENTERPIECE", "ARC" => "ARCH" }

SourceRow = Struct.new(:id, :couple, :amount, :status, :arrangement, :delivery_date, keyword_init: true)
CreditRow = Struct.new(:id, :couple, :amount, :arrangement, :credit_date, :raw_amount, keyword_init: true)

def clean(value) = value.to_s.strip
def canonical_arrangement(value)
  token = clean(value).upcase
  ALIASES.fetch(token, token)
end
def allowed?(value) = ALLOWED.include?(canonical_arrangement(value))
def amount(value) = clean(value).to_i
def headers(path) = CSV.read(path, headers: true).headers

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
    arrangement = canonical_arrangement(row["arrangement"])
    next unless allowed?(arrangement)
    methods[arrangement] = clean(row["enabled"]).casecmp?("true")
  end
  methods
end

def load_sources(source_headers)
  CSV.read(SOURCE, headers: true).map do |row|
    SourceRow.new(
      id: clean(row["order_id"]),
      couple: clean(row["couple_id"]),
      amount: amount(row["amount_cents"]),
      status: clean(row["status"]).upcase,
      arrangement: canonical_arrangement(row["arrangement"]),
      delivery_date: source_headers.include?("delivery_date") ? clean(row["delivery_date"]) : ""
    )
  end
end

def load_credits(action_headers)
  CSV.read(ACTIONS, headers: true).map do |row|
    CreditRow.new(
      id: clean(row["order_id"]),
      couple: clean(row["couple_id"]),
      amount: amount(row["amount_cents"]),
      arrangement: canonical_arrangement(row["arrangement"]),
      credit_date: action_headers.include?("credit_date") ? clean(row["credit_date"]) : "",
      raw_amount: clean(row["amount_cents"])
    )
  end
end

def base_match?(source, credit, methods)
  source.id == credit.id &&
    source.couple == credit.couple &&
    source.amount == credit.amount &&
    source.status == "DELIVERED" &&
    allowed?(credit.arrangement) &&
    source.arrangement == credit.arrangement &&
    methods[source.arrangement]
end

def date_match?(source, credit, dates, dated_mode)
  if dated_mode
    return false if source.delivery_date.empty? || credit.credit_date.empty?
    return false unless dates[credit.credit_date]
    return false if credit.credit_date > source.delivery_date
  end
  true
end

def find_match(sources, credit, used, dates, dated_mode, methods)
  best = nil
  sources.each_with_index do |source, index|
    next if used[index]
    next unless base_match?(source, credit, methods)
    next unless date_match?(source, credit, dates, dated_mode)
    best = index if best.nil? || (dated_mode && source.delivery_date > sources[best].delivery_date)
  end
  best
end

source_headers = headers(SOURCE)
action_headers = headers(ACTIONS)
dated_mode = source_headers.include?("delivery_date") && action_headers.include?("credit_date")
sources = load_sources(source_headers)
credits = load_credits(action_headers)
dates = dated_mode ? open_dates : {}
methods = enabled_methods
used = Array.new(sources.length, false)
FileUtils.mkdir_p(File.dirname(REPORT))
matched_count = matched_amount = unmatched_count = unmatched_amount = 0
CSV.open(REPORT, "w") do |csv|
  csv << ["order_id", "couple_id", "arrangement", "amount_cents", "status"]
  credits.each do |credit|
    idx = find_match(sources, credit, used, dates, dated_mode, methods)
    if idx
      used[idx] = true
      matched_count += 1
      matched_amount += credit.amount
      csv << [credit.id, credit.couple, sources[idx].arrangement, credit.raw_amount, "MATCHED"]
    else
      unmatched_count += 1
      unmatched_amount += credit.amount
      csv << [credit.id, credit.couple, "", credit.raw_amount, "UNMATCHED"]
    end
  end
end
File.write(SUMMARY, JSON.pretty_generate({ matched_count: matched_count, matched_amount_cents: matched_amount, unmatched_count: unmatched_count, unmatched_amount_cents: unmatched_amount }))
RUBY

chmod +x /app/lib/reconcile.rb
/app/scripts/run_batch.sh
