from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from backend.config import get_settings
from backend.semantic.models import SemanticCatalog


CATALOG_PATH = Path(__file__).with_name("catalog.json")
TENANT_SCHEMA_ROOT = Path(__file__).parent.parent.parent / "schema" / "tenants"
ACTIVE_CATALOG_NAME = "semantic_active.json"


@lru_cache(maxsize=1)
def load_semantic_catalog(path: str | Path = CATALOG_PATH) -> SemanticCatalog:
    catalog_path = Path(path)
    with catalog_path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    return SemanticCatalog.model_validate(data)


def active_semantic_catalog_path(tenant_id: str) -> Path:
    return TENANT_SCHEMA_ROOT / tenant_id / ACTIVE_CATALOG_NAME


def load_active_semantic_catalog(tenant_id: str) -> SemanticCatalog:
    active_path = active_semantic_catalog_path(tenant_id)
    return load_semantic_catalog(active_path)


def load_tenant_semantic_catalog(tenant_id: str | None = None) -> SemanticCatalog:
    tenant = tenant_id or get_settings().tenant_id
    active_path = active_semantic_catalog_path(tenant)
    if active_path.exists():
        return load_semantic_catalog(active_path)
    return load_semantic_catalog()


def clear_semantic_catalog_cache() -> None:
    load_semantic_catalog.cache_clear()


semantic_catalog = load_tenant_semantic_catalog()
