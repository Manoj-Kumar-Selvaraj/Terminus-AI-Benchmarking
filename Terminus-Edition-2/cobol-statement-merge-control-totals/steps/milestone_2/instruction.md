After milestone 1, operations still see low totals when the same composite business key spans consecutive sort runs listed in `/app/config/stream_manifest.txt`. Duplicate keys at a run boundary should continue the same merge accumulator instead of splitting debits and credits across separate committed groups.

Keep milestone 1 account/date control breaks and the output contracts documented under `/app/docs`. Processing order within each sort run must be preserved; fix cross-run duplicate keys with boundary carry-forward, not a global sort across runs.

The program must continue to be compiled via GnuCOBOL (`cobc`); `/app/scripts/compile.sh` must remain a GnuCOBOL build script.
