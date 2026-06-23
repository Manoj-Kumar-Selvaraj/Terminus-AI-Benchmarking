#!/usr/bin/env bash
set -euo pipefail
cat > /app/lib/reconcile.rb <<'RUBY'
#!/usr/bin/env ruby
require "csv"
require "json"
require "fileutils"

SOURCE = "/app/data/bookings.csv"
ACTIONS = "/app/data/refunds.csv"
REPORT = "/app/out/refund_report.csv"
SUMMARY = "/app/out/refund_summary.json"
CALENDAR = "/app/config/cutoff_calendar.txt"
ALLOWED = ["ORCH", "MEZZ", "BALC"].freeze
ALIASES = { "ORC" => "ORCH", "MEZ" => "MEZZ", "BAL" => "BALC" }.freeze

SourceRow = Struct.new(:id, :customer, :amount, :status, :dim, :show_date, keyword_init: true)
ActionRow = Struct.new(:id, :customer, :amount, :dim, :refund_date, :raw_amount, keyword_init: true)

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
    memo[clean(date)] = true if clean(status).upcase == "OPEN"
  end
end

source_table = CSV.read(SOURCE, headers: true)
action_table = CSV.read(ACTIONS, headers: true)
date_mode = source_table.headers.include?("show_date") || action_table.headers.include?("refund_date")

sources = source_table.map do |row|
  SourceRow.new(
    id: clean(row["booking_id"]),
    customer: clean(row["patron_id"]),
    amount: parse_amount(row["amount_cents"]),
    status: clean(row["status"]).upcase,
    dim: canonical_dim(row["seat_zone"]),
    show_date: clean(row["show_date"])
  )
end

actions = action_table.map do |row|
  ActionRow.new(
    id: clean(row["booking_id"]),
    customer: clean(row["patron_id"]),
    amount: parse_amount(row["amount_cents"]),
    dim: canonical_dim(row["seat_zone"]),
    refund_date: clean(row["refund_date"]),
    raw_amount: clean(row["amount_cents"])
  )
end

dates = open_dates

def base_match?(source, action)
  source.id == action.id &&
    source.customer == action.customer &&
    source.amount == action.amount &&
    source.status == "TICKETED" &&
    allowed?(action.dim) &&
    source.dim == action.dim
end

def open_count_between(dates, refund_date, show_date)
  dates.keys.count { |date| date > refund_date && date <= show_date }
end

def date_match?(source, action, dates, date_mode)
  return true unless date_mode
  return false if source.show_date.empty? || action.refund_date.empty?
  return false unless dates[source.show_date] && dates[action.refund_date]
  return false unless action.refund_date < source.show_date

  open_count_between(dates, action.refund_date, source.show_date) >= 2
end

def find_match(sources, action, used, dates, date_mode)
  best = nil
  sources.each_with_index do |source, index|
    next if used[index]
    next unless base_match?(source, action)
    next unless date_match?(source, action, dates, date_mode)

    if best.nil? || source.show_date > sources[best].show_date
      best = index
    end
  end
  best
end

used = Array.new(sources.length, false)
FileUtils.mkdir_p(File.dirname(REPORT))
matched_count = 0
matched_amount = 0
unmatched_count = 0
unmatched_amount = 0

CSV.open(REPORT, "w") do |csv|
  csv << ["booking_id", "patron_id", "seat_zone", "amount_cents", "status"]
  actions.each do |action|
    idx = find_match(sources, action, used, dates, date_mode)
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
