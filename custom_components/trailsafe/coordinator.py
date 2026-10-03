"""Data update coordinator for Trailsafe."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import TYPE_CHECKING

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_API_KEY, CONF_SERVER_URL, DOMAIN, ISSUE_PAID_PLAN

if TYPE_CHECKING:
    from . import TrailsafeConfigEntry

_LOGGER = logging.getLogger(__name__)


class TrailsafeCoordinator(DataUpdateCoordinator[dict[str, dict]]):
    """Polls /api/integration/positions and exposes per-device position data.

    The feed returns one entry per device (a user signed in on several
    devices yields several entries, each carrying a ``device_id``). Members
    with no live device fix are returned as a single per-user fallback entry
    without a ``device_id``. Data is keyed by ``device_id`` when present,
    falling back to ``user_sub`` so legacy single-device entities keep their
    identity.
    """

    config_entry: TrailsafeConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: TrailsafeConfigEntry,
        update_interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=update_interval,
        )
        self.server_url = entry.data[CONF_SERVER_URL].rstrip("/")
        self._api_key = entry.data[CONF_API_KEY]
        self._session = async_get_clientsession(hass)

    async def _async_update_data(self) -> dict[str, dict]:
        url = f"{self.server_url}/api/integration/positions"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        issue_id = f"{ISSUE_PAID_PLAN}_{self.config_entry.entry_id}"

        try:
            async with self._session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status == 401:
                    # Revoked or invalid key: let Home Assistant ask for a new
                    # one (reauth flow) instead of failing silently forever.
                    raise ConfigEntryAuthFailed(
                        "The Trail-Safe API key is no longer valid"
                    )
                if resp.status == 403:
                    # The key is fine but the owner's plan no longer includes
                    # the API. A new key won't help, so raise a repair issue
                    # rather than a reauth, and keep retrying (an upgrade
                    # brings it back without any action in HA).
                    ir.async_create_issue(
                        self.hass,
                        DOMAIN,
                        issue_id,
                        is_fixable=False,
                        severity=ir.IssueSeverity.ERROR,
                        translation_key=ISSUE_PAID_PLAN,
                        translation_placeholders={"title": self.config_entry.title},
                    )
                    raise UpdateFailed("The Trail-Safe plan no longer includes API access")
                if resp.status != 200:
                    raise UpdateFailed(f"Trail-Safe server returned {resp.status}")
                data = await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Connection error: {err}") from err

        ir.async_delete_issue(self.hass, DOMAIN, issue_id)

        positions: dict[str, dict] = {}
        for p in data.get("positions", []):
            sub = p.get("user_sub")
            if not sub:
                continue
            device_id = p.get("device_id")
            # The backend's per-user fallback row carries a synthetic
            # ``user:<sub>`` device id (for clients that connect without their
            # own device id). Treat that as the legacy per-user entry: drop the
            # device id so the tracker keeps its stable ``user_sub`` identity
            # and entity id, rather than spawning a new colon-laden one.
            if device_id == f"user:{sub}":
                device_id = None
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
            }
        return positions
