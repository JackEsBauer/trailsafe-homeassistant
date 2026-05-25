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
    """Polls /api/integration/positions and exposes per-user position data."""

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
                        raise UpdateFailed("Invalid API key — check your Trailsafe dashboard")
                    if resp.status == 403:
                        raise UpdateFailed("API key requires a paid Trailsafe plan")
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
            positions[sub] = {
                "user_sub": sub,
                "display_name": p.get("display_name") or p.get("device_name") or sub,
                "lat": p.get("lat", 0),
                "lng": p.get("lng", 0),
                "accuracy": p.get("accuracy", 0),
                "recorded_at": p.get("recorded_at", 0),
                "online": p.get("online", False),
                "sos": p.get("sos", False),
                "avatar_url": p.get("avatar_url"),
            }
        return positions
