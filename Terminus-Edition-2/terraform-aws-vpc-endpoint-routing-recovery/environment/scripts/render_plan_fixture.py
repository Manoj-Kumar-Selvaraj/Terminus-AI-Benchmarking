#!/usr/bin/env python3
"""Render a normalized offline plan-risk view from the module and fixtures."""
# ruff: noqa: E501
from __future__ import annotations

import json
from inspect_network_contract import build_summary
from pathlib import Path

summary = build_summary(Path("/app"))
print(json.dumps({"protected_replacement_risks": summary["protected_replacement_risks"]}, indent=2, sort_keys=True))
