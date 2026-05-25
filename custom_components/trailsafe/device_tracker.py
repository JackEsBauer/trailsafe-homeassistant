"""Device tracker platform for Trailsafe."""

import logging

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
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
        for sub, data in coordinator.data.items():
            if sub not in tracked:
                tracked.add(sub)
                new.append(TrailsafeTracker(coordinator, sub))
        if new:
            async_add_entities(new)

    _check_new()
    entry.async_on_unload(coordinator.async_add_listener(_check_new))


class TrailsafeTracker(CoordinatorEntity, TrackerEntity):
    """Represents one Trailsafe user/device on the map."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: TrailsafeCoordinator, user_sub: str) -> None:
        super().__init__(coordinator)
        self._user_sub = user_sub
        self._attr_unique_id = f"trailsafe_{user_sub}"

    @property
    def _data(self) -> dict | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._user_sub)

    @property
    def name(self) -> str:
        d = self._data
        if d:
            return d.get("display_name", self._user_sub)
        return self._user_sub

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
            "user_sub": self._user_sub,
            "online": d.get("online", False),
            "sos": d.get("sos", False),
        }
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
