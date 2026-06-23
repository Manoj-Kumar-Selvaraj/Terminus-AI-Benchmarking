#!/usr/bin/env ruby
require "csv"
require_relative "../lib/theater/paths"

errors = []
[Paths::BOOKINGS, Paths::REFUNDS].each do |path|
  errors << "missing file: #{path}" unless File.exist?(path)
end
exit 1 if errors.any?

booking_headers = CSV.read(Paths::BOOKINGS, headers: true).headers
refund_headers = CSV.read(Paths::REFUNDS, headers: true).headers
%w[booking_id patron_id amount_cents status seat_zone].each do |col|
  errors << "bookings.csv missing column: #{col}" unless booking_headers.include?(col)
end
%w[booking_id patron_id amount_cents seat_zone].each do |col|
  errors << "refunds.csv missing column: #{col}" unless refund_headers.include?(col)
end

if errors.any?
  warn errors.join("\n")
  exit 1
end
puts "input validation ok"
