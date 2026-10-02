# Changelog

## 0.1.1 (fork of jxmatthews/ha-airzone-dkn-eu 0.1.0)

Reliability fixes; no change to the cloud endpoints used, the config flow, or entity IDs.

- **Rejected commands are no longer shown as applied.** The cloud's acknowledgement is now
  checked; an explicit failure raises an error in Home Assistant and local state is left alone.
- **Unconfirmed commands trigger a resync.** If no acknowledgement arrives, the link is
  reconnected so the server's full state snapshot replaces any guess.
- **Dead connections are detected.** If nothing is received for pingInterval + pingTimeout,
  the link is closed and reconnected (previously a half-open link could go unnoticed until
  the OS gave up on TCP).
- **Entities go unavailable while the cloud link is down**, instead of showing stale state.
- **No task leak on reconnect.** The old socket is closed before a new one is opened; failed
  connection attempts are cleaned up.
- **Credential failures hand off to HA's re-authentication prompt** instead of retrying the
  login every minute indefinitely. Non-auth refresh failures (5xx/network) are retried.
- In-flight commands fail immediately if the link drops, rather than waiting for a timeout.
- `get_installations` retries a 401 once only (previously unbounded recursion).
- Removed `hvac_action`: the cloud exposes only the selected mode, not compressor activity,
  so "heating"/"cooling" was a guess and wrong when a unit was idle at setpoint.
