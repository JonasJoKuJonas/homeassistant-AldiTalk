"""AldiTalk sensor integration."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CURRENCY_EURO, UnitOfInformation
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AldiTalkCoordinator
from .entity import AldiTalkCoordinatorEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the AldiTalk sensors."""

    coordinator: AldiTalkCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        RemainingVolumeSensor(
            {
                "key": "remaining_data_volume",
                "name": "Remaining Data Volume",
                "icon": "mdi:access-point",
            },
            coordinator,
        ),
        VolumeSensor(
            {
                "key": "total_data_volume",
                "name": "Total Data Volume",
                "icon": "mdi:access-point-check",
            },
            coordinator,
        ),
        DateSensor(
            {
                "key": "start_date",
                "name": "Start Day",
                "icon": "mdi:calendar",
            },
            coordinator,
        ),
        DateSensor(
            {
                "key": "end_date",
                "name": "End Day",
                "icon": "mdi:calendar",
            },
            coordinator,
        ),
        BalanceSensor(
            {
                "key": "account_balance",
                "name": "Account Balance",
                "icon": "mdi:cash-multiple",
            },
            coordinator,
        ),
    ]

    async_add_entities(entities)


class VolumeSensor(AldiTalkCoordinatorEntity, SensorEntity):

    def __init__(self, sensor, coordinator):
        """Initialize the sensor."""
        super().__init__(coordinator, sensor)

        self._attr_device_class = SensorDeviceClass.DATA_SIZE
        self._attr_native_unit_of_measurement = UnitOfInformation.MEGABYTES


class RemainingVolumeSensor(VolumeSensor):
    def __init__(self, sensor, coordinator):
        """Initialize the sensor."""
        super().__init__(sensor, coordinator)
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_last_reset = coordinator.api_data.get("start_date")


class DateSensor(AldiTalkCoordinatorEntity, SensorEntity):

    def __init__(self, sensor, coordinator):
        """Initialize the sensor."""
        super().__init__(coordinator, sensor)

        self._attr_device_class = SensorDeviceClass.TIMESTAMP


class BalanceSensor(AldiTalkCoordinatorEntity, SensorEntity):

    def __init__(self, sensor, coordinator):
        """Initialize the sensor."""
        super().__init__(coordinator, sensor)

        self._attr_native_unit_of_measurement = CURRENCY_EURO
        self._attr_state_class = SensorStateClass.TOTAL
