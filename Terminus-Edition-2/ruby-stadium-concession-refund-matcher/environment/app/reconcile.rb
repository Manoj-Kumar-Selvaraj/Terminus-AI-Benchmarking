require 'csv'
require 'fileutils'

# Starter implementation: incomplete matching (prefix folio_id only).
def canon(v)
  v.to_s.strip.upcase
end

sources = CSV.read('/app/data/folios.csv', headers: true).map.with_index do |r, i|
  {
    id: r['folio_id'].strip,
    party: r['fan_id'].strip,
    scope: r['property_id'].strip,
    item_type: canon(r['item_type']),
    amount: r['amount'].strip,
    ts: r['sale_ts'].strip,
    status: r['status'].strip,
    loc: r['stand'].strip,
    row: i,
    used: false
  }
end
actions = CSV.read('/app/data/refunds.csv', headers: true).map do |r|
  {
    aid: r['refund_id'].strip,
    id: r['folio_id'].strip,
    party: r['fan_id'].strip,
    scope: r['property_id'].strip,
    item_type: canon(r['item_type']),
    amount: r['amount'].strip,
    ts: r['refund_ts'].strip,
    reason: r['reason'].strip,
    loc: r['stand'].strip
  }
end

FileUtils.mkdir_p('/app/out')
mc = uc = ma = ua = 0
CSV.open('/app/out/concession_refund_report.csv', 'w') do |csv|
  csv << %w[refund_id folio_id fan_id property_id item_type amount reason status]
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
      csv << [act[:aid], act[:id], act[:party], act[:scope], sources[best][:item_type], act[:amount], act[:reason], 'MATCHED']
    else
      uc += 1
      ua += amt
      csv << [act[:aid], act[:id], act[:party], act[:scope], '', act[:amount], act[:reason], 'UNMATCHED']
    end
  end
end
File.write(
  '/app/out/concession_refund_summary.txt',
  "matched_count=#{mc}\nmatched_amount=#{ma}\nunmatched_count=#{uc}\nunmatched_amount=#{ua}\n"
)
