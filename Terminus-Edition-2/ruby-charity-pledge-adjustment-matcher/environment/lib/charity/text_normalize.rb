# frozen_string_literal: true

module Charity
  module TextNormalize
    module_function

    def clean(value)
      value.to_s.strip
    end

    def upper(value)
      clean(value).upcase
    end
  end
end
