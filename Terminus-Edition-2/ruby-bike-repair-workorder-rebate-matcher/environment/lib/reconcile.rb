#!/usr/bin/env ruby
require "csv"
require "json"
require "fileutils"

SOURCE = "/app/data/workorders.csv"
ACTIONS = "/app/data/rebates.csv"
REPORT = "/app/out/rebate_report.csv"
SUMMARY = "/app/out/rebate_summary.json"

ALLOWED = ["TUNEUP", "DRIVETRAIN"]

def load_csv(path)
  CSV.read(path, headers: true).map(&:to_h)
end

def amount(row)
  row["amount_cents"].to_i
end

def matched?(source, action)
  source["workorder_id"].to_s[0, 8] == action["workorder_id"].to_s[0, 8] &&
    source["rider_id"] == action["rider_id"] &&
    amount(source) == amount(action) &&
    source["status"] == "CLOSED" &&
    ALLOWED.include?(action["repair_type"]) &&
    source["repair_type"] == action["repair_type"]
end

sources = load_csv(SOURCE)
actions = load_csv(ACTIONS)
FileUtils.mkdir_p(File.dirname(REPORT))
matched_count = 0
matched_amount = 0
unmatched_count = 0
unmatched_amount = 0
CSV.open(REPORT, "w") do |csv|
  csv << ["workorder_id", "rider_id", "repair_type", "amount_cents", "status"]
  actions.each do |action|
    found = sources.find { |source| matched?(source, action) }
    if found
      matched_count += 1
      matched_amount -= amount(action)
      csv << [action["workorder_id"], action["rider_id"], action["repair_type"], action["amount_cents"], "MATCHED"]
    else
      unmatched_count += 1
      unmatched_amount += amount(action)
      csv << [action["workorder_id"], action["rider_id"], "", action["amount_cents"], "UNMATCHED"]
    end
  end
end
File.write(SUMMARY, JSON.generate({matched_count: matched_count, matched_amount_cents: matched_amount, unmatched_count: unmatched_count, unmatched_amount_cents: unmatched_amount}))
