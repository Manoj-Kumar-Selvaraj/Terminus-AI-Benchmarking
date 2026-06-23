# frozen_string_literal: true

require_relative "fund_registry"

module Charity
  class Matcher
    LEGACY_ALLOWED = %w[GENERAL RELIEF].freeze

    def initialize(registry: FundRegistry.new)
      @registry = registry
    end

    def match?(pledge, adjustment)
      pledge.id.to_s[0, 8] == adjustment.id.to_s[0, 8] &&
        pledge.donor_id == adjustment.donor_id &&
        pledge.amount == adjustment.amount &&
        pledge.status == "BOOKED" &&
        LEGACY_ALLOWED.include?(adjustment.fund) &&
        pledge.fund == adjustment.fund
    end

    def pick(pledges, adjustment)
      pledges.find { |pledge| match?(pledge, adjustment) }
    end
  end
end
