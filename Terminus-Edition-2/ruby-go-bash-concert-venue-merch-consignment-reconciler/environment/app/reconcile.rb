require 'csv'
require 'json'
require 'fileutils'

APP = '/app'
SOURCES = File.join(APP, 'data', 'sources.csv')
ACTIONS = File.join(APP, 'data', 'actions.csv')
REPORT = File.join(APP, 'out', 'resolution_report.csv')
SUMMARY = File.join(APP, 'out', 'resolution_summary.json')

FileUtils.mkdir_p(File.join(APP, 'out'))
sources = CSV.read(SOURCES, headers: true).map { |r| r.to_h }
actions = CSV.read(ACTIONS, headers: true).map { |r| r.to_h }
used = {}
matched_count = unmatched_count = matched_amount = unmatched_amount = 0

CSV.open(REPORT, 'w') do |csv|
  csv << %w[action_id source_id account_id location_id kind amount_cents reason status]
  actions.each do |act|
    found = sources.find { |src| src['source_id'].to_s.start_with?(act['source_id'].to_s[0, 6]) && !used[src['source_id']] }
    amount = act['amount_cents'].to_i
    if found
      used[found['source_id']] = true
      matched_count += 1
      matched_amount += amount
      csv << [act['action_id'], act['source_id'], act['account_id'], act['location_id'], found['kind'], act['amount_cents'], act['reason'], 'MATCHED']
    else
      unmatched_count += 1
      unmatched_amount += amount
      csv << [act['action_id'], act['source_id'], act['account_id'], act['location_id'], '', act['amount_cents'], act['reason'], 'UNMATCHED']
    end
  end
end
File.write(SUMMARY, JSON.pretty_generate({matched_count: matched_count, matched_amount_cents: matched_amount, unmatched_count: unmatched_count, unmatched_amount_cents: unmatched_amount}))