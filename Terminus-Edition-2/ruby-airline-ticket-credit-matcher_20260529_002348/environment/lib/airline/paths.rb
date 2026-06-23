# frozen_string_literal: true

module Airline
  module Paths
    APP = "/app"
    TICKETS = "#{APP}/data/tickets.csv"
    CREDITS = "#{APP}/data/credits.csv"
    REPORT = "#{APP}/out/credit_report.csv"
    SUMMARY = "#{APP}/out/credit_summary.json"
    CALENDAR = "#{APP}/config/cutoff_calendar.txt"
    METHODS = "#{APP}/config/methods.csv"
    ALIASES = "#{APP}/config/fare_aliases.json"
    SCHEMA = "#{APP}/config/report_schema.json"
  end
end
