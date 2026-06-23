#!/usr/bin/env ruby
require "csv"
require "json"
require "fileutils"

SOURCE = "/app/data/orders.csv"
ACTIONS = "/app/data/credits.csv"
REPORT = "/app/out/credit_report.csv"
SUMMARY = "/app/out/credit_summary.json"

ALLOWED = ["FICTION", "COMIC"]

def load_csv(path)
  CSV.read(path, headers: true).map(&:to_h)
end

def amount(row)
  row["amount_cents"].to_i
end

def matched?(source, action)
  source["order_id"].to_s[0, 8] == action["order_id"].to_s[0, 8] &&
    source["customer_id"] == action["customer_id"] &&
    amount(source) == amount(action) &&
    source["status"] == "RECEIVED" &&
    ALLOWED.include?(action["section"]) &&
    source["section"] == action["section"]
end

sources = load_csv(SOURCE)
actions = load_csv(ACTIONS)
FileUtils.mkdir_p(File.dirname(REPORT))
matched_count = 0
matched_amount = 0
unmatched_count = 0
unmatched_amount = 0
CSV.open(REPORT, "w") do |csv|
  csv << ["order_id", "customer_id", "section", "amount_cents", "status"]
  actions.each do |action|
    found = sources.find { |source| matched?(source, action) }
    if found
      matched_count += 1
      matched_amount -= amount(action)
      csv << [action["order_id"], action["customer_id"], action["section"], action["amount_cents"], "MATCHED"]
    else
      unmatched_count += 1
      unmatched_amount += amount(action)
      csv << [action["order_id"], action["customer_id"], "", action["amount_cents"], "UNMATCHED"]
    end
  end
end
File.write(SUMMARY, JSON.generate({matched_count: matched_count, matched_amount_cents: matched_amount, unmatched_count: unmatched_count, unmatched_amount_cents: unmatched_amount}))
