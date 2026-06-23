#!/usr/bin/env ruby
require "csv"
require "json"
require "fileutils"

SOURCE = "/app/data/deliveries.csv"
ACTIONS = "/app/data/refunds.csv"
REPORT = "/app/out/refund_report.csv"
SUMMARY = "/app/out/refund_summary.json"

ALLOWED = ["SOIL", "PLANTS"]

def load_csv(path)
  CSV.read(path, headers: true).map(&:to_h)
end

def amount(row)
  row["amount_cents"].to_i
end

def matched?(source, action)
  source["delivery_id"].to_s[0, 8] == action["delivery_id"].to_s[0, 8] &&
    source["customer_id"] == action["customer_id"] &&
    amount(source) == amount(action) &&
    source["status"] == "DROPPED" &&
    ALLOWED.include?(action["load_type"]) &&
    source["load_type"] == action["load_type"]
end

sources = load_csv(SOURCE)
actions = load_csv(ACTIONS)
FileUtils.mkdir_p(File.dirname(REPORT))
matched_count = 0
matched_amount = 0
unmatched_count = 0
unmatched_amount = 0
CSV.open(REPORT, "w") do |csv|
  csv << ["delivery_id", "customer_id", "load_type", "amount_cents", "status"]
  actions.each do |action|
    found = sources.find { |source| matched?(source, action) }
    if found
      matched_count += 1
      matched_amount -= amount(action)
      csv << [action["delivery_id"], action["customer_id"], action["load_type"], action["amount_cents"], "MATCHED"]
    else
      unmatched_count += 1
      unmatched_amount += amount(action)
      csv << [action["delivery_id"], action["customer_id"], "", action["amount_cents"], "UNMATCHED"]
    end
  end
end
File.write(SUMMARY, JSON.generate({matched_count: matched_count, matched_amount_cents: matched_amount, unmatched_count: unmatched_count, unmatched_amount_cents: unmatched_amount}))
