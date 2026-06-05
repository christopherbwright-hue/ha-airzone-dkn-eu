# Airzone DKN Cloud EU — API protocol

Reverse-engineered from the official **"Airzone DKN EU"** Android app (a Cordova/Vue app, so the
API client is plain JavaScript). This documents the backend the **DKN Cloud EU** app talks to.
No account-specific data here.

## Hosts
| Environment | Base URL |
|---|---|
| **Production** | `https://dkneu.airzonecloud.com/` |
| Pre | `https://predkneu.airzonecloud.com:8443/` |
| Dev | `https://devdkneu.airzonecloud.com:8443/` |

- **API version prefix:** `api/v1/` → effective base `https://dkneu.airzonecloud.com/api/v1/`
- **Scope:** `dknEU` (suffixed on most paths)
- **Auth header:** `Authorization: Bearer <token>`

## REST endpoints
| Purpose | Method | Path | Body / notes |
|---|---|---|---|
| Login | POST | `auth/login/dknEU` | `{email, password}` → `{token, refreshToken, ...user}` |
| Refresh token | GET | `auth/refreshToken/<refreshToken>/dknEU` | → `{token, newRefreshToken}` |
| Session check | GET | `users/isLoggedin/dknEU` | |
| List installations | GET | `installations/dknEU` | homes + their devices (mac + name) |

## Live state + control = socket.io (not REST)
- **Protocol:** socket.io **v2** / engine.io **v3** (`EIO=3`).
- **Path:** `/api/v1/devices/socket.io/`
- **Auth:** bearer token. The app uses polling with the token in `extraHeaders`; the **websocket**
  transport works too and is simpler (token on the WS handshake). Note that some HTTP clients only
  send custom headers on the engine.io *handshake* and not on subsequent long-poll requests — if
  you see `401` after the handshake on polling, use the websocket transport.
- **Installation namespace:** `/<installationId>::dknEU`
  - **Read:** the server pushes `device-data` → `{ mac, data: {…} }` for every device on connect,
    then again on any change. (It does **not** echo a change back to the socket that made it.)
  - **Write:** `emit('create-machine-event', { mac, property, value })`.

## `device-data` property dictionary (per unit)
| Property | Meaning |
|---|---|
| `power` (bool) | unit on/off |
| `mode` (int) | 1=auto 2=cool 3=heat 4=fan 5=dry · `mode_available` = allowed list |
| `work_temp` / `local_temp` | current room temperature (use `work_temp` then `local_temp`) |
| `setpoint_air_cool` / `_heat` / `_auto` | target temp per mode |
| `range_sp_{cool,hot,auto}_air_{min,max}` | setpoint limits |
| `speed_state` (int) / `speed_available` (list) | fan speed + allowed speeds |
| `slats_autoud`, `slats_swingud`, `slats_vnum` | vane / swing |
| `units` (int) | 0 = °C, 1 = °F |
| `isConnected`, `machineready`, `error_value`, `tsensor_error` | availability / health |
| `block_on/off/mode/setpoint` (bool) | cloud locks on actions |
| `power_acs`, `setpoint_acs`, `acs_available` | hot water / DHW (Altherma) |
| `aqpresent`, `aqready` | air-quality module presence |
| `stat_rssi`, `stat_ssid` | Wi-Fi diagnostics |
| `manufacturer` `{_id,text}`, `version`, `name` | metadata |
| `return_temp`, `exch_heat_temp_iu`, `gas_pipe_temp_iu`, `exp_valv_ui` | VRV indoor-unit sensors |

## Control payloads
`emit('create-machine-event', { mac, property, value })` where `property` is one of the keys above:
- power: `{property:'power', value:true|false}`
- mode: `{property:'mode', value:2}`
- setpoint: `{property:'setpoint_air_cool'|'setpoint_air_heat', value:21}`
- fan: `{property:'speed_state', value:4}`

## Enums
- **MODES:** AUTO=1, COOL=2, HEAT=3, FAN=4, DRY=5
- **UNITS:** CELSIUS=0, FAHRENHEIT=1
- **SLATS:** AUTO=8, SWING=9
