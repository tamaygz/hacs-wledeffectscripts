# WLED Effect Service - Generic Service Wrapper

## Overview

`wledtaskservice.py` provides a **generic, configurable service wrapper** for running any WLED effect in Home Assistant via Pyscript. Instead of creating separate service files for each effect, you configure effects dynamically through service calls.

## Features

✅ **Dynamic Effect Loading** - Load any effect class at runtime
✅ **Configurable Parameters** - Pass effect-specific arguments via service calls
✅ **Auto-Detection Support** - Optionally enable/disable auto-detection
✅ **Manual Overrides** - Override segment ID, LED range, brightness
✅ **State Triggers** - Automatically trigger effects on entity state changes (supports state or state+attribute)
✅ **State Providers** - Connect effects to Home Assistant entities (for StateSyncEffect)
✅ **Multiple Service Actions** - start, stop, run_once, stop_all, status, configure
✅ **Full UI Support** - Proper Home Assistant service UI with type hints and descriptions
✅ **Return Values** - Status service returns structured data for use in automations

## Installation

1. **Install Pyscript** (via HACS if not already installed)
2. **Copy** `wledtaskservice.py` to `<config>/pyscript/` directory
3. **Optional**: Copy `services.yaml` to the same directory for enhanced UI support
4. **Restart** Home Assistant or reload Pyscript

## Services

### `pyscript.wled_effect_configure`

Configure which effect to use and its parameters.

**Parameters:**
- `effect_module` (string) - Python module path (e.g., `wled.effects.rainbow_wave`)
- `effect_class` (string) - Effect class name (e.g., `RainbowWaveEffect`)
- `state_entity` (string, optional) - Entity for state provider (StateSyncEffect only)
- `state_attribute` (string, optional) - Attribute to monitor (None = use state)
- `trigger_entity` (string, optional) - Entity to trigger on changes
- `trigger_attribute` (string, optional) - Attribute to monitor for trigger (None = monitor state)
- `trigger_on_change` (bool) - Run effect once when trigger fires (default: true)
- `auto_detect` (bool) - Enable auto-detection (default: true)
- `segment_id` (int, optional) - Manual segment ID
- `start_led` (int, optional) - Manual start LED
- `stop_led` (int, optional) - Manual stop LED
- `led_brightness` (int, optional) - Manual brightness (0-255)

### `pyscript.wled_effect_start`

Start the configured effect (runs continuously until stopped). No arguments required.

### `pyscript.wled_effect_stop`

Stop the currently running effect. No arguments required.

### `pyscript.wled_effect_run_once`

Run the effect once (single iteration). No arguments required.

### `pyscript.wled_effect_stop_all`

Stop the currently running effect and kill all spawned background tasks, cleanup all resources. No arguments required.

### `pyscript.wled_effect_status`

Get current effect status. **Returns structured data** that can be used in templates and automations:

**Return Value:**
```python
{
  "configured": bool,        # Whether an effect is configured
  "effect_name": str,        # Name of the effect (or None)
  "running": bool,           # Whether effect is currently running
  "trigger_entity": str,     # Entity being monitored for triggers (or None)
  "trigger_attribute": str,  # Attribute being monitored (or None)
  "state_entity": str,       # Entity providing state data (or None)
  "state_attribute": str     # Attribute providing state data (or None)
}
```

**Usage in Automation:**
```yaml
- service: pyscript.wled_effect_status
  response_variable: effect_status

- condition: template
  value_template: "{{ effect_status.running == false }}"
```

## UI Support

Pyscript automatically generates service UI from:
1. **Type hints** in service function signatures
2. **Docstrings** in service functions
3. **services.yaml** file (optional, for enhanced UI)

The included `services.yaml` provides:
- User-friendly field names
- Detailed descriptions
- Input selectors (entity pickers, number sliders, text boxes)
- Example values
- Default values

## Usage Examples

### Example 1: Rainbow Wave Effect (Simple)

```yaml
# Configure the effect
service: pyscript.wled_effect_configure
data:
  effect_module: "wled.effects.rainbow_wave"
  effect_class: "RainbowWaveEffect"
  auto_detect: true

# Start the effect
service: pyscript.wled_effect_start
```

### Example 2: Loading Effect with Manual Configuration

```yaml
# Configure with manual LED range
service: pyscript.wled_effect_configure
data:
  effect_module: "wled.effects.loading"
  effect_class: "LoadingEffect"
  auto_detect: false
  segment_id: 1
  start_led: 10
  stop_led: 50
  led_brightness: 200

# Start
service: pyscript.wled_effect_start
```

### Example 3: Segment Fade Effect (Run Once)

```yaml
# Configure
service: pyscript.wled_effect_configure
data:
  effect_module: "wled.effects.segment_fade"
  effect_class: "SegmentFadeEffect"

# Run single iteration
service: pyscript.wled_effect_run_once
```

### Example 4: State Sync Effect with State Provider

```yaml
# Configure with state provider
service: pyscript.wled_effect_configure
data:
  effect_module: "wled.effects.state_sync"
  effect_class: "StateSyncEffect"
  state_entity: "cover.living_room_curtain"
  state_attribute: "current_position"
  auto_detect: true

# Start continuous sync
service: pyscript.wled_effect_start
```

### Example 5: State Sync with Trigger (Auto-update)

```yaml
# Configure with automatic trigger on state change
service: pyscript.wled_effect_configure
data:
  effect_module: "wled.effects.state_sync"
  effect_class: "StateSyncEffect"
  state_entity: "sensor.curtain_position"
  trigger_entity: "sensor.curtain_position"
  trigger_on_change: true

# Effect will auto-update when sensor changes
# Start for continuous monitoring
service: pyscript.wled_effect_start
```

### Example 6: Volume Level Display

```yaml
# Show media player volume on LED strip
service: pyscript.wled_effect_configure
data:
  effect_module: "wled.effects.state_sync"
  effect_class: "StateSyncEffect"
  state_entity: "media_player.living_room"
  state_attribute: "volume_level"
  trigger_entity: "media_player.living_room"
  trigger_on_change: true

service: pyscript.wled_effect_start
```

### Example 7: Sparkle Effect with Custom Brightness

```yaml
service: pyscript.wled_effect_configure
data:
  effect_module: "wled.effects.rainbow_wave"
  effect_class: "SparkleEffect"
  led_brightness: 128  # Half brightness

service: pyscript.wled_effect_start
```

## Automation Examples

### Automation 1: Rainbow at Sunset

```yaml
automation:
  - alias: "WLED Rainbow at Sunset"
    trigger:
      - platform: sun
        event: sunset
    action:
      - service: pyscript.wled_effect_configure
        data:
          effect_module: "wled.effects.rainbow_wave"
          effect_class: "RainbowWaveEffect"
      - service: pyscript.wled_effect_start
```

### Automation 2: Sync Curtain Position to LEDs

```yaml
automation:
  - alias: "WLED Curtain Position Sync"
    trigger:
      - platform: state
        entity_id: cover.living_room_curtain
    action:
      - service: pyscript.wled_effect_configure
        data:
          effect_module: "wled.effects.state_sync"
          effect_class: "StateSyncEffect"
          state_entity: "cover.living_room_curtain"
          state_attribute: "current_position"
          trigger_entity: "cover.living_room_curtain"
          trigger_on_change: true
      - service: pyscript.wled_effect_start
```

### Automation 3: Different Effect per Room Occupancy

```yaml
automation:
  - alias: "WLED Living Room Effect"
    trigger:
      - platform: state
        entity_id: binary_sensor.living_room_occupancy
        to: "on"
    action:
      - service: pyscript.wled_effect_configure
        data:
          effect_module: "wled.effects.segment_fade"
          effect_class: "SegmentFadeEffect"
      - service: pyscript.wled_effect_start

  - alias: "WLED Kitchen Effect"
    trigger:
      - platform: state
        entity_id: binary_sensor.kitchen_occupancy
        to: "on"
    action:
      - service: pyscript.wled_effect_configure
        data:
          effect_module: "wled.effects.loading"
          effect_class: "LoadingEffect"
      - service: pyscript.wled_effect_start
```

### Automation 4: Stop Effect when Away

```yaml
automation:
  - alias: "Stop WLED when Away"
    trigger:
      - platform: state
        entity_id: person.home_owner
        to: "not_home"
    action:
      - service: pyscript.wled_effect_stop
```

## Available Effects

| Module | Class | Description | Requires State Provider |
|--------|-------|-------------|------------------------|
| `wled.effects.rainbow_wave` | `RainbowWaveEffect` | Moving rainbow wave | No |
| `wled.effects.rainbow_wave` | `SparkleEffect` | Random sparkles | No |
| `wled.effects.loading` | `LoadingEffect` | Sequential LED fade | No |
| `wled.effects.segment_fade` | `SegmentFadeEffect` | Fading segments | No |
| `wled.effects.state_sync` | `StateSyncEffect` | Sync to HA entity | Yes |

## Configuration Tips

### Auto-Detection (Recommended)

```yaml
# Let the system detect LED count and segments
auto_detect: true
```

### Manual Configuration (Advanced)

```yaml
# Specify exact values
auto_detect: false
segment_id: 1
start_led: 0
stop_led: 49
led_brightness: 255
```

### Partial Override

```yaml
# Auto-detect LED count but use specific segment
auto_detect: true
segment_id: 2
```

## Troubleshooting

### Effect Not Starting

1. **Check logs**: Look in Home Assistant logs for error messages
2. **Verify WLED device**: Ensure WLED device is reachable
3. **Check module path**: Ensure effect module/class names are correct
4. **Run status service**: Call `pyscript.wled_effect_status` to see current state

### State Provider Issues

```yaml
# For StateSyncEffect, ensure:
# 1. state_entity exists and is accessible
# 2. state_attribute is correct (or None for state)
# 3. Entity returns numeric values 0-100
```

### Trigger Not Working

The state trigger uses a string pattern match. If triggers aren't firing:
1. Ensure `trigger_entity` matches exactly the entity_id
2. Check that the entity actually changes state
3. Verify `trigger_on_change` is set to `true`

## Advanced: Creating Custom Effects

To use your own custom effect with this service:

1. **Create effect class** extending `WLEDEffectBase`
2. **Place in** `modules/wled/effects/` directory
3. **Configure** via service call with your module path

Example:
```yaml
service: pyscript.wled_effect_configure
data:
  effect_module: "wled.effects.my_custom_effect"
  effect_class: "MyCustomEffect"
```

## Comparison with Legacy Approach

### Old Way (Separate Service File per Effect)

```python
# wledtask_fade.py
from wled.effects.segment_fade import SegmentFadeEffect

@service
async def wled_fade_start():
    await effect.start()
```

**Problems:**
- One file per effect
- Hardcoded parameters
- No flexibility

### New Way (Generic Service)

```yaml
service: pyscript.wled_effect_configure
data:
  effect_module: "wled.effects.segment_fade"
  effect_class: "SegmentFadeEffect"
  
service: pyscript.wled_effect_start
```

**Benefits:**
- Single service file
- Dynamic configuration
- Full parameter control
- Works with any effect

## See Also

- [Effect Base Documentation](README_EFFECTS.md)
- [Auto-Detection Guide](README_AUTO_DETECTION.md)
- [Deployment Guide](README_DEPLOYMENT.md)
