# frozen_string_literal: true

require_relative "csv_loader"
require_relative "matcher"
require_relative "report_writer"

module Theater
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
      bookings = @loader.load_bookings
      refunds = @loader.load_refunds
      matched_count = 0
      matched_amount = 0
      unmatched_count = 0
      unmatched_amount = 0
      rows = refunds.map do |refund|
        booking = @matcher.pick(bookings, refund)
        if booking
          matched_count += 1
          matched_amount -= refund.amount
          [refund.id, refund.patron_id, refund.seat_zone, refund.raw_amount, "MATCHED"]
        else
          unmatched_count += 1
          unmatched_amount += refund.amount
          [refund.id, refund.patron_id, "", refund.raw_amount, "UNMATCHED"]
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
