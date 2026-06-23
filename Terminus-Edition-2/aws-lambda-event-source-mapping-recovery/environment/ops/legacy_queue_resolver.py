#!/usr/bin/env python3
"""Legacy diagnostic helper retained for operator comparison.

This file intentionally reads the old dashboard label and is not part of the live simulator path. It is kept because operators referenced it during the incident, but changing it is not required by the task contract.
"""
OLD_LABEL = "payments-ledger-old-consumer"

def displayed_queue_label():
    return OLD_LABEL
