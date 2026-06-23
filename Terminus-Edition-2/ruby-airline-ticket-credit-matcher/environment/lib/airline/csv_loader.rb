# frozen_string_literal: true

require "csv"
require_relative "paths"
require_relative "row_types"

module Airline
  class CsvLoader
    def load_tickets
      CSV.read(Paths::TICKETS, headers: true).map do |row|
        TicketRow.new(
          id: row["ticket_id"].to_s.strip,
          traveler_id: row["traveler_id"],
          amount: row["amount_cents"].to_s.strip.to_i,
          status: row["status"],
          fare_class: row["fare_class"],
          flight_date: row["flight_date"].to_s
        )
      end
    end

    def load_credits
      CSV.read(Paths::CREDITS, headers: true).map do |row|
        CreditRow.new(
          id: row["ticket_id"].to_s.strip,
          traveler_id: row["traveler_id"],
          amount: row["amount_cents"].to_s.strip.to_i,
          fare_class: row["fare_class"],
          credit_date: row["credit_date"].to_s,
          raw_amount: row["amount_cents"]
        )
      end
    end
  end
end
