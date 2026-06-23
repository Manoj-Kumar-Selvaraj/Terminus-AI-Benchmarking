# frozen_string_literal: true

require "csv"
require_relative "paths"
require_relative "row_types"
require_relative "text_normalize"

module Theater
  class CsvLoader
    def load_bookings
      CSV.read(Paths::BOOKINGS, headers: true).map { |row| booking_from(row) }
    end

    def load_refunds
      CSV.read(Paths::REFUNDS, headers: true).map { |row| refund_from(row) }
    end

    private

    def booking_from(row)
      BookingRow.new(
        id: TextNormalize.clean(row["booking_id"]),
        patron_id: row["patron_id"],
        amount: TextNormalize.clean(row["amount_cents"]).to_i,
        status: row["status"],
        seat_zone: row["seat_zone"],
        show_date: row["show_date"].to_s
      )
    end

    def refund_from(row)
      RefundRow.new(
        id: TextNormalize.clean(row["booking_id"]),
        patron_id: row["patron_id"],
        amount: TextNormalize.clean(row["amount_cents"]).to_i,
        seat_zone: row["seat_zone"],
        refund_date: row["refund_date"].to_s,
        raw_amount: row["amount_cents"]
      )
    end
  end
end
