# Airzone DKN Cloud EU — Home Assistant integration

[![hacs](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
![version](https://img.shields.io/badge/version-0.1.1-blue.svg)
![license](https://img.shields.io/badge/license-MIT-green.svg)

> **Fork note:** this is a fork of [jxmatthews/ha-airzone-dkn-eu](https://github.com/jxmatthews/ha-airzone-dkn-eu) with reliability fixes — see [CHANGELOG.md](CHANGELOG.md).

A Home Assistant integration for **Daikin / Airzone air-conditioning systems that use the
"DKN Cloud EU" app** — the ones with `DAIKIN ES.DKNWSERVER` Wi-Fi adapters whose backend is
`dkneu.airzonecloud.com`. Each indoor unit appears as a **climate** entity with live state and
full control, plus **diagnostic sensors**.

> **Why this exists.** The existing community integrations
> ([`max13fr/AirzoneCloudDaikin`](https://github.com/max13fr/AirzonecloudDaikin),
> [`eXPerience83/DKNCloud-HASS`](https://github.com/eXPerience83/DKNCloud-HASS)) target the
> **older, non-EU** cloud (`dkn.airzonecloud.com`, a REST `/users/sign_in` + `/events` API).
> The **EU** cloud is a different generation entirely — bearer-token auth and **socket.io**
> for both live state and control — so those integrations return *"invalid username and
> password"* for EU accounts. This is a clean-room implementation of the EU API. If the
> **DKN Cloud EU** app is the one that works for you, this is your integration.

## Features
- 🌡️ One **climate** entity per indoor unit: off / cool / heat / fan / dry (only the modes your
  unit actually reports), current temperature, target setpoint, fan speed, and min/max limits.
- 📊 **Diagnostic sensors** (VRV indoor-unit telemetry): return-air, heat-exchanger and gas-pipe
  temperatures, expansion-valve position, and Wi-Fi signal (disabled by default).
- ⚡ **Real-time push** updates over a persistent socket.io link — no polling — with optimistic
  local echo on control.
- 🔌 **No external Python dependencies.** A small, self-contained engine.io-v3 / socket.io-v2
  client built on `aiohttp` (already shipped with Home Assistant), so there is no
  `python-socketio` version pin to clash with the rest of your install.
- 🔐 UI **config flow** (email + password), token refresh, and automatic socket reconnection.
- 🏠 Multi-installation and multi-account capable; entities grouped per device.

## Installation

### HACS (custom repository)
1. HACS → ⋮ (top right) → **Custom repositories**
2. Repository: `https://github.com/jxmatthews/ha-airzone-dkn-eu`, Category: **Integration** → **Add**
3. Find **"Airzone DKN Cloud EU"** in HACS, **Download**, then **restart Home Assistant**
4. **Settings → Devices & Services → Add Integration → "Airzone DKN Cloud EU"**
5. Sign in with the email + password you use in the **DKN Cloud EU** app

### Manual
Copy `custom_components/airzone_dkneu` into your Home Assistant `config/custom_components/`
directory and restart, then add the integration as in steps 4–5 above.

## Supported / tested
- ✅ Verified against a live **6-unit ducted VRV** installation (DKN Cloud EU).
- Should work for any account that signs in via the **DKN Cloud EU** app. If yours is the plain
  **"Airzone Cloud"** app (not DKN), use the built-in
  [Airzone Cloud](https://www.home-assistant.io/integrations/airzone_cloud/) integration instead.

## Not yet supported (roadmap — contributions welcome)
The cloud exposes more than v0.1 surfaces. Planned / open for PRs:
- Vane / swing control (`slats_*` → `swing_mode`)
- Fault / error binary-sensor (`error_value`, `machineready`, `tsensor_error`)
- Friendlier fan-speed labels (Low / Medium / High)
- **Hot water / DHW** (`power_acs`, Altherma water mode) — *untested, needs hardware that has it*
- **Air-quality / IAQ** sensors — *untested, needs hardware that has it*
- Cloud schedules / scenes

These are gated on field-presence, so units that lack a feature simply won't get those entities.

## How it works
The EU API (login, `installations`, the socket.io control/state channel, the per-unit property
dictionary, and the control payloads) was reverse-engineered from the official app. See
[`PROTOCOL.md`](PROTOCOL.md) for the full contract.

## Disclaimer
Community project, provided **as-is** under the MIT license, **best-effort** support. Not
affiliated with, endorsed by, or supported by Airzone or Daikin. Use at your own risk; an API
change on Airzone's side could break it at any time.

## Credits
Thanks to [`@max13fr`](https://github.com/max13fr) and
[`@eXPerience83`](https://github.com/eXPerience83) — whose DKN (non-EU) work mapped out the
problem space. This project implements the EU (`dknEU`) cloud and its socket.io transport
independently.

## License
[MIT](LICENSE) © 2026 James Matthews
