# Snapshot, compaction, and legacy replay contract

Compaction replaces replayed journal history with `snapshot.json` and may then remove journal bytes. It must preserve rollout definitions, delivery identities and statuses, lease owner and expiry, claim tokens, gateway sequences, errors, and regional active-generation fences. Compaction is not permission to discard acknowledged or superseded history or to turn completed work back into pending work.

The snapshot records the journal byte offset already represented. This makes both sides of the atomic replacement safe:

- before snapshot rename, the old snapshot and journal remain authoritative;
- after snapshot rename but before journal truncation, replay skips only the represented prefix;
- after truncation, the snapshot remains authoritative and new journal records begin at offset zero.

Restarting after `after-snapshot-rename` must expose each rollout once and must not repeat completed gateway work. A claimed delivery must retain its lease and stable command identity across compaction.

The current controller must also read legacy version-1 queued records produced by the previous release:

```json
{"version":1,"type":"queued","id":"rollout-id","revision":42,"policy":"{...}","regions":["us-east"]}
```

Legacy records are normalized to the current status model, derive the normal policy digest and stable delivery identities, and remain fully dispatchable and compactable. Unknown journal versions remain errors.
