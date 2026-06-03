"""Device tracker platform for Trailsafe."""

import logging

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TrailsafeCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: TrailsafeCoordinator = hass.data[DOMAIN][entry.entry_id]

    tracked: set[str] = set()

    @callback
    def _check_new() -> None:
        new = []
        for key in coordinator.data:
            if key not in tracked:
                tracked.add(key)
                new.append(TrailsafeTracker(coordinator, key))
        if new:
            async_add_entities(new)

    _check_new()
    entry.async_on_unload(coordinator.async_add_listener(_check_new))


class TrailsafeTracker(CoordinatorEntity, TrackerEntity):
    """Represents one Trailsafe device on the map.

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

    @property
    def _data(self) -> dict | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._key)

    @property
    def device_info(self) -> DeviceInfo:
        d = self._data or {}
        return DeviceInfo(
            identifiers={(DOMAIN, self._user_sub)},
            name=d.get("display_name") or self._user_sub,
            manufacturer="Trailsafe",
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
    def location_accuracy(self) -> int:
        d = self._data
        if d and d.get("accuracy"):
            return int(d["accuracy"])
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
        if d and d.get("avatar_url"):
            server = self.coordinator._server_url
            return f"{server}{d['avatar_url']}"
        return None
