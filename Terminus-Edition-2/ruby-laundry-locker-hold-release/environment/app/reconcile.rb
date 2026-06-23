require 'csv'
require 'fileutils'

def canon(v)
  v.to_s.strip.upcase
end

sources = CSV.read('/app/data/locker_holds.csv', headers: true).map.with_index do |r, i|
  {
    id: r['hold_id'].strip,
    party: r['customer_id'].strip,
    scope: r['site_id'].strip,
    rate_type: canon(r['service_tier']),
    amount: r['amount'].strip,
    ts: r['hold_ts'].strip,
    status: r['status'].strip,
    loc: r['locker'].strip,
    row: i,
    used: false
  }
end

actions = CSV.read('/app/data/locker_releases.csv', headers: true).map do |r|
  {
    aid: r['release_id'].strip,
    id: r['hold_id'].strip,
    party: r['customer_id'].strip,
    scope: r['site_id'].strip,
    rate_type: canon(r['service_tier']),
    amount: r['amount'].strip,
    ts: r['release_ts'].strip,
    reason: r['reason'].strip,
    loc: r['locker'].strip
  }
end

FileUtils.mkdir_p('/app/out')
mc = uc = ma = ua = 0

CSV.open('/app/out/locker_release_report.csv', 'w') do |csv|
  csv << %w[release_id hold_id customer_id site_id service_tier amount reason status]
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

File.write('/app/out/locker_release_summary.txt', <<~SUMMARY)
  matched_count=#{mc}
  matched_amount=#{ma}
  unmatched_count=#{uc}
  unmatched_amount=#{ua}
SUMMARY
