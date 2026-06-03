"""Data update coordinator for Trailsafe."""

from datetime import timedelta
import logging

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_SERVER_URL, CONF_API_KEY, DOMAIN

_LOGGER = logging.getLogger(__name__)


class TrailsafeCoordinator(DataUpdateCoordinator):
    """Polls /api/integration/positions and exposes per-device position data.

    The feed returns one entry per device (a user signed in on several
    devices yields several entries, each carrying a ``device_id``). Members
    with no live device fix are returned as a single per-user fallback entry
    without a ``device_id``. Data is keyed by ``device_id`` when present,
    falling back to ``user_sub`` so legacy single-device entities keep their
    identity.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        update_interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )
        self._server_url = entry.data[CONF_SERVER_URL].rstrip("/")
        self._api_key = entry.data[CONF_API_KEY]

    async def _async_update_data(self) -> dict:
        url = f"{self._server_url}/api/integration/positions"
        headers = {"Authorization": f"Bearer {self._api_key}"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 401:
                        raise UpdateFailed("Invalid API key — check your Trail-Safe dashboard")
                    if resp.status == 403:
                        raise UpdateFailed("API key requires a paid Trail-Safe plan")
                    if resp.status != 200:
                        raise UpdateFailed(f"Server returned {resp.status}")
                    data = await resp.json()
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Connection error: {err}") from err

        positions = {}
        for p in data.get("positions", []):
            sub = p.get("user_sub")
            if not sub:
                continue
            device_id = p.get("device_id")
            # Key by device so a user with several devices yields several
            # trackers. The per-user fallback entry (no device_id) keeps the
            # user_sub key, preserving the legacy entity for that member.
            key = device_id or sub
            positions[key] = {
                "key": key,
                "user_sub": sub,
                "device_id": device_id,
                "display_name": p.get("display_name") or sub,
                "device_name": p.get("device_name"),
                "lat": p.get("lat", 0),
                "lng": p.get("lng", 0),
                "accuracy": p.get("accuracy", 0),
                "recorded_at": p.get("recorded_at", 0),
                "online": p.get("online", False),
                "sos": p.get("sos", False),
                "avatar_url": p.get("avatar_url"),
            }
        return positions
