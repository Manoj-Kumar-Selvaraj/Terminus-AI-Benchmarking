#!/usr/bin/env bash
set -euo pipefail
cat > /app/lib/reconcile.rb <<'RUBY'
#!/usr/bin/env ruby
require "csv"
require "json"
require "fileutils"

SOURCE = "/app/data/invoices.csv"
ACTIONS = "/app/data/rebates.csv"
REPORT = "/app/out/rebate_report.csv"
SUMMARY = "/app/out/rebate_summary.json"
CALENDAR = "/app/config/cutoff_calendar.txt"
ALLOWED = ["EXPRESS", "STANDARD", "DETAIL"]
ALIASES = { "EXP" => "EXPRESS", "STD" => "STANDARD", "DTL" => "DETAIL" }

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
  CSV.read(SOURCE, headers: true).map do |row|
    SourceRow.new(
      id: clean(row["invoice_id"]),
      customer: clean(row["vehicle_id"]),
      amount: parse_amount(row["amount_cents"]),
      status: clean(row["status"]).upcase,
      dim: canonical_dim(row["bay"]),
      due_date: clean(row["service_date"])
    )
  end
end

def load_actions
  CSV.read(ACTIONS, headers: true).map do |row|
    ActionRow.new(
      id: clean(row["invoice_id"]),
      customer: clean(row["vehicle_id"]),
      amount: parse_amount(row["amount_cents"]),
      dim: canonical_dim(row["bay"]),
      action_date: clean(row["rebate_date"]),
      raw_amount: clean(row["amount_cents"])
    )
  end
end

def base_match?(source, action)
  source.id == action.id &&
    source.customer == action.customer &&
    source.amount == action.amount &&
    source.status == "CLOSED" &&
    allowed?(action.dim) &&
    source.dim == action.dim
end

def date_match?(source, action, dates, dated_mode)
  return true unless dated_mode
  return false if source.due_date.empty? || action.action_date.empty?
  return false unless dates[action.action_date]
  action.action_date <= source.due_date
end

def find_match(sources, action, used, dates, dated_mode)
  best = nil
  sources.each_with_index do |source, index|
    next if used[index]
    next unless base_match?(source, action)
    next unless date_match?(source, action, dates, dated_mode)
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
dated_mode = CSV.read(SOURCE, headers: true).headers.include?("service_date") &&
  CSV.read(ACTIONS, headers: true).headers.include?("rebate_date")
dates = dated_mode ? open_dates : {}
used = Array.new(sources.length, false)
FileUtils.mkdir_p(File.dirname(REPORT))
matched_count = 0
matched_amount = 0
unmatched_count = 0
unmatched_amount = 0
CSV.open(REPORT, "w") do |csv|
  csv << ["invoice_id", "vehicle_id", "bay", "amount_cents", "status"]
  actions.each do |action|
    idx = find_match(sources, action, used, dates, dated_mode)
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
