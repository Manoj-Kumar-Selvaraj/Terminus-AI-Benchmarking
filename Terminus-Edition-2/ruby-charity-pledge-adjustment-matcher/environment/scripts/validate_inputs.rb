#!/usr/bin/env ruby
require "csv"
require_relative "../lib/charity/paths"

errors = []
[Paths::PLEDGES, Paths::ADJUSTMENTS].each do |path|
  errors << "missing file: #{path}" unless File.exist?(path)
end
raise SystemExit(1) if errors.any?

pledge_headers = CSV.read(Paths::PLEDGES, headers: true).headers
adj_headers = CSV.read(Paths::ADJUSTMENTS, headers: true).headers
required_pledge = %w[pledge_id donor_id amount_cents status fund]
required_adj = %w[pledge_id donor_id amount_cents fund]
(required_pledge - pledge_headers).each { |col| errors << "pledges.csv missing column: #{col}" }
(required_adj - adj_headers).each { |col| errors << "adjustments.csv missing column: #{col}" }

if errors.any?
  warn errors.join("\n")
  exit 1
end
puts "input validation ok"
