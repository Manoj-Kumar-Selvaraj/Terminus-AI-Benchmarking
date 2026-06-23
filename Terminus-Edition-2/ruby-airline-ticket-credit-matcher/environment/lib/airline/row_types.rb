# frozen_string_literal: true

module Airline
  TicketRow = Struct.new(:id, :traveler_id, :amount, :status, :fare_class, :flight_date, keyword_init: true)
  CreditRow = Struct.new(:id, :traveler_id, :amount, :fare_class, :credit_date, :raw_amount, keyword_init: true)
end
