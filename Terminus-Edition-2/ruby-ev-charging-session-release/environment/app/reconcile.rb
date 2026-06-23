require 'csv'
require 'fileutils'

def canon(v)
  v.to_s.strip.upcase
end

sources = CSV.read('/app/data/charge_sessions.csv', headers: true).map.with_index do |r, i|
  {
    id: r['session_id'].strip,
    party: r['vehicle_id'].strip,
    scope: r['station_id'].strip,
    rate_type: canon(r['rate_plan']),
    amount: r['amount'].strip,
    ts: r['plug_ts'].strip,
    status: r['status'].strip,
    loc: r['port'].strip,
    row: i,
    used: false
  }
end

actions = CSV.read('/app/data/session_releases.csv', headers: true).map do |r|
  {
    aid: r['release_id'].strip,
    id: r['session_id'].strip,
    party: r['vehicle_id'].strip,
    scope: r['station_id'].strip,
    rate_type: canon(r['rate_plan']),
    amount: r['amount'].strip,
    ts: r['release_ts'].strip,
    reason: r['reason'].strip,
    loc: r['port'].strip
  }
end

FileUtils.mkdir_p('/app/out')
mc = uc = ma = ua = 0

CSV.open('/app/out/ev_release_report.csv', 'w') do |csv|
  csv << %w[release_id session_id vehicle_id station_id rate_plan amount reason status]
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

File.write('/app/out/ev_release_summary.txt', <<~SUMMARY)
  matched_count=#{mc}
  matched_amount=#{ma}
  unmatched_count=#{uc}
  unmatched_amount=#{ua}
SUMMARY
