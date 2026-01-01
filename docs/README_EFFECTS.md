# WLED Effects Framework - Technical Reference

A comprehensive framework for creating custom WLED LED strip effects with full Home Assistant Pyscript support and standalone testing capabilities.

## Architecture Overview

### Base Class: `WLEDEffectBase`

The foundation of all effects, providing production-ready infrastructure:

**Core Features:**
- 🔌 **Device Management**: Automatic connection testing and configuration validation
- 🎛️ **Live Mode Handling**: Detects and exits UDP/E1.31 streaming modes
- 📊 **Statistics Tracking**: Real-time success/failure counts for all commands
- 🔄 **Retry Logic**: Automatic retry with exponential backoff for network issues
- 🧹 **Clean Shutdown**: Proper async task cleanup and device reset
- ⚡ **Interruptible Operations**: Instant response to stop commands

**Abstraction Layer:**
The base class uses adapter pattern to work in multiple environments:
- `task_manager`: Provides `sleep()`, `create_task()`, `kill_task()`
- `logger`: Provides `debug()`, `info()`, `warning()`, `error()`
- `http_client`: Provides `get_state()` and `send_command(payload)` async methods

This abstraction allows the same effect code to run in:
- Home Assistant Pyscript (with pyscript adapters)
- Standalone Python (with aiohttp adapters)
- Custom environments (implement your own adapters)

## Built-in Effects

### 1. Segment Fade Effect

**File:** `modules/wled/effects/segment_fade.py`

Random segments that fade in smoothly, stay on, then fade out. Multiple segments can overlap with smooth transitions.

**Configuration:**
```python
NUM_SEGMENTS_MIN = 1           # Minimum concurrent segments
NUM_SEGMENTS_MAX = 1           # Maximum concurrent segments
SEGMENT_LENGTH_MIN = 3         # Minimum segment length (LEDs)
SEGMENT_LENGTH_MAX = 5         # Maximum segment length (LEDs)
FADE_IN_SECONDS = 5            # Fade in duration
STAY_ON_MIN = 10               # Minimum stay lit duration
STAY_ON_MAX = 15               # Maximum stay lit duration
FADE_OUT_SECONDS = 10          # Fade out duration
FADE_STEPS_PER_SECOND = 5      # Smoothness of transitions
MIN_SPACING = 1                # Minimum LED gap between segments
SEGMENT_COLORS = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]  # RGB tuples
```

**Features:**
- Smooth easing functions for natural transitions
- Collision prevention (configurable spacing)
- Random color selection per segment
- Multiple concurrent segments

**Use Cases:**
- Ambient mood lighting
- Decorative effects
- Attention-drawing displays

---

### 2. Loading Effect

**File:** `modules/wled/effects/loading.py`

Sequential LED fade-in from first to last LED with trailing effect, loops continuously.

**Configuration:**
```python
LOADING_COLOR = (0, 150, 255)  # RGB color tuple
LOADING_FADE_STEPS = 10        # Brightness steps per LED
LOADING_STEP_DELAY = 0.05      # Seconds between steps
LOADING_WAIT_TIME = 1.0        # Pause before restart
LOADING_TRAIL_LENGTH = 5       # Number of trailing LEDs (0 = no trail)
```

**Features:**
- Smooth brightness ramping per LED
- Configurable trailing effect
- Auto-restart with pause
- Single color, highly configurable

**Use Cases:**
- Progress indicators
- Loading animations
- Notification effects

---

### 3. Rainbow Wave Effect

**File:** `modules/wled/effects/rainbow_wave.py`

Animated rainbow colors that move smoothly across the entire LED strip.

**Configuration:**
```python
RAINBOW_WAVE_SPEED = 0.1       # Seconds between updates
RAINBOW_WAVE_WIDTH = 5         # Width of color transitions
```

**Features:**
- Full HSV to RGB color conversion
- Smooth color transitions
- Continuous looping animation
- Adjustable speed and wavelength

**Use Cases:**
- Party mode
- Decorative displays
- Colorful ambient lighting

---

### 4. Sparkle Effect

**File:** `modules/wled/effects/rainbow_wave.py` (same file)

Random twinkling sparkles that fade in and out across the strip.

**Configuration:**
```python
SPARKLE_DENSITY = 5            # Maximum concurrent sparkles
SPARKLE_FADE_STEPS = 20        # Fade duration (higher = slower)
SPARKLE_NEW_RATE = 0.5         # Seconds between new sparkles
```

**Features:**
- Random sparkle positions
- Smooth fade out
- Configurable density
- White sparkles

**Use Cases:**
- Starfield effects
- Subtle ambient lighting
- Night mode displays

---

### 5. State Sync Effect

**File:** `modules/wled/effects/state_sync.py`

Synchronizes LED strip display to a Home Assistant entity state (0-100%), creating a visual bar graph.

**Configuration:**
```python
SYNC_COLOR = (0, 200, 255)         # Color for "filled" LEDs
SYNC_BACKGROUND_COLOR = (0, 0, 0)  # Color for "empty" LEDs
SYNC_SMOOTH_TRANSITION = True       # Animate changes
SYNC_TRANSITION_STEPS = 10          # Steps for animation
SYNC_TRANSITION_SPEED = 0.05        # Seconds per step
```

**Features:**
- Real-time state monitoring
- Smooth transitions between values
- Configurable fill and background colors
- State provider abstraction (works with any numeric source)

**Requires:** State provider with `async get_state()` method returning 0-100 float.

**Use Cases:**
- Curtain position display
- Volume level indicators
- Sensor value visualization (temperature, humidity, etc.)
- Battery level indicators
- Progress tracking

**Example State Provider (Pyscript):**
```python
class HAStateProvider:
    def __init__(self, entity_id, attribute=None):
        self.entity_id = entity_id
        self.attribute = attribute
    
    async def get_state(self):
        if self.attribute:
            value = state.get(f"{self.entity_id}.{self.attribute}")
        else:
            value = state.get(self.entity_id)
        return float(value)  # Must return 0-100
```

## Creating Custom Effects

### Step 1: Create Effect Class

Create a new file in `modules/wled/effects/`:

```python
from wled.wled_effect_base import (
    WLEDEffectBase, 
    SEGMENT_ID, START_LED, STOP_LED, LED_BRIGHTNESS
)

class MyCustomEffect(WLEDEffectBase):
    def __init__(self, task_manager, logger, http_client):
        # Use explicit parent class call (pyscript compatibility)
        WLEDEffectBase.__init__(self, task_manager, logger, http_client)
        # Your initialization here
        self.counter = 0
    
    def get_effect_name(self):
        return "My Custom Effect"
    
    async def run_effect(self):
        \"\"\"Main effect loop - MUST check self.running\"\"\"
        self.log.info(f"Starting {self.get_effect_name()}")
        
        while self.running:
            # Build LED array: [led_index, hex_color, led_index, hex_color, ...]
            led_array = []
            
            for led_pos in range(START_LED, STOP_LED + 1):
                # Calculate color for this LED
                r, g, b = self.calculate_color(led_pos)
                hex_color = f"{r:02x}{g:02x}{b:02x}"
                
                # LED indices are 0-based in payload
                led_array.extend([led_pos - START_LED, hex_color])
            
            # Send command
            payload = {
                "seg": {
                    "id": SEGMENT_ID,
                    "i": led_array,
                    "bri": LED_BRIGHTNESS
                }
            }
            await self.send_wled_command(payload, f"Update {self.counter}")
            
            self.counter += 1
            
            # Use interruptible sleep (responds to stop immediately)
            await self.interruptible_sleep(0.1)
        
        self.log.info("Effect complete")
    
    def calculate_color(self, led_pos):
        # Your color logic here
        return (255, 0, 0)  # Red
```

### Step 2: Create Runner (Optional)

For standalone testing, create `standalone/my_effect_test.py`:

```python
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'modules'))

from wled.effects.my_custom_effect import MyCustomEffect
from wled.wled_effect_base import WLED_URL
import asyncio
import aiohttp

# ... (copy adapters from wledtask_standalone.py)

async def main():
    task_mgr = StandaloneTaskManager()
    http_client = StandaloneHTTPClient()
    effect = MyCustomEffect(task_mgr, log, http_client)
    
    try:
        await effect.start()
        while effect.running:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await effect.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

### Step 3: Create Pyscript Runner (Optional)

For Home Assistant, create `wledtask_myeffect.py`:

```python
from wled.effects.my_custom_effect import MyCustomEffect
from wled.wled_effect_base import WLED_URL, WLED_IP
import asyncio

# Logger wrapper (required for pyscript)
class Logger:
    def debug(self, msg): log.debug(msg)
    def info(self, msg): log.info(msg)
    def warning(self, msg): log.warning(msg)
    def error(self, msg): log.error(msg)

# ... (copy adapters from wledtask.py)

effect = None

@service
async def my_effect_start():
    global effect
    if effect is None:
        task_mgr = PyscriptTaskManager()
        http_client = PyscriptHTTPClient()
        logger = Logger()
        effect = MyCustomEffect(task_mgr, logger, http_client)
    await effect.start()

@service
async def my_effect_stop():
    global effect
    if effect:
        await effect.stop()
```

## Pyscript Compatibility Notes

Pyscript has Python limitations that affect implementation:

### 1. No `super()` Calls

**❌ Don't do this:**
```python
def __init__(self, task_manager, logger, http_client):
    super().__init__(task_manager, logger, http_client)
```

**✅ Do this instead:**
```python
def __init__(self, task_manager, logger, http_client):
    WLEDEffectBase.__init__(self, task_manager, logger, http_client)
```

### 2. Logger Wrapper Required

Pyscript `log` builtin is not accessible in nested scopes (class methods). Use wrapper:

```python
class Logger:
    \"\"\"Wrapper to access pyscript log builtin\"\"\"
    def debug(self, msg): log.debug(msg)
    def info(self, msg): log.info(msg)
    def warning(self, msg): log.warning(msg)
    def error(self, msg): log.error(msg)
```

### 3. Absolute Imports Only

**❌ Don't use relative imports:**
```python
from ..wled_effect_base import WLEDEffectBase
```

**✅ Use absolute imports:**
```python
from wled.wled_effect_base import WLEDEffectBase
```

### 4. No Relative Imports in `__init__.py`

The `effects/__init__.py` cannot use relative imports. Leave it minimal or empty.

## API Reference

### Methods Available in Effects

**Command Sending:**
```python
await self.send_wled_command(payload, description)
```
Sends JSON payload to WLED with retry logic and statistics tracking.

**Sleep:**
```python
await self.interruptible_sleep(duration)
```
Sleep that immediately returns if `self.running` becomes False.

**Device Control:**
```python
await self.blackout_segment()
```
Turn off all LEDs in the segment.

**State:**
```python
self.running  # Boolean, True while effect should run
self.command_count  # Total commands sent
self.success_count  # Successful commands
self.fail_count     # Failed commands
```

**Logging:**
```python
self.log.debug("Debug message")
self.log.info("Info message")
self.log.warning("Warning message")
self.log.error("Error message")
```

### Required Methods to Implement

```python
def get_effect_name(self) -> str
```
Return the effect name for logging.

```python
async def run_effect(self) -> None
```
Main effect loop. Must check `self.running` and use `interruptible_sleep()`.

## Performance Tips

1. **Batch LED updates** - Send many LEDs in one command instead of many commands
2. **Limit command rate** - WLED can handle ~20-50 commands/second max
3. **Use adequate sleep intervals** - 0.05-0.1s is usually sufficient
4. **Minimize payload size** - Large payloads (>1KB) may cause disconnects
5. **Check `self.running` often** - Allows quick shutdown

## Troubleshooting

**ServerDisconnectedError:**
- Reduce command rate (increase sleep duration)
- Reduce payload size (fewer LEDs per command)
- Check WLED device network stability

**Effect doesn't stop:**
- Ensure `run_effect()` checks `self.running` in loop
- Use `interruptible_sleep()` not regular sleep

**Import errors in pyscript:**
- Verify `modules/` folder structure
- Check all `__init__.py` files exist
- Use absolute imports (`from wled.effects...`)

**Lag or stuttering:**
- Increase sleep duration between updates
- Reduce number of LEDs updated per command
- Check network latency to WLED device

## Configuration Reference

**Global Settings** (in `wled_effect_base.py`):
```python
WLED_IP = "192.168.1.50"   # WLED device IP address
SEGMENT_ID = 1              # WLED segment ID to control
START_LED = 1               # First LED index (1-based)
STOP_LED = 40               # Last LED index (inclusive)
LED_BRIGHTNESS = 255        # Maximum brightness (0-255)
DEBUG_MODE = True           # Enable verbose logging
```

## License

MIT License - Free to use, modify, and distribute.
