#!/usr/bin/env python3
"""Set local STB AI credentials from OPENAI_API_KEY and OPENAI_BASE_URL."""

from __future__ import annotations

import configparser
import os
import sys
from pathlib import Path


def update_config(path: Path) -> None:
    api_key = os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("OPENAI_BASE_URL")
    if not api_key or not base_url:
        raise SystemExit("OPENAI_API_KEY and OPENAI_BASE_URL must both be set")

    path.parent.mkdir(parents=True, exist_ok=True)
    config = configparser.ConfigParser()
    config.read(path)
    if "auth" not in config:
        config["auth"] = {}
    if "portkey" not in config:
        config["portkey"] = {}

    config["auth"]["env"] = "portkey"
    config["portkey"]["api_key"] = api_key
    config["portkey"]["gateway_url"] = base_url

    with path.open("w", encoding="utf-8") as handle:
        config.write(handle)


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: set_stb_ai_credentials.py <config.ini> [<config.ini>...]")
    for arg in sys.argv[1:]:
        update_config(Path(arg))
        print(f"updated {arg}")


if __name__ == "__main__":
    main()
