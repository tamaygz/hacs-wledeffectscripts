"""
WLED Effects - Generic Service Wrapper for Home Assistant Pyscript
Dynamically loads and controls any WLED effect with configurable parameters
"""

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


class HAStateProvider:
    """Provides state values from Home Assistant for effects that need it"""
    
    def __init__(self, entity_id, attribute=None):
        self.entity_id = entity_id
        self.attribute = attribute
    
    async def get_state(self):
        """Get current state value as percentage (0-100)"""
        if self.attribute:
            value = state.get(f"{self.entity_id}.{self.attribute}")
        else:
            value = state.get(self.entity_id)
        
        if value is None or value == "unavailable" or value == "unknown":
            log.warning(f"State {self.entity_id} is unavailable")
            return 0.0
        
        try:
            numeric_value = float(value)
            percentage = max(0.0, min(100.0, numeric_value))
            return percentage
        except (ValueError, TypeError):
            log.error(f"Could not convert state value '{value}' to number")
            return 0.0


class PyscriptTaskManager:
    """Adapter for pyscript task management"""
    
    def __init__(self):
        self._tasks = {}
        self._spawned_tasks = []  # Track all tasks we create
    
    async def sleep(self, duration):
        await task.sleep(duration)
    
    async def create_task(self, name, coro):
        task.unique(name)
        self._spawned_tasks.append(name)
        coro  # In pyscript, just call the coroutine directly
    
    def kill_task(self, name):
        task.unique(name, kill_me=True)
        if name in self._spawned_tasks:
            self._spawned_tasks.remove(name)
    
    def kill_all_tasks(self):
        """Kill all tasks that were spawned by this manager"""
        killed_count = 0
        for task_name in list(self._spawned_tasks):  # Copy list to avoid modification during iteration
            try:
                task.unique(task_name, kill_me=True)
                killed_count += 1
            except Exception as e:
                log.warning(f"Could not kill task {task_name}: {e}")
        self._spawned_tasks.clear()
        return killed_count


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


class WLEDEffectManager:
    """Manages dynamic loading and control of WLED effects"""
    
    def __init__(self):
        self.effect = None
        self.effect_class = None
        self.effect_args = {}
        self.state_provider = None
        self.trigger_entity = None
        self.trigger_attribute = None
        self.trigger_on_change = False
        
        # Shared resources
        self.task_mgr = PyscriptTaskManager()
        self.http_client = PyscriptHTTPClient()
        self.logger = Logger()
    
    def load_effect_class(self, effect_name):
        """
        Load an effect class by name
        
        Args:
            effect_name: Effect name (e.g., "Rainbow Wave", "Segment Fade", etc.)
        """
        try:
            # Map effect names to their imports
            effect_map = {
                "Rainbow Wave": ("wled.effects.rainbow_wave", "RainbowWaveEffect"),
                "Segment Fade": ("wled.effects.segment_fade", "SegmentFadeEffect"),
                "Loading": ("wled.effects.loading", "LoadingEffect"),
                "State Sync": ("wled.effects.state_sync", "StateSyncEffect"),
            }
            
            if effect_name not in effect_map:
                log.error(f"Unknown effect: {effect_name}")
                return False
            
            module_path, class_name = effect_map[effect_name]
            
            # Import the effect class
            import_statement = f"from {module_path} import {class_name}"
            local_vars = {}
            exec(import_statement, globals(), local_vars)
            
            self.effect_class = local_vars[class_name]
            
            log.info(f"Loaded effect: {effect_name} ({class_name})")
            return True
        except Exception as e:
            log.error(f"Failed to load effect {effect_name}: {e}")
            import traceback
            log.error(f"Traceback: {traceback.format_exc()}")
            return False
    
    def create_effect(self, **kwargs):
        """
        Create effect instance with provided kwargs
        
        Args:
            **kwargs: Additional arguments for effect constructor
        """
        if self.effect_class is None:
            log.error("No effect class loaded")
            return False
        
        try:
            # Store kwargs for re-creation if needed
            self.effect_args = kwargs
            
            # Base args are always: task_manager, logger, http_client
            base_args = [self.task_mgr, self.logger, self.http_client]
            
            # Check if effect requires state provider using class attribute
            if getattr(self.effect_class, 'REQUIRES_STATE_PROVIDER', False):
                if 'state_provider' in kwargs:
                    base_args.append(kwargs.pop('state_provider'))
                elif self.state_provider:
                    base_args.append(self.state_provider)
                else:
                    log.error(f"Effect {self.effect_class.__name__} requires a state_provider")
                    return False
            
            # Create effect instance with base args and remaining kwargs
            self.effect = self.effect_class(*base_args, **kwargs)
            
            log.info(f"Created effect instance: {self.effect.get_effect_name()}")
            return True
        except Exception as e:
            log.error(f"Failed to create effect instance: {e}")
            import traceback
            log.error(f"Traceback: {traceback.format_exc()}")
            return False
    
    def setup_state_provider(self, entity_id, attribute=None):
        """Setup state provider for effects that need it"""
        self.state_provider = HAStateProvider(entity_id, attribute)
        log.info(f"Setup state provider for {entity_id}" + 
                 (f".{attribute}" if attribute else ""))
    
    def setup_trigger(self, entity_id, attribute=None, run_on_change=True):
        """
        Setup state trigger configuration
        
        Args:
            entity_id: Entity to monitor
            attribute: Optional attribute to monitor (None = monitor state)
            run_on_change: If True, runs effect once when entity changes
        """
        self.trigger_entity = entity_id
        self.trigger_attribute = attribute
        self.trigger_on_change = run_on_change
        
        trigger_desc = f"{entity_id}"
        if attribute:
            trigger_desc += f".{attribute}"
        log.info(f"Configured trigger for {trigger_desc} (run_on_change={run_on_change})")
    
    async def start_effect(self):
        """Start the effect"""
        if self.effect is None:
            log.error("No effect instance available")
            return False
        
        try:
            await self.effect.start()
            return True
        except Exception as e:
            log.error(f"Error starting effect: {e}")
            import traceback
            log.error(f"Traceback: {traceback.format_exc()}")
            return False
    
    async def stop_effect(self):
        """Stop the effect"""
        if self.effect is None:
            log.warning("No effect instance to stop")
            return False
        
        try:
            await self.effect.stop()
            return True
        except Exception as e:
            log.error(f"Error stopping effect: {e}")
            return False
    
    async def stop_all(self):
        """Stop effect and kill all spawned tasks"""
        stopped_effect = False
        
        # Stop the current effect if running
        if self.effect is not None:
            try:
                await self.effect.stop()
                stopped_effect = True
            except Exception as e:
                log.error(f"Error stopping effect: {e}")
        
        # Kill all tasks
        killed_count = self.task_mgr.kill_all_tasks()
        
        # Cleanup HTTP session
        try:
            await self.http_client.cleanup()
        except Exception as e:
            log.warning(f"Error cleaning up HTTP client: {e}")
        
        log.info(f"Stop all: Effect stopped={stopped_effect}, Tasks killed={killed_count}")
        return True
    
    async def run_once_effect(self):
        """Run effect once"""
        if self.effect is None:
            log.error("No effect instance available")
            return False
        
        try:
            await self.effect.run_once()
            return True
        except Exception as e:
            log.error(f"Error running effect once: {e}")
            import traceback
            log.error(f"Traceback: {traceback.format_exc()}")
            return False
    
    async def handle_trigger(self, trigger_value=None):
        """
        Handle state trigger event
        
        Args:
            trigger_value: The new value that triggered the change
        """
        if self.effect is None:
            log.warning("Trigger fired but no effect loaded")
            return
        
        trigger_desc = f"{self.trigger_entity}"
        if self.trigger_attribute:
            trigger_desc += f".{self.trigger_attribute}"
        
        if self.trigger_on_change:
            # Run effect once on state change
            if not self.effect.running:
                log.info(f"Trigger: {trigger_desc} changed to {trigger_value} - running effect once")
                await self.run_once_effect()
            else:
                log.debug(f"Trigger: {trigger_desc} changed to {trigger_value} - effect already running")


# Global manager instance
manager = WLEDEffectManager()


@service
def wled_effect_configure(
    effect: str = "Segment Fade",
    state_entity: str = None,
    state_attribute: str = None,
    trigger_entity: str = None,
    trigger_attribute: str = None,
    trigger_on_change: bool = True,
    auto_detect: bool = True,
    segment_id: int = None,
    start_led: int = None,
    stop_led: int = None,
    led_brightness: int = None
):
    """yaml
name: Configure WLED Effect
description: Load and configure a WLED effect with optional state monitoring and triggers
fields:
  effect:
    description: Select the WLED effect to use
    required: true
    default: "Segment Fade"
    example: "Rainbow Wave"
    selector:
      select:
        options:
          - "Rainbow Wave"
          - "Segment Fade"
          - "Loading"
          - "State Sync"
  state_entity:
    description: Entity ID for state provider (required for State Sync effect)
    example: "sensor.living_room_temperature"
    selector:
      entity:
  state_attribute:
    description: Attribute name for state provider (None = use entity state)
    example: "temperature"
    selector:
      text:
  trigger_entity:
    description: Entity to monitor for triggering effect (None = no trigger)
    example: "binary_sensor.motion_detected"
    selector:
      entity:
  trigger_attribute:
    description: Attribute to monitor for trigger (None = monitor state)
    example: "battery_level"
    selector:
      text:
  trigger_on_change:
    description: Run effect once when trigger entity changes
    default: true
    selector:
      boolean:
  auto_detect:
    description: Enable auto-detection of LED configuration from WLED device
    default: true
    selector:
      boolean:
  segment_id:
    description: Manual segment ID override (None = auto-detect)
    example: 0
    selector:
      number:
        min: 0
        max: 31
        mode: box
  start_led:
    description: Manual start LED override (None = auto-detect)
    example: 0
    selector:
      number:
        min: 0
        max: 1000
        mode: box
  stop_led:
    description: Manual stop LED override (None = auto-detect)
    example: 60
    selector:
      number:
        min: 0
        max: 1000
        mode: box
  led_brightness:
    description: Manual brightness override (None = use default/auto)
    example: 128
    selector:
      number:
        min: 0
        max: 255
        mode: slider
"""
    global manager
    
    log.info(f"Configuring effect: {effect}")
    
    # Load effect class
    if not manager.load_effect_class(effect):
        log.error("Failed to load effect")
        return
    
    # Setup state provider if needed
    if state_entity:
        manager.setup_state_provider(state_entity, state_attribute)
    
    # Setup trigger if configured
    if trigger_entity:
        manager.setup_trigger(trigger_entity, trigger_attribute, trigger_on_change)
    
    # Build effect constructor kwargs
    effect_kwargs = {}
    
    # Add state provider if exists (for StateSyncEffect)
    if manager.state_provider:
        effect_kwargs["state_provider"] = manager.state_provider
    
    # Add configuration overrides
    if auto_detect is not None:
        effect_kwargs["auto_detect"] = auto_detect
    if segment_id is not None:
        effect_kwargs["segment_id"] = segment_id
    if start_led is not None:
        effect_kwargs["start_led"] = start_led
    if stop_led is not None:
        effect_kwargs["stop_led"] = stop_led
    if led_brightness is not None:
        effect_kwargs["led_brightness"] = led_brightness
    
    # Create effect instance
    if manager.create_effect(**effect_kwargs):
        log.info("Effect configured successfully")
    else:
        log.error("Failed to create effect instance")


@service
async def wled_effect_start():
    """yaml
name: Start WLED Effect
description: Start the currently configured WLED effect in continuous loop mode
"""
    global manager
    
    log.info("Starting WLED effect...")
    if await manager.start_effect():
        log.info("Effect started successfully")
    else:
        log.error("Failed to start effect")


@service
async def wled_effect_stop():
    """yaml
name: Stop WLED Effect
description: Stop the currently running WLED effect
"""
    global manager
    
    log.info("Stopping WLED effect...")
    if await manager.stop_effect():
        log.info("Effect stopped successfully")
    else:
        log.warning("Effect stop had issues or no effect was running")


@service
async def wled_effect_run_once():
    """yaml
name: Run WLED Effect Once
description: Run the configured WLED effect once (single iteration)
"""
    global manager
    
    log.info("Running WLED effect once...")
    if await manager.run_once_effect():
        log.info("Effect completed single run")
    else:
        log.error("Failed to run effect once")


@service
async def wled_effect_stop_all():
    """yaml
name: Stop All WLED Tasks
description: Stop effect and kill all spawned background tasks, cleanup resources
"""
    global manager
    
    log.info("Stopping all WLED effect tasks...")
    if await manager.stop_all():
        log.info("All tasks stopped successfully")
    else:
        log.error("Failed to stop all tasks")


@service
def wled_effect_status():
    """yaml
name: Get WLED Effect Status
description: Get current status of the configured effect (returns structured data)
"""
    global manager
    
    status = {
        "configured": manager.effect is not None,
        "effect_name": None,
        "running": False,
        "trigger_entity": None,
        "trigger_attribute": None,
        "state_entity": None,
        "state_attribute": None
    }
    
    if manager.effect is None:
        log.info("No effect configured")
        return status
    
    status["effect_name"] = manager.effect.get_effect_name()
    status["running"] = manager.effect.running
    status["trigger_entity"] = manager.trigger_entity
    status["trigger_attribute"] = manager.trigger_attribute
    
    if manager.state_provider:
        status["state_entity"] = manager.state_provider.entity_id
        status["state_attribute"] = manager.state_provider.attribute
    
    # Log for debugging
    log.info(f"Effect: {status['effect_name']}")
    log.info(f"Running: {status['running']}")
    trigger_desc = f"{status['trigger_entity'] or 'None'}"
    if status['trigger_attribute']:
        trigger_desc += f".{status['trigger_attribute']}"
    log.info(f"Trigger: {trigger_desc}")
    
    if status['state_entity']:
        state_desc = status['state_entity']
        if status['state_attribute']:
            state_desc += f".{status['state_attribute']}"
        log.info(f"State Provider: {state_desc}")
    
    return status


# Dynamic state trigger registration
# Supports both state-only and state+attribute patterns
@state_trigger("manager.trigger_entity", "manager.trigger_attribute")
async def wled_effect_trigger(var_name=None, value=None, old_value=None):
    """
    Handle state changes for configured trigger entity
    
    Supports two patterns:
    1. State-only: trigger_entity without trigger_attribute (monitors entity state)
    2. State+Attribute: trigger_entity with trigger_attribute (monitors specific attribute)
    """
    global manager
    
    if not manager.trigger_entity:
        return
    
    # Determine what changed
    if manager.trigger_attribute:
        # Monitoring a specific attribute
        expected_var = f"{manager.trigger_entity}.{manager.trigger_attribute}"
        if var_name and expected_var in var_name:
            log.debug(f"Attribute trigger: {var_name} = {value} (was {old_value})")
            await manager.handle_trigger(value)
    else:
        # Monitoring the state itself
        if var_name and manager.trigger_entity in var_name:
            log.debug(f"State trigger: {var_name} = {value} (was {old_value})")
            await manager.handle_trigger(value)
