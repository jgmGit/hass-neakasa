from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import PERCENTAGE, SIGNAL_STRENGTH_DECIBELS, UnitOfTime, EntityCategory, UnitOfMass
from datetime import datetime

from .const import DOMAIN
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
            NeakasaSensor(coordinator, device_info, translation="sand_percent", key="sandLevelPercent", unit=PERCENTAGE),
            NeakasaSensor(coordinator, device_info, translation="wifi_rssi", key="wifiRssi", unit=SIGNAL_STRENGTH_DECIBELS, visible=False, category=EntityCategory.DIAGNOSTIC, icon="mdi:wifi"),
            NeakasaSensor(coordinator, device_info, translation="stay_time", key="stayTime", unit=UnitOfTime.SECONDS, visible=False),
            NeakasaTimestampSensor(coordinator, device_info, translation="last_usage", key="lastUse"),
            NeakasaMapSensor(coordinator, device_info, translation="current_status", key="bucketStatus", options=['idle', 'cleaning', 'cleaning', 'leveling', 'flipover', 'cat_present', 'paused', 'side_bin_locking_panels_missing', None, 'cleaning_interrupted'], icon="mdi:state-machine"),
            NeakasaMapSensor(coordinator, device_info, translation="sand_state", key="sandLevelState", options=['insufficient', 'moderate', 'sufficient', 'overfilled']),
            NeakasaMapSensor(coordinator, device_info, translation="bin_state", key="room_of_bin", options=['normal', 'full', 'missing'], icon="mdi:delete")
        ])

        for cat in coordinator.data.cat_list:
            sensors.append(
                NeakasaCatSensor(coordinator, device_info, catName=cat['name'], catId=cat['id'], icon="mdi:cat")
            )
    else:
        # Vacuum Robot sensors
        sensors.extend([
            NeakasaSensor(coordinator, device_info, translation="battery", key="battery", unit=PERCENTAGE, icon="mdi:battery", device_class=SensorDeviceClass.BATTERY),
            NeakasaSensor(coordinator, device_info, translation="clean_area", key="clean_area", unit="m²", icon="mdi:map-marker-path"),
            NeakasaSensor(coordinator, device_info, translation="clean_time", key="clean_time", unit=UnitOfTime.MINUTES, icon="mdi:timer-outline"),
            NeakasaSensor(coordinator, device_info, translation="total_clean_areas", key="total_clean_areas", unit="m²", icon="mdi:map-marker-path", category=EntityCategory.DIAGNOSTIC),
            NeakasaSensor(coordinator, device_info, translation="total_clean_times", key="total_clean_times", unit=UnitOfTime.MINUTES, icon="mdi:timer-outline", category=EntityCategory.DIAGNOSTIC),
            NeakasaSensor(coordinator, device_info, translation="sweeping_times", key="sweeping_times", unit=None, icon="mdi:counter", category=EntityCategory.DIAGNOSTIC),
            NeakasaSensor(coordinator, device_info, translation="filter_time", key="filter_time", unit=UnitOfTime.HOURS, icon="mdi:air-filter", category=EntityCategory.DIAGNOSTIC),
            NeakasaSensor(coordinator, device_info, translation="main_brush_time", key="main_brush_time", unit=UnitOfTime.HOURS, icon="mdi:brush", category=EntityCategory.DIAGNOSTIC),
            NeakasaSensor(coordinator, device_info, translation="side_brush_time", key="side_brush_time", unit=UnitOfTime.HOURS, icon="mdi:menu", category=EntityCategory.DIAGNOSTIC),
            NeakasaSensor(coordinator, device_info, translation="wifi_rssi", key="wifiRssi", unit=SIGNAL_STRENGTH_DECIBELS, visible=False, category=EntityCategory.DIAGNOSTIC, icon="mdi:wifi"),
        ])

    # Create the sensors.
    async_add_entities(sensors)

class NeakasaCatSensor(CoordinatorEntity):

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, coordinator: NeakasaCoordinator, deviceinfo: DeviceInfo, catName: str, catId: str, icon: str = None, visible: bool = True, category: str = None) -> None:
        super().__init__(coordinator)
        self.device_info = deviceinfo
        self.entity_registry_enabled_default = visible
        self._attr_translation_key = "cat_sensor"
        self._attr_translation_placeholders = {"name": catName}
        self._attr_unique_id = f"{coordinator.deviceid}-cat-{catId}"
        self._attr_unit_of_measurement = UnitOfMass.KILOGRAMS
        self._catId = catId
        if icon is not None:
            self._attr_icon = icon
        if category is not None:
            self._attr_entity_category = category

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def _records(self):
        return list(filter(lambda record: record['cat_id'] == self._catId, self.coordinator.data.record_list))

    @property
    def state(self):
        if len(self._records) == 0:
            return 0
        last_record = self._records[0]
        return last_record['weight']

    @property
    def extra_state_attributes(self):
        if len(self._records) == 0:
            return {}
        last_record = self._records[0]
        return {
            "state_class": SensorStateClass.MEASUREMENT,
            "start_time": datetime.fromtimestamp(last_record['start_time']),
            "end_time": datetime.fromtimestamp(last_record['end_time'])
        }

class NeakasaSensor(CoordinatorEntity):

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, coordinator: NeakasaCoordinator, deviceinfo: DeviceInfo, translation: str, key: str, unit: str, icon: str = None, visible: bool = True, category: str = None, device_class: str = None) -> None:
        super().__init__(coordinator)
        self.device_info = deviceinfo
        self.data_key = key
        self.translation_key = translation
        self.entity_registry_enabled_default = visible
        self._attr_unique_id = f"{coordinator.deviceid}-{translation}"
        self._attr_unit_of_measurement = unit
        if icon is not None:
            self._attr_icon = icon
        if category is not None:
            self._attr_entity_category = category
        if device_class is not None:
            self._attr_device_class = device_class

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def state(self):
        if self.coordinator.category == "CatLitter":
            return getattr(self.coordinator.data, self.data_key)

        # Vacuum mapping
        mapping = {
            "battery": "BatteryState",
            "clean_area": "CleanAreas",
            "clean_time": "CleanRunTime",
            "total_clean_areas": "TotalCleanAreas",
            "total_clean_times": "TotalCleanTimes",
            "sweeping_times": "RunTimes",
            "filter_time": "FilterTime",
            "main_brush_time": "MainBrushTime",
            "side_brush_time": "SideBrushTime",
            "wifiRssi": "WiFI_RSSI"
        }

        raw_key = mapping.get(self.data_key, self.data_key)
        val = self.coordinator.data.raw_data.get(raw_key, {}).get("value")

        if val is None:
            return None

        # Clean time is in seconds, convert to minutes
        if self.data_key == "clean_time" or self.data_key == "total_clean_times":
            return round(val / 60)

        # Consumables raw value is minutes used. Calculate hours remaining.
        if self.data_key == "filter_time":
            return max(0, (9000 - val) // 60)

        if self.data_key == "main_brush_time":
            return max(0, (18000 - val) // 60)

        if self.data_key == "side_brush_time":
            return max(0, (12000 - val) // 60)

        return val

    @property
    def extra_state_attributes(self):
        attrs = {"state_class": SensorStateClass.MEASUREMENT}

        if getattr(self, "data_key", None) == "filter_time" and self.state is not None:
             val = self.coordinator.data.raw_data.get("FilterTime", {}).get("value", 0)
             attrs["percentage"] = max(0, 100 - int((val * 100) / 9000))
        elif getattr(self, "data_key", None) == "main_brush_time" and self.state is not None:
             val = self.coordinator.data.raw_data.get("MainBrushTime", {}).get("value", 0)
             attrs["percentage"] = max(0, 100 - int((val * 100) / 18000))
        elif getattr(self, "data_key", None) == "side_brush_time" and self.state is not None:
             val = self.coordinator.data.raw_data.get("SideBrushTime", {}).get("value", 0)
             attrs["percentage"] = max(0, 100 - int((val * 100) / 12000))

        return attrs

class NeakasaMapSensor(CoordinatorEntity):
    
    _attr_should_poll = False
    _attr_has_entity_name = True
    
    def __init__(self, coordinator: NeakasaCoordinator, deviceinfo: DeviceInfo, translation: str, key: str, options: list, icon: str = None, visible: bool = True) -> None:
        super().__init__(coordinator)
        self.device_info = deviceinfo
        self.data_key = key
        self.translation_key = translation
        self.entity_registry_enabled_default = visible
        self._attr_unique_id = f"{coordinator.deviceid}-{translation}"
        self.key_options = options
        if icon is not None:
            self._attr_icon = icon

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
    
    @property
    def state(self):
        rawValue = getattr(self.coordinator.data, self.data_key)
        if rawValue >= len(self.key_options):
            return rawValue

        value = self.key_options[rawValue]
        if value is None:
            return rawValue
        
        return value

class NeakasaTimestampSensor(CoordinatorEntity):
    
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    
    def __init__(self, coordinator: NeakasaCoordinator, deviceinfo: DeviceInfo, translation: str, key: str, icon: str = None, visible: bool = True) -> None:
        super().__init__(coordinator)
        self.device_info = deviceinfo
        self.data_key = key
        self.translation_key = translation
        self.entity_registry_enabled_default = visible
        self._attr_unique_id = f"{coordinator.deviceid}-{translation}"
        if icon is not None:
            self._attr_icon = icon

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
    
    @property
    def state(self):
        timestamp = getattr(self.coordinator.data, self.data_key) / 1000
        return datetime.fromtimestamp(timestamp)
