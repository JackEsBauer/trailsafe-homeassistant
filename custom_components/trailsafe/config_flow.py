"""Config flow for Trailsafe integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_API_KEY, CONF_SERVER_URL, DOMAIN

DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_SERVER_URL, default="https://trail-safe.app"): str,
    vol.Required(CONF_API_KEY): str,
})

REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_API_KEY): str})


async def _probe(hass: HomeAssistant, server_url: str, api_key: str) -> tuple[str | None, dict]:
    """Call the feed once. Returns (error key or None, response JSON)."""
    session = async_get_clientsession(hass)
    try:
        async with session.get(
            f"{server_url}/api/integration/positions",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status == 401:
                return "invalid_auth", {}
            if resp.status == 403:
                return "paid_plan_required", {}
            if resp.status != 200:
                return "cannot_connect", {}
            return None, await resp.json()
    except (aiohttp.ClientError, TimeoutError):
        return "cannot_connect", {}


class TrailsafeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Trailsafe."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            server_url = user_input[CONF_SERVER_URL].rstrip("/")
            api_key = user_input[CONF_API_KEY].strip()
            error, data = await _probe(self.hass, server_url, api_key)
            if error:
                errors["base"] = error
            else:
                plan = data.get("plan", "unknown")
                count = len(data.get("positions", []))

                # Unchanged since v1.0: existing entries are keyed on it.
                await self.async_set_unique_id(api_key[:16])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"Trail-Safe ({plan}, {count} members)",
                    data={CONF_SERVER_URL: server_url, CONF_API_KEY: api_key},
                )

        return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """The stored API key was rejected (revoked or invalid)."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new API key and keep the existing entry and its entities."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            error, _ = await _probe(self.hass, entry.data[CONF_SERVER_URL], api_key)
            if error:
                errors["base"] = error
            else:
                # The entry's unique id stays the OLD key prefix on purpose:
                # changing it would orphan nothing, but there is no need to.
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_API_KEY: api_key}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
            errors=errors,
            description_placeholders={"server_url": entry.data[CONF_SERVER_URL]},
        )
