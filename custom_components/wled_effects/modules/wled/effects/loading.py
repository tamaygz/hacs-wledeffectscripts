"""
Loading Effect
LEDs fade in sequentially from first to last, then restart
"""

from wled.wled_effect_base import (
    WLEDEffectBase, 
    DEFAULT_LED_BRIGHTNESS,
    DEFAULT_SEGMENT_ID,
    DEFAULT_START_LED,
    DEFAULT_STOP_LED
)


# Effect Configuration
LOADING_COLOR = (0, 150, 255)  # Blue by default (R, G, B)
LOADING_FADE_STEPS = 10        # Number of brightness steps per LED
LOADING_STEP_DELAY = 0.05      # Seconds between steps
LOADING_WAIT_TIME = 1.0        # Seconds to wait at end before restarting
LOADING_TRAIL_LENGTH = 5       # Number of LEDs in the fading trail (0 = no trail, just moving dot)


class LoadingEffect(WLEDEffectBase):
    """Sequential LED fade-in effect that loops continuously"""
    
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
        return "Loading Effect"
    
    async def run_effect(self):
        """Main effect loop - sequential fade from first to last LED"""
        self.log.info(f"Starting loading animation with color RGB{LOADING_COLOR}")
        
        while self.running:
            # Fade in each LED sequentially
            for current_led in range(self.start_led, self.stop_led + 1):
                if not self.running:
                    return
                
                # Build LED array for current state
                led_array = []
                
                # Calculate which LEDs should be on and at what brightness
                for led_pos in range(self.start_led, self.stop_led + 1):
                    if led_pos <= current_led:
                        # This LED should be on
                        if LOADING_TRAIL_LENGTH == 0:
                            # No trail - just show current LED
                            if led_pos == current_led:
                                brightness_factor = 1.0
                            else:
                                brightness_factor = 0.0
                        else:
                            # With trail - calculate fade based on distance from current
                            distance = current_led - led_pos
                            if distance < LOADING_TRAIL_LENGTH:
                                # Within trail - calculate brightness
                                brightness_factor = 1.0 - (distance / LOADING_TRAIL_LENGTH)
                            else:
                                # Outside trail
                                brightness_factor = 0.0
                        
                        if brightness_factor > 0:
                            # Apply color and brightness
                            r = int(LOADING_COLOR[0] * brightness_factor * (self.led_brightness / 255.0))
                            g = int(LOADING_COLOR[1] * brightness_factor * (self.led_brightness / 255.0))
                            b = int(LOADING_COLOR[2] * brightness_factor * (self.led_brightness / 255.0))
                            
                            hex_color = f"{r:02x}{g:02x}{b:02x}"
                            led_array.extend([led_pos - self.start_led, hex_color])
                        else:
                            # LED is off
                            led_array.extend([led_pos - self.start_led, "000000"])
                    else:
                        # This LED hasn't been reached yet
                        led_array.extend([led_pos - self.start_led, "000000"])
                
                # Send command
                payload = {"seg": {"id": self.segment_id, "i": led_array, "bri": 255}}
                await self.send_wled_command(payload, f"Loading at LED {current_led}")
                
                # Wait before next step
                await self.interruptible_sleep(LOADING_STEP_DELAY)
            
            if not self.running:
                return
            
            # Check if we should exit after one iteration
            if self.run_once_mode:
                self.log.info("Loading completed single iteration")
                break
            
            # Wait at the end before restarting
            self.log.debug(f"Loading complete, waiting {LOADING_WAIT_TIME}s before restart")
            await self.interruptible_sleep(LOADING_WAIT_TIME)
            
            # Clear all LEDs before restarting
            if self.running:
                led_array = []
                for led_pos in range(self.start_led, self.stop_led + 1):
                    led_array.extend([led_pos - self.start_led, "000000"])
                
                payload = {"seg": {"id": self.segment_id, "i": led_array, "bri": 255}}
                await self.send_wled_command(payload, "Clear for restart")
                await self.interruptible_sleep(0.1)
        
        self.log.info("Loading animation complete")
