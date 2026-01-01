"""
WLED Device Configuration Auto-Detection
Automatically detects LED counts, segments, and device capabilities from WLED API
"""

import logging
from typing import Optional, Dict, List, Tuple


class WLEDDeviceConfig:
    """Auto-detects and manages WLED device configuration"""
    
    def __init__(self, http_client, logger: Optional[logging.Logger] = None):
        """
        Initialize device configuration manager
        
        Args:
            http_client: Object with get_state() and get_info() async methods
            logger: Optional logger object
        """
        self.http = http_client
        self.log = logger or logging.getLogger(__name__)
        
        # Device information (populated by detect())
        self.total_led_count: int = 0
        self.segments: List[Dict] = []
        self.max_segments: int = 0
        self.device_name: str = ""
        self.version: str = ""
        self.platform: str = ""
        self.supports_rgbw: bool = False
        self.fps: int = 0
        
        # Detection status
        self._detected: bool = False
    
    async def detect(self) -> bool:
        """
        Auto-detect device configuration from WLED API
        
        Returns:
            True if detection successful, False otherwise
        """
        self.log.info("Auto-detecting WLED device configuration...")
        
        # Get device info
        info = await self.http.get_info()
        if info is None:
            self.log.error("Failed to get device info from WLED API")
            return False
        
        # Extract LED information
        leds_info = info.get("leds", {})
        self.total_led_count = leds_info.get("count", 0)
        self.max_segments = leds_info.get("maxseg", 1)
        self.fps = leds_info.get("fps", 0)
        
        # Check for RGBW support (deprecated fields, but check for backward compatibility)
        self.supports_rgbw = leds_info.get("rgbw", False)
        
        # Extract device information
        self.device_name = info.get("name", "Unknown WLED Device")
        self.version = info.get("ver", "Unknown")
        self.platform = info.get("arch", "Unknown")
        
        self.log.info(f"Device: {self.device_name}")
        self.log.info(f"Version: {self.version} ({self.platform})")
        self.log.info(f"Total LEDs: {self.total_led_count}")
        self.log.info(f"Max Segments: {self.max_segments}")
        self.log.info(f"FPS: {self.fps}")
        if self.supports_rgbw:
            self.log.info("RGBW Support: Yes")
        
        # Get current state to read active segments
        state = await self.http.get_state()
        if state is None:
            self.log.warning("Failed to get device state, using defaults")
            self._create_default_segment()
        else:
            # Extract segment configuration
            self.segments = state.get("seg", [])
            if not self.segments:
                self.log.warning("No segments found, creating default segment")
                self._create_default_segment()
            else:
                self.log.info(f"Found {len(self.segments)} configured segment(s):")
                for seg in self.segments:
                    seg_id = seg.get("id", 0)
                    start = seg.get("start", 0)
                    stop = seg.get("stop", self.total_led_count)
                    length = stop - start
                    is_on = seg.get("on", True)
                    status = "ON" if is_on else "OFF"
                    self.log.info(f"  Segment {seg_id}: LEDs {start}-{stop-1} ({length} LEDs) [{status}]")
        
        self._detected = True
        return True
    
    def _create_default_segment(self):
        """Create a default segment covering all LEDs"""
        self.segments = [{
            "id": 0,
            "start": 0,
            "stop": self.total_led_count,
            "len": self.total_led_count,
            "on": True
        }]
    
    def is_detected(self) -> bool:
        """Check if device configuration has been detected"""
        return self._detected
    
    def get_segment_by_id(self, segment_id: int) -> Optional[Dict]:
        """
        Get segment configuration by ID
        
        Args:
            segment_id: Segment ID to retrieve
            
        Returns:
            Segment dict or None if not found
        """
        for seg in self.segments:
            if seg.get("id") == segment_id:
                return seg
        return None
    
    def get_segment_range(self, segment_id: int = 0) -> Tuple[int, int]:
        """
        Get LED range for a specific segment
        
        Args:
            segment_id: Segment ID (default: 0)
            
        Returns:
            Tuple of (start_led, stop_led) inclusive range
            Returns (0, total_led_count-1) if segment not found
        """
        seg = self.get_segment_by_id(segment_id)
        if seg:
            start = seg.get("start", 0)
            stop = seg.get("stop", self.total_led_count)
            return (start, stop - 1)  # Make stop inclusive
        
        # Fallback to full range
        return (0, self.total_led_count - 1)
    
    def get_segment_length(self, segment_id: int = 0) -> int:
        """
        Get LED count for a specific segment
        
        Args:
            segment_id: Segment ID (default: 0)
            
        Returns:
            Number of LEDs in segment
        """
        start, stop = self.get_segment_range(segment_id)
        return stop - start + 1
    
    def get_active_segments(self) -> List[Dict]:
        """
        Get list of segments that are currently on
        
        Returns:
            List of active segment dicts
        """
        return [seg for seg in self.segments if seg.get("on", True)]
    
    def get_first_active_segment_id(self) -> int:
        """
        Get ID of first active segment
        
        Returns:
            Segment ID (default: 0)
        """
        active = self.get_active_segments()
        if active:
            return active[0].get("id", 0)
        return 0
    
    def validate_led_range(self, start_led: int, stop_led: int, segment_id: int = 0) -> bool:
        """
        Validate if LED range is valid for the given segment
        
        Args:
            start_led: Start LED position
            stop_led: Stop LED position (inclusive)
            segment_id: Segment ID to validate against
            
        Returns:
            True if range is valid
        """
        seg_start, seg_stop = self.get_segment_range(segment_id)
        
        if start_led < seg_start or stop_led > seg_stop:
            self.log.warning(
                f"LED range {start_led}-{stop_led} exceeds segment {segment_id} "
                f"bounds {seg_start}-{seg_stop}"
            )
            return False
        
        return True
    
    def get_summary(self) -> str:
        """
        Get a summary string of device configuration
        
        Returns:
            Multi-line summary string
        """
        if not self._detected:
            return "Device not detected yet. Call detect() first."
        
        lines = [
            f"WLED Device: {self.device_name}",
            f"Version: {self.version} ({self.platform})",
            f"Total LEDs: {self.total_led_count}",
            f"Max Segments: {self.max_segments}",
            f"Active Segments: {len(self.get_active_segments())}/{len(self.segments)}",
            f"FPS: {self.fps}",
        ]
        
        if self.segments:
            lines.append("\nSegments:")
            for seg in self.segments:
                seg_id = seg.get("id", 0)
                start, stop = self.get_segment_range(seg_id)
                length = self.get_segment_length(seg_id)
                is_on = seg.get("on", True)
                status = "ON" if is_on else "OFF"
                lines.append(f"  [{seg_id}] LEDs {start}-{stop} ({length} LEDs) - {status}")
        
        return "\n".join(lines)


class WLEDDeviceHTTPClient:
    """Extended HTTP client that supports both state and info endpoints"""
    
    def __init__(self, base_http_client):
        """
        Initialize extended HTTP client
        
        Args:
            base_http_client: Basic HTTP client with get_state() and send_command() methods
        """
        self.base_client = base_http_client
    
    async def get_state(self):
        """Get device state (delegates to base client)"""
        return await self.base_client.get_state()
    
    async def send_command(self, payload):
        """Send command (delegates to base client)"""
        return await self.base_client.send_command(payload)
    
    async def get_info(self):
        """
        Get device info from /json/info endpoint
        
        Returns:
            Dict with device info or None on error
        """
        # Check if base client has get_info method
        if hasattr(self.base_client, 'get_info'):
            return await self.base_client.get_info()
        
        # Otherwise, try to construct info endpoint URL from state URL
        if hasattr(self.base_client, 'get_json'):
            return await self.base_client.get_json('/json/info')
        
        # Fallback: try to parse from base client attributes
        raise NotImplementedError(
            "Base HTTP client must implement get_info() or get_json() method"
        )
    
    async def cleanup(self):
        """Cleanup HTTP client resources"""
        if hasattr(self.base_client, 'cleanup'):
            await self.base_client.cleanup()
