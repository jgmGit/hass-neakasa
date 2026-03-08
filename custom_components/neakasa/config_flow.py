import voluptuous as vol
from typing import Any
from homeassistant.config_entries import ConfigFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_FRIENDLY_NAME,
    CONF_USERNAME,
    CONF_PASSWORD,
)
from .api import NeakasaAPI, APIAuthError, APIConnectionError
from .const import DOMAIN, _LOGGER


class NeakasaConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._username: str | None = None
        self._password: str | None = None
        self._discovered_devices: dict[str, str] = {}
        _LOGGER.debug("Initializing NeakasaConfigFlow")

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        # Prevent duplicate config for the same account
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_USERNAME): str,
                        vol.Required(CONF_PASSWORD): str,
                    }
                ),
            )

        _LOGGER.debug("Collecting username/password for Neakasa")
        self._username = user_input[CONF_USERNAME].strip()
        self._password = user_input[CONF_PASSWORD]

        # Use email (account) as unique id to enforce single instance per account
        account_uid = f"account:{self._username.lower()}"
        await self.async_set_unique_id(account_uid, raise_on_progress=False)
        self._abort_if_unique_id_configured()

        try:
            session = async_get_clientsession(self.hass)
            api = NeakasaAPI(session, self.hass.async_add_executor_job)
            await api.connect(self._username, self._password)

            devices = await api.getDevices()
            _LOGGER.debug("Discovered Neakasa devices: %s", devices)
            self._discovered_devices = {}
            for device in devices:
                category = device.get("categoryKey")
                device_id = device.get("iotId")

                base_name = device.get("nickName") or device.get("identityAlias") or device.get("name") or device.get("deviceName") or device_id
                product_model = device.get("productModel")

                if product_model and product_model not in base_name:
                    device_name = f"{base_name} ({product_model})"
                else:
                    device_name = base_name

                _LOGGER.debug("Inspecting device: %s, category: %s", device_name, category)
                
                # Support CatLitter and try to find the vacuum
                # We'll be more inclusive for now to see what's returned
                if category:
                    self._discovered_devices[device_id] = {
                        "name": device_name,
                        "category": category,
                        "productKey": device.get("productKey"),
                        "deviceModel": device.get("deviceModel"),
                    }

            if not self._discovered_devices:
                _LOGGER.warning("No devices found in Neakasa account")
                return self.async_abort(reason="no_devices_found")

            return await self.async_step_device(None)

        except APIAuthError:
            # Bad creds → stop the flow with a clear reason
            return self.async_abort(reason="authentication")
        except APIConnectionError:
            # Network/service problem → stop cleanly
            return self.async_abort(reason="connection")

    async def async_step_device(self, user_input: dict[str, Any] | None = None):
        if user_input is None:
            # Generate choices for the dropdown
            device_choices = {
                id: info["name"] for id, info in self._discovered_devices.items()
            }
            return self.async_show_form(
                step_id="device",
                data_schema=vol.Schema(
                    {vol.Required(CONF_DEVICE_ID): vol.In(device_choices)}
                ),
            )

        device_id = user_input[CONF_DEVICE_ID]
        device_info = self._discovered_devices[device_id]
        
        # Keep device id as the entry's unique id too, to avoid dup device entries
        await self.async_set_unique_id(device_id, raise_on_progress=False)
        self._abort_if_unique_id_configured()

        data = {
            CONF_DEVICE_ID: device_id,
            CONF_FRIENDLY_NAME: device_info["name"],
            CONF_USERNAME: self._username,
            CONF_PASSWORD: self._password,
            "category": device_info["category"],
            "productKey": device_info.get("productKey"),
            "deviceModel": device_info.get("deviceModel"),
        }
        title = device_info["name"]
        return self.async_create_entry(title=title, data=data)
