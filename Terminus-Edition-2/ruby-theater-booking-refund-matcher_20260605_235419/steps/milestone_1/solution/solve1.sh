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
ALLOWED = ["ORCH", "MEZZ", "BALC"]

SourceRow = Struct.new(:id, :customer, :amount, :status, :dim, keyword_init: true)
ActionRow = Struct.new(:id, :customer, :amount, :dim, :raw_amount, keyword_init: true)

def clean(value)
  value.to_s.strip
end

def norm_zone(value)
  clean(value).upcase
end

def allowed?(value)
  ALLOWED.include?(norm_zone(value))
end

def parse_amount(value)
  clean(value).to_i
end

def load_sources
  CSV.read(SOURCE, headers: true).map do |row|
    SourceRow.new(
      id: clean(row["booking_id"]),
      customer: clean(row["patron_id"]),
      amount: parse_amount(row["amount_cents"]),
      status: clean(row["status"]).upcase,
      dim: norm_zone(row["seat_zone"])
    )
  end
end

def load_actions
  CSV.read(ACTIONS, headers: true).map do |row|
    ActionRow.new(
      id: clean(row["booking_id"]),
      customer: clean(row["patron_id"]),
      amount: parse_amount(row["amount_cents"]),
      dim: norm_zone(row["seat_zone"]),
      raw_amount: clean(row["amount_cents"])
    )
  end
end

def base_match?(source, action)
  source.id == action.id &&
    source.customer == action.customer &&
    source.amount == action.amount &&
    source.status == "TICKETED" &&
    allowed?(action.dim) &&
    source.dim == action.dim
end

def find_match(sources, action, used)
  sources.each_with_index do |source, index|
    next if used[index]
    return index if base_match?(source, action)
  end
  nil
end

sources = load_sources
actions = load_actions
used = Array.new(sources.length, false)
FileUtils.mkdir_p(File.dirname(REPORT))
matched_count = 0
matched_amount = 0
unmatched_count = 0
unmatched_amount = 0
CSV.open(REPORT, "w") do |csv|
  csv << ["booking_id", "patron_id", "seat_zone", "amount_cents", "status"]
  actions.each do |action|
    idx = find_match(sources, action, used)
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
