"""Device tracker platform for PaceGuard."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.components.device_tracker import (
    ENTITY_ID_FORMAT,
    SourceType,
    TrackerEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.components.http.auth import async_sign_path
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util, slugify

from . import TrailsafeConfigEntry
from .avatar import avatar_path
from .const import DOMAIN
from .coordinator import TrailsafeCoordinator

_LOGGER = logging.getLogger(__name__)

# A tracker whose device has been gone from the feed this long (removed,
# merged into another device, re-linked under a new id) is deleted from the
# entity registry, so dead trackers don't pile up. Only counted while the
# feed itself is non-empty, so a blank or failed poll never deletes anything.
STALE_AFTER = timedelta(hours=24)

# The map marker / entity picture is a signed Home Assistant path to the
# avatar view (the browser can't send the PaceGuard API key). Signed for a
# week and re-signed when a day is left, so the attribute changes about once
# a week instead of on every poll.
AVATAR_SIGN_FOR = timedelta(days=7)
AVATAR_RESIGN_BEFORE = timedelta(days=1)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TrailsafeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    registry = er.async_get(hass)

    tracked: set[str] = set()
    missing_since: dict[str, object] = {}

    @callback
    def _sync() -> None:
        data = coordinator.data or {}
        new = []
        for key in data:
            missing_since.pop(key, None)
            if key not in tracked:
                tracked.add(key)
                new.append(TrailsafeTracker(coordinator, key))
        if new:
            async_add_entities(new)

        if not data or not coordinator.last_update_success:
            return
        now = dt_util.utcnow()
        for key in list(tracked):
            if key in data:
                continue
            since = missing_since.setdefault(key, now)
            if now - since < STALE_AFTER:
                continue
            entity_id = registry.async_get_entity_id(
                "device_tracker", DOMAIN, f"trailsafe_{key}"
            )
            if entity_id:
                _LOGGER.info("Removing %s: gone from the PaceGuard feed for %s", entity_id, STALE_AFTER)
                registry.async_remove(entity_id)
            tracked.discard(key)
            missing_since.pop(key, None)

    # Pick up trackers that exist in the registry from earlier runs but are no
    # longer in the feed, so they go stale (and get cleaned up) too.
    for reg in er.async_entries_for_config_entry(registry, entry.entry_id):
        if reg.domain == "device_tracker" and reg.unique_id.startswith("trailsafe_"):
            key = reg.unique_id.removeprefix("trailsafe_")
            if key not in (coordinator.data or {}):
                tracked.add(key)

    _sync()
    entry.async_on_unload(coordinator.async_add_listener(_sync))


class TrailsafeTracker(CoordinatorEntity[TrailsafeCoordinator], TrackerEntity):
    """Represents one PaceGuard device on the map.

    Entities are keyed per device. All devices owned by the same user are
    grouped under a single Home Assistant device (named after the user) via
    ``device_info``, so a family member with four watches shows up as one
    device holding four ``device_tracker`` entities.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: TrailsafeCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"trailsafe_{key}"
        # Capture the owning user at construction so the HA device identifier
        # stays stable even if the entry later drops out of the feed.
        d = coordinator.data.get(key) or {}
        self._user_sub = d.get("user_sub") or key
        self._display_name = d.get("display_name") or self._user_sub
        self._picture: tuple[str, object] | None = None  # (signed url, expires)

        # Build a readable, stable entity_id of the form
        # ``device_tracker.trailsafe_<account>_<device>`` rather than letting
        # HA derive it from the (often email-shaped) display name. The account
        # part strips any email domain; the device part uses the friendly
        # device name, falling back to a short id slice for the per-user row.
        # Two devices with the same name (two identical watches) get a short
        # id suffix instead of HA's anonymous "_2". Only applies to NEW
        # entities: the registry keeps existing entity ids.
        account = self._display_name.split("@", 1)[0]
        device_label = d.get("device_name")
        if not device_label and d.get("device_id"):
            device_label = d["device_id"][:6]
        elif device_label and d.get("device_id") and _name_is_shared(coordinator, key, d):
            device_label = f"{device_label} {d['device_id'][:4]}"
        parts = [slugify(p) for p in ("trailsafe", account, device_label or "")]
        self.entity_id = ENTITY_ID_FORMAT.format("_".join(p for p in parts if p))

    @property
    def _data(self) -> dict | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._key)

    @property
    def available(self) -> bool:
        # Gone from the feed (removed / merged / re-linked) → unavailable,
        # rather than frozen on the last fix as if it were still there.
        return super().available and self._data is not None

    @property
    def device_info(self) -> DeviceInfo:
        d = self._data or {}
        return DeviceInfo(
            identifiers={(DOMAIN, self._user_sub)},
            name=d.get("display_name") or self._display_name,
            manufacturer="PaceGuard",
        )

    @property
    def name(self) -> str | None:
        d = self._data
        # Per-device rows name the entity after the device; Home Assistant
        # prefixes the owning user's name from device_info ("Sander Watch").
        # The legacy per-user row (no device_id) returns None so the entity
        # simply adopts the user's name.
        if d and d.get("device_id"):
            return d.get("device_name") or f"Device {d['device_id'][:6]}"
        return None

    @property
    def latitude(self) -> float | None:
        d = self._data
        if d and d.get("lat"):
            return d["lat"]
        return None

    @property
    def longitude(self) -> float | None:
        d = self._data
        if d and d.get("lng"):
            return d["lng"]
        return None

    @property
    def location_accuracy(self) -> float:
        d = self._data
        if d and d.get("accuracy"):
            return float(d["accuracy"])
        return 0

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def icon(self) -> str:
        d = self._data
        if d and d.get("sos"):
            return "mdi:alert"
        if d and d.get("online"):
            return "mdi:walk"
        return "mdi:account-clock"

    @property
    def extra_state_attributes(self) -> dict:
        d = self._data
        if not d:
            return {}
        attrs = {
            "user_sub": d.get("user_sub"),
            "online": d.get("online", False),
            "sos": d.get("sos", False),
        }
        if d.get("device_id"):
            attrs["device_id"] = d["device_id"]
        if d.get("device_name"):
            attrs["device_name"] = d["device_name"]
        if d.get("recorded_at"):
            attrs["recorded_at"] = d["recorded_at"]
        return attrs

    @property
    def entity_picture(self) -> str | None:
        d = self._data
        if not d or not d.get("avatar_url"):
            self._picture = None
            return None
        now = dt_util.utcnow()
        if self._picture is None or self._picture[1] - now < AVATAR_RESIGN_BEFORE:
            url = async_sign_path(
                self.hass,
                avatar_path(self.coordinator.config_entry.entry_id, self._user_sub),
                AVATAR_SIGN_FOR,
            )
            self._picture = (url, now + AVATAR_SIGN_FOR)
        return self._picture[0]


def _name_is_shared(coordinator: TrailsafeCoordinator, key: str, d: dict) -> bool:
    """Whether another device of the same member carries the same name."""
    for other_key, other in (coordinator.data or {}).items():
        if other_key == key:
            continue
        if other.get("user_sub") == d.get("user_sub") and other.get("device_name") == d.get("device_name"):
            return True
    return False
