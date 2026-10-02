"""The Airzone DKN Cloud EU integration."""
from __future__ import annotations

import asyncio

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .airzone_api import DknEuApi, DknEuAuthError, DknEuError
from .const import DOMAIN
from .coordinator import DknEuCoordinator

PLATFORMS = [Platform.CLIMATE, Platform.SENSOR]

type DknEuConfigEntry = ConfigEntry[DknEuCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: DknEuConfigEntry) -> bool:
    """Set up Airzone DKN Cloud EU from a config entry."""
    session = async_get_clientsession(hass)
    api = DknEuApi(session, entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])

    try:
        await api.login()
    except DknEuAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except (DknEuError, aiohttp.ClientError, asyncio.TimeoutError) as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = DknEuCoordinator(hass, entry, api)
    try:
        await coordinator.async_setup()
    except (DknEuError, aiohttp.ClientError, asyncio.TimeoutError, OSError) as err:
        await coordinator.async_close()
        raise ConfigEntryNotReady(str(err)) from err

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DknEuConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_close()
    return unload_ok
