"""The AldiTalk base entity."""

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN


class AldiTalkCoordinatorEntity(CoordinatorEntity):
    """AldiTalk base entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, sensor: dict) -> None:
        """Initialize the Trias base entity."""
        super().__init__(coordinator)
        self._key = sensor["key"]
        self._attr_unique_id = f"{coordinator.config["username"]}_{sensor['key']}"
        self._attr_name = sensor["name"]
        self._attr_icon = sensor["icon"]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config["username"])},
            manufacturer="Aldi Talk",
            name=coordinator.config["username"],
        )

    @property
    def native_value(self):
        """Return the state of the device."""
        return self.coordinator.api_data.get(self._key)
