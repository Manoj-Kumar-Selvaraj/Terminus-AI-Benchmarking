require 'csv'
require 'fileutils'

FileUtils.mkdir_p('/app/out')
sources = CSV.read('/app/data/holds.csv', headers: true)
actions = CSV.read('/app/data/disbursements.csv', headers: true)
matched_count = 0
matched_amount = 0
unmatched_count = 0
unmatched_amount = 0

CSV.open('/app/out/disbursement_report.csv', 'w') do |csv|
  csv << ['action_id','escrow_id','payee_id','trust_id','kind','amount','reason','status']
  actions.each do |act|
    best = sources.find do |src|
      src['amount'].to_s.strip == act['amount'].to_s.strip &&
        (src['escrow_id'].to_s.start_with?(act['escrow_id'].to_s) || act['escrow_id'].to_s.start_with?(src['escrow_id'].to_s))
    end
    amount = act['amount'].to_i
    if best
      matched_count += 1
      matched_amount += amount
      csv << [act['action_id'], act['escrow_id'], act['payee_id'], act['trust_id'], best['kind'], act['amount'], act['reason'], 'MATCHED']
    else
      unmatched_count += 1
      unmatched_amount += amount
      csv << [act['action_id'], act['escrow_id'], act['payee_id'], act['trust_id'], '', act['amount'], act['reason'], 'UNMATCHED']
    end
  end
end

File.write('/app/out/disbursement_summary.txt', "matched_count=#{matched_count}
matched_amount=#{matched_amount}
unmatched_count=#{unmatched_count}
unmatched_amount=#{unmatched_amount}
")
