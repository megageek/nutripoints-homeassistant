"""Config-entry naming and entity-registry identity utilities."""

from __future__ import annotations

from urllib.parse import urlsplit

from custom_components.nutri_points.const import CONF_BASE_URL, DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify

LEGACY_ENTITY_OBJECT_ID_PREFIX = f"{DOMAIN}_"
LEGACY_ENTITY_UNIQUE_ID_PREFIX = f"{DOMAIN}_"
LEGACY_DEFAULT_OBJECT_SUFFIXES = {
    "activity_points": "activity_points",
    "budget_points": "budget_points",
    "food_points": "food_points",
    "over_budget": "over_budget",
    "points_low": "points_low",
    "remaining_points": "remaining_points",
    "total_drink_volume_ml": "drink_volume",
    "weigh_in_due": "weigh_in_due",
    "weight": "current_weight",
}


def default_server_name(base_url: str) -> str:
    """Derive a readable default server label from a base URL."""
    return urlsplit(base_url).hostname or "Nutri Points"


def entity_unique_id(entry: ConfigEntry, key: str) -> str:
    """Return an entry-scoped unique ID while retaining legacy compatibility."""
    if entry.unique_id is None:
        return f"{LEGACY_ENTITY_UNIQUE_ID_PREFIX}{key}"
    return f"{entry.unique_id}_{key}"


def async_migrate_entity_registry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    rename_default_entity_ids: bool,
) -> None:
    """Remove obsolete entities and scope legacy unique IDs to the server."""
    registry = er.async_get(hass)
    obsolete_unique_ids = {f"{LEGACY_ENTITY_UNIQUE_ID_PREFIX}has_planned_food"}
    if entry.unique_id is not None:
        obsolete_unique_ids.add(f"{entry.unique_id}_has_planned_food")
    for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if registry_entry.unique_id in obsolete_unique_ids:
            registry.async_remove(registry_entry.entity_id)

    if entry.unique_id is None:
        return
    server_name = str(entry.data.get(CONF_NAME) or default_server_name(str(entry.data.get(CONF_BASE_URL, ""))))
    server_slug = slugify(server_name)

    for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if not registry_entry.unique_id.startswith(LEGACY_ENTITY_UNIQUE_ID_PREFIX):
            continue
        key = registry_entry.unique_id.removeprefix(LEGACY_ENTITY_UNIQUE_ID_PREFIX)
        new_entity_id: str | None = None
        domain, object_id = registry_entry.entity_id.split(".", 1)
        legacy_default_suffix = LEGACY_DEFAULT_OBJECT_SUFFIXES.get(key)
        generated_object_ids = {
            slugify(candidate)
            for candidate in (
                registry_entry.suggested_object_id,
                registry_entry.object_id_base,
            )
            if candidate
        }
        is_default_entity_id = object_id in generated_object_ids or (
            legacy_default_suffix is not None
            and object_id == f"{LEGACY_ENTITY_OBJECT_ID_PREFIX}{legacy_default_suffix}"
        )
        if rename_default_entity_ids and object_id.startswith(LEGACY_ENTITY_OBJECT_ID_PREFIX) and is_default_entity_id:
            legacy_default_suffix = object_id.removeprefix(LEGACY_ENTITY_OBJECT_ID_PREFIX)
            new_entity_id = registry.async_get_available_entity_id(
                domain,
                f"{server_slug}_{legacy_default_suffix}",
                current_entity_id=registry_entry.entity_id,
            )
        registry.async_update_entity(
            registry_entry.entity_id,
            new_entity_id=new_entity_id or registry_entry.entity_id,
            new_unique_id=entity_unique_id(entry, key),
        )
