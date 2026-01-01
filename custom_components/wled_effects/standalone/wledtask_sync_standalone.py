"""  
WLED State Sync - Standalone Test Version
Tests the state sync effect with simulated state changes
Run with: python3 wledtask_sync_standalone.py
"""

import sys
import os
# Add modules directory to path for imports (parent directory)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'modules'))

from wled.effects.state_sync import StateSyncEffect
from wled.wled_effect_base import WLED_URL, WLED_IP
import asyncio
import aiohttp
import logging
import random

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)


class MockStateProvider:
    """Mock state provider that simulates changing values for testing"""
    
    def __init__(self, mode="random"):
        """
        Args:
            mode: "random" - random values
                  "ramp_up" - slowly increase from 0 to 100
                  "ramp_down" - slowly decrease from 100 to 0
                  "sine" - sine wave pattern
                  "static" - fixed value for testing
        """
        self.mode = mode
        self.current_value = 50.0
        self.time_counter = 0
        self.static_value = 75.0
    
    async def get_state(self):
        """Get simulated state value as percentage (0-100)"""
        self.time_counter += 1
        
        if self.mode == "random":
            # Random walk
            change = random.uniform(-5, 5)
            self.current_value = max(0, min(100, self.current_value + change))
        
        elif self.mode == "ramp_up":
            # Slowly increase
            self.current_value = min(100, self.current_value + 0.5)
            if self.current_value >= 100:
                self.current_value = 0  # Reset
        
        elif self.mode == "ramp_down":
            # Slowly decrease
            self.current_value = max(0, self.current_value - 0.5)
            if self.current_value <= 0:
                self.current_value = 100  # Reset
        
        elif self.mode == "sine":
            # Sine wave (0-100)
            import math
            self.current_value = 50 + 50 * math.sin(self.time_counter * 0.1)
        
        elif self.mode == "static":
            # Fixed value
            self.current_value = self.static_value
        
        return self.current_value


# Standalone adapters (same as wledtask_standalone.py)
class StandaloneTaskManager:
    """Adapter for standalone task management"""
    
    def __init__(self):
        self._tasks = {}
    
    async def sleep(self, duration):
        await asyncio.sleep(duration)
    
    async def create_task(self, name, coro):
        t = asyncio.create_task(coro)
        self._tasks[name] = t
    
    def kill_task(self, name):
        if name in self._tasks:
            task = self._tasks[name]
            if not task.done():
                task.cancel()
            del self._tasks[name]


class StandaloneHTTPClient:
    """Adapter for HTTP requests in standalone mode"""
    
    def __init__(self):
        self.shared_session = None
    
    async def get_state(self):
        """Get current WLED device state"""
        if self.shared_session is None:
            connector = aiohttp.TCPConnector(limit=1, limit_per_host=1, force_close=False, enable_cleanup_closed=True)
            self.shared_session = aiohttp.ClientSession(connector=connector)
        
        try:
            async with self.shared_session.get(
                f"http://{WLED_IP}/json/state",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    log.error(f"Failed to get device state: HTTP {resp.status}")
                    return None
        except Exception as e:
            log.error(f"Error getting device state: {e}")
            return None
    
    async def get_info(self):
        """Get WLED device information"""
        if self.shared_session is None:
            connector = aiohttp.TCPConnector(limit=1, limit_per_host=1, force_close=False, enable_cleanup_closed=True)
            self.shared_session = aiohttp.ClientSession(connector=connector)
        
        try:
            async with self.shared_session.get(
                f"http://{WLED_IP}/json/info",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    log.error(f"Failed to get device info: HTTP {resp.status}")
                    return None
        except Exception as e:
            log.error(f"Error getting device info: {e}")
            return None
    
    async def send_command(self, payload, retry_count=2):
        """Send command to WLED using REST API with retry logic"""
        if self.shared_session is None:
            connector = aiohttp.TCPConnector(limit=1, limit_per_host=1, force_close=False, enable_cleanup_closed=True)
            self.shared_session = aiohttp.ClientSession(connector=connector)
        
        for attempt in range(retry_count + 1):
            try:
                async with self.shared_session.post(
                    WLED_URL, 
                    json=payload, 
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        return True
                    else:
                        log.error(f"✗ WLED returned {resp.status}")
                        return False
            except asyncio.TimeoutError:
                if attempt < retry_count:
                    log.warning(f"⏱ Timeout (attempt {attempt + 1}/{retry_count + 1}), retrying...")
                    await asyncio.sleep(0.2)
                else:
                    log.error(f"✗ Timeout after {retry_count + 1} attempts")
                    return False
            except Exception as e:
                if attempt < retry_count:
                    log.warning(f"⚠ Error (attempt {attempt + 1}): {e}")
                    await asyncio.sleep(0.2)
                else:
                    log.error(f"✗ Failed after {retry_count + 1} attempts: {e}")
                    return False
        return False
    
    async def cleanup(self):
        """Cleanup HTTP session"""
        if self.shared_session:
            await self.shared_session.close()
            self.shared_session = None


async def main():
    """Main entry point"""
    log.info("WLED State Sync Effect - Standalone Test")
    log.info(f"Target device: {WLED_URL}")
    log.info("\nSimulation modes:")
    log.info("  - random: Random walk between 0-100%")
    log.info("  - ramp_up: Slowly increase 0->100")
    log.info("  - ramp_down: Slowly decrease 100->0")
    log.info("  - sine: Sine wave pattern")
    log.info("  - static: Fixed at 75%")
    log.info("\nPress Ctrl+C to stop\n")
    
    # Create mock state provider (change mode here to test different patterns)
    state_provider = MockStateProvider(mode="ramp_up")
    
    # Create adapters
    task_mgr = StandaloneTaskManager()
    http_client = StandaloneHTTPClient()
    
    # Create effect instance
    effect = StateSyncEffect(task_mgr, log, http_client, state_provider)
    
    try:
        # state_provider.mode = "random"
        await effect.start()
        # await effect.run_once()
        # Keep running until interrupted
        while effect.running:
            await asyncio.sleep(0.5)
    except KeyboardInterrupt:
        log.info("\nKeyboard interrupt received")
        await effect.stop()
    except Exception as e:
        log.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
        await effect.stop()


if __name__ == "__main__":
    asyncio.run(main())
