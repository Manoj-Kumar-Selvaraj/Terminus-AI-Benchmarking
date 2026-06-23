require 'csv'
require 'fileutils'

def canon(v)
  v.to_s.strip.upcase
end

def digits?(v) = v.to_s.match?(/\A\d{14}\z/)
def sku_type_ok?(v) = ['CPU', 'GPU'].include?(v)
def reason_ok?(v) = ["BURST", "RECLAIM", "CORRECT"].include?(v)

def window_ok?(src, act, windows)
  return false unless digits?(src[:ts]) && digits?(act[:ts])

  windows.any? do |w|
    w[:scope] == src[:scope] &&
      w[:state] == 'OPEN' &&
      digits?(w[:open]) &&
      digits?(w[:close]) &&
      src[:ts] >= w[:open] &&
      src[:ts] <= w[:close] &&
      act[:ts] >= src[:ts] &&
      act[:ts] <= w[:close]
  end
end

sources = CSV.read('/app/data/seat_events.csv', headers: true).map.with_index do |r, i|
  {
    id: r['event_id'].strip,
    party: r['account_id'].strip,
    scope: r['reservation_id'].strip,
    sku_type: canon(r['sku_type']),
    amount: r['amount'].strip,
    ts: r['reserve_ts'].strip,
    status: r['status'].strip,
    loc: r['region'].strip,
    row: i,
    used: false
  }
end

actions = CSV.read('/app/data/credits.csv', headers: true).map do |r|
  {
    aid: r['credit_id'].strip,
    id: r['event_id'].strip,
    party: r['account_id'].strip,
    scope: r['reservation_id'].strip,
    sku_type: canon(r['sku_type']),
    amount: r['amount'].strip,
    ts: r['credit_ts'].strip,
    reason: r['reason'].strip,
    loc: r['region'].strip
  }
end

windows = CSV.read('/app/config/windows.csv', headers: true).map do |r|
  {
    scope: r['reservation_id'].strip,
    open: r['open_ts'].strip,
    close: r['close_ts'].strip,
    state: r['state'].strip
  }
end

FileUtils.mkdir_p('/app/out')
mc = uc = ma = ua = 0

CSV.open('/app/out/seat_credit_report.csv', 'w') do |csv|
  csv << ['credit_id', 'event_id', 'account_id', 'reservation_id', 'sku_type', 'amount', 'reason', 'status']
  actions.each do |act|
    candidates = []
    sources.each_with_index do |src, i|
      next unless (src[:id].start_with?(act[:id]) || act[:id].start_with?(src[:id])) &&
                  src[:amount] == act[:amount] &&
                  !src[:used] &&
                  src[:party] == act[:party] &&
                  src[:scope] == act[:scope] &&
                  src[:loc] == act[:loc] &&
                  sku_type_ok?(src[:sku_type]) &&
                  sku_type_ok?(act[:sku_type]) &&
                  src[:status] == 'ALLOCATED' &&
                  reason_ok?(act[:reason]) &&
                  window_ok?(src, act, windows)

      candidates << i
    end
    candidates.sort_by! { |i| [-sources[i][:ts].to_i, sources[i][:row]] }
    best = candidates.first
    amt = act[:amount].to_i
    if best
      mc += 1
      ma += amt
      csv << [act[:aid], act[:id], act[:party], act[:scope], sources[best][:sku_type], act[:amount], act[:reason], 'MATCHED']
    else
      uc += 1
      ua += amt
      csv << [act[:aid], act[:id], act[:party], act[:scope], '', act[:amount], act[:reason], 'UNMATCHED']
    end
  end
end

File.write('/app/out/seat_credit_summary.txt', "matched_count=#{mc}\nmatched_amount=#{ma}\nunmatched_count=#{uc}\nunmatched_amount=#{ua}\n")
