#!/usr/bin/env bash
set -euo pipefail
cat > /app/cmd/normalize/main.go <<'GO'
package main

import (
	"encoding/csv"
	"fmt"
	"os"
	"strings"
)

func norm(v string) string { return strings.ToUpper(strings.TrimSpace(v)) }

func main() {
	if len(os.Args) < 2 { return }
	value := norm(os.Args[1])
	if len(os.Args) >= 3 {
		if f, err := os.Open(os.Args[2]); err == nil {
			defer f.Close()
			rows, _ := csv.NewReader(f).ReadAll()
			for _, row := range rows[1:] {
				if len(row) >= 2 && norm(row[0]) == value {
					fmt.Print(norm(row[1]))
					return
				}
			}
		}
	}
	fmt.Print(value)
}
GO
cat > /app/app/reconcile.rb <<'RUBY'
require 'csv'
require 'json'
require 'fileutils'
require 'shellwords'

LEVEL = 3
APP = '/app'
SOURCES = File.join(APP, 'data', 'sources.csv')
ACTIONS = File.join(APP, 'data', 'actions.csv')
ALIASES = File.join(APP, 'config', 'kind_aliases.csv')
WINDOWS = File.join(APP, 'config', 'windows.csv')
POLICY = File.join(APP, 'config', 'policy.csv')
CALENDAR = File.join(APP, 'config', 'calendar.txt')
TOLERANCE = File.join(APP, 'config', 'tolerance.conf')
BLOCKLIST = File.join(APP, 'config', 'blocked_accounts.txt')
REPLAY = File.join(APP, 'config', 'replay_ledger.csv')
REPORT = File.join(APP, 'out', 'resolution_report.csv')
SUMMARY = File.join(APP, 'out', 'resolution_summary.json')
AUDIT = File.join(APP, 'out', 'resolution_audit.json')
HELPER = File.join(APP, 'build', 'kindnorm')

FileUtils.mkdir_p(File.join(APP, 'out'))

def clean(v) = v.to_s.strip

def canon(v)
  raw = clean(v)
  return raw.upcase if LEVEL < 2
  out = `#{HELPER} #{Shellwords.escape(raw)} #{Shellwords.escape(ALIASES)}`.strip
  out.empty? ? raw.upcase : out
end

def numeric_ts?(v) = clean(v).match?(/\A\d{14}\z/)
def date_of(v) = clean(v)[0, 8]
def reason_ok?(v) = %w[CREDIT ADJUST RETURN].include?(clean(v).upcase)
def allowed_kinds
  LEVEL >= 2 ? %w[STANDARD PREMIUM VIP] : %w[STANDARD PREMIUM]
end

def amount_ok?(src, act)
  delta = (src[:amount].to_i - act[:amount].to_i).abs
  max_delta = 0
  if LEVEL >= 6 && File.exist?(TOLERANCE)
    File.read(TOLERANCE).each_line do |line|
      key, value = line.strip.split('=', 2)
      max_delta = value.to_i if key == 'max_delta_cents'
    end
  end
  delta <= max_delta
end

def window_ok?(src, act)
  return true if LEVEL < 3
  return false unless numeric_ts?(src[:source_ts]) && numeric_ts?(act[:action_ts])
  return false if act[:action_ts] < src[:source_ts]
  CSV.read(WINDOWS, headers: true).any? do |row|
    clean(row['location_id']) == src[:location_id] && clean(row['state']).upcase == 'OPEN' &&
      numeric_ts?(row['open_ts']) && numeric_ts?(row['close_ts']) &&
      src[:source_ts] >= clean(row['open_ts']) && src[:source_ts] <= clean(row['close_ts']) &&
      act[:action_ts] <= clean(row['close_ts'])
  end
end

def policy
  return {} unless File.exist?(POLICY)
  CSV.read(POLICY, headers: true).each_with_object({}) do |row, memo|
    memo[clean(row['kind']).upcase] = {enabled: clean(row['enabled']).upcase == 'Y', priority: clean(row['priority']).to_i}
  end
end

def policy_ok?(kind, pol)
  return true if LEVEL < 4
  pol.fetch(kind, {enabled: false})[:enabled]
end

def open_dates
  return [] unless File.exist?(CALENDAR)
  File.readlines(CALENDAR).filter_map do |line|
    parts = line.strip.split(/\s+/)
    parts[0] if parts.length >= 2 && parts[1].upcase == 'OPEN'
  end
end

def calendar_ok?(src, act, dates)
  return true if LEVEL < 5
  sdate = date_of(src[:source_ts])
  adate = date_of(act[:action_ts])
  return false unless dates.include?(sdate) && dates.include?(adate)
  return false if adate < sdate
  dates.count { |d| d > sdate && d <= adate } <= 2
end

def blocked_accounts
  return [] unless File.exist?(BLOCKLIST)
  File.readlines(BLOCKLIST).map { |line| clean(line) }.reject(&:empty?)
end

def replayed_actions
  return [] unless File.exist?(REPLAY)
  CSV.read(REPLAY, headers: true).map { |row| clean(row['action_id']) }
end

sources = CSV.read(SOURCES, headers: true).map.with_index do |r, i|
  {source_id: clean(r['source_id']), account_id: clean(r['account_id']), location_id: clean(r['location_id']), kind: canon(r['kind']), amount: clean(r['amount_cents']), source_ts: clean(r['source_ts']), status: clean(r['status']).upcase, lane: clean(r['lane']), row: i, used: false}
end
actions = CSV.read(ACTIONS, headers: true).map.with_index do |r, i|
  {action_id: clean(r['action_id']), source_id: clean(r['source_id']), account_id: clean(r['account_id']), location_id: clean(r['location_id']), kind: canon(r['kind']), amount: clean(r['amount_cents']), action_ts: clean(r['action_ts']), reason: clean(r['reason']).upcase, lane: clean(r['lane']), row: i}
end
pol = policy
dates = open_dates
blocked = blocked_accounts
replayed = replayed_actions
matched_ids = []
unmatched_ids = []
matched_count = unmatched_count = matched_amount = unmatched_amount = 0

CSV.open(REPORT, 'w') do |csv|
  csv << %w[action_id source_id account_id location_id kind amount_cents reason status]
  actions.each do |act|
    candidates = []
    unless LEVEL >= 7 && (blocked.include?(act[:account_id]) || replayed.include?(act[:action_id]))
      sources.each do |src|
        kind_match = LEVEL >= 4 && act[:kind] == 'ANY' ? true : src[:kind] == act[:kind]
        candidates << src if !src[:used] && src[:source_id] == act[:source_id] && src[:account_id] == act[:account_id] && src[:location_id] == act[:location_id] && src[:lane] == act[:lane] && src[:status] == 'ACTIVE' && reason_ok?(act[:reason]) && allowed_kinds.include?(src[:kind]) && kind_match && amount_ok?(src, act) && window_ok?(src, act) && policy_ok?(src[:kind], pol) && calendar_ok?(src, act, dates)
      end
    end
    candidates.sort_by! do |src|
      priority = pol.fetch(src[:kind], {priority: 999})[:priority]
      LEVEL >= 4 ? [-src[:source_ts].to_i, priority, src[:row]] : (LEVEL >= 3 ? [-src[:source_ts].to_i, src[:row]] : [src[:row]])
    end
    best = candidates.first
    amount = act[:amount].to_i
    if best
      best[:used] = true
      matched_count += 1
      matched_amount += amount
      matched_ids << act[:action_id]
      csv << [act[:action_id], act[:source_id], act[:account_id], act[:location_id], best[:kind], act[:amount], act[:reason], 'MATCHED']
    else
      unmatched_count += 1
      unmatched_amount += amount
      unmatched_ids << act[:action_id]
      csv << [act[:action_id], act[:source_id], act[:account_id], act[:location_id], '', act[:amount], act[:reason], 'UNMATCHED']
    end
  end
end
File.write(SUMMARY, JSON.pretty_generate({matched_count: matched_count, matched_amount_cents: matched_amount, unmatched_count: unmatched_count, unmatched_amount_cents: unmatched_amount}))
if LEVEL >= 7
  File.write(AUDIT, JSON.pretty_generate({matched_action_ids: matched_ids, unmatched_action_ids: unmatched_ids, blocked_accounts: blocked}))
end
RUBY
/app/scripts/run_batch.sh
