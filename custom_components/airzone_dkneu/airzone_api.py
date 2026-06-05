"""Airzone DKN Cloud EU API client — REST auth + a self-contained
engine.io-v3 / socket.io-v2 client over aiohttp (no external deps).

Reverse-engineered from the official 'Airzone DKN EU' app. See aircon-dkneu-api.md.
This module is Home-Assistant-independent so it can be unit-tested standalone.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable

import aiohttp

_LOGGER = logging.getLogger(__name__)

API_BASE = "https://dkneu.airzonecloud.com/api/v1/"
WS_URL = "wss://dkneu.airzonecloud.com/api/v1/devices/socket.io/?EIO=3&transport=websocket"
SCOPE = "dknEU"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)


class DknEuError(Exception):
    """Generic API error."""


class DknEuAuthError(DknEuError):
    """Login / token failure."""


class DknEuApi:
    """REST half of the DKN EU cloud: login, token refresh, installations."""

    def __init__(self, session: aiohttp.ClientSession, email: str, password: str) -> None:
        self._session = session
        self._email = email
        self._password = password
        self.token: str | None = None
        self.refresh_token: str | None = None

    def _headers(self, auth: bool = True) -> dict[str, str]:
        h = {"User-Agent": USER_AGENT, "Accept": "application/json, text/plain, */*"}
        if auth and self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    async def login(self) -> dict[str, Any]:
        url = f"{API_BASE}auth/login/{SCOPE}"
        body = {"email": self._email, "password": self._password}
        async with self._session.post(url, json=body, headers=self._headers(auth=False)) as r:
            if r.status in (400, 401, 403):
                raise DknEuAuthError(f"login rejected ({r.status})")
            if r.status != 200:
                raise DknEuError(f"login failed ({r.status})")
            data = await r.json()
        self.token = str(data["token"])
        self.refresh_token = str(data["refreshToken"])
        return data

    async def async_refresh_token(self) -> str:
        if not self.refresh_token:
            raise DknEuAuthError("no refresh token; must login")
        url = f"{API_BASE}auth/refreshToken/{self.refresh_token}/{SCOPE}"
        async with self._session.get(url, headers=self._headers(auth=False)) as r:
            if r.status != 200:
                raise DknEuAuthError(f"refresh failed ({r.status})")
            data = await r.json()
        self.token = str(data["token"])
        self.refresh_token = str(data.get("newRefreshToken", self.refresh_token))
        return self.token

    async def get_installations(self) -> list[dict[str, Any]]:
        url = f"{API_BASE}installations/{SCOPE}"
        async with self._session.get(url, headers=self._headers()) as r:
            if r.status == 401:
                await self.async_refresh_token()
                return await self.get_installations()
            if r.status != 200:
                raise DknEuError(f"installations failed ({r.status})")
            return await r.json()


class DknEuSocket:
    """Minimal engine.io-v3 / socket.io-v2 client (websocket transport).

    Protocol (verified on the wire):
      engine.io packet = '<type><data>'  (0 open,1 close,2 ping,3 pong,4 message)
      socket.io packet (inside type 4)   = '<type>[/ns,][ackid][json]'
                                            (0 connect,1 disconnect,2 event,3 ack,4 error)
    EIO3 => the CLIENT sends ping ('2') every pingInterval; server replies pong ('3').
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        token: str,
        install_id: str,
        on_device_data: Callable[[dict[str, Any]], None],
        on_disconnect: Callable[[], None] | None = None,
    ) -> None:
        self._session = session
        self._token = token
        self._ns = f"/{install_id}::{SCOPE}"
        self._on_device_data = on_device_data
        self._on_disconnect = on_disconnect
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._ping_interval = 15.0
        self._ack_id = 0
        self._acks: dict[int, asyncio.Future] = {}
        self._tasks: list[asyncio.Task] = []
        self._ns_connected = asyncio.Event()
        self._closing = False

    async def connect(self, timeout: float = 20.0) -> None:
        headers = {"Authorization": f"Bearer {self._token}", "User-Agent": USER_AGENT}
        self._ws = await self._session.ws_connect(WS_URL, headers=headers, heartbeat=None)
        self._tasks.append(asyncio.ensure_future(self._receive_loop()))
        await asyncio.wait_for(self._ns_connected.wait(), timeout=timeout)

    async def _send(self, data: str) -> None:
        if self._ws and not self._ws.closed:
            await self._ws.send_str(data)

    async def _receive_loop(self) -> None:
        try:
            assert self._ws is not None
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        await self._handle_packet(msg.data)
                    except Exception:  # noqa: BLE001 — never let one bad frame kill the loop
                        _LOGGER.exception("error handling packet: %r", msg.data[:120])
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    break
        finally:
            if not self._closing and self._on_disconnect:
                self._on_disconnect()

    async def _handle_packet(self, packet: str) -> None:
        if not packet:
            return
        etype, body = packet[0], packet[1:]
        if etype == "0":  # engine.io OPEN
            info = json.loads(body)
            self._ping_interval = info.get("pingInterval", 15000) / 1000.0
            await self._send("40" + self._ns + ",")          # connect our namespace
            self._tasks.append(asyncio.ensure_future(self._heartbeat()))
        elif etype == "2":  # server ping (rare in EIO3) -> pong
            await self._send("3")
        elif etype == "3":  # pong
            pass
        elif etype == "4":  # socket.io message
            await self._handle_sio(body)
        # 1 close / 5 upgrade / 6 noop -> ignore

    async def _handle_sio(self, body: str) -> None:
        if not body:
            return
        sio_type, rest = body[0], body[1:]
        ns = "/"
        if rest.startswith("/"):
            comma = rest.find(",")
            if comma != -1:
                ns, rest = rest[:comma], rest[comma + 1:]
        # leading digits = ack id
        i = 0
        while i < len(rest) and rest[i].isdigit():
            i += 1
        ack_id = int(rest[:i]) if i else None
        payload = rest[i:]

        if sio_type == "0":            # CONNECT
            if ns == self._ns:
                self._ns_connected.set()
        elif sio_type == "2":          # EVENT
            data = json.loads(payload) if payload else []
            event = data[0] if data else None
            arg = data[1] if len(data) > 1 else None
            if event == "device-data" and isinstance(arg, dict):
                self._on_device_data(arg)
        elif sio_type == "3":          # ACK
            data = json.loads(payload) if payload else []
            fut = self._acks.pop(ack_id, None) if ack_id is not None else None
            if fut and not fut.done():
                fut.set_result(data)
        elif sio_type == "4":          # ERROR
            _LOGGER.warning("socket.io error on %s: %s", ns, payload)

    async def _heartbeat(self) -> None:
        try:
            while not self._closing:
                await asyncio.sleep(self._ping_interval)
                await self._send("2")
        except asyncio.CancelledError:
            pass

    async def emit(self, event: str, data: Any, with_ack: bool = True, timeout: float = 10.0) -> Any:
        self._ack_id += 1
        ack_id = self._ack_id
        frame = "42" + self._ns + ","
        if with_ack:
            frame += str(ack_id)
        frame += json.dumps([event, data], separators=(",", ":"))
        fut: asyncio.Future | None = None
        if with_ack:
            fut = asyncio.get_event_loop().create_future()
            self._acks[ack_id] = fut
        await self._send(frame)
        if fut is not None:
            try:
                return await asyncio.wait_for(fut, timeout)
            finally:
                self._acks.pop(ack_id, None)
        return None

    async def set_value(self, mac: str, prop: str, value: Any) -> Any:
        """Send one control change. Returns the server ack (e.g. [True])."""
        return await self.emit("create-machine-event", {"mac": mac, "property": prop, "value": value})

    @property
    def connected(self) -> bool:
        return self._ws is not None and not self._ws.closed

    async def close(self) -> None:
        self._closing = True
        for t in self._tasks:
            t.cancel()
        if self._ws and not self._ws.closed:
            await self._ws.close()
