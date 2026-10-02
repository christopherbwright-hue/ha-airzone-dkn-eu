"""Coordinator: REST auth + a live socket.io link per installation.

Push-based: device-data events from the cloud update state and notify entities.
Handles token refresh, socket reconnection with backoff, and hands credential
failures to Home Assistant's re-authentication flow.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .airzone_api import (
    DknEuApi,
    DknEuAuthError,
    DknEuCommandRejected,
    DknEuError,
    DknEuSocket,
)
from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)

INITIAL_STATE_TIMEOUT = 12  # seconds to wait for first device-data on setup
RECONNECT_FIRST_DELAY = 2   # seconds; doubles per failed attempt
RECONNECT_MAX_DELAY = 60


class DknEuCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Holds device state keyed by MAC, fed by per-installation sockets."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: DknEuApi) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN)
        self.api = api
        self.units: dict[str, dict[str, Any]] = {}        # mac -> {name, icon, mac, install_id}
        self.installations: list[dict[str, Any]] = []
        self.data: dict[str, dict[str, Any]] = {}         # mac -> live state
        self._sockets: dict[str, DknEuSocket] = {}        # install_id -> socket
        self._online: set[str] = set()                    # install_ids with a live link
        self._reconnect_tasks: dict[str, asyncio.Task] = {}
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

    def unit_available(self, mac: str) -> bool:
        """True only if the cloud link is up AND the cloud reports the unit online.

        Without the link check, a dropped connection would leave entities showing
        their last-known state as if it were live.
        """
        unit = self.units.get(mac)
        if not unit or unit["install_id"] not in self._online:
            return False
        d = self.data.get(mac, {})
        return bool(d) and bool(d.get("isConnected"))

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
        if self._closing:
            await sock.close()
            return
        self._sockets[install_id] = sock
        self._online.add(install_id)
        self.async_update_listeners()

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
        if self._closing:
            return
        self._online.discard(install_id)
        self.async_update_listeners()  # entities go unavailable immediately
        if install_id in self._reconnect_tasks:
            return
        self._reconnect_tasks[install_id] = self.config_entry.async_create_background_task(
            self.hass,
            self._reconnect(install_id),
            f"{DOMAIN} reconnect {install_id}",
        )

    async def _reconnect(self, install_id: str) -> None:
        delay = RECONNECT_FIRST_DELAY
        try:
            old = self._sockets.pop(install_id, None)
            if old is not None:
                await old.close()  # stop its tasks; prevents a leak per reconnect
            while not self._closing:
                await asyncio.sleep(delay)
                try:
                    try:
                        await self.api.async_refresh_token()
                    except DknEuAuthError:
                        await self.api.login()
                except DknEuAuthError as err:
                    # Password changed / account locked: stop hammering the login
                    # endpoint and ask the user via HA's re-auth flow instead.
                    _LOGGER.error(
                        "DKN EU credentials rejected (%s); re-authentication required", err
                    )
                    self.config_entry.async_start_reauth(self.hass)
                    return
                except Exception as err:  # noqa: BLE001 — network/server trouble: retry
                    delay = min(delay * 2, RECONNECT_MAX_DELAY)
                    _LOGGER.warning("DKN EU token refresh failed (%s); retrying in %ss", err, delay)
                    continue
                try:
                    await self._connect_installation(install_id)
                except Exception as err:  # noqa: BLE001 — keep retrying on any failure
                    delay = min(delay * 2, RECONNECT_MAX_DELAY)
                    _LOGGER.warning("DKN EU reconnect failed (%s); retrying in %ss", err, delay)
                    continue
                _LOGGER.info("Reconnected DKN EU installation %s", install_id)
                return
        finally:
            self._reconnect_tasks.pop(install_id, None)

    async def async_set_value(self, mac: str, prop: str, value: Any) -> None:
        """Send one control change; reflect it locally only once the cloud accepts it."""
        unit = self.units.get(mac)
        if not unit:
            raise HomeAssistantError(f"Unknown unit {mac}")
        sock = self._sockets.get(unit["install_id"])
        if not sock or not sock.connected:
            raise HomeAssistantError("DKN EU cloud not connected")
        try:
            ack = await sock.set_value(mac, prop, value)
        except DknEuCommandRejected as err:
            raise HomeAssistantError(f"DKN EU cloud rejected the change: {err}") from err
        except TimeoutError as err:
            # Outcome unknown, and the cloud never echoes our own changes, so
            # force a reconnect: the server sends a full state snapshot on connect.
            _LOGGER.warning("No ack for %s %s=%s; resyncing state", mac, prop, value)
            self.hass.async_create_task(sock.abort())
            raise HomeAssistantError(
                "DKN EU cloud did not confirm the change; resyncing state"
            ) from err
        except DknEuError as err:
            raise HomeAssistantError(f"DKN EU command failed: {err}") from err
        # The cloud doesn't echo our own change, so update locally for instant UI.
        self.data.setdefault(mac, {})[prop] = value
        self.async_set_updated_data(self.data)
        _LOGGER.debug("set %s %s=%s ack=%s", mac, prop, value, ack)

    async def async_close(self) -> None:
        self._closing = True
        for task in list(self._reconnect_tasks.values()):
            task.cancel()
        self._reconnect_tasks.clear()
        for sock in list(self._sockets.values()):
            await sock.close()
        self._sockets.clear()
        self._online.clear()
