# WLED Device Auto-Detection

## Overview

The `WLEDDeviceConfig` component provides automatic detection of WLED device configuration, eliminating the need for hardcoded constants like `START_LED`, `STOP_LED`, and `SEGMENT_ID`.

## Features

- **Automatic LED Count Detection**: Queries the device to determine total LED count
- **Segment Discovery**: Detects all configured segments with their start/stop positions
- **Device Information**: Retrieves device name, version, platform, and capabilities
- **Validation**: Validates LED ranges against actual device configuration
- **Runtime Updates**: Can re-detect configuration if device setup changes

## API Endpoints Used

The component queries two WLED JSON API endpoints:

1. **`/json/info`** - Device information
   - Total LED count (`info.leds.count`)
   - Maximum segments (`info.leds.maxseg`)
   - Device name, version, platform
   - RGBW support, FPS

2. **`/json/state`** - Current state
   - Active segments (`state.seg[]`)
   - Segment ranges (start, stop, length)
   - Segment on/off status

## Usage

### Basic Example

```python
from wled.wled_device_config import WLEDDeviceConfig, WLEDDeviceHTTPClient

# Wrap your HTTP client
extended_client = WLEDDeviceHTTPClient(http_client)

# Create config manager
device_config = WLEDDeviceConfig(extended_client, logger)

# Auto-detect configuration
if await device_config.detect():
    # Get LED range for segment 0
    start_led, stop_led = device_config.get_segment_range(0)
    total_leds = device_config.get_segment_length(0)
    
    print(f"Segment 0: LEDs {start_led}-{stop_led} ({total_leds} total)")
else:
    print("Detection failed!")
```

### In an Effect Class

```python
class MyAutoDetectEffect(WLEDEffectBase):
    def __init__(self, task_manager, logger, http_client):
        super().__init__(task_manager, logger, http_client)
        
        # Setup auto-detection
        extended_client = WLEDDeviceHTTPClient(http_client)
        self.device_config = WLEDDeviceConfig(extended_client, logger)
    
    async def initialize(self):
        """Call this before start()"""
        if not await self.device_config.detect():
            return False
        
        # Use detected values
        self.start_led, self.stop_led = self.device_config.get_segment_range(0)
        self.total_leds = self.device_config.get_segment_length(0)
        
        self.log.info(f"Auto-detected: {self.total_leds} LEDs")
        return True
    
    async def run_effect(self):
        # Use self.start_led, self.stop_led, self.total_leds
        for led in range(self.start_led, self.stop_led + 1):
            # ... effect logic
            pass
```

## Available Methods

### Detection

- `detect()` - Auto-detect device configuration (async)
- `is_detected()` - Check if detection has been performed

### Segment Information

- `get_segment_by_id(segment_id)` - Get full segment dict
- `get_segment_range(segment_id)` - Get (start, stop) tuple (inclusive)
- `get_segment_length(segment_id)` - Get LED count for segment
- `get_active_segments()` - List of segments that are currently on
- `get_first_active_segment_id()` - ID of first active segment

### Validation

- `validate_led_range(start, stop, segment_id)` - Check if range is valid

### Device Info

- `total_led_count` - Total LEDs on device
- `max_segments` - Maximum supported segments
- `device_name` - Friendly device name
- `version` - WLED version
- `platform` - ESP8266/ESP32
- `supports_rgbw` - RGBW support flag
- `fps` - Current frames per second

### Utilities

- `get_summary()` - Get formatted device info string

## Example Output

```
Auto-detecting WLED device configuration...
Device: My WLED Strip
Version: 0.14.0 (esp32)
Total LEDs: 150
Max Segments: 16
FPS: 42
Found 3 configured segment(s):
  Segment 0: LEDs 0-49 (50 LEDs) [ON]
  Segment 1: LEDs 50-99 (50 LEDs) [ON]
  Segment 2: LEDs 100-149 (50 LEDs) [OFF]
```

## HTTP Client Requirements

Your HTTP client must implement:

- `get_state()` - Returns `/json/state` response
- `get_info()` - Returns `/json/info` response
- `send_command(payload)` - Sends POST to `/json`

The `WLEDDeviceHTTPClient` wrapper can extend basic clients that only have `get_state()` and `send_command()`.

## Benefits

### Before (Hardcoded)
```python
START_LED = 1
STOP_LED = 40
SEGMENT_ID = 1
```

**Problems:**
- Must manually update when strip size changes
- Requires code modification for different setups
- Can't detect segment configuration changes

### After (Auto-Detection)
```python
device_config = WLEDDeviceConfig(client, logger)
await device_config.detect()
start, stop = device_config.get_segment_range(0)
```

**Advantages:**
- Automatically adapts to any strip size
- No code changes needed for different devices
- Runtime detection of configuration changes
- Safer (validates against actual device)

## Migration Guide

### Step 1: Add Detection to Effect

```python
# Old
class MyEffect(WLEDEffectBase):
    async def run_effect(self):
        for led in range(START_LED, STOP_LED + 1):
            # ...

# New
class MyEffect(WLEDEffectBase):
    def __init__(self, task_manager, logger, http_client):
        super().__init__(task_manager, logger, http_client)
        extended_client = WLEDDeviceHTTPClient(http_client)
        self.device_config = WLEDDeviceConfig(extended_client, logger)
        self.start_led = 0
        self.stop_led = 0
    
    async def initialize(self):
        await self.device_config.detect()
        self.start_led, self.stop_led = self.device_config.get_segment_range(0)
        return True
    
    async def run_effect(self):
        for led in range(self.start_led, self.stop_led + 1):
            # ... (same logic)
```

### Step 2: Update Effect Initialization

```python
# Old
effect = MyEffect(task_mgr, logger, http_client)
await effect.start()

# New
effect = MyEffect(task_mgr, logger, http_client)
await effect.initialize()  # Auto-detect first
await effect.start()
```

## See Also

- `auto_detect_example.py` - Complete working example
- `wled_device_config.py` - Implementation source
- WLED JSON API docs: https://kno.wled.ge/interfaces/json-api/
