from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import (
    STATE_ON,
    STATE_OFF,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import PERCENTAGE

from .const import DOMAIN, _LOGGER
from .coordinator import NeakasaCoordinator

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    """Set up the Sensors."""
    # This gets the data update coordinator from hass.data as specified in your __init__.py
    coordinator: NeakasaCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ].coordinator

    device_info = DeviceInfo(
        name=coordinator.devicename,
        manufacturer="Neakasa",
        identifiers={(DOMAIN, coordinator.deviceid)}
    )

    sensors = []

    if coordinator.category == "CatLitter":
        sensors.extend([
            NeakasaSwitch(coordinator, device_info, translation="auto_clean", key="cleanCfg", subkey="active", icon="mdi:vacuum"),
            NeakasaSwitch(coordinator, device_info, translation="young_cat_mode", key="youngCatMode", visible=False, icon="mdi:cat"),
            NeakasaSwitch(coordinator, device_info, translation="child_lock", key="childLockOnOff", icon="mdi:lock-alert"),
            NeakasaSwitch(coordinator, device_info, translation="auto_bury", key="autoBury", icon="mdi:window-closed"),
            NeakasaSwitch(coordinator, device_info, translation="auto_level", key="autoLevel", icon="mdi:spirit-level"),
            NeakasaSwitch(coordinator, device_info, translation="silent_mode", key="silentMode", icon="mdi:volume-off"),
            NeakasaSwitch(coordinator, device_info, translation="auto_recovery", key="autoForceInit", visible=False, icon="mdi:alert-outline"),
            NeakasaSwitch(coordinator, device_info, translation="unstoppable_cycle", key="bIntrptRangeDet", icon="mdi:cached")
        ])
    else:
        # Vacuum Robot switches
        sensors.extend([
            NeakasaSwitch(coordinator, device_info, translation="led_switch", key="LedSwitch", icon="mdi:lightbulb"),
            NeakasaSwitch(coordinator, device_info, translation="quiet_mode", key="Quiet", icon="mdi:volume-off"),
        ])

    # Create the sensors.
    async_add_entities(sensors)

class NeakasaSwitch(CoordinatorEntity):
    
    _attr_should_poll = False
    _attr_has_entity_name = True
    
    def __init__(self, coordinator: NeakasaCoordinator, deviceinfo: DeviceInfo, translation: str, key: str, subkey: str = None, icon: str = None, visible: bool = True) -> None:
        super().__init__(coordinator)
        self.device_info = deviceinfo
        self.data_key = key
        self.data_subkey = subkey
        self.translation_key = translation
        self.entity_registry_enabled_default = visible
        self._attr_unique_id = f"{coordinator.deviceid}-{translation}"
        if icon is not None:
            self._attr_icon = icon

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
    
    async def async_turn_on(self, **kwargs):
        await self._set_state(1)

    async def async_turn_off(self, **kwargs):
        await self._set_state(0)

    async def _set_state(self, state: int):
        """Helper to set device state."""
        if self.data_subkey is None:
            await self.coordinator.setProperty(self.data_key, state)
            return

        value = getattr(self.coordinator.data, self.data_key, None)
        value[self.data_subkey] = state

        await self.coordinator.setProperty(self.data_key, value)

    @property
    def is_on(self) -> bool:
        """Return the state of the sensor."""
        if self.coordinator.category == "CatLitter":
            value = getattr(self.coordinator.data, self.data_key, None)

            if self.data_subkey is None:
                return value

            sub_value = value.get(self.data_subkey, None)

            return sub_value
        
        # Vacuum mapping
        val = self.coordinator.data.raw_data.get(self.data_key, {}).get("value")
        return val == 1

    @property
    def state(self):
        return STATE_ON if self.is_on else STATE_OFF
