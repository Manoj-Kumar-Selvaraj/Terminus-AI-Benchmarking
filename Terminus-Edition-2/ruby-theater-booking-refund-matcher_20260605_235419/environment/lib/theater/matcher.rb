# frozen_string_literal: true

require_relative "seat_zone_registry"

module Theater
  class Matcher
    LEGACY_ALLOWED = %w[ORCH BALC].freeze

    def initialize(registry: SeatZoneRegistry.new)
      @registry = registry
    end

    def match?(booking, refund)
      booking.id.to_s[0, 8] == refund.id.to_s[0, 8] &&
        booking.patron_id == refund.patron_id &&
        booking.amount == refund.amount &&
        booking.status == "TICKETED" &&
        LEGACY_ALLOWED.include?(refund.seat_zone) &&
        booking.seat_zone == refund.seat_zone
    end

    def pick(bookings, refund)
      bookings.find { |booking| match?(booking, refund) }
    end
  end
end
