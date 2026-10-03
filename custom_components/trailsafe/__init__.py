"""Trailsafe GPS Tracker integration for Home Assistant."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import TrailsafeCoordinator

PLATFORMS = [Platform.DEVICE_TRACKER]

type TrailsafeConfigEntry = ConfigEntry[TrailsafeCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: TrailsafeConfigEntry) -> bool:
    coordinator = TrailsafeCoordinator(
        hass,
        entry,
        update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

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
