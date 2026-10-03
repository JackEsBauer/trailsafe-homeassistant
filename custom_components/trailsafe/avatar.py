"""Serve member avatars to the Home Assistant frontend.

The PaceGuard avatar URLs need the integration API key, which must never
reach the browser. So the map/entity picture points at this view instead,
behind Home Assistant's own auth (the entity picture is a signed path), and
the view fetches the image from PaceGuard server-side with the API key.
"""

from __future__ import annotations

from http import HTTPStatus
import logging
import time

import aiohttp
from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import CONF_API_KEY, DOMAIN

_LOGGER = logging.getLogger(__name__)

AVATAR_PATH = "/api/trailsafe/avatar/{entry_id}/{user_sub}"
# Avatars change rarely; keep each one this long before asking PaceGuard again.
AVATAR_CACHE_SECONDS = 600


def avatar_path(entry_id: str, user_sub: str) -> str:
    return AVATAR_PATH.format(entry_id=entry_id, user_sub=user_sub)


class TrailsafeAvatarView(HomeAssistantView):
    """GET /api/trailsafe/avatar/{entry_id}/{user_sub} → the member's avatar."""

    url = AVATAR_PATH
    name = "api:trailsafe:avatar"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._cache: dict[tuple[str, str], tuple[float, bytes, str]] = {}

    async def get(self, request: web.Request, entry_id: str, user_sub: str) -> web.Response:
        entry = self.hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN or not hasattr(entry, "runtime_data"):
            return web.Response(status=HTTPStatus.NOT_FOUND)
        coordinator = entry.runtime_data
        # Only avatars this entry's feed actually offers: the view can't be
        # used to fetch arbitrary accounts' pictures with the stored key.
        avatar_url = next(
            (
                d.get("avatar_url")
                for d in (coordinator.data or {}).values()
                if d.get("user_sub") == user_sub and d.get("avatar_url")
            ),
            None,
        )
        if not avatar_url or not avatar_url.startswith("/"):
            return web.Response(status=HTTPStatus.NOT_FOUND)

        key = (entry_id, user_sub)
        cached = self._cache.get(key)
        if cached and time.monotonic() - cached[0] < AVATAR_CACHE_SECONDS:
            return self._image(cached[1], cached[2])

        try:
            async with coordinator.session.get(
                f"{coordinator.server_url}{avatar_url}",
                headers={"Authorization": f"Bearer {entry.data[CONF_API_KEY]}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    _LOGGER.debug("Avatar for %s: PaceGuard returned %s", user_sub, resp.status)
                    return web.Response(status=HTTPStatus.NOT_FOUND)
                body = await resp.read()
                ctype = resp.headers.get("Content-Type", "image/png")
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.debug("Avatar for %s: %s", user_sub, err)
            if cached:  # serve the stale copy rather than a broken image
                return self._image(cached[1], cached[2])
            return web.Response(status=HTTPStatus.BAD_GATEWAY)

        self._cache[key] = (time.monotonic(), body, ctype)
        return self._image(body, ctype)

    @staticmethod
    def _image(body: bytes, ctype: str) -> web.Response:
        return web.Response(
            body=body,
            content_type=ctype.split(";")[0],
            headers={"Cache-Control": "private, max-age=300"},
        )
