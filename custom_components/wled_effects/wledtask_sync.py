"""
WLED State Sync - Home Assistant Pyscript Version
Synchronizes WLED strip to a Home Assistant entity state
Uses @state_trigger for efficient state change monitoring
"""

from wled.effects.state_sync import StateSyncEffect, SYNC_COLOR
from wled.wled_effect_base import WLED_URL, WLED_IP
import asyncio


# Configuration - Change these to match your setup
ENTITY_TO_MONITOR = "sensor.curtainopenpercentage"  # Entity to monitor
ATTRIBUTE_NAME = None  # Set to attribute name if monitoring an attribute, or None for state
# ENTITY_TO_MONITOR = "cover.curtain_comedor"  # Entity to monitor
# ATTRIBUTE_NAME = "current_position"  # Set to attribute name if monitoring an attribute, or None for state
# Examples:
# ENTITY_TO_MONITOR = "cover.living_room_curtain" with ATTRIBUTE_NAME = "current_position"
# ENTITY_TO_MONITOR = "media_player.living_room" with ATTRIBUTE_NAME = "volume_level"
# ENTITY_TO_MONITOR = "input_number.brightness_slider" with ATTRIBUTE_NAME = None (uses state)

STATECHANGE_RUN_ONCE = True  # If True, effect runs atleast once per state change, even if the effect isnt currently running

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


class HAStateProvider:
    """Provides state values from Home Assistant"""
    
    def __init__(self, entity_id, attribute=None):
        self.entity_id = entity_id
        self.attribute = attribute
    
    async def get_state(self):
        """Get current state value as percentage (0-100)"""
        if self.attribute:
            # Get attribute value
            value = state.get(f"{self.entity_id}.{self.attribute}")
        else:
            # Get state value
            value = state.get(self.entity_id)
        
        # Convert to float
        if value is None or value == "unavailable" or value == "unknown":
            log.warning(f"State {self.entity_id} is unavailable")
            return 0.0
        
        try:
            # Try to convert to float
            numeric_value = float(value)
            
            # Clamp to 0-100 range
            percentage = max(0.0, min(100.0, numeric_value))
            
            return percentage
        except (ValueError, TypeError):
            log.error(f"Could not convert state value '{value}' to number")
            return 0.0


# Pyscript adapters (same as wledtask.py)
class PyscriptTaskManager:
    """Adapter for pyscript task management"""
    
    def __init__(self):
        self._tasks = {}
    
    async def sleep(self, duration):
        await task.sleep(duration)
    
    async def create_task(self, name, coro):
        task.unique(name)
        coro  # In pyscript, just call the coroutine directly
    
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
    
    async def get_info(self):
        """Get WLED device information"""
        import aiohttp
        
        if self.shared_session is None:
            self.shared_session = aiohttp.ClientSession()
        
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
        import aiohttp
        
        if self.shared_session is None:
            self.shared_session = aiohttp.ClientSession()
        
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
                        log.warning(f"WLED returned status {resp.status}")
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
                    log.error(f"Error sending WLED command: {e}")
                    return False
        return False
    
    async def cleanup(self):
        """Cleanup HTTP session"""
        if self.shared_session:
            await self.shared_session.close()
            self.shared_session = None


# Global effect instance
effect = None
state_provider_instance = None

if effect is None:
    task_mgr = PyscriptTaskManager()
    http_client = PyscriptHTTPClient()
    state_provider_instance = HAStateProvider(ENTITY_TO_MONITOR, ATTRIBUTE_NAME)
    logger = Logger()
    effect = StateSyncEffect(task_mgr, logger, http_client, state_provider_instance)
        
@service
async def wled_sync_start():
    """Start the WLED state sync effect"""
    global effect, state_provider_instance
    
    if effect is None:
        task_mgr = PyscriptTaskManager()
        http_client = PyscriptHTTPClient()
        state_provider_instance = HAStateProvider(ENTITY_TO_MONITOR, ATTRIBUTE_NAME)
        logger = Logger()
        effect = StateSyncEffect(task_mgr, logger, http_client, state_provider_instance)
    
    await effect.start()


@service
async def wled_sync_stop():
    """Stop the WLED state sync effect"""
    global effect
    
    if effect:
        await effect.stop()

@service
async def wled_sync_run_once():
    """Run the WLED state sync effect for one iteration"""
    global effect, state_provider_instance
    log.info("WLED State Sync: Running single iteration")
    if effect:
        await effect.run_once()
        
# Optional: Auto-trigger on state changes for even more responsiveness
@state_trigger(f"{ENTITY_TO_MONITOR}")
async def state_changed_trigger(var_name=None, value=None):
    """Trigger when monitored entity changes - makes effect more responsive"""
    global effect, state_provider_instance
    
    # Only process if effect is running
    if effect and effect.running and state_provider_instance:
        # The effect's polling loop will pick up the change
        # This trigger just ensures minimal latency
        log.debug(f"State trigger fired: {var_name} = {value}")
    elif STATECHANGE_RUN_ONCE == True:
        # If effect is not running, start it for one iteration
        log.info("State changed - starting effect for one iteration")
        await effect.run_once()
