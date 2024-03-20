"""Example integration using DataUpdateCoordinator."""

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .aldi_talk import AldiTalk
from .const import DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class AldiTalkCoordinator(DataUpdateCoordinator):
    """AldiTalk coordinator."""

    def __init__(self, hass: HomeAssistant, entry):
        """Initialize AldiTalk coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Aldi Talk Sensor",
            update_interval=timedelta(minutes=DEFAULT_SCAN_INTERVAL),
        )

        self.hass = hass
        self.config = entry.data

        self.aldi_talk = AldiTalk(self.config["username"], self.config["password"])

        self.api_data = {}

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        self.api_data = await self.hass.async_add_executor_job(self.aldi_talk.get_data)
