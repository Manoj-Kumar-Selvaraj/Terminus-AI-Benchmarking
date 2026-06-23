# frozen_string_literal: true

module Charity
  PledgeRow = Struct.new(:id, :donor_id, :amount, :status, :fund, :pledge_due, keyword_init: true)
  AdjustmentRow = Struct.new(:id, :donor_id, :amount, :fund, :adjustment_date, :raw_amount, keyword_init: true)
end
