"""
WLED Effect Base Class
Shared codebase for both pyscript and standalone usage
Provides base class for device management
"""

import asyncio
from abc import ABC, abstractmethod

# Device Configuration
WLED_IP = "192.168.1.50"
WLED_URL = f"http://{WLED_IP}/json/state"
SEGMENT_ID = 1
DEBUG_MODE = True  # Enable detailed logging

# 1D Strip configuration
START_LED = 1
STOP_LED = 40
LED_BRIGHTNESS = 255  # Maximum brightness level (0-255)


class WLEDEffectBase(ABC):
    """Base class for all WLED effects - handles device management"""
    
    def __init__(self, task_manager, logger, http_client):
        """
        Initialize the effect controller
        
        Args:
            task_manager: Object with sleep(), create_task(), kill_task() methods
            logger: Logger object with info(), debug(), warning(), error() methods
            http_client: Object with get_state() and send_command(payload) async methods
        """
        self.task = task_manager
        self.log = logger
        self.http = http_client
        
        # State
        self.running = False
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
        total_leds = STOP_LED - START_LED + 1
        
        led_array = []
        for i in range(START_LED, STOP_LED + 1):
            led_array.extend([i, "000000"])
        
        payload = {"seg": {"id": SEGMENT_ID, "i": led_array}}
        await self.send_wled_command(payload, f"Blackout {total_leds} LEDs")
        await self.task.sleep(0.2)
        
        payload2 = {
            "seg": {
                "id": SEGMENT_ID,
                "i": [],
                "col": [[0, 0, 0]],
                "bri": 1,
                "on": True,
            }
        }
        await self.send_wled_command(payload2, "Reset segment")
        await self.task.sleep(0.5)
    
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
        self.log.info(f"Configuring segment {SEGMENT_ID} for LEDs {START_LED}-{STOP_LED}...")
        
        setup_payload = {
            "seg": {
                "id": SEGMENT_ID,
                "start": START_LED,
                "stop": STOP_LED + 1,  # Stop is exclusive in WLED
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
            self.log.info(f"  Segment {SEGMENT_ID} covers LEDs {START_LED} to {STOP_LED}")
        else:
            self.log.error("✗ WLED segment configuration FAILED!")
            self.log.error(f"  Check: Does your WLED device have enough LEDs ({STOP_LED + 1} needed)?")
            self.log.error(f"  Check: Is segment {SEGMENT_ID} available on your device?")
        return success
    
    async def start(self):
        """Start the WLED effect"""
        self.log.info(f"Starting {self.get_effect_name()} - current running state: {self.running}")
        
        if self.running:
            self.log.warning(f"{self.get_effect_name()} is already running - stopping it first")
            await self.stop()
            await self.task.sleep(1)
        
        self.log.info(f"Starting {self.get_effect_name()} - IP: {WLED_IP}, Segment: {SEGMENT_ID}")
        self.log.info(f"1D Strip: LEDs {START_LED} to {STOP_LED} ({STOP_LED - START_LED + 1} LEDs total)")
        
        # Test connection first
        if not await self.test_connection():
            self.log.error("Cannot start effect - device not reachable")
            return
        
        self.running = True
        self.active_tasks = set()
        
        # Clear segment
        self.log.info("Clearing WLED segment...")
        await self.blackout_segment()
        self.log.info("Blackout complete")
        
        # Start effect task
        self.log.info(f"Creating {self.get_effect_name()} task...")
        await self.task.create_task("wled_effect_main", self.run_effect())
        
        self.log.info(f"{self.get_effect_name()} started")
    
    async def stop(self):
        """Stop the WLED effect"""
        self.log.info(f"Stopping {self.get_effect_name()} - killing {len(self.active_tasks)} tasks")
        
        self.running = False
        
        # Kill main effect task
        self.task.kill_task("wled_effect_main")
        
        # Kill all active tasks
        for task_name in list(self.active_tasks):
            self.log.debug(f"Killing task: {task_name}")
            self.task.kill_task(task_name)
        
        self.active_tasks.clear()
        
        # Clear all LEDs immediately
        await self.blackout_segment()
        
        # Cleanup http client
        await self.http.cleanup()
        
        self.log.info(f"{self.get_effect_name()} stopped")
