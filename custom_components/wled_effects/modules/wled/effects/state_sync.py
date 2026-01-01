"""
State Sync Effect
Synchronizes LED display to a Home Assistant entity state/attribute value
Example: Show curtain position, volume level, or any numeric value (0-100%)
"""

from wled.wled_effect_base import (
    WLEDEffectBase, 
    SEGMENT_ID, START_LED, STOP_LED, LED_BRIGHTNESS
)


# Effect Configuration
EFFECT_ANIM_MODE = "Single"         # Animation mode: "Single", "Dual", or "Center"
                                     # Single: Fill from start to end (left to right)
                                     # Dual: Fill from both ends toward middle
                                     # Center: Fill from middle outward to both ends
SYNC_COLOR = (0, 200, 255)         # Color for "filled" LEDs (cyan by default)
SYNC_BACKGROUND_COLOR = (0, 0, 0)  # Color for "empty" LEDs (dim black)
SYNC_SMOOTH_TRANSITION = True       # Animate changes smoothly
SYNC_TRANSITION_STEPS = 10          # Steps for smooth animation
SYNC_TRANSITION_SPEED = 0.05        # Seconds per step


class StateSyncEffect(WLEDEffectBase):
    """Synchronize LED strip to display a numeric state value (0-100%)"""
    
    def __init__(self, task_manager, logger, http_client, state_provider):
        """
        Args:
            state_provider: Object with get_state() method that returns 0-100 value
                           For pyscript: provides access to HA entity state
                           For standalone: mock object that returns test values
        """
        # Initialize base class attributes (pyscript compatible)
        self.task = task_manager
        self.log = logger
        self.http = http_client
        self.running = False
        self.run_once_mode = False
        self.active_tasks = set()
        self.command_count = 0
        self.success_count = 0
        self.fail_count = 0
        
        # Effect-specific initialization
        self.state_provider = state_provider
        self.current_percentage = 0
        self.target_percentage = 0
    
    def get_effect_name(self):
        return "State Sync Effect"
    
    async def render_percentage(self, percentage):
        """Render the LED strip to show a specific percentage"""
        total_leds = STOP_LED - START_LED + 1
        lit_count = int((percentage / 100.0) * total_leds)
        
        led_array = []
        
        for led_pos in range(START_LED, STOP_LED + 1):
            led_index = led_pos - START_LED
            
            # Determine if this LED should be lit based on animation mode
            should_light = False
            
            if EFFECT_ANIM_MODE == "Single":
                # Fill from start to end (left to right)
                should_light = (led_index < lit_count)
                
            elif EFFECT_ANIM_MODE == "Dual":
                # Fill from both ends toward middle
                lit_per_side = int((percentage / 200.0) * total_leds)
                should_light = (led_index < lit_per_side) or (led_index >= total_leds - lit_per_side)
                
            elif EFFECT_ANIM_MODE == "Center":
                # Fill from middle outward to both ends
                center_index = total_leds / 2.0
                start_index = int(center_index - lit_count / 2.0)
                end_index = start_index + lit_count
                should_light = (start_index <= led_index < end_index)
            
            # Set color based on whether LED should be lit
            if should_light:
                # This LED should be "filled" (active color)
                r = int(SYNC_COLOR[0] * (LED_BRIGHTNESS / 255.0))
                g = int(SYNC_COLOR[1] * (LED_BRIGHTNESS / 255.0))
                b = int(SYNC_COLOR[2] * (LED_BRIGHTNESS / 255.0))
            else:
                # This LED should be "empty" (background color)
                r = int(SYNC_BACKGROUND_COLOR[0] * (LED_BRIGHTNESS / 255.0))
                g = int(SYNC_BACKGROUND_COLOR[1] * (LED_BRIGHTNESS / 255.0))
                b = int(SYNC_BACKGROUND_COLOR[2] * (LED_BRIGHTNESS / 255.0))
            
            hex_color = f"{r:02x}{g:02x}{b:02x}"
            led_array.extend([led_index, hex_color])
        
        payload = {"seg": {"id": SEGMENT_ID, "i": led_array, "bri": 255}}
        await self.send_wled_command(payload, f"Display {percentage:.1f}% ({EFFECT_ANIM_MODE} mode)")
    
    async def smooth_transition(self, from_pct, to_pct):
        """Smoothly animate from one percentage to another"""
        if not SYNC_SMOOTH_TRANSITION or from_pct == to_pct:
            await self.render_percentage(to_pct)
            return
        
        steps = SYNC_TRANSITION_STEPS
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
                await self.interruptible_sleep(SYNC_TRANSITION_SPEED)
    
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
