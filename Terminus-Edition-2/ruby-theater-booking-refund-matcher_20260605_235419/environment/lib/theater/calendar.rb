# frozen_string_literal: true

require_relative "paths"
require_relative "text_normalize"

module Theater
  class Calendar
    def self.open_dates(path = Paths::CALENDAR)
      return {} unless File.exist?(path)

      File.readlines(path).each_with_object({}) do |line, memo|
        date, status = line.split
        memo[TextNormalize.clean(date)] = true if TextNormalize.upper(status) == "OPEN"
      end
    end
  end
end
