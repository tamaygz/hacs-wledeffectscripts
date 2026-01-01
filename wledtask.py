"""
WLED Effects - Pyscript Loader for Home Assistant
Requires: Pyscript integration (install via HACS)
"""

from wled.effects.segment_fade import SegmentFadeEffect
from wled.wled_effect_base import WLED_URL, WLED_IP
import asyncio


# Logger wrapper to make pyscript log available in nested scopes
class Logger:
    """Wrapper to access pyscript log builtin"""
    def debug(self, msg):
        log.debug(msg)
    
    def info(self, msg):
        log.info(msg)
    
    def warning(self, msg):
        log.warning(msg)
    
    def error(self, msg):
        log.error(msg)


# Pyscript adapters
class PyscriptTaskManager:
    """Adapter for pyscript task management"""
    
    def __init__(self):
        self._tasks = {}
    
    async def sleep(self, duration):
        await task.sleep(duration)
    
    async def create_task(self, name, coro):
        task.unique(name)
        # In pyscript, just call the coroutine directly (it becomes a task)
        coro
    
    def kill_task(self, name):
        task.unique(name, kill_me=True)


class PyscriptHTTPClient:
    """Adapter for HTTP requests in pyscript"""
    
    def __init__(self):
        self.shared_session = None
    
    async def get_state(self):
        """Get current WLED device state"""
        import aiohttp
        
        if self.shared_session is None:
            self.shared_session = aiohttp.ClientSession()
        
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
    
    async def send_command(self, payload, retry_count=2):
        """Send command to WLED using REST API with retry logic"""
        import aiohttp
        
        # Create shared session if it doesn't exist
        if self.shared_session is None:
            self.shared_session = aiohttp.ClientSession()
        
        for attempt in range(retry_count + 1):
            try:
                log.debug(f"Sending to {WLED_URL}: {payload}")
                async with self.shared_session.post(
                    WLED_URL, 
                    json=payload, 
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        log.debug(f"WLED command successful")
                        return True
                    else:
                        log.warning(f"WLED returned status {resp.status}")
                        response_text = await resp.text()
                        log.warning(f"Response: {response_text}")
                        return False
            except asyncio.TimeoutError:
                if attempt < retry_count:
                    log.warning(f"Timeout on attempt {attempt + 1}/{retry_count + 1}, retrying...")
                    await task.sleep(0.1)
                else:
                    log.error(f"Timeout sending WLED command after {retry_count + 1} attempts")
                    return False
            except Exception as e:
                if attempt < retry_count:
                    log.warning(f"Error on attempt {attempt + 1}: {e}, retrying...")
                    await task.sleep(0.1)
                else:
                    log.error(f"Error sending WLED command to {WLED_URL}: {e}")
                    import traceback
                    log.error(f"Traceback: {traceback.format_exc()}")
                    return False
        return False
    
    async def cleanup(self):
        """Cleanup HTTP session"""
        if self.shared_session:
            await self.shared_session.close()
            self.shared_session = None


# Global effect instance
effect = None


@service
async def wled_test_start():
    """Start the WLED fade effect"""
    global effect
    
    if effect is None:
        task_mgr = PyscriptTaskManager()
        http_client = PyscriptHTTPClient()
        logger = Logger()
        effect = SegmentFadeEffect(task_mgr, logger, http_client)
    
    await effect.start()


@service
async def wled_test_stop():
    """Stop the WLED fade effect"""
    global effect
    
    if effect:
        await effect.stop()
