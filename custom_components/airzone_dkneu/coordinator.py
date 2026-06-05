"""Coordinator: REST auth + a live socket.io link per installation.

Push-based: device-data events from the cloud update state and notify entities.
Handles token refresh and socket reconnection with backoff.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .airzone_api import DknEuApi, DknEuAuthError, DknEuError, DknEuSocket
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

INITIAL_STATE_TIMEOUT = 12  # seconds to wait for first device-data on setup


class DknEuCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Holds device state keyed by MAC, fed by per-installation sockets."""

    def __init__(self, hass: HomeAssistant, api: DknEuApi) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN)
        self.api = api
        self.units: dict[str, dict[str, Any]] = {}        # mac -> {name, icon, mac, install_id}
        self.installations: list[dict[str, Any]] = []
        self.data: dict[str, dict[str, Any]] = {}         # mac -> live state
        self._sockets: dict[str, DknEuSocket] = {}        # install_id -> socket
        self._reconnecting: set[str] = set()
        self._closing = False

    async def async_setup(self) -> None:
        """Discover installations/units and open a socket per installation."""
        self.installations = await self.api.get_installations()
        for inst in self.installations:
            iid = inst["_id"]
            for dev in inst.get("devices", []):
                mac = dev["mac"]
                self.units[mac] = {**dev, "install_id": iid}
                self.data.setdefault(mac, {})

        for inst in self.installations:
            await self._connect_installation(inst["_id"])

        # Wait briefly for the initial state snapshot so entities start populated.
        for _ in range(INITIAL_STATE_TIMEOUT * 4):
            if self.units and all(
                "mode" in self.data.get(mac, {}) or "isConnected" in self.data.get(mac, {})
                for mac in self.units
            ):
                break
            await asyncio.sleep(0.25)

        self.async_set_updated_data(self.data)

    async def _connect_installation(self, install_id: str) -> None:
        session = async_get_clientsession(self.hass)
        sock = DknEuSocket(
            session,
            self.api.token,
            install_id,
            self._on_device_data,
            on_disconnect=lambda iid=install_id: self._handle_disconnect(iid),
        )
        await sock.connect()
        self._sockets[install_id] = sock

    @callback
    def _on_device_data(self, payload: dict[str, Any]) -> None:
        mac = payload.get("mac")
        data = payload.get("data") or {}
        if not mac:
            return
        self.data.setdefault(mac, {}).update(data)
        self.async_set_updated_data(self.data)

    @callback
    def _handle_disconnect(self, install_id: str) -> None:
        if self._closing or install_id in self._reconnecting:
            return
        self._reconnecting.add(install_id)
        self.hass.async_create_task(self._reconnect(install_id))

    async def _reconnect(self, install_id: str) -> None:
        delay = 5
        try:
            while not self._closing:
                await asyncio.sleep(delay)
                try:
                    try:
                        await self.api.async_refresh_token()
                    except DknEuAuthError:
                        await self.api.login()
                    await self._connect_installation(install_id)
                    _LOGGER.info("Reconnected DKN EU installation %s", install_id)
                    return
                except Exception as err:  # noqa: BLE001 — keep retrying on any failure
                    _LOGGER.warning("DKN EU reconnect failed (%s); retrying in %ss", err, min(delay * 2, 60))
                    delay = min(delay * 2, 60)
        finally:
            self._reconnecting.discard(install_id)

    async def async_set_value(self, mac: str, prop: str, value: Any) -> None:
        """Send one control change and optimistically reflect it locally."""
        unit = self.units.get(mac)
        if not unit:
            raise HomeAssistantError(f"Unknown unit {mac}")
        sock = self._sockets.get(unit["install_id"])
        if not sock or not sock.connected:
            raise HomeAssistantError("DKN EU cloud not connected")
        try:
            ack = await sock.set_value(mac, prop, value)
        except (DknEuError, asyncio.TimeoutError) as err:
            raise HomeAssistantError(f"DKN EU command failed: {err}") from err
        # The cloud doesn't echo our own change, so update locally for instant UI.
        self.data.setdefault(mac, {})[prop] = value
        self.async_set_updated_data(self.data)
        _LOGGER.debug("set %s %s=%s ack=%s", mac, prop, value, ack)

    async def async_close(self) -> None:
        self._closing = True
        for sock in self._sockets.values():
            await sock.close()
        self._sockets.clear()
