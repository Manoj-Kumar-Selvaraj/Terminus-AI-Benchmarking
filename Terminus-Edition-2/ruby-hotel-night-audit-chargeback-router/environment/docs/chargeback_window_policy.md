# Chargeback Window Policy

Night-audit chargebacks are eligible only when the folio source timestamp falls inside an open property window and the chargeback action timestamp is not earlier than the folio timestamp.

The reconciler must treat closed, missing, malformed, unlisted, and after-close windows as ineligible.
