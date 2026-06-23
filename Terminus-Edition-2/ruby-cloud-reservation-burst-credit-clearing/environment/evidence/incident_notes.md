# Incident notes

Support observed that the cloud reservation credit batch could mark individual credits as matched while the reservation cycle itself remained incomplete. A later remediation attempt updated matched rows but consumed regional capacity for groups that should have stayed held. During a replay after an interrupted run, already committed groups were credited a second time.
