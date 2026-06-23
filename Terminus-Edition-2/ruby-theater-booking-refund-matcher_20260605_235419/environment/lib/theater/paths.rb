# frozen_string_literal: true

module Theater
  module Paths
    APP = "/app"
    BOOKINGS = "#{APP}/data/bookings.csv"
    REFUNDS = "#{APP}/data/refunds.csv"
    REPORT = "#{APP}/out/refund_report.csv"
    SUMMARY = "#{APP}/out/refund_summary.json"
    CALENDAR = "#{APP}/config/cutoff_calendar.txt"
    METHODS = "#{APP}/config/methods.csv"
    ALIASES = "#{APP}/config/seat_aliases.json"
    SCHEMA = "#{APP}/config/report_schema.json"
    APP_CONFIG = "#{APP}/config/app.toml"
  end
end
