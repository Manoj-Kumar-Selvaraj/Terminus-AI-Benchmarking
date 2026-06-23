# frozen_string_literal: true

require_relative "csv_loader"
require_relative "matcher"
require_relative "report_writer"

module Airline
  class Runner
    def self.run
      new.run
    end

    def run
      tickets = CsvLoader.new.load_tickets
      credits = CsvLoader.new.load_credits
      matched_count = 0
      matched_amount = 0
      unmatched_count = 0
      unmatched_amount = 0
      rows = credits.map do |credit|
        if Matcher.new.pick(tickets, credit)
          matched_count += 1
          matched_amount -= credit.amount
          [credit.id, credit.traveler_id, credit.fare_class, credit.raw_amount, "MATCHED"]
        else
          unmatched_count += 1
          unmatched_amount += credit.amount
          [credit.id, credit.traveler_id, "", credit.raw_amount, "UNMATCHED"]
        end
      end
      ReportWriter.new.write(
        rows,
        matched_count: matched_count,
        matched_amount_cents: matched_amount,
        unmatched_count: unmatched_count,
        unmatched_amount_cents: unmatched_amount
      )
    end
  end
end
