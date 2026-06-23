from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_manifest_bundle(manifest_dir: Path) -> dict[str, Any]:
    docs: dict[str, Any] = {
        "namespaces": [],
        "serviceaccounts": [],
        "configmaps": [],
        "roles": [],
        "rolebindings": [],
        "cronjobs": [],
    }
    for path in sorted(manifest_dir.glob("*.yaml")):
        for doc in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            if not doc:
                continue
            kind = doc.get("kind")
            bucket = {
                "Namespace": "namespaces",
                "ServiceAccount": "serviceaccounts",
                "ConfigMap": "configmaps",
                "Role": "roles",
                "RoleBinding": "rolebindings",
                "CronJob": "cronjobs",
            }.get(kind)
            if bucket:
                docs[bucket].append(doc)
    return docs


def find_by_name(items: list[dict[str, Any]], name: str, namespace: str | None = None) -> dict[str, Any] | None:
    for item in items:
        meta = item.get("metadata", {})
        if meta.get("name") != name:
            continue
        if namespace is not None and meta.get("namespace") != namespace:
            continue
        return item
    return None
