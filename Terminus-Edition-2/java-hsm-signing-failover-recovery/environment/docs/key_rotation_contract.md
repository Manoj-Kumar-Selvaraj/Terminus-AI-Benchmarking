# Key Rotation Contract

Rotation is a fenced administrative operation. It increments the policy generation, makes the new key active for newly prepared requests, and records a grace deadline for the previous active key.

A prepared request is pinned to the key and policy generation selected when it was first accepted:

- retries and recovery never substitute the current active key;
- an unsigned request pinned to an old key may reach the HSM only while `now <= grace_until` and the key is not revoked;
- after grace or revocation, that unsigned request remains pending and recovery fails visibly;
- if the HSM audit already proves the pinned operation completed, recovery may finalize the existing signature even after grace or revocation because it must not repeat or erase the external side effect;
- newly prepared requests always use the current active key;
- rotation with a grace deadline earlier than `now` is rejected without changing policy state.
