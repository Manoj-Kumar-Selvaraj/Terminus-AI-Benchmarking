# frozen_string_literal: true

require "csv"
require "json"
require "fileutils"
require_relative "paths"

module Airline
  class ReportWriter
    def write(rows, summary)
      FileUtils.mkdir_p(File.dirname(Paths::REPORT))
      CSV.open(Paths::REPORT, "w") do |csv|
        csv << %w[ticket_id traveler_id fare_class amount_cents status]
        rows.each { |row| csv << row }
      end
      File.write(Paths::SUMMARY, JSON.generate(summary))
    end
  end
end
