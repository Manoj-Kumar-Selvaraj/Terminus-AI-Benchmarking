#!/usr/bin/env bash
set -euo pipefail
cat > /app/lib/reconcile.rb <<'RUBY'
#!/usr/bin/env ruby
require "csv"
require "json"
require "fileutils"
require "date"

LEVEL = 3
APP = "/app"
APPOINTMENTS = File.join(APP, "data", "appointments.csv")
REFUNDS = File.join(APP, "data", "refunds.csv")
REPORT = File.join(APP, "out", "refund_report.csv")
SUMMARY = File.join(APP, "out", "refund_summary.json")
SELECTION = File.join(APP, "out", "appointment_selection.csv")
CALENDAR = File.join(APP, "config", "cutoff_calendar.txt")
ALIASES = File.join(APP, "config", "service_aliases.csv")
METHODS = File.join(APP, "config", "methods.csv")
LIMITS = File.join(APP, "config", "client_limits.csv")
SUPPORTED = ["MASSAGE", "FACIAL", "SAUNA"].freeze
DEFAULT_ALIASES = {"MSG" => "MASSAGE", "FAC" => "FACIAL", "SAU" => "SAUNA"}.freeze
INF_PRIORITY = 1_000_000

def clean(value)
  value.nil? ? "" : value.to_s.strip
end

def token(value)
  clean(value).upcase
end

def read_csv(path)
  return [] unless File.exist?(path)
  CSV.read(path, headers: true).map(&:to_h)
rescue CSV::MalformedCSVError
  []
end

def csv_headers(path)
  return [] unless File.exist?(path)
  table = CSV.read(path, headers: true)
  table.headers || []
rescue CSV::MalformedCSVError
  []
end

def parse_positive_int(value)
  raw = clean(value)
  return [false, nil, raw] unless raw.match?(/\A\d+\z/)
  amount = raw.to_i
  return [false, nil, raw] unless amount.positive?
  [true, amount, raw]
end

def truth_token(value)
  v = token(value)
  return true if v == "TRUE"
  return false if v == "FALSE"
  nil
end

def enabled_alias?(row)
  return true unless row.key?("enabled")
  truth_token(row["enabled"]) == true
end

def load_aliases
  aliases = {}
  if LEVEL >= 2 && File.exist?(ALIASES)
    read_csv(ALIASES).each do |row|
      a = token(row["alias"])
      c = token(row["canonical"])
      next if a.empty? || aliases.key?(a)
      next unless enabled_alias?(row)
      next unless SUPPORTED.include?(c)
      aliases[a] = c
    end
  elsif LEVEL >= 2
    aliases.merge!(DEFAULT_ALIASES)
  end
  aliases
end

def canonical_service(value, aliases, allow_any: false)
  v = token(value)
  return "ANY" if allow_any && v == "ANY"
  return v if SUPPORTED.include?(v)
  aliases[v]
end

def valid_iso_date(value)
  s = clean(value)
  return nil unless s.match?(/\A\d{4}-\d{2}-\d{2}\z/)
  d = Date.iso8601(s)
  return nil unless d.strftime("%Y-%m-%d") == s
  d
rescue ArgumentError
  nil
end

def load_open_dates
  dates = {}
  return dates unless File.exist?(CALENDAR)
  File.readlines(CALENDAR).each do |line|
    stripped = line.strip
    next if stripped.empty? || stripped.start_with?("#")
    parts = stripped.split(/\s+/)
    next if parts.length < 2
    d = valid_iso_date(parts[0])
    next unless d
    dates[parts[0]] = d if parts[1].to_s.upcase == "OPEN"
  end
  dates
end

def load_methods(aliases)
  default = {}
  SUPPORTED.each_with_index { |svc, idx| default[svc] = {enabled: true, priority: idx + 1} }
  return default unless LEVEL >= 4 && File.exist?(METHODS)
  policy = {}
  read_csv(METHODS).each_with_index do |row, idx|
    service = canonical_service(row["service_area"], aliases)
    enabled = truth_token(row["enabled"])
    next if service.nil? || enabled.nil?
    raw_priority = clean(row["priority"])
    priority = raw_priority.match?(/\A\d+\z/) ? raw_priority.to_i : INF_PRIORITY + idx
    policy[service] = {enabled: enabled, priority: priority}
  end
  policy
end

def parse_allow_any(row)
  return false unless row.key?("allow_any")
  truth_token(row["allow_any"])
end

def load_limits(aliases)
  return nil unless LEVEL >= 5 && File.exist?(LIMITS)
  limits = {}
  read_csv(LIMITS).each do |row|
    client = clean(row["client_id"])
    service = canonical_service(row["service_area"], aliases)
    amount_valid, amount, = parse_positive_int(row["max_refund_cents"])
    enabled = truth_token(row["enabled"])
    any = parse_allow_any(row)
    next if client.empty? || service.nil? || !amount_valid || enabled.nil? || any.nil?
    limits[[client, service]] = {enabled: enabled, max: amount, allow_any: any}
  end
  limits
end

def date_mode?
  return false unless LEVEL >= 3
  csv_headers(APPOINTMENTS).include?("service_date") || csv_headers(REFUNDS).include?("refund_date")
end

def load_sources(aliases)
  read_csv(APPOINTMENTS).map.with_index do |row, idx|
    amount_valid, amount, raw_amount = parse_positive_int(row["amount_cents"])
    {
      index: idx,
      id: clean(row["appointment_id"]),
      client: clean(row["client_id"]),
      amount_valid: amount_valid,
      amount: amount,
      raw_amount: raw_amount,
      status: token(row["status"]),
      service: canonical_service(row["service_area"], aliases),
      service_date_raw: clean(row["service_date"]),
      service_date: valid_iso_date(row["service_date"])
    }
  end
end

def load_refunds(aliases)
  read_csv(REFUNDS).map.with_index do |row, idx|
    amount_valid, amount, raw_amount = parse_positive_int(row["amount_cents"])
    {
      index: idx,
      id: clean(row["appointment_id"]),
      client: clean(row["client_id"]),
      amount_valid: amount_valid,
      amount: amount,
      raw_amount: raw_amount,
      service: canonical_service(row["service_area"], aliases, allow_any: LEVEL >= 4),
      refund_date_raw: clean(row["refund_date"]),
      refund_date: valid_iso_date(row["refund_date"])
    }
  end
end

def service_enabled?(service, methods)
  entry = methods[service]
  !entry.nil? && entry[:enabled] == true
end

def service_priority(service, methods)
  entry = methods[service]
  entry ? entry[:priority] : INF_PRIORITY * 2
end

def base_candidate?(source, refund)
  return false unless source[:id] == refund[:id]
  return false unless source[:client] == refund[:client]
  return false unless source[:amount_valid] && refund[:amount_valid]
  return false unless source[:amount] == refund[:amount]
  return false unless source[:status] == "COMPLETED"
  return false if source[:service].nil? || refund[:service].nil?
  true
end

def service_candidate?(source, refund, methods)
  return false unless service_enabled?(source[:service], methods)
  if refund[:service] == "ANY"
    LEVEL >= 4
  else
    source[:service] == refund[:service]
  end
end

def date_candidate?(source, refund, open_dates, dates_enabled)
  return true unless dates_enabled
  return false if source[:service_date].nil? || refund[:refund_date].nil?
  return false unless open_dates.key?(refund[:refund_date_raw])
  refund[:refund_date] <= source[:service_date]
end

def limit_candidate?(source, refund, limits)
  return true if limits.nil?
  policy = limits[[refund[:client], source[:service]]]
  return false if policy.nil? || policy[:enabled] != true
  return false if refund[:amount].nil? || refund[:amount] > policy[:max]
  return false if refund[:service] == "ANY" && policy[:allow_any] != true
  true
end

def better_candidate?(candidate, incumbent, refund, methods, dates_enabled)
  return true if incumbent.nil?
  if dates_enabled
    cd = candidate[:service_date]
    id = incumbent[:service_date]
    return cd > id if cd != id
  end
  if refund[:service] == "ANY"
    cp = service_priority(candidate[:service], methods)
    ip = service_priority(incumbent[:service], methods)
    return cp < ip if cp != ip
  end
  candidate[:index] < incumbent[:index]
end

def find_match(sources, refund, used, methods, open_dates, dates_enabled, limits)
  return nil unless refund[:amount_valid]
  best_idx = nil
  sources.each_with_index do |source, idx|
    next if used[idx]
    next unless base_candidate?(source, refund)
    next unless service_candidate?(source, refund, methods)
    next unless date_candidate?(source, refund, open_dates, dates_enabled)
    next unless limit_candidate?(source, refund, limits)
    if best_idx.nil? || better_candidate?(source, sources[best_idx], refund, methods, dates_enabled)
      best_idx = idx
    end
  end
  best_idx
end

aliases = load_aliases
methods = load_methods(aliases)
limits = load_limits(aliases)
sources = load_sources(aliases)
refunds = load_refunds(aliases)
dates_enabled = date_mode?
open_dates = dates_enabled ? load_open_dates : {}
used = Array.new(sources.length, false)
FileUtils.mkdir_p(File.dirname(REPORT))
matched_count = 0
matched_amount = 0
unmatched_count = 0
unmatched_amount = 0
selection_rows = []
CSV.open(REPORT, "w") do |csv|
  csv << ["appointment_id", "client_id", "service_area", "amount_cents", "status"]
  refunds.each_with_index do |refund, refund_row|
    idx = find_match(sources, refund, used, methods, open_dates, dates_enabled, limits)
    if idx
      used[idx] = true
      matched_count += 1
      matched_amount += refund[:amount]
      csv << [refund[:id], refund[:client], sources[idx][:service], refund[:raw_amount], "MATCHED"]
      if LEVEL >= 3 && dates_enabled
        selection_rows << [refund_row, idx, sources[idx][:service_date_raw]]
      end
    else
      unmatched_count += 1
      unmatched_amount += refund[:amount] if refund[:amount_valid]
      csv << [refund[:id], refund[:client], "", refund[:raw_amount], "UNMATCHED"]
    end
  end
end
if LEVEL >= 3
  CSV.open(SELECTION, "w") do |csv|
    csv << ["refund_row", "appointment_row", "service_date"]
    selection_rows.each { |row| csv << row } if dates_enabled
  end
end
File.write(SUMMARY, JSON.generate({matched_count: matched_count, matched_amount_cents: matched_amount, unmatched_count: unmatched_count, unmatched_amount_cents: unmatched_amount}))

RUBY
chmod +x /app/lib/reconcile.rb
/app/scripts/run_batch.sh
