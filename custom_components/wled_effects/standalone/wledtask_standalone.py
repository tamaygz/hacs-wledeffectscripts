"""
WLED Effects - Standalone Runner
Run with: python3 wledtask_standalone.py
"""

import sys
import os
# Add modules directory to path for imports (parent directory)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'modules'))

from wled.effects.loading import LoadingEffect
from wled.effects.rainbow_wave import RainbowWaveEffect
from wled.effects.segment_fade import SegmentFadeEffect
from wled.wled_effect_base import WLED_URL, WLED_IP
import asyncio
import aiohttp
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)


# Standalone adapters
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
            log.debug(f"Killed task: {name}")


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
        # Create shared session if it doesn't exist
        if self.shared_session is None:
            connector = aiohttp.TCPConnector(limit=1, limit_per_host=1, force_close=False, enable_cleanup_closed=True)
            self.shared_session = aiohttp.ClientSession(connector=connector)
            log.info(f"Created shared HTTP session for {WLED_URL}")
        
        for attempt in range(retry_count + 1):
            try:
                # Show payload size for debugging
                import json
                payload_str = json.dumps(payload)
                payload_size = len(payload_str)
                
                async with self.shared_session.post(
                    WLED_URL, 
                    json=payload, 
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    response_text = await resp.text()
                    if resp.status == 200:
                        log.debug(f"✓ Command OK ({payload_size} bytes) -> {resp.status}")
                        return True
                    else:
                        log.error(f"✗ WLED returned {resp.status}: {response_text[:100]}")
                        return False
            except asyncio.TimeoutError:
                if attempt < retry_count:
                    log.warning(f"⏱ Timeout (attempt {attempt + 1}/{retry_count + 1}), retrying...")
                    await asyncio.sleep(0.2)
                else:
                    log.error(f"✗ Timeout after {retry_count + 1} attempts (payload: {payload_size} bytes)")
                    return False
            except aiohttp.ServerDisconnectedError as e:
                if attempt < retry_count:
                    log.warning(f"⚠ Server disconnected (attempt {attempt + 1}/{retry_count + 1}), retrying...")
                    # Recreate session on disconnect
                    await self.cleanup()
                    await asyncio.sleep(0.3)
                else:
                    log.error(f"✗ Server keeps disconnecting after {retry_count + 1} attempts")
                    log.error(f"   Payload size: {payload_size} bytes - may be too large or sent too fast")
                    return False
            except Exception as e:
                if attempt < retry_count:
                    log.warning(f"⚠ Error (attempt {attempt + 1}): {type(e).__name__}: {e}")
                    await asyncio.sleep(0.2)
                else:
                    log.error(f"✗ Failed after {retry_count + 1} attempts: {type(e).__name__}: {e}")
                    return False
        return False
    
    async def cleanup(self):
        """Cleanup HTTP session"""
        if self.shared_session:
            await self.shared_session.close()
            self.shared_session = None


async def main():
    """Main entry point"""
    log.info("WLED Effects - Standalone Test")
    log.info(f"Target device: {WLED_URL}")
    log.info("\nPress Ctrl+C to stop\n")
    
    # Create adapters
    task_mgr = StandaloneTaskManager()
    http_client = StandaloneHTTPClient()
    
    # Create effect instance
    effect = SegmentFadeEffect(task_mgr, log, http_client)
    # effect = LoadingEffect(task_mgr, log, http_client)
    try:
        await effect.start()
        # Keep running until interrupted
        while effect.running:
            await asyncio.sleep(1)
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
