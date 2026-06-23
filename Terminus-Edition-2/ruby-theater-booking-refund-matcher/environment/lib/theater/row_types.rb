# frozen_string_literal: true

module Theater
  BookingRow = Struct.new(:id, :patron_id, :amount, :status, :seat_zone, :show_date, keyword_init: true)
  RefundRow = Struct.new(:id, :patron_id, :amount, :seat_zone, :refund_date, :raw_amount, keyword_init: true)
end
