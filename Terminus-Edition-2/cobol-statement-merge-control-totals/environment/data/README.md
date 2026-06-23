Sample statement streams for the nightly merge batch. Each line is a 48-byte fixed-width
statement record sorted within the run file by composite key (account + stmt date + seq).

The manifest at `/app/config/stream_manifest.txt` lists sort runs in merge order.
