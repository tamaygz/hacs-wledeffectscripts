"""
WLED Effect Base Class
Shared codebase for both pyscript and standalone usage
Provides base class for device management
"""

import asyncio
from abc import ABC, abstractmethod

# Device Configuration (defaults, can be overridden or auto-detected)
WLED_IP = "192.168.1.50"
WLED_URL = f"http://{WLED_IP}/json/state"
DEBUG_MODE = True  # Enable detailed logging

# Default configuration (used as fallback if auto-detection fails)
DEFAULT_SEGMENT_ID = 1
DEFAULT_START_LED = 1
DEFAULT_STOP_LED = 40
DEFAULT_LED_BRIGHTNESS = 255  # Maximum brightness level (0-255)

# Legacy aliases for backward compatibility
SEGMENT_ID = DEFAULT_SEGMENT_ID
START_LED = DEFAULT_START_LED
STOP_LED = DEFAULT_STOP_LED
LED_BRIGHTNESS = DEFAULT_LED_BRIGHTNESS


class WLEDEffectBase(ABC):
    """Base class for all WLED effects - handles device management"""
    
    # Class attribute to indicate if effect requires state provider
    REQUIRES_STATE_PROVIDER = False
    
    # Class-level instance counter for unique task names
    _instance_counter = 0
    
    def __init__(self, task_manager, logger, http_client, auto_detect=True,
                 segment_id=None, start_led=None, stop_led=None, led_brightness=None,
                 effect_config=None):
        """
        Initialize the effect controller
        
        Args:
            task_manager: Object with sleep(), create_task(), kill_task() methods
            logger: Logger object with info(), debug(), warning(), error() methods
            http_client: Object with get_state() and send_command(payload) async methods
            auto_detect: If True, automatically detect device configuration (default: True)
            segment_id: Manual segment ID override (None = use auto-detect or default)
            start_led: Manual start LED override (None = use auto-detect or default)
            stop_led: Manual stop LED override (None = use auto-detect or default)
            led_brightness: Manual brightness override (None = use default)
        """
        # Assign unique instance ID for this effect
        WLEDEffectBase._instance_counter += 1
        self.instance_id = WLEDEffectBase._instance_counter
        
        self.task = task_manager
        self.log = logger
        self.http = http_client
        
        # Auto-detection settings
        self.auto_detect_enabled = auto_detect
        self.device_config = None
        self._auto_detected = False
        
        # Configuration (will be populated by auto-detect or use manual/default values)
        self.segment_id = segment_id if segment_id is not None else DEFAULT_SEGMENT_ID
        self.start_led = start_led if start_led is not None else DEFAULT_START_LED
        self.stop_led = stop_led if stop_led is not None else DEFAULT_STOP_LED
        self.led_brightness = led_brightness if led_brightness is not None else DEFAULT_LED_BRIGHTNESS
        
        # Store manual overrides
        self._manual_segment_id = segment_id is not None
        self._manual_start_led = start_led is not None
        self._manual_stop_led = stop_led is not None
        
        # Effect-specific configuration (key-value store)
        self.config = effect_config if effect_config is not None else {}
        
        # State
        self.running = False
        self.run_once_mode = False
        self.active_tasks = set()
        
        # Diagnostics
        self.command_count = 0
        self.success_count = 0
        self.fail_count = 0
    
    @abstractmethod
    async def run_effect(self):
        """Override this method to implement your effect logic"""
        pass
    
    @abstractmethod
    def get_effect_name(self):
        """Return the name of this effect"""
        pass
    
    async def interruptible_sleep(self, duration):
        """Sleep in small chunks so we can exit quickly if stopped"""
        remaining_time = duration
        while remaining_time > 0 and self.running:
            sleep_time = min(0.5, remaining_time)
            await self.task.sleep(sleep_time)
            remaining_time -= sleep_time
        return self.running
    
    async def send_wled_command(self, payload, description=""):
        """Wrapper to track command success/failure"""
        self.command_count += 1
        if DEBUG_MODE and description:
            self.log.info(f"[CMD #{self.command_count}] {description}")
        
        success = await self.http.send_command(payload)
        
        if success:
            self.success_count += 1
        else:
            self.fail_count += 1
            self.log.error(f"[CMD #{self.command_count}] FAILED - {description}")
        
        if self.command_count % 20 == 0:
            self.log.info(f"Stats: {self.success_count} success, {self.fail_count} failed out of {self.command_count} total")
        
        return success
    
    async def blackout_segment(self):
        """Clear all LEDs"""
        total_leds = self.stop_led - self.start_led + 1
        
        led_array = []
        for i in range(self.start_led, self.stop_led + 1):
            led_array.extend([i, "000000"])
        
        payload = {"seg": {"id": self.segment_id, "i": led_array}}
        await self.send_wled_command(payload, f"Blackout {total_leds} LEDs")
        await self.task.sleep(0.2)
        
        payload2 = {
            "seg": {
                "id": self.segment_id,
                "i": [],
                "col": [[0, 0, 0]],
                "bri": 1,
                "on": True,
            }
        }
        await self.send_wled_command(payload2, "Reset segment")
        await self.task.sleep(0.5)
    
    async def _auto_detect_configuration(self):
        """
        Auto-detect device configuration from WLED API
        
        Returns:
            True if detection successful or disabled, False on error
        """
        if not self.auto_detect_enabled:
            self.log.debug("Auto-detection disabled, using configured values")
            return True
        
        if self._auto_detected:
            self.log.debug("Already auto-detected, skipping")
            return True
        
        try:
            # Import here to avoid circular dependency
            from wled.wled_device_config import WLEDDeviceConfig, WLEDDeviceHTTPClient
            
            # Create device config manager
            extended_client = WLEDDeviceHTTPClient(self.http)
            self.device_config = WLEDDeviceConfig(extended_client, self.log)
            
            # Perform detection
            self.log.info("Auto-detecting WLED device configuration...")
            success = await self.device_config.detect()
            
            if not success:
                self.log.warning("Auto-detection failed, using default/manual values")
                return True  # Don't fail, just use defaults
            
            # Apply auto-detected values (only if not manually overridden)
            if not self._manual_segment_id:
                # Use first active segment
                detected_segment_id = self.device_config.get_first_active_segment_id()
                if detected_segment_id != self.segment_id:
                    self.log.info(f"Auto-detected segment ID: {detected_segment_id}")
                    self.segment_id = detected_segment_id
            
            if not self._manual_start_led or not self._manual_stop_led:
                # Get segment range
                detected_start, detected_stop = self.device_config.get_segment_range(self.segment_id)
                
                if not self._manual_start_led:
                    if detected_start != self.start_led:
                        self.log.info(f"Auto-detected start LED: {detected_start} (was {self.start_led})")
                        self.start_led = detected_start
                
                if not self._manual_stop_led:
                    if detected_stop != self.stop_led:
                        self.log.info(f"Auto-detected stop LED: {detected_stop} (was {self.stop_led})")
                        self.stop_led = detected_stop
            
            # Log summary
            total_leds = self.stop_led - self.start_led + 1
            self.log.info(f"Configuration: Segment {self.segment_id}, LEDs {self.start_led}-{self.stop_led} ({total_leds} total)")
            
            self._auto_detected = True
            return True
            
        except Exception as e:
            self.log.warning(f"Auto-detection error: {e}")
            self.log.warning("Continuing with default/manual configuration")
            return True  # Don't fail the effect start
    
    async def test_connection(self):
        """Test if WLED device is reachable and responsive, and configure it for API control"""
        self.log.info("Testing WLED device connection...")
        
        # Step 1: Get current device state to check for live mode and other settings
        state = await self.http.get_state()
        if state is None:
            self.log.error(f"✗ Failed to connect to WLED device")
            self.log.error(f"  Check: Is {WLED_IP} correct and device powered on?")
            return False
        
        # Check if device is in live/realtime mode
        is_live = state.get("live", False)
        lor = state.get("lor", 0)
        is_on = state.get("on", False)
        
        self.log.info(f"Current device state: on={is_on}, live={is_live}, lor={lor}")
        
        if is_live:
            self.log.warning("⚠ Device is in realtime/live mode (UDP/E1.31 streaming active)")
            self.log.info("Setting live override to take API control...")
        
        # Step 2: Disable live mode and set override, ensure device is on
        control_payload = {
            "on": True,          # Turn device on
            "live": False,       # Exit live/realtime mode
            "lor": 1,            # Live override: allow API control even if streaming resumes
            "bri": 255          # Set master brightness
        }
        
        self.log.info("Configuring device for API control...")
        success = await self.http.send_command(control_payload)
        if not success:
            self.log.error("✗ Failed to configure device state")
            return False
        
        await self.task.sleep(0.3)  # Give device time to process
        
        # Step 3: Configure the segment properly
        self.log.info(f"Configuring segment {self.segment_id} for LEDs {self.start_led}-{self.stop_led}...")
        
        setup_payload = {
            "seg": {
                "id": self.segment_id,
                "start": self.start_led,
                "stop": self.stop_led + 1,  # Stop is exclusive in WLED
                "on": True,
                "bri": 255,
                "fx": 0  # Solid effect (required before individual LED control)
            }
        }
        success = await self.http.send_command(setup_payload)
        if success:
            self.log.info("✓ WLED device is reachable and configured for API control")
            self.log.info(f"  Device is ON and ready for commands")
            self.log.info(f"  Live mode disabled, API override enabled")
            self.log.info(f"  Segment {self.segment_id} covers LEDs {self.start_led} to {self.stop_led}")
        else:
            self.log.error("✗ WLED segment configuration FAILED!")
            self.log.error(f"  Check: Does your WLED device have enough LEDs ({self.stop_led + 1} needed)?")
            self.log.error(f"  Check: Is segment {self.segment_id} available on your device?")
        return success
    
    async def start(self):
        """Start the WLED effect"""
        self.log.info(f"Starting {self.get_effect_name()} - current running state: {self.running}")
        
        if self.running:
            self.log.warning(f"{self.get_effect_name()} is already running - stopping it first")
            await self.stop()
            await self.task.sleep(1)
        
        # Auto-detect configuration if enabled
        await self._auto_detect_configuration()
        
        self.log.info(f"Starting {self.get_effect_name()} - IP: {WLED_IP}, Segment: {self.segment_id}")
        self.log.info(f"1D Strip: LEDs {self.start_led} to {self.stop_led} ({self.stop_led - self.start_led + 1} LEDs total)")
        
        # Test connection first
        if not await self.test_connection():
            self.log.error("Cannot start effect - device not reachable")
            return
        
        self.running = True
        self.active_tasks = set()
        
        if self.run_once_mode == True:
            self.log.info("Running in single iteration mode")
            await self.run_effect()
        else:
            # Clear segment
            self.log.info("Clearing WLED segment...")
            await self.blackout_segment()
            self.log.info("Blackout complete")
            
            # Start effect task with unique name
            task_name = f"wled_effect_{self.instance_id}_main"
            self.log.info(f"Creating {self.get_effect_name()} task ({task_name})...")
            await self.task.create_task(task_name, self.run_effect())
        
        self.log.info(f"{self.get_effect_name()} started")
    
    async def run_once(self):
        """Run the effect once without looping, then automatically stop.
        
        Sets run_once_mode flag - implementers of run_effect() should check
        self.run_once_mode and break their loop after one iteration.
        """
        self.log.info(f"Running {self.get_effect_name()} once (single iteration mode)")
        
        # Set the flag for effect implementers to check
        self.run_once_mode = True
        
        try:
            # Use existing start method
            await self.start()
            self.log.info(f"Running {self.get_effect_name()} once (single iteration mode)")
            
            # Wait for effect to complete (it should exit after one iteration)
            # Note: The implementer's run_effect() should check self.run_once_mode
        finally:
            # Always clean up
            self.run_once_mode = False
            if self.running:
                await self.stop(blackout_on_stop=False)
    
    async def stop(self, blackout_on_stop=True):
        """Stop the WLED effect"""
        self.log.info(f"Stopping {self.get_effect_name()} - killing {len(self.active_tasks)} tasks")
        
        self.running = False
        
        # Kill main effect task
        task_name = f"wled_effect_{self.instance_id}_main"
        self.task.kill_task(task_name)
        
        # Kill all active tasks
        for task_name in list(self.active_tasks):
            self.log.debug(f"Killing task: {task_name}")
            self.task.kill_task(task_name)
        
        self.active_tasks.clear()
        
        # Clear all LEDs immediately
        if blackout_on_stop:
            self.log.info("Blackouting segment on stop...")
            await self.blackout_segment()
            self.log.info("Blackout complete")
        
        # Cleanup http client
        await self.http.cleanup()
        
        self.log.info(f"{self.get_effect_name()} stopped")
