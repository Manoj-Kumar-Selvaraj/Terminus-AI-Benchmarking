# frozen_string_literal: true

module Charity
  module Paths
    APP = "/app"
    PLEDGES = "#{APP}/data/pledges.csv"
    ADJUSTMENTS = "#{APP}/data/adjustments.csv"
    REPORT = "#{APP}/out/adjustment_report.csv"
    SUMMARY = "#{APP}/out/adjustment_summary.json"
    CALENDAR = "#{APP}/config/cutoff_calendar.txt"
    METHODS = "#{APP}/config/methods.csv"
    ALIASES = "#{APP}/config/fund_aliases.json"
    SCHEMA = "#{APP}/config/report_schema.json"
    APP_CONFIG = "#{APP}/config/app.toml"
  end
end
