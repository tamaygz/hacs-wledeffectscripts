"""
State Sync Effect
Synchronizes LED display to a Home Assistant entity state/attribute value
Example: Show curtain position, volume level, or any numeric value (0-100%)
"""

from wled.wled_effect_base import (
    WLEDEffectBase, 
    DEFAULT_LED_BRIGHTNESS,
    DEFAULT_SEGMENT_ID,
    DEFAULT_START_LED,
    DEFAULT_STOP_LED
)


# Default Effect Configuration
DEFAULT_ANIM_MODE = "Center"         # Animation mode: "Single", "Dual", or "Center"
                                      # Single: Fill from start to end (left to right)
                                      # Dual: Fill from both ends toward middle
                                      # Center: Fill from middle outward to both ends
DEFAULT_SYNC_COLOR = (255, 30, 10)         # Color for "filled" LEDs (brownish by default)
DEFAULT_SYNC_BACKGROUND_COLOR = (0, 0, 0)  # Color for "empty" LEDs (dim black)
DEFAULT_SMOOTH_TRANSITION = True           # Animate changes smoothly
DEFAULT_TRANSITION_STEPS = 10              # Steps for smooth animation
DEFAULT_TRANSITION_SPEED = 0.05            # Seconds per step


class StateSyncEffect(WLEDEffectBase):
    """Synchronize LED strip to display a numeric state value (0-100%)"""
    
    # Indicate this effect requires a state provider
    REQUIRES_STATE_PROVIDER = True
    
    def __init__(self, task_manager, logger, http_client, state_provider, auto_detect=True,
                 segment_id=None, start_led=None, stop_led=None, led_brightness=None,
                 effect_config=None):
        """
        Args:
            state_provider: Object with get_state() method that returns 0-100 value
                           For pyscript: provides access to HA entity state
                           For standalone: mock object that returns test values
        """
        # Manually initialize all base class attributes (pyscript doesn't fully support super())
        # Assign unique instance ID for this effect
        from wled.wled_effect_base import WLEDEffectBase
        WLEDEffectBase._instance_counter += 1
        self.instance_id = WLEDEffectBase._instance_counter
        
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
        
        # Effect-specific configuration
        self.config = effect_config if effect_config is not None else {}
        
        # Effect-specific initialization
        self.state_provider = state_provider
        self.current_percentage = 0
        self.target_percentage = 0
    
    def get_effect_name(self):
        return "State Sync Effect"
    
    async def render_percentage(self, percentage):
        """Render the LED strip to show a specific percentage"""
        total_leds = self.stop_led - self.start_led + 1
        lit_count = int((percentage / 100.0) * total_leds)
        
        # Get config values with defaults
        anim_mode = self.config.get('anim_mode', DEFAULT_ANIM_MODE)
        sync_color = self.config.get('sync_color', DEFAULT_SYNC_COLOR)
        bg_color = self.config.get('background_color', DEFAULT_SYNC_BACKGROUND_COLOR)
        
        led_array = []
        
        for led_pos in range(self.start_led, self.stop_led + 1):
            led_index = led_pos - self.start_led
            
            # Determine if this LED should be lit based on animation mode
            should_light = False
            
            if anim_mode == "Single":
                # Fill from start to end (left to right)
                should_light = (led_index < lit_count)
                
            elif anim_mode == "Dual":
                # Fill from both ends toward middle
                lit_per_side = int((percentage / 200.0) * total_leds)
                should_light = (led_index < lit_per_side) or (led_index >= total_leds - lit_per_side)
                
            elif anim_mode == "Center":
                # Fill from middle outward to both ends
                center_index = total_leds / 2.0
                start_index = int(center_index - lit_count / 2.0)
                end_index = start_index + lit_count
                should_light = (start_index <= led_index < end_index)
            
            # Set color based on whether LED should be lit
            if should_light:
                # This LED should be "filled" (active color)
                r = int(sync_color[0] * (self.led_brightness / 255.0))
                g = int(sync_color[1] * (self.led_brightness / 255.0))
                b = int(sync_color[2] * (self.led_brightness / 255.0))
            else:
                # This LED should be "empty" (background color)
                r = int(bg_color[0] * (self.led_brightness / 255.0))
                g = int(bg_color[1] * (self.led_brightness / 255.0))
                b = int(bg_color[2] * (self.led_brightness / 255.0))
            
            hex_color = f"{r:02x}{g:02x}{b:02x}"
            led_array.extend([led_index, hex_color])
        
        payload = {"seg": {"id": self.segment_id, "i": led_array, "bri": 255}}
        await self.send_wled_command(payload, f"Display {percentage:.1f}% ({anim_mode} mode)")
    
    async def smooth_transition(self, from_pct, to_pct):
        """Smoothly animate from one percentage to another"""
        smooth = self.config.get('smooth_transition', DEFAULT_SMOOTH_TRANSITION)
        steps = self.config.get('transition_steps', DEFAULT_TRANSITION_STEPS)
        speed = self.config.get('transition_speed', DEFAULT_TRANSITION_SPEED)
        
        if not smooth or from_pct == to_pct:
            await self.render_percentage(to_pct)
            return
        
        for step in range(steps + 1):
            if not self.running:
                return
            
            # Check if target changed during animation
            new_target = await self.state_provider.get_state()
            if new_target != to_pct:
                # Target changed, restart animation from current position
                current = from_pct + (to_pct - from_pct) * (step / steps)
                await self.smooth_transition(current, new_target)
                return
            
            # Calculate intermediate percentage
            progress = step / steps
            current = from_pct + (to_pct - from_pct) * progress
            
            await self.render_percentage(current)
            
            if step < steps:
                await self.interruptible_sleep(speed)
    
    async def run_effect(self):
        """Main effect loop - monitors state and updates display"""
        self.log.info("Starting state sync animation")
        
        # Initial render
        self.target_percentage = await self.state_provider.get_state()
        self.current_percentage = self.target_percentage
        await self.render_percentage(self.current_percentage)
        self.log.info(f"Initial state: {self.current_percentage:.1f}%")
        
        # Main loop - poll for state changes
        while self.running:
            # Get current state value
            new_percentage = await self.state_provider.get_state()

            # Check if it changed
            if abs(new_percentage - self.target_percentage) > 0.5:  # 0.5% threshold
                self.log.info(f"State changed: {self.target_percentage:.1f}% -> {new_percentage:.1f}%")
                self.target_percentage = new_percentage
                
                # Animate to new value
                await self.smooth_transition(self.current_percentage, self.target_percentage)
                self.current_percentage = self.target_percentage
            
            # Check if we should exit after one iteration
            if self.run_once_mode:
                self.log.info("State sync completed single iteration")
                break
            
            # Wait before next check
            await self.interruptible_sleep(0.5)
        
        self.log.info("State sync animation complete")
