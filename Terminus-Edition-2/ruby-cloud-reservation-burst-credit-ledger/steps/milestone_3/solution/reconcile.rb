require 'csv'
require 'fileutils'
def canon(v)
  v = v.to_s.strip.upcase
  return "CPU" if v == "C" || v == "CPU"
  return "GPU" if v == "GPUF" || v == "GPU"
  return "MEM" if v == "MEMORY" || v == "MEM"
  v
end
def digits?(v) = v.to_s.match?(/\A\d{14}\z/)
def integer?(v) = v.to_s.match?(/\A\d+\z/)
def sku_type_ok?(v) = ['CPU', 'GPU', 'MEM'].include?(v)
def reason_ok?(v) = ["BURST", "RECLAIM", "CORRECT"].include?(v)
def window_ok?(src, act, windows)
  return false unless digits?(src[:ts]) && digits?(act[:ts])
  windows.any? { |w| w[:scope] == src[:scope] && w[:state] == 'OPEN' && digits?(w[:open]) && digits?(w[:close]) && src[:ts] >= w[:open] && src[:ts] <= w[:close] && act[:ts] >= src[:ts] && act[:ts] <= w[:close] }
end
sources = CSV.read('/app/data/seat_events.csv', headers: true).map.with_index { |r,i| {id:r['event_id'].strip, party:r['account_id'].strip, scope:r['reservation_id'].strip, sku_type:canon(r['sku_type']), amount:r['amount'].strip, ts:r['reserve_ts'].strip, status:r['status'].strip, loc:r['region'].strip, row:i, used:false} }
actions = CSV.read('/app/data/credits.csv', headers: true).map { |r| {aid:r['credit_id'].strip, id:r['event_id'].strip, party:r['account_id'].strip, scope:r['reservation_id'].strip, sku_type:canon(r['sku_type']), amount:r['amount'].strip, ts:r['credit_ts'].strip, reason:r['reason'].strip, loc:r['region'].strip} }
windows = CSV.read('/app/config/windows.csv', headers: true).map { |r| {scope:r['reservation_id'].strip, open:r['open_ts'].strip, close:r['close_ts'].strip, state:r['state'].strip} }
FileUtils.mkdir_p('/app/out')
mc=uc=ma=ua=0
CSV.open('/app/out/seat_credit_report.csv', 'w') do |csv|
  csv << ['credit_id','event_id','account_id','reservation_id','sku_type','amount','reason','status']
  actions.each do |act|
    candidates = []
    sources.each_with_index do |src,i|
      candidates << i if (src[:id] == act[:id]) && integer?(src[:amount]) && integer?(act[:amount]) && src[:amount].to_i == act[:amount].to_i && !src[:used] && src[:party] == act[:party] && src[:scope] == act[:scope] && src[:loc] == act[:loc] && sku_type_ok?(src[:sku_type]) && sku_type_ok?(act[:sku_type]) && src[:status] == "ALLOCATED" && reason_ok?(act[:reason]) && window_ok?(src, act, windows)
    end
    candidates.sort_by! { |i| [-sources[i][:ts].to_i, sources[i][:row]] }
    best = candidates.first
    amt = act[:amount].to_i
    if best
      sources[best][:used] = true
      mc += 1; ma += amt
      csv << [act[:aid], act[:id], act[:party], act[:scope], sources[best][:sku_type], act[:amount], act[:reason], 'MATCHED']
    else
      uc += 1; ua += amt
      csv << [act[:aid], act[:id], act[:party], act[:scope], '', act[:amount], act[:reason], 'UNMATCHED']
    end
  end
end
File.write('/app/out/seat_credit_summary.txt', "matched_count=#{mc}
matched_amount=#{ma}
unmatched_count=#{uc}
unmatched_amount=#{ua}
")
