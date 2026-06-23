require 'csv'
require 'fileutils'

def canon(v)
  v.to_s.strip.upcase
end

sources = CSV.read('/app/data/seat_events.csv', headers: true).map.with_index do |r, i|
  {
    id: r['event_id'].strip,
    account: r['account_id'].strip,
    scope: r['subscription_id'].strip,
    kind: canon(r['kind']),
    amount: r['amount'].strip,
    ts: r['source_ts'].strip,
    status: r['status'].strip,
    loc: r['location'].strip,
    row: i,
    used: false
  }
end

actions = CSV.read('/app/data/credits.csv', headers: true).map do |r|
  {
    aid: r['action_id'].strip,
    id: r['event_id'].strip,
    account: r['account_id'].strip,
    scope: r['subscription_id'].strip,
    kind: canon(r['kind']),
    amount: r['amount'].strip,
    ts: r['action_ts'].strip,
    reason: r['reason'].strip,
    loc: r['location'].strip
  }
end

FileUtils.mkdir_p('/app/out')
mc = uc = ma = ua = 0
CSV.open('/app/out/seat_credit_report.csv', 'w') do |csv|
  csv << ['action_id', 'event_id', 'account_id', 'subscription_id', 'kind', 'amount', 'reason', 'status']
  actions.each do |act|
    candidates = []
    sources.each_with_index do |src, i|
      next unless src[:id].start_with?(act[:id]) || act[:id].start_with?(src[:id])
      next unless src[:amount].to_i == act[:amount].to_i

      candidates << i
    end
    candidates.sort_by! { |i| [-sources[i][:ts].to_i, sources[i][:row]] }
    best = candidates.first
    amt = act[:amount].to_i
    if best
      mc += 1
      ma += amt
      csv << [act[:aid], act[:id], act[:account], act[:scope], sources[best][:kind], act[:amount], act[:reason], 'MATCHED']
    else
      uc += 1
      ua += amt
      csv << [act[:aid], act[:id], act[:account], act[:scope], '', act[:amount], act[:reason], 'UNMATCHED']
    end
  end
end
File.write(
  '/app/out/seat_credit_summary.txt',
  "matched_count=#{mc}\nmatched_amount=#{ma}\nunmatched_count=#{uc}\nunmatched_amount=#{ua}\n"
)
