# frozen_string_literal: true

require_relative "csv_loader"
require_relative "matcher"
require_relative "report_writer"

module Charity
  class Runner
    def self.run
      new.run
    end

    def initialize(loader: CsvLoader.new, matcher: Matcher.new, writer: ReportWriter.new)
      @loader = loader
      @matcher = matcher
      @writer = writer
    end

    def run
      pledges = @loader.load_pledges
      adjustments = @loader.load_adjustments
      matched_count = 0
      matched_amount = 0
      unmatched_count = 0
      unmatched_amount = 0
      rows = adjustments.map do |adjustment|
        pledge = @matcher.pick(pledges, adjustment)
        if pledge
          matched_count += 1
          matched_amount -= adjustment.amount
          [adjustment.id, adjustment.donor_id, adjustment.fund, adjustment.raw_amount, "MATCHED"]
        else
          unmatched_count += 1
          unmatched_amount += adjustment.amount
          [adjustment.id, adjustment.donor_id, "", adjustment.raw_amount, "UNMATCHED"]
        end
      end
      @writer.write(
        rows,
        {
          matched_count: matched_count,
          matched_amount_cents: matched_amount,
          unmatched_count: unmatched_count,
          unmatched_amount_cents: unmatched_amount
        }
      )
    end
  end
end
