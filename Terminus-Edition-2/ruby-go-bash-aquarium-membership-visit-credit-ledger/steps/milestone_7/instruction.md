Fix the Ruby entrypoint /app/app/reconcile.rb for the aquarium membership visit credit ledger. The single-container task intentionally uses Ruby for orchestration, Go for canonical kind normalization in /app/cmd/normalize/main.go, and Bash in /app/scripts/run_batch.sh to compile the helper and run the batch. Do not move the solution to another entrypoint. Read /app/data/sources.csv and /app/data/actions.csv, then write /app/out/resolution_report.csv and /app/out/resolution_summary.json.

Milestone 1: match only on full source id, account id, location id, lane, exact amount, ACTIVE source status, eligible reason CREDIT/ADJUST/RETURN, canonical kinds STANDARD or PREMIUM, numeric timestamp ordering, and single-use source rows. Preserve action order, emit MATCHED/UNMATCHED, and leave kind blank on unmatched rows.

Milestone 2: keep milestone 1 and normalize aliases from /app/config/kind_aliases.csv: STD to STANDARD, PREM to PREMIUM, and ELITE to VIP. From this milestone onward VIP is also a valid canonical kind, and matched rows must emit only canonical kind values.

Milestone 3: keep prior behavior and apply /app/config/windows.csv. The source timestamp must fall in an OPEN window for the same location, and the action timestamp must be on or after the source timestamp and not after the window close. Choose latest source timestamp, then earliest source input row.

Milestone 4: keep prior behavior and apply /app/config/policy.csv. Only enabled canonical kinds can match. An action kind of ANY may match any enabled kind and chooses latest source timestamp, then lowest policy priority number, then earliest source row.

Milestone 5: keep prior behavior and apply /app/config/calendar.txt. Source and action dates must both be OPEN calendar dates. Count OPEN days after the source date through the action date; zero, one, or two open days are eligible, but three or more are not.

Milestone 6: keep prior behavior and apply /app/config/tolerance.conf. max_delta_cents allows source and action amounts to differ within that absolute tolerance. Reports and summaries still use the action amount as positive cents.

Milestone 7: keep prior behavior and apply /app/config/blocked_accounts.txt plus /app/config/replay_ledger.csv. Blocked accounts and replayed action ids must stay unmatched. Also write /app/out/resolution_audit.json with matched and unmatched action id arrays.