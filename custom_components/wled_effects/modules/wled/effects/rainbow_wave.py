"""
Rainbow Wave and Sparkle Effects
Example effects demonstrating how to create new WLED effects
"""

from wled.wled_effect_base import (
    WLEDEffectBase, 
    DEFAULT_LED_BRIGHTNESS,
    DEFAULT_SEGMENT_ID,
    DEFAULT_START_LED,
    DEFAULT_STOP_LED
)
import random


# ==============================================================================
# RAINBOW WAVE EFFECT
# ==============================================================================

# Configuration for this effect
RAINBOW_WAVE_SPEED = 0.1  # Seconds between steps
RAINBOW_WAVE_WIDTH = 5    # Width of the color wave


class RainbowWaveEffect(WLEDEffectBase):
    """Rainbow wave that moves across the strip"""
    
    def __init__(self, task_manager, logger, http_client, auto_detect=True,
                 segment_id=None, start_led=None, stop_led=None, led_brightness=None,
                 effect_config=None):
        # Manually initialize all base class attributes (pyscript doesn't fully support super())
        # Assign unique instance ID for this effect
        from wled.wled_effect_base import WLEDEffectBase
        WLEDEffectBase._instance_counter += 1
        self.instance_id = WLEDEffectBase._instance_counter
        
        # Effect-specific configuration
        self.config = effect_config if effect_config is not None else {}
        
        self.task = task_manager
        self.log = logger
        self.http = http_client
        
        # Auto-detection settings
        self.auto_detect_enabled = auto_detect
        self.device_config = None
        self._auto_detected = False
        
        # Configuration
        self.segment_id = segment_id if segment_id is not None else DEFAULT_SEGMENT_ID
        self.start_led = start_led if start_led is not None else DEFAULT_START_LED
        self.stop_led = stop_led if stop_led is not None else DEFAULT_STOP_LED
        self.led_brightness = led_brightness if led_brightness is not None else DEFAULT_LED_BRIGHTNESS
        
        # Store manual overrides
        self._manual_segment_id = segment_id is not None
        self._manual_start_led = start_led is not None
        self._manual_stop_led = stop_led is not None
        
        # State
        self.running = False
        self.run_once_mode = False
        self.active_tasks = set()
        
        # Diagnostics
        self.command_count = 0
        self.success_count = 0
        self.fail_count = 0
    
    def get_effect_name(self):
        return "Rainbow Wave Effect"
    
    def get_rainbow_color(self, position, offset):
        """Generate rainbow color based on position"""
        # Create a rainbow using HSV to RGB conversion
        hue = ((position + offset) % 360) / 360.0
        
        # Simple HSV to RGB (S=1, V=1)
        h = hue * 6
        x = int((1 - abs(h % 2 - 1)) * 255)
        
        if h < 1:
            return (255, x, 0)
        elif h < 2:
            return (x, 255, 0)
        elif h < 3:
            return (0, 255, x)
        elif h < 4:
            return (0, x, 255)
        elif h < 5:
            return (x, 0, 255)
        else:
            return (255, 0, x)
    
    async def run_effect(self):
        """Main effect loop - moves a rainbow wave across the strip"""
        self.log.info("Starting rainbow wave animation")
        
        offset = 0
        
        while self.running:
            # Build LED array for all LEDs
            led_array = []
            
            for led_pos in range(self.start_led, self.stop_led + 1):
                # Calculate position in rainbow (0-360 degrees)
                position = (led_pos - self.start_led) * (360.0 / (self.stop_led - self.start_led + 1))
                
                # Get color for this position with offset
                r, g, b = self.get_rainbow_color(position, offset)
                
                # Apply brightness
                r = int(r * (self.led_brightness / 255.0))
                g = int(g * (self.led_brightness / 255.0))
                b = int(b * (self.led_brightness / 255.0))
                
                hex_color = f"{r:02x}{g:02x}{b:02x}"
                led_array.extend([led_pos - self.start_led, hex_color])
            
            # Send command
            payload = {"seg": {"id": self.segment_id, "i": led_array, "bri": 255}}
            await self.send_wled_command(payload, f"Rainbow wave offset={offset}")
            
            # Move the wave
            offset = (offset + 10) % 360
            
            # Check if we should exit after one iteration
            if self.run_once_mode:
                self.log.info("Rainbow wave completed single iteration")
                break
            
            # Wait before next step
            await self.interruptible_sleep(RAINBOW_WAVE_SPEED)
        
        self.log.info("Rainbow wave animation complete")


# ==============================================================================
# SPARKLE EFFECT
# ==============================================================================

SPARKLE_DENSITY = 5       # Number of sparkles at a time
SPARKLE_FADE_STEPS = 10   # How many steps to fade out
SPARKLE_NEW_RATE = 0.3    # Seconds between new sparkles


class SparkleEffect(WLEDEffectBase):
    """Random sparkles that fade in and out"""
    
    def __init__(self, task_manager, logger, http_client):
        # Initialize base class attributes (pyscript compatible)
        self.task = task_manager
        self.log = logger
        self.http = http_client
        self.running = False
        self.active_tasks = set()
        self.command_count = 0
        self.success_count = 0
        self.fail_count = 0
        
        # Effect-specific initialization
        self.sparkles = {}  # {led_pos: brightness_level}
    
    def get_effect_name(self):
        return "Sparkle Effect"
    
    async def run_effect(self):
        """Main effect loop - random sparkles"""
        self.log.info("Starting sparkle animation")
        
        step_count = 0
        
        while self.running:
            # Add new sparkle occasionally
            if step_count % int(SPARKLE_NEW_RATE / 0.05) == 0:
                if len(self.sparkles) < SPARKLE_DENSITY:
                    new_pos = random.randint(self.start_led, self.stop_led)
                    if new_pos not in self.sparkles:
                        self.sparkles[new_pos] = SPARKLE_FADE_STEPS
            
            # Update all sparkles
            led_array = []
            sparkles_to_remove = []
            
            for led_pos, brightness_level in list(self.sparkles.items()):
                # Fade out
                new_level = brightness_level - 1
                
                if new_level <= 0:
                    sparkles_to_remove.append(led_pos)
                    # Turn off
                    led_array.extend([led_pos - self.start_led, "000000"])
                else:
                    self.sparkles[led_pos] = new_level
                    # Calculate brightness
                    factor = new_level / SPARKLE_FADE_STEPS
                    brightness = int(255 * factor * (self.led_brightness / 255.0))
                    hex_color = f"{brightness:02x}{brightness:02x}{brightness:02x}"
                    led_array.extend([led_pos - self.start_led, hex_color])
            
            # Remove dead sparkles
            for pos in sparkles_to_remove:
                del self.sparkles[pos]
            
            # Send command if we have changes
            if led_array:
                payload = {"seg": {"id": self.segment_id, "i": led_array, "bri": 255}}
                await self.send_wled_command(payload, f"Sparkle update ({len(self.sparkles)} active)")
            
            step_count += 1
            
            # Check if we should exit after one iteration
            if self.run_once_mode:
                self.log.info("Sparkle completed single iteration")
                break
            
            await self.interruptible_sleep(0.05)
        
        self.log.info("Sparkle animation complete")
