# Incident Notes

The first incident looked like a simple mismatch in the realtime escrow disbursement report. After strict row eligibility was restored, operations found that packages could clear one row at a time even when the closing package was incomplete. Funding later drifted because held packages still consumed trust balance during reruns.
