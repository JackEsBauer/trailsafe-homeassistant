"""PaceGuard GPS Tracker integration for Home Assistant."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .avatar import TrailsafeAvatarView
from .const import CONF_SERVER_URL, DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import TrailsafeCoordinator

PLATFORMS = [Platform.DEVICE_TRACKER]

# The service is PaceGuard now; these older hostnames reach the same backend
# (same accounts and API keys), so existing entries are moved over.
LEGACY_SERVER_URLS = {
    "https://trail-safe.app",
    "https://www.trail-safe.app",
    "https://api.trailsafe.nl",
}
SERVER_URL = "https://paceguard.io"

type TrailsafeConfigEntry = ConfigEntry[TrailsafeCoordinator]


async def async_migrate_entry(hass: HomeAssistant, entry: TrailsafeConfigEntry) -> bool:
    """1.1 → 1.2: point entries at paceguard.io instead of the Trail-Safe hosts."""
    if entry.version > 1:
        return False  # downgrade from a future major version
    if entry.minor_version < 2:
        data = dict(entry.data)
        if data.get(CONF_SERVER_URL, "").rstrip("/") in LEGACY_SERVER_URLS:
            data[CONF_SERVER_URL] = SERVER_URL
        title = entry.title.replace("Trail-Safe", "PaceGuard")
        hass.config_entries.async_update_entry(entry, data=data, title=title, minor_version=2)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: TrailsafeConfigEntry) -> bool:
    coordinator = TrailsafeCoordinator(
        hass,
        entry,
        update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # One avatar view for all entries (it looks the entry up per request).
    if not hass.data.get(f"{DOMAIN}_avatar_view"):
        hass.http.register_view(TrailsafeAvatarView(hass))
        hass.data[f"{DOMAIN}_avatar_view"] = True

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TrailsafeConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: TrailsafeConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Allow deleting a member's device once none of its trackers are in the feed.

    Devices are per member (user_sub). A member still present in the feed
    can't be deleted (it would come straight back on the next poll).
    """
    data = entry.runtime_data.data or {}
    live_subs = {d["user_sub"] for d in data.values()}
    return not any(
        domain == DOMAIN and ident in live_subs for domain, ident in device.identifiers
    )
