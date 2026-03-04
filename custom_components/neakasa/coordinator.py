from dataclasses import dataclass, field
from datetime import timedelta
import time
from typing import Optional, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_FRIENDLY_NAME,
    CONF_USERNAME,
    CONF_PASSWORD,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import APIAuthError, APIConnectionError
from .value_cacher import ValueCacher
from .const import DOMAIN, _LOGGER

@dataclass
class NeakasaAPIData:
    """Class to hold api data."""

    # Common fields
    wifiRssi: int
    
    # Litter Box specific (optional)
    binFullWaitReset: Optional[bool] = None
    cleanCfg: Optional[dict[str, Any]] = None
    sandLevelState: Optional[int] = None
    sandLevelPercent: Optional[int] = None
    bucketStatus: Optional[int] = None
    room_of_bin: Optional[int] = None
    youngCatMode: Optional[bool] = None
    childLockOnOff: Optional[bool] = None
    autoBury: Optional[bool] = None
    autoLevel: Optional[bool] = None
    silentMode: Optional[bool] = None
    autoForceInit: Optional[bool] = None
    bIntrptRangeDet: Optional[bool] = None
    stayTime: Optional[int] = None
    lastUse: Optional[int] = None
    cat_list: list[object] = field(default_factory=list)
    record_list: list[object] = field(default_factory=list)

    # Generic storage for newer devices
    raw_data: dict[str, Any] = field(default_factory=dict)

class NeakasaCoordinator(DataUpdateCoordinator):
    """My coordinator."""

    data: NeakasaAPIData

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize coordinator."""

        # Set variables from values entered in config flow setup
        self.deviceid = config_entry.data[CONF_DEVICE_ID]
        self.devicename = config_entry.data[CONF_FRIENDLY_NAME]
        self.username = config_entry.data[CONF_USERNAME]
        self.password = config_entry.data[CONF_PASSWORD]
        self.category = config_entry.data.get("category", "CatLitter")

        self._deviceName = None
        self.lastUseDate = None

        self._recordsCache = ValueCacher(refresh_after=timedelta(minutes=30), discard_after=timedelta(hours=4))
        self._devicePropertiesCache = ValueCacher(refresh_after=timedelta(seconds=0), discard_after=timedelta(minutes=30))

        # Initialise DataUpdateCoordinator
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({config_entry.unique_id})",
            # Method to call on every update interval.
            update_method=self.async_update_data,
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(seconds=60),
        )

        # API will be obtained from the shared manager when needed
        self.api = None
        

    async def setProperty(self, key: str, value: Any):
        from . import get_shared_api
        api = await get_shared_api(self.hass, self.username, self.password)
        _LOGGER.debug("Setting property %s to %s for %s", key, value, self.devicename)
        await api.setDeviceProperties(self.deviceid, {key: value})
        
        # Update local cached data
        if hasattr(self.data, key):
            setattr(self.data, key, value)
        
        # Also update raw_data
        if self.data.raw_data is None:
            self.data.raw_data = {}
        
        if key in self.data.raw_data:
            self.data.raw_data[key]["value"] = value
        else:
            self.data.raw_data[key] = {"value": value, "time": int(time.time() * 1000)}

        self.async_set_updated_data(self.data)

    async def invokeService(self, service: str):
        from . import get_shared_api
        api = await get_shared_api(self.hass, self.username, self.password)
        _LOGGER.debug("Invoking service %s for %s", service, self.devicename)
        match service:
            case 'clean':
                return await api.cleanNow(self.deviceid)
            case 'level':
                return await api.sandLeveling(self.deviceid)
            case 'go_home':
                # Trying chargeNow in api.py
                return await api.goHome(self.deviceid)
            case 'locate':
                if hasattr(api, 'findMe'):
                    return await api.findMe(self.deviceid)
                return await api._invokeService(self.deviceid, "findMe", {})
        raise Exception('cannot find service to invoke')

    async def _getDeviceName(self):
        if self._deviceName is not None:
            return self._deviceName

        """get deviceName by iotId"""
        from . import get_shared_api
        api = await get_shared_api(self.hass, self.username, self.password)
        devices = await api.getDevices()
        devices = list(filter(lambda devices: devices['iotId'] == self.deviceid, devices))
        if(len(devices) == 0):
            raise APIConnectionError("iotId not found in device list")
        deviceName = devices[0]['deviceName']
        self._deviceName = deviceName
        return deviceName

    async def _getRecords(self):
        async def fetch():
            deviceName = await self._getDeviceName()
            from . import get_shared_api
            api = await get_shared_api(self.hass, self.username, self.password)
            return await api.getRecords(deviceName)

        return await self._recordsCache.get_or_update(fetch)

    async def _getDeviceProperties(self):
        async def fetch():
            from . import get_shared_api
            api = await get_shared_api(self.hass, self.username, self.password)
            return await api.getDeviceProperties(self.deviceid)

        return await self._devicePropertiesCache.get_or_update(fetch)

    async def _async_fetch_data(self):
        """Internal method to fetch and parse data."""
        devicedata = await self._getDeviceProperties()
        _LOGGER.debug("Raw device data for %s: %s", self.devicename, devicedata)
        
        if self.category == "CatLitter":
            newLastUseDate = devicedata['catLeft']['time']

            if self.lastUseDate != newLastUseDate:
                self._recordsCache.mark_as_stale()

            self.lastUseDate = newLastUseDate
            
            records = await self._getRecords()

            return NeakasaAPIData(
                binFullWaitReset=devicedata['binFullWaitReset']['value'] == 1,
                cleanCfg=devicedata['cleanCfg']['value'],
                youngCatMode=devicedata['youngCatMode']['value'] == 1,
                childLockOnOff=devicedata['childLockOnOff']['value'] == 1,
                autoBury=devicedata['autoBury']['value'] == 1,
                autoLevel=devicedata['autoLevel']['value'] == 1,
                silentMode=devicedata['silentMode']['value'] == 1,
                autoForceInit=devicedata['autoForceInit']['value'] == 1,
                bIntrptRangeDet=devicedata['bIntrptRangeDet']['value'] == 1,
                sandLevelPercent=devicedata['Sand']['value']['percent'],
                wifiRssi=devicedata['NetWorkStatus']['value']['WiFi_RSSI'],
                bucketStatus=devicedata['bucketStatus']['value'],
                room_of_bin=devicedata['room_of_bin']['value'],
                sandLevelState=devicedata['Sand']['value']['level'],
                stayTime=devicedata['catLeft']['value'].get('stayTime', 0),
                lastUse=newLastUseDate,

                cat_list=records['cat_list'],
                record_list=records['record_list'],
                raw_data=devicedata
            )
        
        # Generic or Vacuum robot data
        if not hasattr(self, "_tsl_logged"):
            try:
                from . import get_shared_api
                api = await get_shared_api(self.hass, self.username, self.password)
                
                # Fetch productKey if not in config
                product_key = self.config_entry.data.get("productKey")
                if not product_key:
                    devices = await api.getDevices()
                    match = next((d for d in devices if d['iotId'] == self.deviceid), None)
                    if match:
                        product_key = match.get("productKey")

                tsl = await api.getDeviceTSL(self.deviceid, product_key)
                if tsl:
                    _LOGGER.info("TSL for %s: %s", self.devicename, tsl)
                else:
                    _LOGGER.debug("TSL discovery returned None for %s (productKey: %s)", self.devicename, product_key)
                self._tsl_logged = True
            except Exception as exc:
                _LOGGER.debug("Error getting TSL for %s: %s", self.devicename, exc)
                self._tsl_logged = True

        wifi_rssi = devicedata.get('WiFI_RSSI', {}).get('value', 0)
        if not wifi_rssi:
            wifi_rssi = devicedata.get('NetWorkStatus', {}).get('value', {}).get('WiFi_RSSI', 0)

        return NeakasaAPIData(
            wifiRssi=wifi_rssi,
            raw_data=devicedata
        )

    async def async_update_data(self):
        """Fetch data from API endpoint."""
        try:
            return await self._async_fetch_data()
        except APIAuthError as err:
            _LOGGER.warning(f"Authentication error for device {self.devicename}, attempting to reconnect: {err}")
            try:
                from . import force_reconnect_api
                await force_reconnect_api(self.hass, self.username, self.password)
                return await self._async_fetch_data()
            except Exception as reconnect_err:
                _LOGGER.error(f"Failed to reconnect API for device {self.devicename}: {reconnect_err}")
                raise UpdateFailed(f"Authentication failed and reconnection failed: {err}") from err
        except APIConnectionError as err:
            if "identityId is blank" in str(err):
                _LOGGER.debug(f"IdentityId error for device {self.devicename}, attempting automatic reconnection")
                try:
                    from . import clear_shared_api, force_reconnect_api
                    clear_shared_api(self.username, self.password)
                    await force_reconnect_api(self.hass, self.username, self.password)
                    return await self._async_fetch_data()
                except Exception as reconnect_err:
                    _LOGGER.error(f"Failed to reconnect API after identityId error for device {self.devicename}: {reconnect_err}")
                    raise UpdateFailed(f"IdentityId error and reconnection failed: {err}") from err
            else:
                _LOGGER.error(f"API connection error for device {self.devicename}: {err}")
                raise UpdateFailed(err) from err
