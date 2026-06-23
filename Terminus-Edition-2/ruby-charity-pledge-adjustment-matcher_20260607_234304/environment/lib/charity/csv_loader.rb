# frozen_string_literal: true

require "csv"
require_relative "paths"
require_relative "row_types"
require_relative "text_normalize"
require_relative "fund_registry"

module Charity
  class CsvLoader
    def initialize(registry: FundRegistry.new)
      @registry = registry
    end

    def load_pledges
      CSV.read(Paths::PLEDGES, headers: true).map { |row| pledge_from(row) }
    end

    def load_adjustments
      CSV.read(Paths::ADJUSTMENTS, headers: true).map { |row| adjustment_from(row) }
    end

    def pledge_headers
      CSV.read(Paths::PLEDGES, headers: true).headers
    end

    def adjustment_headers
      CSV.read(Paths::ADJUSTMENTS, headers: true).headers
    end

    private

    def pledge_from(row)
      PledgeRow.new(
        id: TextNormalize.clean(row["pledge_id"]),
        donor_id: row["donor_id"],
        amount: TextNormalize.clean(row["amount_cents"]).to_i,
        status: row["status"],
        fund: row["fund"],
        pledge_due: row["pledge_due"].to_s
      )
    end

    def adjustment_from(row)
      AdjustmentRow.new(
        id: TextNormalize.clean(row["pledge_id"]),
        donor_id: row["donor_id"],
        amount: TextNormalize.clean(row["amount_cents"]).to_i,
        fund: row["fund"],
        adjustment_date: row["adjustment_date"].to_s,
        raw_amount: row["amount_cents"]
      )
    end
  end
end
