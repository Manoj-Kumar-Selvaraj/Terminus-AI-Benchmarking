#!/usr/bin/env ruby
require "csv"
require "json"
require "fileutils"

SOURCE = "/app/data/kegs.csv"
ACTIONS = "/app/data/deposits.csv"
REPORT = "/app/out/deposit_report.csv"
SUMMARY = "/app/out/deposit_summary.json"

ALLOWED = ["HALF", "CORNELIUS"]

def load_csv(path)
  CSV.read(path, headers: true).map(&:to_h)
end

def amount(row)
  row["amount_cents"].to_i
end

def matched?(source, action)
  source["keg_id"].to_s[0, 8] == action["keg_id"].to_s[0, 8] &&
    source["distributor_id"] == action["distributor_id"] &&
    amount(source) == amount(action) &&
    source["status"] == "RETURNED" &&
    ALLOWED.include?(action["keg_type"]) &&
    source["keg_type"] == action["keg_type"]
end

sources = load_csv(SOURCE)
actions = load_csv(ACTIONS)
FileUtils.mkdir_p(File.dirname(REPORT))
matched_count = 0
matched_amount = 0
unmatched_count = 0
unmatched_amount = 0
CSV.open(REPORT, "w") do |csv|
  csv << ["keg_id", "distributor_id", "keg_type", "amount_cents", "status"]
  actions.each do |action|
    found = sources.find { |source| matched?(source, action) }
    if found
      matched_count += 1
      matched_amount -= amount(action)
      csv << [action["keg_id"], action["distributor_id"], action["keg_type"], action["amount_cents"], "MATCHED"]
    else
      unmatched_count += 1
      unmatched_amount += amount(action)
      csv << [action["keg_id"], action["distributor_id"], "", action["amount_cents"], "UNMATCHED"]
    end
  end
end
File.write(SUMMARY, JSON.generate({matched_count: matched_count, matched_amount_cents: matched_amount, unmatched_count: unmatched_count, unmatched_amount_cents: unmatched_amount}))
