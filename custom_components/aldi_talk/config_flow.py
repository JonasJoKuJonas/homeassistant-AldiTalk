import voluptuous as vol
from homeassistant import config_entries
from .aldi_talk import AldiTalk
from .const import DOMAIN


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    async def async_step_user(self, info):
        if info is not None:
            api = AldiTalk(info["username"], info["password"])
            try:
                await self.hass.async_add_executor_job(api.update)
            except ValueError:
                return self.async_show_form(
                    step_id="user",
                    data_schema=vol.Schema(
                        {
                            vol.Required("username"): str,
                            vol.Required("password"): str,
                        }
                    ),
                    errors={"base": "invalid_auth"},
                )
            return self.async_create_entry(title=info["username"], data=info)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required("username"): str, vol.Required("password"): str}
            ),
        )
