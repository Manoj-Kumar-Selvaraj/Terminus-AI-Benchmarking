# Operator Shift Note

The orbit downlink frame auditor is still invoked with `/app/scripts/run_batch.sh`.
Do not assume the sample rule deck values are stable. Recent incidents include rejected valid audits, duplicate replay rows after receiver restart, and unexplained gaps in VC0.

Non-blocking observations from the same shift:

- Antenna azimuth correction exceeded a soft threshold during AOS.
- Receiver AGC drifted briefly while the archival compressor was rotating files.
- A legacy dashboard footer displayed a stale accepted count after midnight UTC.
