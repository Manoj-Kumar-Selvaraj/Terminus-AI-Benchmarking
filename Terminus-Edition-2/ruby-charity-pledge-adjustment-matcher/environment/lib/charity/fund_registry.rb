# frozen_string_literal: true

require "csv"
require "json"
require_relative "paths"
require_relative "text_normalize"

module Charity
  class FundRegistry
    def initialize
      @allowed = load_enabled_funds
      @aliases = load_aliases
    end

    def canonical(fund)
      token = TextNormalize.upper(fund)
      @aliases.fetch(token, token)
    end

    def allowed?(fund)
      @allowed.include?(canonical(fund))
    end

    def allowed_funds
      @allowed.dup
    end

    def alias_map
      @aliases.dup
    end

    private

    def load_enabled_funds
      CSV.read(Paths::METHODS, headers: true).filter_map do |row|
        next unless TextNormalize.upper(row["enabled"]) == "TRUE"

        TextNormalize.upper(row["fund"])
      end
    end

    def load_aliases
      return {} unless File.exist?(Paths::ALIASES)

      JSON.parse(File.read(Paths::ALIASES))
    end
  end
end
