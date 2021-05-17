"""Platform for LGE climate integration."""
import logging

from datetime import timedelta
from .wideq.ac import AirConditionerDevice, ACMode
from .wideq.device import UNIT_TEMP_FAHRENHEIT

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_TEMP,
    HVAC_MODE_AUTO,
    HVAC_MODE_COOL,
    HVAC_MODE_DRY,
    HVAC_MODE_FAN_ONLY,
    HVAC_MODE_HEAT,
    HVAC_MODE_HEAT_COOL,
    HVAC_MODE_OFF,
    SUPPORT_FAN_MODE,
    SUPPORT_SWING_MODE,
    SUPPORT_TARGET_TEMPERATURE,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import TEMP_CELSIUS, TEMP_FAHRENHEIT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import CLIMATE_DEVICE_TYPES, LGEDevice
from .const import DOMAIN, LGE_DEVICES

HVAC_MODE_LOOKUP = {
    ACMode.AI.name: HVAC_MODE_AUTO,
    ACMode.HEAT.name: HVAC_MODE_HEAT,
    ACMode.DRY.name: HVAC_MODE_DRY,
    ACMode.COOL.name: HVAC_MODE_COOL,
    ACMode.FAN.name: HVAC_MODE_FAN_ONLY,
    ACMode.ACO.name: HVAC_MODE_HEAT_COOL,
}
HVAC_MODE_REVERSE_LOOKUP = {v: k for k, v in HVAC_MODE_LOOKUP.items()}

SCAN_INTERVAL = timedelta(seconds=30)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up LGE device climate based on config_entry."""
    entry_config = hass.data[DOMAIN]
    lge_devices = entry_config.get(LGE_DEVICES)
    if not lge_devices:
        return

    climate_devices = []
    for dev_type, devices in lge_devices.items():
        if dev_type in CLIMATE_DEVICE_TYPES:
            climate_devices.extend(devices)

    lge_climates = []
    lge_climates.extend(
        [
            LGEACClimate(lge_device, lge_device.device)
            for lge_device in climate_devices
        ]
    )

    async_add_entities(lge_climates)


class LGEClimate(CoordinatorEntity, ClimateEntity):
    """Base climate device."""

    def __init__(self, device: LGEDevice):
        """Initialize the climate."""
        super().__init__(device.coordinator)
        self._api = device
        self._name = device.name

    @property
    def device_info(self):
        """Return a device description for device registry."""
        return self._api.device_info

    @property
    def should_poll(self) -> bool:
        """We overwrite coordinator property default setting because we need
           to poll to avoid the effect that after changing a climate settings
           it is immediately set to prev state. The coordinator polling interval
           is disabled for climate devices. Side effect is that disabling climate
           entity all related sensor also stop refreshing."""
        return True

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._api.available


class LGEACClimate(LGEClimate):
    """Air-to-Air climate device."""

    def __init__(self, device: LGEDevice, ac_device: AirConditionerDevice) -> None:
        """Initialize the climate."""
        super().__init__(device)
        self._device = ac_device

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return f"{self._api.unique_id}-AC"

    @property
    def name(self):
        """Return the display name of this entity."""
        return self._name

    @property
    def target_temperature_step(self) -> float:
        """Return the supported step of target temperature."""
        return self._device.target_temperature_step

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement used by the platform."""
        return (
            TEMP_FAHRENHEIT
            if self._device.temperature_unit == UNIT_TEMP_FAHRENHEIT
            else TEMP_CELSIUS
        )

    @property
    def hvac_mode(self) -> str:
        """Return hvac operation ie. heat, cool mode."""
        mode = self._api.state.operation_mode
        if not self._api.state.is_on or mode is None:
            return HVAC_MODE_OFF
        return HVAC_MODE_LOOKUP.get(mode)

    def set_hvac_mode(self, hvac_mode: str) -> None:
        """Set new target hvac mode."""
        if hvac_mode == HVAC_MODE_OFF:
            self._device.power(False)
            return

        operation_mode = HVAC_MODE_REVERSE_LOOKUP.get(hvac_mode)
        if operation_mode is None:
            raise ValueError(f"Invalid hvac_mode [{hvac_mode}]")

        if self.hvac_mode == HVAC_MODE_OFF:
            self._device.power(True)
        self._device.set_op_mode(operation_mode)

    @property
    def hvac_modes(self):
        """Return the list of available hvac operation modes."""
        return [HVAC_MODE_OFF] + [
            HVAC_MODE_LOOKUP.get(mode)
            for mode in self._device.op_modes
            if mode in HVAC_MODE_LOOKUP
        ]

    @property
    def current_temperature(self) -> float:
        """Return the current temperature."""
        return self._api.state.current_temp

    @property
    def target_temperature(self) -> float:
        """Return the temperature we try to reach."""
        return self._api.state.target_temp

    def set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        self._device.set_target_temp(
            kwargs.get("temperature", self.target_temperature)
        )

    @property
    def fan_mode(self) -> str:
        """Return the fan setting."""
        return self._api.state.fan_speed

    def set_fan_mode(self, fan_mode: str) -> None:
        """Set new target fan mode."""
        self._device.set_fan_speed(fan_mode)

    @property
    def fan_modes(self):
        """Return the list of available fan modes."""
        return self._device.fan_speeds

    @property
    def swing_mode(self) -> str:
        """Return the swing mode setting."""
        return self._api.state.vert_swing_mode

    def set_swing_mode(self, swing_mode: str) -> None:
        """Set new target swing mode."""
        self._device.set_vert_swing_mode(swing_mode)

    @property
    def swing_modes(self):
        """Return the list of available swing modes."""
        return self._device.vert_swing_modes

    @property
    def supported_features(self) -> int:
        """Return the list of supported features."""
        features = SUPPORT_FAN_MODE | SUPPORT_TARGET_TEMPERATURE
        if len(self._device.vert_swing_modes) > 1:
            features |= SUPPORT_SWING_MODE
        return features

    def turn_on(self) -> None:
        """Turn the entity on."""
        self._device.power(True)

    def turn_off(self) -> None:
        """Turn the entity off."""
        self._device.power(False)

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        min_value = self._device.target_temperature_min
        if min_value is not None:
            return min_value

        return self._device.conv_temp_unit(DEFAULT_MIN_TEMP)

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        max_value = self._device.target_temperature_max
        if max_value is not None:
            return max_value

        return self._device.conv_temp_unit(DEFAULT_MAX_TEMP)
