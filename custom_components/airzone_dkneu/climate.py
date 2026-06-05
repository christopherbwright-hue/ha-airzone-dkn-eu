"""Climate platform for Airzone DKN Cloud EU (one entity per unit)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DknEuConfigEntry
from .const import (
    AZ_MODE_AUTO,
    AZ_MODE_COOL,
    AZ_MODE_DRY,
    AZ_MODE_FAN,
    AZ_MODE_HEAT,
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_TEMP,
    DOMAIN,
    MANUFACTURER,
    RANGE_BY_MODE,
    SETPOINT_BY_MODE,
)
from .coordinator import DknEuCoordinator

AZ_TO_HVAC = {
    AZ_MODE_AUTO: HVACMode.HEAT_COOL,
    AZ_MODE_COOL: HVACMode.COOL,
    AZ_MODE_HEAT: HVACMode.HEAT,
    AZ_MODE_FAN: HVACMode.FAN_ONLY,
    AZ_MODE_DRY: HVACMode.DRY,
}
HVAC_TO_AZ = {v: k for k, v in AZ_TO_HVAC.items()}
AZ_TO_ACTION = {
    AZ_MODE_COOL: HVACAction.COOLING,
    AZ_MODE_HEAT: HVACAction.HEATING,
    AZ_MODE_FAN: HVACAction.FAN,
    AZ_MODE_DRY: HVACAction.DRYING,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DknEuConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(DknEuClimate(coordinator, mac) for mac in coordinator.units)


class DknEuClimate(CoordinatorEntity[DknEuCoordinator], ClimateEntity):
    """A single Airzone DKN EU indoor unit."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_target_temperature_step = 1.0
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator: DknEuCoordinator, mac: str) -> None:
        super().__init__(coordinator)
        self._mac = mac
        meta = coordinator.units[mac]
        init = coordinator.data.get(mac, {})
        self._attr_unique_id = mac
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac)},
            name=meta.get("name"),
            manufacturer=MANUFACTURER,
            model="DKN ES.DKNWSERVER",
            sw_version=str(init["version"]) if init.get("version") else None,
        )

    @property
    def _d(self) -> dict[str, Any]:
        return self.coordinator.data.get(self._mac, {})

    @property
    def available(self) -> bool:
        d = self._d
        return bool(d) and bool(d.get("isConnected"))

    @property
    def temperature_unit(self) -> str:
        return (
            UnitOfTemperature.FAHRENHEIT
            if self._d.get("units") == 1
            else UnitOfTemperature.CELSIUS
        )

    @property
    def hvac_modes(self) -> list[HVACMode]:
        modes = [HVACMode.OFF]
        for m in self._d.get("mode_available", []):
            if m in AZ_TO_HVAC and AZ_TO_HVAC[m] not in modes:
                modes.append(AZ_TO_HVAC[m])
        return modes

    @property
    def hvac_mode(self) -> HVACMode:
        if not self._d.get("power"):
            return HVACMode.OFF
        return AZ_TO_HVAC.get(self._d.get("mode"), HVACMode.OFF)

    @property
    def hvac_action(self) -> HVACAction | None:
        if not self._d.get("power"):
            return HVACAction.OFF
        return AZ_TO_ACTION.get(self._d.get("mode"))

    @property
    def current_temperature(self) -> float | None:
        d = self._d
        return d.get("work_temp") or d.get("local_temp")

    @property
    def target_temperature(self) -> float | None:
        key = SETPOINT_BY_MODE.get(self._d.get("mode"))
        return self._d.get(key) if key else None

    @property
    def min_temp(self) -> float:
        keys = RANGE_BY_MODE.get(self._d.get("mode"))
        if keys and self._d.get(keys[0]) is not None:
            return self._d[keys[0]]
        return DEFAULT_MIN_TEMP

    @property
    def max_temp(self) -> float:
        keys = RANGE_BY_MODE.get(self._d.get("mode"))
        if keys and self._d.get(keys[1]) is not None:
            return self._d[keys[1]]
        return DEFAULT_MAX_TEMP

    @property
    def fan_modes(self) -> list[str]:
        return [str(s) for s in self._d.get("speed_available", [])]

    @property
    def fan_mode(self) -> str | None:
        s = self._d.get("speed_state")
        return str(s) if s is not None else None

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        key = SETPOINT_BY_MODE.get(self._d.get("mode"))
        if temp is None or not key:
            return
        await self.coordinator.async_set_value(self._mac, key, int(round(temp)))

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self.coordinator.async_set_value(self._mac, "power", False)
            return
        az = HVAC_TO_AZ.get(hvac_mode)
        if az is None:
            return
        if not self._d.get("power"):
            await self.coordinator.async_set_value(self._mac, "power", True)
        await self.coordinator.async_set_value(self._mac, "mode", az)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        await self.coordinator.async_set_value(self._mac, "speed_state", int(fan_mode))

    async def async_turn_on(self) -> None:
        await self.coordinator.async_set_value(self._mac, "power", True)

    async def async_turn_off(self) -> None:
        await self.coordinator.async_set_value(self._mac, "power", False)
