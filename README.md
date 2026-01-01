# WLED Effects Framework for Home Assistant

A modular Python framework for creating custom WLED LED strip effects that run seamlessly in Home Assistant via Pyscript, with full standalone testing support.

credit: based off https://github.com/christianweinmayr/hacs-wled-scripts

## 🌟 Features

- **5 Built-in Effects**: Segment fade, loading animation, rainbow wave, sparkles, and state synchronization
- **Home Assistant Integration**: Native pyscript support with service controls
- **State Synchronization**: Link LED display to any Home Assistant entity (curtains, volume, sensors, etc.)
- **Standalone Testing**: Test effects locally without Home Assistant
- **Production Ready**: Device validation, auto-recovery, retry logic, and statistics tracking
- **Extensible Architecture**: Easy base class for creating custom effects
- **Smart Device Management**: Automatically handles WLED streaming modes and configuration

## 🚀 Quick Start

### 1. Install Pyscript in Home Assistant

Install via HACS and add to `configuration.yaml`:
```yaml
pyscript:
  allow_all_imports: true
```

### 2. Deploy Files

Copy to your Home Assistant:
```bash
/config/pyscript/
├── modules/wled/           # Core effects library
├── wledtask.py            # Segment fade service
└── wledtask_sync.py       # State sync service
```

### 3. Configure

Edit `modules/wled/wled_effect_base.py`:
```python
WLED_IP = "192.168.1.50"  # Your WLED device IP
START_LED = 1
STOP_LED = 40
```

### 4. Use the Effects

```yaml
# Start segment fade effect
service: pyscript.wled_test_start

# Stop effect
service: pyscript.wled_test_stop

# Sync LEDs to curtain position
service: pyscript.wled_sync_start
```

## 📦 Available Effects

| Effect | Description | Configuration |
|--------|-------------|---------------|
| **Segment Fade** | Random segments that fade in/out smoothly | Colors, timing, segment size |
| **Loading** | Sequential LED fade-in with trailing effect | Color, speed, trail length |
| **Rainbow Wave** | Animated rainbow colors moving across strip | Speed, wave width |
| **Sparkle** | Random twinkling sparkles | Density, fade rate |
| **State Sync** | Display HA entity state as LED bar (0-100%) | Color, smoothing, entity |

## 🔧 Development

### Local Testing

```bash
# Test effects locally
cd standalone
python wledtask_standalone.py
python wledtask_sync_standalone.py
```

### Create Custom Effects

```python
from wled.wled_effect_base import WLEDEffectBase

class MyEffect(WLEDEffectBase):
    def get_effect_name(self):
        return "My Custom Effect"
    
    async def run_effect(self):
        while self.running:
            # Your effect logic
            payload = {"seg": {"id": 1, "col": [[255, 0, 0]]}}
            await self.send_wled_command(payload, "Red")
            await self.interruptible_sleep(1.0)
```

The base class handles device setup, error recovery, cleanup, and statistics automatically.

## 📚 Documentation

- **[Deployment Guide](docs/README_DEPLOYMENT.md)** - Complete installation and setup instructions
- **[Effects Reference](docs/README_EFFECTS.md)** - Technical documentation and development guide

## 🏗️ Architecture

```
modules/wled/
├── wled_effect_base.py     # Base class with device management
└── effects/
    ├── segment_fade.py     # Fade effect
    ├── loading.py          # Loading animation
    ├── rainbow_wave.py     # Rainbow + sparkles
    └── state_sync.py       # HA state synchronization

wledtask.py                 # Pyscript runner (segment fade)
wledtask_sync.py           # Pyscript runner (state sync)

standalone/                 # Test runners
├── wledtask_standalone.py
└── wledtask_sync_standalone.py
```

## 🐛 Troubleshooting

**Effects not appearing in HA:**
- Verify pyscript is installed and configured
- Check `/config/pyscript/` has `modules/` folder
- Reload pyscript: Developer Tools → YAML → Pyscript reload

**WLED not responding:**
- Verify WLED_IP is correct
- Check WLED is not in UDP streaming mode (E1.31/Art-Net)
- Test API manually: `curl http://YOUR_IP/json/state`

**Import errors:**
- Ensure `modules/` folder structure is intact
- Check all `__init__.py` files exist

## 🔑 Key Capabilities

- **Device Validation**: Automatically tests WLED connectivity and configuration on startup
- **Live Mode Handling**: Exits UDP/E1.31 streaming mode when effects start
- **Retry Logic**: Automatic retry with exponential backoff for network issues
- **Statistics**: Real-time success/failure tracking for all commands
- **Clean Shutdown**: Proper async task cleanup and device reset
- **Interruptible Sleep**: Effects respond instantly to stop commands

## 📋 Requirements

- Home Assistant with Pyscript (HACS installation recommended)
- WLED device (ESP8266/ESP32 with WLED firmware)
- Python 3.8+ for standalone testing (optional)

## 🎯 Use Cases

- **Ambient lighting** that responds to curtain positions, door states, or time of day
- **Visual notifications** for sensor thresholds or automation triggers  
- **Media sync** with volume levels or playback states
- **Custom animations** triggered by Home Assistant events
- **Status indicators** for system states using LED bars

## 📝 License

MIT License - Feel free to use, modify, and distribute.

## 🙏 Credits

Built for the Home Assistant and WLED communities. WLED API by Aircoookie.
