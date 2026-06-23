# frozen_string_literal: true

module Airline
  class Matcher
    LEGACY_ALLOWED = %w[ECONOMY FIRST].freeze

    def match?(ticket, credit)
      ticket.id.to_s[0, 8] == credit.id.to_s[0, 8] &&
        ticket.traveler_id == credit.traveler_id &&
        ticket.amount == credit.amount &&
        ticket.status == "FLOWN" &&
        LEGACY_ALLOWED.include?(credit.fare_class) &&
        ticket.fare_class == credit.fare_class
    end

    def pick(tickets, credit)
      tickets.find { |ticket| match?(ticket, credit) }
    end
  end
end
