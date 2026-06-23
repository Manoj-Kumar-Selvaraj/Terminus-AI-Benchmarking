#!/bin/bash
set -euo pipefail
cat > /app/app/reconcile.rb <<'RUBY'
require 'csv'
require 'fileutils'
def canon(v)
  v = v.to_s.strip.upcase
  return "SELLER" if v == "SLR" || v == "SELLER"
  return "BROKER" if v == "BRK" || v == "BROKER"
  return "TAX" if v == "TAXAUTH" || v == "TAX"
  v
end
def digits?(v) = v.to_s.match?(/\A\d{14}\z/)
def right_type_ok?(v) = ['SELLER', 'BROKER', 'TAX'].include?(v)
def reason_ok?(v) = ["CLOSE", "CORRECT", "PAY"].include?(v)
def window_ok?(src, act, windows)
  return false unless digits?(src[:ts]) && digits?(act[:ts])
  windows.any? { |w| w[:scope] == src[:scope] && w[:state].casecmp('OPEN').zero? && digits?(w[:open]) && digits?(w[:close]) && src[:ts] >= w[:open] && src[:ts] <= w[:close] && act[:ts] >= src[:ts] && act[:ts] <= w[:close] }
end
sources = CSV.read('/app/data/holds.csv', headers: true).map.with_index { |r,i| {id:r['play_id'].strip, party:r['payee_id'].strip, scope:r['trust_id'].strip, right_type:canon(r['right_type']), amount:r['amount'].strip, ts:r['play_ts'].strip, status:r['status'].strip, loc:r['market'].strip, row:i, used:false} }
actions = CSV.read('/app/data/settlements.csv', headers: true).map { |r| {aid:r['settlement_id'].strip, id:r['play_id'].strip, party:r['payee_id'].strip, scope:r['trust_id'].strip, right_type:canon(r['right_type']), amount:r['amount'].strip, ts:r['settle_ts'].strip, reason:r['reason'].strip, loc:r['market'].strip} }
windows = CSV.read('/app/config/windows.csv', headers: true).map { |r| {scope:r['trust_id'].strip, open:r['open_ts'].strip, close:r['close_ts'].strip, state:r['state'].strip} }
FileUtils.mkdir_p('/app/out')
mc=uc=ma=ua=0
CSV.open('/app/out/royalty_settlement_report.csv', 'w') do |csv|
  csv << ['settlement_id','play_id','payee_id','trust_id','right_type','amount','reason','status']
  actions.each do |act|
    best = nil
    sources.each_with_index do |src, i|
      next if src[:used]
      next unless src[:id] == act[:id] && src[:amount].to_i == act[:amount].to_i && src[:party] == act[:party] && src[:scope] == act[:scope] && src[:loc] == act[:loc] && right_type_ok?(src[:right_type]) && src[:status] == "HELD" && src[:right_type] == act[:right_type] && reason_ok?(act[:reason]) && window_ok?(src, act, windows)
      best = i
      break
    end
    amt = act[:amount].to_i
    if best
      sources[best][:used] = true
      mc += 1; ma += amt
      csv << [act[:aid], act[:id], act[:party], act[:scope], sources[best][:right_type], act[:amount], act[:reason], 'MATCHED']
    else
      uc += 1; ua += amt
      csv << [act[:aid], act[:id], act[:party], act[:scope], '', act[:amount], act[:reason], 'UNMATCHED']
    end
  end
end
File.write('/app/out/royalty_settlement_summary.txt', "matched_count=#{mc}\nmatched_amount=#{ma}\nunmatched_count=#{uc}\nunmatched_amount=#{ua}\n")
RUBY
/app/scripts/run_batch.sh
