from homeassistant.components.vacuum import (
    StateVacuumEntity,
    VacuumEntityFeature,
    VacuumActivity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NeakasaCoordinator

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    """Set up the Vacuum."""
    coordinator: NeakasaCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ].coordinator
    
    # Only setup vacuum for robots
    if coordinator.category == "CatLitter":
        return

    device_info = DeviceInfo(
        name=coordinator.devicename,
        manufacturer="Neakasa",
        identifiers={(DOMAIN, coordinator.deviceid)}
    )

    async_add_entities([NeakasaVacuum(coordinator, device_info)])

class NeakasaVacuum(CoordinatorEntity, StateVacuumEntity):
    
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_supported_features = (
        VacuumEntityFeature.START
        | VacuumEntityFeature.PAUSE
        | VacuumEntityFeature.STOP
        | VacuumEntityFeature.RETURN_HOME
        | VacuumEntityFeature.BATTERY
        | VacuumEntityFeature.FAN_SPEED
        | VacuumEntityFeature.STATE
        | VacuumEntityFeature.LOCATE
    )
    _attr_fan_speed_list = ["Quiet", "Standard", "Strong", "Super"]

    def __init__(self, coordinator: NeakasaCoordinator, deviceinfo: DeviceInfo) -> None:
        super().__init__(coordinator)
        self.device_info = deviceinfo
        self._attr_unique_id = f"{coordinator.deviceid}-vacuum"

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def activity(self) -> VacuumActivity:
        """Return the current activity of the vacuum."""
        mode = self.coordinator.data.raw_data.get("WorkMode", {}).get("value")
        paused = self.coordinator.data.raw_data.get("PauseSwitch", {}).get("value") == 1

        if paused:
            return VacuumActivity.PAUSED

        # Mapping from Android BaseActivity7 Enum:
        # 0: StandBy, 2: Cleaning, 3: Charging, 10: Pausing, 11: Faulting
        # 12: Dormant, 13: BackCharging (Returning), 14: FullCharge
        # 15: BackChargePause, 16: ShutDown, 17: RemoteControlling
        # 18: SelfCleaning, 19: Drying, 20: DustCollecting

        if mode in (2, 17, 18, 20):
            return VacuumActivity.CLEANING
        if mode == 13:
            return VacuumActivity.RETURNING
        if mode in (3, 14, 19):
            return VacuumActivity.DOCKED
        if mode in (10, 15):
            return VacuumActivity.PAUSED
        if mode == 11:
            return VacuumActivity.ERROR
        if mode in (0, 12, 16):
            return VacuumActivity.IDLE
            
        return VacuumActivity.IDLE

    @property
    def battery_level(self) -> int:
        """Return the battery level of the vacuum cleaner."""
        return int(self.coordinator.data.raw_data.get("BatteryState", {}).get("value", 0))

    @property
    def fan_speed(self) -> str:
        """Return the fan speed of the vacuum cleaner."""
        speed = self.coordinator.data.raw_data.get("WindPower", {}).get("value", 1)
        if 0 <= speed < len(self._attr_fan_speed_list):
            return self._attr_fan_speed_list[speed]
        return self._attr_fan_speed_list[1]

    async def async_start(self):
        """Start or resume the vacuum."""
        # Resume if paused, else start new clean
        mode = self.coordinator.data.raw_data.get("WorkMode", {}).get("value")
        if mode == 0: # Idle
             await self.coordinator.invokeService("clean")
        else:
             await self.coordinator.setProperty("PauseSwitch", 0)

    async def async_pause(self):
        """Pause the vacuum."""
        await self.coordinator.setProperty("PauseSwitch", 1)

    async def async_stop(self, **kwargs):
        """Stop the vacuum."""
        await self.coordinator.setProperty("PauseSwitch", 1)
        await self.coordinator.invokeService("go_home")

    async def async_return_to_base(self, **kwargs):
        """Return to base."""
        await self.coordinator.invokeService("go_home")

    async def async_set_fan_speed(self, fan_speed: str, **kwargs):
        """Set fan speed."""
        try:
            speed_idx = self._attr_fan_speed_list.index(fan_speed)
            await self.coordinator.setProperty("WindPower", speed_idx)
        except ValueError:
            pass

    async def async_locate(self, **kwargs):
        """Locate the vacuum."""
        await self.coordinator.invokeService("locate")
