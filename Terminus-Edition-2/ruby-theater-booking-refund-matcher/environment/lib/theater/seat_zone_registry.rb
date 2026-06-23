# frozen_string_literal: true

require "csv"
require "json"
require_relative "paths"
require_relative "text_normalize"

module Theater
  class SeatZoneRegistry
    def initialize
      @allowed = load_enabled_zones
      @aliases = load_aliases
    end

    def canonical(seat_zone)
      token = TextNormalize.upper(seat_zone)
      @aliases.fetch(token, token)
    end

    def allowed?(seat_zone)
      @allowed.include?(canonical(seat_zone))
    end

    private

    def load_enabled_zones
      CSV.read(Paths::METHODS, headers: true).filter_map do |row|
        next unless TextNormalize.upper(row["enabled"]) == "TRUE"

        TextNormalize.upper(row["seat_zone"])
      end
    end

    def load_aliases
      return {} unless File.exist?(Paths::ALIASES)

      JSON.parse(File.read(Paths::ALIASES))
    end
  end
end
