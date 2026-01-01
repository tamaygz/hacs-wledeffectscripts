# WLED Effects - Home Assistant Pyscript Deployment Guide

## Overview
This project contains modular WLED effects that can run both in Home Assistant (via pyscript) and standalone for testing.

## Project Structure

```
hass_pyscripts_tg/
├── modules/                    # Required by pyscript for custom imports
│   └── wled/                  # Main WLED effects module
│       ├── wled_effect_base.py
│       └── effects/
│           ├── __init__.py
│           ├── segment_fade.py
│           ├── rainbow_wave.py
│           ├── loading.py
│           └── state_sync.py
│
├── wledtask.py                # Pyscript runner for segment fade effect
├── wledtask_sync.py           # Pyscript runner for state sync effect
│
├── standalone/                # Test runners for local development
│   ├── wledtask_standalone.py
│   └── wledtask_sync_standalone.py
│
└── docs/                      # Documentation
    ├── README_DEPLOYMENT.md   # This file
    └── README_EFFECTS.md      # Effects reference
```

**Note:** Only `modules/`, `wledtask.py`, and `wledtask_sync.py` need to be deployed to Home Assistant. The `standalone/` and `docs/` directories are for local development only.

## Home Assistant Deployment

### Step 1: Install Pyscript
1. Install **Pyscript** via HACS (Home Assistant Community Store)
2. Add to your `configuration.yaml`:
```yaml
pyscript:
  allow_all_imports: true
  hass_is_global: false
```
3. Restart Home Assistant

### Step 2: Copy Files to Home Assistant

Copy the following to your Home Assistant's pyscript directory (`/config/pyscript/`):

```bash
# Method 1: Copy entire structure
cp -r modules /config/pyscript/
cp wledtask.py /config/pyscript/
cp wledtask_sync.py /config/pyscript/

# Method 2: Using Samba/File Editor
# Navigate to /config/pyscript/ in your file browser
# Copy the modules/ folder and .py files there
```

Your Home Assistant pyscript folder should look like:
```
/config/pyscript/
├── modules/
│   └── wled/
│       ├── wled_effect_base.py
│       └── effects/
│           ├── __init__.py
│           ├── segment_fade.py
│           ├── rainbow_wave.py
│           ├── loading.py
│           └── state_sync.py
│
├── wledtask.py
└── wledtask_sync.py
```

### Step 3: Configure WLED IP Address

Edit the WLED IP address in `modules/wled/wled_effect_base.py`:
```python
WLED_IP = "192.168.1.100"  # Change to your WLED device IP
```

### Step 4: Reload Pyscript
- Go to Developer Tools > YAML
- Click "Pyscript reload"
- Or restart Home Assistant

### Step 5: Use the Effects

The following services will be available:

#### Segment Fade Effect
```yaml
# Start the segment fade effect
service: pyscript.wled_test_start

# Stop the effect
service: pyscript.wled_test_stop
```

#### State Sync Effect
First configure which entity to monitor in `wledtask_sync.py`:
```python
ENTITY_TO_MONITOR = "cover.curtain_comedor"  # Your entity
ATTRIBUTE_NAME = None  # Or "current_position", "volume_level", etc.
```

Then use:
```yaml
# Start state sync
service: pyscript.wled_sync_start

# Stop state sync
service: pyscript.wled_sync_stop
```

## Local Development / Testing

For local development and testing without Home Assistant:

```bash
# Test segment fade effect
python standalone/wledtask_standalone.py

# Test state sync effect (uses mock state provider)
python standalone/wledtask_sync_standalone.py
```

Both standalone and pyscript versions now use the same unified `modules/wled/` structure for consistency.

## Why the `modules/` folder?

Pyscript requires custom Python modules to be placed in a `modules/` subdirectory. Pyscript automatically adds the `modules/` directory to Python's import path, so all imports use absolute paths from the `wled` package.

### Unified Import Pattern

**All files now use the same import pattern:**
```python
from wled.effects.segment_fade import SegmentFadeEffect
from wled.wled_effect_base import WLED_URL
```

- **Pyscript**: `modules/` is automatically in the path
- **Standalone**: Scripts add `modules/` to `sys.path` at startup

This ensures consistent imports across both environments!

## Troubleshooting

### Import Errors
If you see `ModuleNotFoundError: No module named 'wled'` or similar:
1. Ensure the `modules/` folder is in `/config/pyscript/`
2. Verify all `__init__.py` files exist in the directory structure
3. Check that files were copied (not moved) - the structure must be intact
4. Reload pyscript or restart Home Assistant

### Effect Not Working
1. Check logs in Home Assistant: Configuration > Logs
2. Look for pyscript errors
3. Verify WLED_IP is correct in `modules/wled/wled_effect_base.py`
4. Test WLED device manually: `http://YOUR_WLED_IP/json/state`
5. Ensure WLED is not in UDP streaming mode (E1.31/Art-Net)

### State Sync Not Updating
1. Verify entity ID in `wledtask_sync.py` is correct
2. Check that the entity's state is numeric (0-100 range)
3. For attributes, ensure `ATTRIBUTE_NAME` is set correctly
4. Look for state_trigger errors in logs
5. Test entity state in Developer Tools → States

### Services Not Appearing
1. Verify pyscript integration is installed and running
2. Reload pyscript: Developer Tools → YAML → Pyscript reload
3. Check that no syntax errors exist in the Python files
4. Review Home Assistant logs for pyscript loading errors

### Pyscript-Specific Issues
Pyscript has some Python limitations:
- **No `super()` calls**: Use `ParentClass.__init__(self, ...)` instead
- **No relative imports in `__init__.py`**: Import directly where needed
- **`log` is a builtin**: Access via Logger wrapper for nested scopes
- **Limited module support**: May need `allow_all_imports: true` in config

## Adding New Effects

To add a new effect:

1. Create effect class in `modules/wled/effects/your_effect.py`
2. Inherit from `WLEDEffectBase`
3. Create a new pyscript runner like `wledtask_youreffect.py`
4. Import with: `from modules.wled.effects.your_effect import YourEffect`
5. Copy to `/config/pyscript/` and reload

## Resources

- [Pyscript Documentation](https://hacs-pyscript.readthedocs.io/)
- [WLED API Documentation](https://kno.wled.ge/interfaces/json-api/)
- [Home Assistant Pyscript on HACS](https://github.com/custom-components/pyscript)
