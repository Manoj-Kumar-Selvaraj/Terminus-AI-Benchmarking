# frozen_string_literal: true

require "csv"
require "json"
require "fileutils"
require_relative "paths"

module Charity
  class ReportWriter
    HEADERS = %w[pledge_id donor_id fund amount_cents status].freeze

    def initialize(report_path: Paths::REPORT, summary_path: Paths::SUMMARY)
      @report_path = report_path
      @summary_path = summary_path
    end

    def write(rows, summary)
      FileUtils.mkdir_p(File.dirname(@report_path))
      CSV.open(@report_path, "w") do |csv|
        csv << HEADERS
        rows.each { |row| csv << row }
      end
      File.write(@summary_path, JSON.generate(summary))
    end
  end
end
