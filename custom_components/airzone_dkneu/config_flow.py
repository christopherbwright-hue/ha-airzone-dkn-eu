"""Config flow for Airzone DKN Cloud EU."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .airzone_api import DknEuApi, DknEuAuthError, DknEuError
from .const import DOMAIN


async def _validate(hass, username: str, password: str) -> None:
    session = async_get_clientsession(hass)
    await DknEuApi(session, username, password).login()


class DknEuConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Airzone DKN Cloud EU."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
            self._abort_if_unique_id_configured()
            try:
                await _validate(self.hass, user_input[CONF_USERNAME], user_input[CONF_PASSWORD])
            except DknEuAuthError:
                errors["base"] = "invalid_auth"
            except DknEuError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_USERNAME], data=user_input
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()
        if user_input is not None:
            try:
                await _validate(
                    self.hass, reauth_entry.data[CONF_USERNAME], user_input[CONF_PASSWORD]
                )
            except DknEuAuthError:
                errors["base"] = "invalid_auth"
            except DknEuError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data={**reauth_entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            description_placeholders={CONF_USERNAME: reauth_entry.data[CONF_USERNAME]},
            errors=errors,
        )
