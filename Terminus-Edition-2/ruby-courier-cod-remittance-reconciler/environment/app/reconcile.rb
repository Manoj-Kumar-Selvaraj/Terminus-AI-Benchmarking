require 'csv'
require 'fileutils'

# Starter implementation: incomplete matching (prefix parcel_id only).
def canon(v)
  v.to_s.strip.upcase
end

sources = CSV.read('/app/data/deliveries.csv', headers: true).map.with_index do |r, i|
  {
    id: r['parcel_id'].strip,
    party: r['courier_id'].strip,
    scope: r['station_id'].strip,
    kind: canon(r['kind']),
    amount: r['amount'].strip,
    ts: r['source_ts'].strip,
    status: r['status'].strip,
    loc: r['location'].strip,
    row: i,
    used: false
  }
end
actions = CSV.read('/app/data/remittances.csv', headers: true).map do |r|
  {
    aid: r['action_id'].strip,
    id: r['parcel_id'].strip,
    party: r['courier_id'].strip,
    scope: r['station_id'].strip,
    kind: canon(r['kind']),
    amount: r['amount'].strip,
    ts: r['action_ts'].strip,
    reason: r['reason'].strip,
    loc: r['location'].strip
  }
end

FileUtils.mkdir_p('/app/out')
mc = uc = ma = ua = 0
CSV.open('/app/out/cod_remittance_report.csv', 'w') do |csv|
  csv << %w[action_id parcel_id courier_id station_id kind amount reason status]
  actions.each do |act|
    best = nil
    sources.each_with_index do |src, i|
      next if src[:used]
      next unless src[:id].start_with?(act[:id]) || act[:id].start_with?(src[:id])
      next unless src[:amount] == act[:amount]

      best = i
    end
    amt = act[:amount].to_i
    if best
      sources[best][:used] = true
      mc += 1
      ma += amt
      csv << [act[:aid], act[:id], act[:party], act[:scope], sources[best][:kind], act[:amount], act[:reason], 'MATCHED']
    else
      uc += 1
      ua += amt
      csv << [act[:aid], act[:id], act[:party], act[:scope], '', act[:amount], act[:reason], 'UNMATCHED']
    end
  end
end
File.write(
  '/app/out/cod_remittance_summary.txt',
  "matched_count=#{mc}\nmatched_amount=#{ma}\nunmatched_count=#{uc}\nunmatched_amount=#{ua}\n"
)
