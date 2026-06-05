"""Constants for the Airzone DKN Cloud EU integration."""

DOMAIN = "airzone_dkneu"

# Public manufacturer label (Device Registry).
MANUFACTURER = "Daikin / Airzone"

# Airzone "mode" integer values (from the official app's app.config.js).
AZ_MODE_AUTO = 1
AZ_MODE_COOL = 2
AZ_MODE_HEAT = 3
AZ_MODE_FAN = 4
AZ_MODE_DRY = 5

# Per-mode setpoint property names in the device-data payload.
SETPOINT_BY_MODE = {
    AZ_MODE_AUTO: "setpoint_air_auto",
    AZ_MODE_COOL: "setpoint_air_cool",
    AZ_MODE_HEAT: "setpoint_air_heat",
}

# Per-mode setpoint range (min, max) property names.
RANGE_BY_MODE = {
    AZ_MODE_AUTO: ("range_sp_auto_air_min", "range_sp_auto_air_max"),
    AZ_MODE_COOL: ("range_sp_cool_air_min", "range_sp_cool_air_max"),
    AZ_MODE_HEAT: ("range_sp_hot_air_min", "range_sp_hot_air_max"),
}

DEFAULT_MIN_TEMP = 16
DEFAULT_MAX_TEMP = 32
