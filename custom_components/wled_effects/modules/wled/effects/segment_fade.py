"""
Segment Fade Effect
Random segments that fade in and out with smooth transitions
"""

import random
import math
from wled.wled_effect_base import (
    WLEDEffectBase, 
    DEFAULT_LED_BRIGHTNESS, 
    DEFAULT_SEGMENT_ID,
    DEFAULT_START_LED,
    DEFAULT_STOP_LED,
    DEBUG_MODE
)

# Effect Configuration
NUM_SEGMENTS_MIN = 1
NUM_SEGMENTS_MAX = 1
SEGMENT_LENGTH_MIN = 3
SEGMENT_LENGTH_MAX = 5
FADE_IN_SECONDS = 5
STAY_ON_MIN = 10
STAY_ON_MAX = 15
FADE_OUT_SECONDS = 10
FADE_STEPS_PER_SECOND = 5
MIN_SPACING = 1
SEGMENT_COLORS = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]  # Red, green, blue
# SEGMENT_COLORS = None  # Uncomment for white


class SegmentFadeEffect(WLEDEffectBase):
    """Random segments that fade in and out with smooth transitions"""
    
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
        
        # Effect-specific initialization
        self.active_segments = {}
        self.segment_counter = 0
    
    def get_effect_name(self):
        return "Segment Fade Effect"
    
    def ease_in_out(self, t):
        """Smooth easing function"""
        if t < 0.5:
            return 4 * t * t * t
        else:
            return 1 - math.pow(-2 * t + 2, 3) / 2
    
    def get_segment_color(self):
        """Get color for a segment (either random from list or white)"""
        if SEGMENT_COLORS is None or len(SEGMENT_COLORS) == 0:
            return (255, 255, 255)  # White
        return random.choice(SEGMENT_COLORS)
    
    def check_overlap(self, start_pos, end_pos):
        """Check if a LED position range overlaps with any active segments"""
        for seg_id, (seg_start, seg_end) in self.active_segments.items():
            if not (end_pos + MIN_SPACING < seg_start or start_pos > seg_end + MIN_SPACING):
                return True
        return False
    
    async def fade_segment_lifecycle(self, segment_id):
        """Run one complete lifecycle for a single segment"""
        task_name = f"segment_{segment_id}"
        
        # Random delay before starting
        if not await self.interruptible_sleep(random.uniform(0, 3)):
            self.active_tasks.discard(task_name)
            return
        
        if not self.running:
            self.active_tasks.discard(task_name)
            return
        
        # Choose random position
        segment_length = random.randint(SEGMENT_LENGTH_MIN, SEGMENT_LENGTH_MAX)
        max_start_pos = self.stop_led - segment_length + 1
        
        # Try to find non-overlapping position
        start_pos = None
        for attempt in range(20):
            candidate_start = random.randint(self.start_led, max_start_pos)
            candidate_end = candidate_start + segment_length - 1
            
            if not self.check_overlap(candidate_start, candidate_end):
                start_pos = candidate_start
                break
        
        if start_pos is None:
            self.log.debug(f"Segment {segment_id} skipped - no space available")
            self.active_tasks.discard(task_name)
            return
        
        # Register segment
        end_pos = start_pos + segment_length - 1
        self.active_segments[segment_id] = (start_pos, end_pos)
        
        # Get color for this segment
        base_color = self.get_segment_color()
        color_name = "white" if base_color == (255, 255, 255) else f"RGB{base_color}"
        
        self.log.info(f"Segment {segment_id}: LEDs {start_pos}-{end_pos} ({segment_length} LEDs), Color: {color_name}")
        
        # FADE IN
        num_steps = int(FADE_IN_SECONDS * FADE_STEPS_PER_SECOND)
        step_duration = FADE_IN_SECONDS / num_steps
        
        self.log.info(f"Segment {segment_id}: Fading in over {num_steps} steps ({FADE_IN_SECONDS}s)")
        
        for step in range(num_steps + 1):
            if not self.running:
                self.active_tasks.discard(task_name)
                return
            
            progress = step / num_steps
            brightness_factor = self.ease_in_out(progress)
            
            # Apply brightness to each color channel
            r = int(base_color[0] * brightness_factor * (self.led_brightness / 255.0))
            g = int(base_color[1] * brightness_factor * (self.led_brightness / 255.0))
            b = int(base_color[2] * brightness_factor * (self.led_brightness / 255.0))
            
            led_array = []
            hex_color = f"{r:02x}{g:02x}{b:02x}"
            for abs_index in range(start_pos, end_pos + 1):
                led_array.extend([abs_index - self.start_led, hex_color])
            
            payload = {"seg": {"id": self.segment_id, "i": led_array, "bri": 255}}
            desc = f"Seg {segment_id} fade in step {step}/{num_steps} (factor={brightness_factor:.2f})"
            await self.send_wled_command(payload, desc if DEBUG_MODE else "")
            await self.task.sleep(step_duration)
        
        if not self.running:
            self.active_tasks.discard(task_name)
            return
        
        # STAY ON
        stay_duration = random.uniform(STAY_ON_MIN, STAY_ON_MAX)
        
        # Spawn replacement during stay-on phase
        spawn_delay = max(stay_duration - FADE_IN_SECONDS, stay_duration * 0.5)
        if not await self.interruptible_sleep(spawn_delay):
            self.active_tasks.discard(task_name)
            return
        
        # Spawn replacement now
        self.segment_counter += 1
        new_task_name = f"segment_{self.segment_counter}"
        self.active_tasks.add(new_task_name)
        await self.task.create_task(new_task_name, self.fade_segment_lifecycle(self.segment_counter))
        
        # Wait for the rest of the stay duration
        remaining_stay = stay_duration - spawn_delay
        if remaining_stay > 0:
            if not await self.interruptible_sleep(remaining_stay):
                self.active_tasks.discard(task_name)
                return
        
        # FADE OUT
        num_steps = int(FADE_OUT_SECONDS * FADE_STEPS_PER_SECOND)
        step_duration = FADE_OUT_SECONDS / num_steps
        
        self.log.info(f"Segment {segment_id}: Fading out over {num_steps} steps ({FADE_OUT_SECONDS}s)")
        
        for step in range(num_steps + 1):
            if not self.running:
                self.active_tasks.discard(task_name)
                return
            
            progress = step / num_steps
            brightness_factor = self.ease_in_out(1.0 - progress)
            
            # Apply brightness to each color channel
            r = int(base_color[0] * brightness_factor * (self.led_brightness / 255.0))
            g = int(base_color[1] * brightness_factor * (self.led_brightness / 255.0))
            b = int(base_color[2] * brightness_factor * (self.led_brightness / 255.0))
            
            led_array = []
            hex_color = f"{r:02x}{g:02x}{b:02x}"
            for abs_index in range(start_pos, end_pos + 1):
                led_array.extend([abs_index - self.start_led, hex_color])
            
            payload = {"seg": {"id": self.segment_id, "i": led_array, "bri": 255}}
            desc = f"Seg {segment_id} fade out step {step}/{num_steps} (factor={brightness_factor:.2f})"
            await self.send_wled_command(payload, desc if DEBUG_MODE else "")
            await self.task.sleep(step_duration)
        
        # Clear LEDs
        led_array = []
        for abs_index in range(start_pos, end_pos + 1):
            led_array.extend([abs_index - self.start_led, "000000"])
        
        payload = {"seg": {"id": self.segment_id, "i": led_array, "bri": 255}}
        await self.send_wled_command(payload, f"Clear segment {segment_id} LEDs")
        
        # Unregister this segment
        self.active_segments.pop(segment_id, None)
        self.active_tasks.discard(task_name)
        
        self.log.info(f"Segment {segment_id} complete")
    
    async def run_effect(self):
        """Main effect loop"""
        target_segments = random.randint(NUM_SEGMENTS_MIN, NUM_SEGMENTS_MAX)
        
        self.log.info(f"Starting {target_segments} initial segments")
        
        # Start initial segments
        for i in range(target_segments):
            self.segment_counter += 1
            task_name = f"segment_{self.segment_counter}"
            self.active_tasks.add(task_name)
            self.log.info(f"Creating segment {self.segment_counter}")
            await self.task.create_task(task_name, self.fade_segment_lifecycle(self.segment_counter))
            await self.task.sleep(random.uniform(0.5, 1.5))
        
        # Keep running
        while self.running:
            # Check if we should exit after one iteration
            if self.run_once_mode:
                self.log.info("Segment fade completed initial segments launch")
                break
            
            await self.task.sleep(10)
