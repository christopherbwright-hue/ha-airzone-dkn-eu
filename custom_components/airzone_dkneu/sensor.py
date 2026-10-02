"""Diagnostic sensors for Airzone DKN Cloud EU units (VRV indoor-unit telemetry)."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DknEuConfigEntry
from .const import DOMAIN, MANUFACTURER
from .coordinator import DknEuCoordinator

_TEMP = dict(
    device_class=SensorDeviceClass.TEMPERATURE,
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    state_class=SensorStateClass.MEASUREMENT,
    entity_category=EntityCategory.DIAGNOSTIC,
)

SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(key="return_temp", translation_key="return_temp", **_TEMP),
    SensorEntityDescription(key="exch_heat_temp_iu", translation_key="exch_heat_temp_iu", **_TEMP),
    SensorEntityDescription(key="gas_pipe_temp_iu", translation_key="gas_pipe_temp_iu", **_TEMP),
    SensorEntityDescription(
        key="exp_valv_ui",
        translation_key="exp_valv_ui",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="stat_rssi",
        translation_key="stat_rssi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DknEuConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[DknEuSensor] = []
    for mac in coordinator.units:
        state = coordinator.data.get(mac, {})
        for desc in SENSORS:
            if desc.key in state:
                entities.append(DknEuSensor(coordinator, mac, desc))
    async_add_entities(entities)


class DknEuSensor(CoordinatorEntity[DknEuCoordinator], SensorEntity):
    """A single diagnostic value from a unit's device-data."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DknEuCoordinator,
        mac: str,
        description: SensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self._mac = mac
        self.entity_description = description
        self._attr_unique_id = f"{mac}_{description.key}"
        meta = coordinator.units[mac]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac)},
            name=meta.get("name"),
            manufacturer=MANUFACTURER,
        )

    @property
    def available(self) -> bool:
        return self.coordinator.unit_available(self._mac)

    @property
    def native_value(self) -> float | int | None:
        return self.coordinator.data.get(self._mac, {}).get(self.entity_description.key)
