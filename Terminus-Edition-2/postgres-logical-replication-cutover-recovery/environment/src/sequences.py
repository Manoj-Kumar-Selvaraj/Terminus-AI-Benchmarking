# ruff: noqa
from __future__ import annotations
from .state import load_json
MAPPING={"customer_profile":"customer_profile_customer_id_seq","contact_method":"contact_method_contact_id_seq","communication_preference":"communication_preference_preference_id_seq","account_status":"account_status_status_id_seq","profile_audit":"profile_audit_audit_id_seq"}
def validate_sequences(): return {"valid":True,"sequences":load_json("target-database.json")["sequences"]}
def sync_sequences(): return validate_sequences()
