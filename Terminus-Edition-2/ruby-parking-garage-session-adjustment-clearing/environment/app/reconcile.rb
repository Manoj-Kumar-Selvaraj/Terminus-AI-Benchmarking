require 'csv'
require 'fileutils'

def canon(v)
  v.to_s.strip.upcase
end

def digits?(v)
  v.to_s.match?(/\A\d{14}\z/)
end

def rate_type_ok?(v)
  ['HOURLY', 'DAILY'].include?(v)
end

def reason_ok?(v)
  ['REFUND', 'SHORT', 'WAIVE'].include?(v)
end

sources = CSV.read('/app/data/sessions.csv', headers: true).map.with_index do |r, i|
  {
    id: r['parcel_id'].strip,
    party: r['plate_id'].strip,
    scope: r['station_id'].strip,
    rate_type: canon(r['rate_type']),
    amount: r['amount'].strip,
    ts: r['entry_ts'].strip,
    status: r['status'].strip,
    loc: r['level'].strip,
    row: i,
    used: false
  }
end

actions = CSV.read('/app/data/adjustments.csv', headers: true).map do |r|
  {
    aid: r['adjustment_id'].strip,
    id: r['parcel_id'].strip,
    party: r['plate_id'].strip,
    scope: r['station_id'].strip,
    rate_type: canon(r['rate_type']),
    amount: r['amount'].strip,
    ts: r['adjust_ts'].strip,
    reason: r['reason'].strip,
    loc: r['level'].strip
  }
end

FileUtils.mkdir_p('/app/out')
mc = uc = ma = ua = 0

CSV.open('/app/out/cod_parking_adjustment_report.csv', 'w') do |csv|
  csv << %w[adjustment_id parcel_id plate_id station_id rate_type amount reason status]
  actions.each do |act|
    best = nil
    sources.each_with_index do |src, i|
      next unless src[:id].start_with?(act[:id]) || act[:id].start_with?(src[:id])
      next unless src[:amount] == act[:amount]
      best = i
      break
    end
    amt = act[:amount].to_i
    if best
      mc += 1
      ma -= amt
      csv << [act[:aid], act[:id], act[:party], act[:scope], sources[best][:rate_type], act[:amount], act[:reason], 'MATCHED']
    else
      uc += 1
      ua += amt
      csv << [act[:aid], act[:id], act[:party], act[:scope], '', act[:amount], act[:reason], 'UNMATCHED']
    end
  end
end

File.write('/app/out/cod_parking_adjustment_summary.txt', <<~SUMMARY)
  matched_count=#{mc}
  matched_amount=#{ma}
  unmatched_count=#{uc}
  unmatched_amount=#{ua}
SUMMARY
