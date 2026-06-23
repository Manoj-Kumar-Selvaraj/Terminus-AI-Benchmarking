#!/usr/bin/env python3
"""Deprecated Python driver stub.

FNBULKUP is implemented in Go under /app/cmd/finbulk and /app/internal/finbulk.
Use /app/bin/run_finbulk.sh to build and execute the batch driver.
"""
from __future__ import annotations

import sys


def main() -> int:
    sys.stderr.write(
        "bulk_update.py is deprecated. Repair /app/internal/finbulk and "
        "run /app/bin/run_finbulk.sh instead.\n"
    )
    return 99


if __name__ == "__main__":
    raise SystemExit(main())
