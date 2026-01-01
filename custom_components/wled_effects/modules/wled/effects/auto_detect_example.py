"""
Auto-Detection Example Effect
Demonstrates how to use WLEDDeviceConfig for automatic device detection
instead of hardcoded constants
"""

from wled.wled_effect_base import WLEDEffectBase, SEGMENT_ID, LED_BRIGHTNESS
from wled.wled_device_config import WLEDDeviceConfig, WLEDDeviceHTTPClient


class AutoDetectRainbowEffect(WLEDEffectBase):
    """Rainbow effect that auto-detects LED count and segment configuration"""
    
    def __init__(self, task_manager, logger, http_client):
        """Initialize with auto-detection"""
        # Initialize base class
        super().__init__(task_manager, logger, http_client)
        
        # Create device config for auto-detection
        # Note: We need an extended HTTP client that supports get_info()
        extended_client = WLEDDeviceHTTPClient(http_client)
        self.device_config = WLEDDeviceConfig(extended_client, logger)
        
        # These will be populated after detection
        self.start_led = 0
        self.stop_led = 0
        self.total_leds = 0
        self.segment_id = SEGMENT_ID  # Default from base config
    
    def get_effect_name(self):
        return "Auto-Detect Rainbow Effect"
    
    async def initialize(self):
        """
        Auto-detect device configuration before running effect
        Should be called before start()
        """
        success = await self.device_config.detect()
        
        if not success:
            self.log.error("Failed to auto-detect device configuration")
            return False
        
        # Log device summary
        self.log.info("Device Configuration Detected:")
        for line in self.device_config.get_summary().split('\n'):
            self.log.info(f"  {line}")
        
        # Get segment configuration
        self.start_led, self.stop_led = self.device_config.get_segment_range(self.segment_id)
        self.total_leds = self.device_config.get_segment_length(self.segment_id)
        
        self.log.info(f"Using Segment {self.segment_id}: LEDs {self.start_led}-{self.stop_led} ({self.total_leds} LEDs)")
        
        # Validate configuration
        if self.total_leds == 0:
            self.log.error("No LEDs detected in segment!")
            return False
        
        return True
    
    def get_rainbow_color(self, position, offset):
        """Generate rainbow color based on position"""
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
        """Main effect loop - rainbow wave using auto-detected LED count"""
        self.log.info(f"Starting auto-detected rainbow animation on {self.total_leds} LEDs")
        
        offset = 0
        
        while self.running:
            # Build LED array for detected range
            led_array = []
            
            for led_pos in range(self.start_led, self.stop_led + 1):
                # Calculate position in rainbow (0-360 degrees)
                position = (led_pos - self.start_led) * (360.0 / self.total_leds)
                
                # Get color for this position with offset
                r, g, b = self.get_rainbow_color(position, offset)
                
                # Apply brightness
                r = int(r * (LED_BRIGHTNESS / 255.0))
                g = int(g * (LED_BRIGHTNESS / 255.0))
                b = int(b * (LED_BRIGHTNESS / 255.0))
                
                hex_color = f"{r:02x}{g:02x}{b:02x}"
                led_array.extend([led_pos - self.start_led, hex_color])
            
            # Send command
            payload = {"seg": {"id": self.segment_id, "i": led_array, "bri": 255}}
            await self.send_wled_command(payload, f"Rainbow wave offset={offset}")
            
            # Move the wave
            offset = (offset + 10) % 360
            
            # Check if we should exit after one iteration
            if self.run_once_mode:
                self.log.info("Auto-detect rainbow completed single iteration")
                break
            
            # Wait before next step
            await self.interruptible_sleep(0.1)
        
        self.log.info("Auto-detect rainbow animation complete")


# Usage example (in pyscript or standalone):
"""
# Initialize the effect
effect = AutoDetectRainbowEffect(task_manager, logger, http_client)

# Auto-detect device configuration
if await effect.initialize():
    # Start the effect (it now uses auto-detected values)
    await effect.start()
else:
    logger.error("Failed to initialize effect - check device connection")
"""
