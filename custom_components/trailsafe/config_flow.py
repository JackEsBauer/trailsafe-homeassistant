"""Config flow for Trailsafe integration."""

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, CONF_SERVER_URL, CONF_API_KEY

DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_SERVER_URL, default="https://trail-safe.app"): str,
    vol.Required(CONF_API_KEY): str,
})


class TrailsafeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Trailsafe."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        errors = {}
        if user_input is not None:
            server_url = user_input[CONF_SERVER_URL].rstrip("/")
            api_key = user_input[CONF_API_KEY].strip()

            try:
                url = f"{server_url}/api/integration/positions"
                headers = {"Authorization": f"Bearer {api_key}"}
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 401:
                            errors["base"] = "invalid_auth"
                        elif resp.status == 403:
                            errors["base"] = "paid_plan_required"
                        elif resp.status != 200:
                            errors["base"] = "cannot_connect"
                        else:
                            data = await resp.json()
                            plan = data.get("plan", "unknown")
                            count = len(data.get("positions", []))

                            await self.async_set_unique_id(api_key[:16])
                            self._abort_if_unique_id_configured()

                            return self.async_create_entry(
                                title=f"Trailsafe ({plan}, {count} members)",
                                data={
                                    CONF_SERVER_URL: server_url,
                                    CONF_API_KEY: api_key,
                                },
                            )
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA,
            errors=errors,
        )
