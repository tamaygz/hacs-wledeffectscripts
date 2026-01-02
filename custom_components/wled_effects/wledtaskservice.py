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
        
        # Track all started effects by name for proper cleanup and targeting
        self.started_effects = {}  # {effect_name: effect_instance}
        self.effect_counter = 0  # For auto-generated names
        
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
        """Start the most recently configured effect"""
        return await self.start_effect_instance(self.effect)
    
    async def start_effect_instance(self, effect):
        """Start a specific effect instance"""
        if effect is None:
            log.error("No effect instance available")
            return False
        
        try:
            await effect.start()
            return True
        except Exception as e:
            log.error(f"Error starting effect: {e}")
            import traceback
            log.error(f"Traceback: {traceback.format_exc()}")
            return False
    
    async def stop_effect(self):
        """Stop the most recently configured effect"""
        return await self.stop_effect_instance(self.effect)
    
    async def stop_effect_instance(self, effect):
        """Stop a specific effect instance"""
        if effect is None:
            log.warning("No effect instance to stop")
            return False
        
        try:
            await effect.stop()
            return True
        except Exception as e:
            log.error(f"Error stopping effect: {e}")
            return False
    
    async def stop_all(self):
        """Stop ALL effects and kill all spawned tasks"""
        stopped_count = 0
        
        # Stop ALL tracked effects
        for effect_name, effect in list(self.started_effects.items()):
            try:
                log.info(f"Stopping effect '{effect_name}' (instance {effect.instance_id})")
                await effect.stop()
                stopped_count += 1
            except Exception as e:
                log.error(f"Error stopping effect '{effect_name}': {e}")
        
        # Clear the dict
        self.started_effects.clear()
        
        # Kill all tasks
        killed_count = self.task_mgr.kill_all_tasks()
        
        # Cleanup HTTP session
        try:
            await self.http_client.cleanup()
        except Exception as e:
            log.warning(f"Error cleaning up HTTP client: {e}")
        
        log.info(f"Stop all: {stopped_count} effects stopped, {killed_count} tasks killed")
        return True
    
    async def run_once_effect(self):
        """Run the most recently configured effect once"""
        return await self.run_once_effect_instance(self.effect)
    
    async def run_once_effect_instance(self, effect):
        """Run a specific effect instance once"""
        if effect is None:
            log.error("No effect instance available")
            return False
        
        try:
            await effect.run_once()
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
    effect_name: str = None,
    effect_config: dict = None,
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
  effect_name:
    description: Name for this effect instance (for targeting specific effects). Auto-generated if not provided.
    example: "rainbow_seg1"
    selector:
      text:
  effect_config:
    description: Effect-specific configuration (key-value pairs, e.g. {"anim_mode":"Single","sync_color":[255,0,0]})
    example: '{"anim_mode":"Dual","smooth_transition":false}'
    selector:
      object:
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
    
    # Generate effect name if not provided
    if not effect_name:
        manager.effect_counter += 1
        effect_name = f"effect_{manager.effect_counter}"
    
    log.info(f"Configuring effect '{effect_name}': {effect}")
    
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
    
    # Add effect-specific configuration
    if effect_config:
        effect_kwargs["effect_config"] = effect_config
    
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
        # Store with name for targeting
        manager.started_effects[effect_name] = manager.effect
        log.info(f"Effect '{effect_name}' configured successfully (segment={manager.effect.segment_id})")
    else:
        log.error("Failed to create effect instance")


@service
async def wled_effect_start(
    effect_name: str = None,
    effect: str = None,
    effect_config: dict = None,
    state_entity: str = None,
    state_attribute: str = None,
    auto_detect: bool = True,
    segment_id: int = None,
    start_led: int = None,
    stop_led: int = None,
    led_brightness: int = None
):
    """yaml
name: Start WLED Effect
description: Start a WLED effect in continuous loop mode. Can either reference a pre-configured effect or configure+start in one call.
fields:
  effect_name:
    description: Name of specific effect to start (if already configured). Leave empty to configure inline.
    example: "rainbow_seg1"
    selector:
      text:
  effect:
    description: Effect type to configure and start (if not using pre-configured effect)
    example: "Rainbow Wave"
    selector:
      select:
        options:
          - "Rainbow Wave"
          - "Segment Fade"
          - "Loading"
          - "State Sync"
  effect_config:
    description: Effect-specific configuration (key-value pairs)
    example: '{"anim_mode":"Dual","sync_color":[255,0,0]}'
    selector:
      object:
  state_entity:
    description: Entity ID for state provider (for State Sync effect)
    example: "sensor.living_room_temperature"
    selector:
      entity:
  state_attribute:
    description: Attribute name for state provider (None = use entity state)
    example: "temperature"
    selector:
      text:
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
    
    # Case 1: Reference existing configured effect
    if effect_name and effect_name in manager.started_effects:
        effect_inst = manager.started_effects[effect_name]
        log.info(f"Starting pre-configured effect '{effect_name}'...")
        
        if await manager.start_effect_instance(effect_inst):
            log.info(f"Effect '{effect_name}' started successfully")
        else:
            log.error("Failed to start effect")
        return
    
    # Case 2: Configure and start inline
    if effect:
        # Generate name if not provided
        if not effect_name:
            manager.effect_counter += 1
            effect_name = f"effect_{manager.effect_counter}"
        
        log.info(f"Configuring and starting effect '{effect_name}': {effect}")
        
        # Load effect class
        if not manager.load_effect_class(effect):
            log.error("Failed to load effect")
            return
        
        # Setup state provider if needed
        if state_entity:
            manager.setup_state_provider(state_entity, state_attribute)
        
        # Build kwargs
        effect_kwargs = {}
        if effect_config:
            effect_kwargs["effect_config"] = effect_config
        if manager.state_provider:
            effect_kwargs["state_provider"] = manager.state_provider
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
        
        # Create and start
        if manager.create_effect(**effect_kwargs):
            manager.started_effects[effect_name] = manager.effect
            
            if await manager.start_effect_instance(manager.effect):
                log.info(f"Effect '{effect_name}' configured and started successfully")
            else:
                log.error("Failed to start effect")
        else:
            log.error("Failed to create effect")
        return
    
    # Case 3: Start most recently configured effect
    if manager.effect is None:
        log.error("No effect configured or specified")
        return
    
    log.info("Starting most recently configured effect...")
    if await manager.start_effect_instance(manager.effect):
        log.info("Effect started successfully")
    else:
        log.error("Failed to start effect")


@service
async def wled_effect_stop(effect_name: str = None):
    """yaml
name: Stop WLED Effect
description: Stop the currently running WLED effect
fields:
  effect_name:
    description: Name of specific effect to stop (leave empty for most recently configured)
    example: "rainbow_seg1"
    selector:
      text:
"""
    global manager
    
    # Determine which effect to stop
    if effect_name:
        if effect_name not in manager.started_effects:
            log.error(f"Effect '{effect_name}' not found")
            return
        effect = manager.started_effects[effect_name]
        log.info(f"Stopping effect '{effect_name}'...")
    else:
        if manager.effect is None:
            log.warning("No effect configured")
            return
        effect = manager.effect
        log.info("Stopping most recently configured effect...")
    
    if await manager.stop_effect_instance(effect):
        log.info(f"Effect '{effect_name or 'default'}' stopped successfully")
    else:
        log.warning("Effect stop had issues")


@service
async def wled_effect_run_once(
    effect_name: str = None,
    effect: str = None,
    effect_config: dict = None,
    state_entity: str = None,
    state_attribute: str = None,
    auto_detect: bool = True,
    segment_id: int = None,
    start_led: int = None,
    stop_led: int = None,
    led_brightness: int = None
):
    """yaml
name: Run WLED Effect Once
description: Run a WLED effect once (single iteration). Can either reference a pre-configured effect or configure+run in one call.
fields:
  effect_name:
    description: Name of specific effect to run (if already configured). Leave empty to configure inline.
    example: "rainbow_seg1"
    selector:
      text:
  effect:
    description: Effect type to configure and run once (if not using pre-configured effect)
    example: "Loading"
    selector:
      select:
        options:
          - "Rainbow Wave"
          - "Segment Fade"
          - "Loading"
          - "State Sync"
  effect_config:
    description: Effect-specific configuration (key-value pairs)
    example: '{"anim_mode":"Single","smooth_transition":true}'
    selector:
      object:
  state_entity:
    description: Entity ID for state provider (for State Sync effect)
    example: "sensor.living_room_temperature"
    selector:
      entity:
  state_attribute:
    description: Attribute name for state provider (None = use entity state)
    example: "temperature"
    selector:
      text:
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
    
    # Case 1: Reference existing configured effect
    if effect_name and effect_name in manager.started_effects:
        effect_inst = manager.started_effects[effect_name]
        log.info(f"Running pre-configured effect '{effect_name}' once...")
        
        if await manager.run_once_effect_instance(effect_inst):
            log.info(f"Effect '{effect_name}' completed single run")
        else:
            log.error("Failed to run effect once")
        return
    
    # Case 2: Configure and run once inline
    if effect:
        # Generate name if not provided
        if not effect_name:
            manager.effect_counter += 1
            effect_name = f"effect_{manager.effect_counter}"
        
        log.info(f"Configuring and running effect '{effect_name}' once: {effect}")
        
        # Load effect class
        if not manager.load_effect_class(effect):
            log.error("Failed to load effect")
            return
        
        # Setup state provider if needed
        if state_entity:
            manager.setup_state_provider(state_entity, state_attribute)
        
        # Build kwargs
        effect_kwargs = {}
        if effect_config:
            effect_kwargs["effect_config"] = effect_config
        if manager.state_provider:
            effect_kwargs["state_provider"] = manager.state_provider
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
        
        # Create and run once
        if manager.create_effect(**effect_kwargs):
            manager.started_effects[effect_name] = manager.effect
            
            if await manager.run_once_effect_instance(manager.effect):
                log.info(f"Effect '{effect_name}' configured and completed single run")
            else:
                log.error("Failed to run effect once")
        else:
            log.error("Failed to create effect")
        return
    
    # Case 3: Run most recently configured effect once
    if manager.effect is None:
        log.error("No effect configured or specified")
        return
    
    log.info("Running most recently configured effect once...")
    if await manager.run_once_effect_instance(manager.effect):
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
description: Get current status of all configured effects (returns structured data)
"""
    global manager
    
    status = {
        "effects": {},
        "effect_count": len(manager.started_effects)
    }
    
    # Add info for each effect
    for effect_name, effect in manager.started_effects.items():
        status["effects"][effect_name] = {
            "effect_type": effect.get_effect_name(),
            "running": effect.running,
            "instance_id": effect.instance_id,
            "segment_id": effect.segment_id,
            "start_led": effect.start_led,
            "stop_led": effect.stop_led
        }
    
    # Log summary
    log.info(f"Active effects: {len(manager.started_effects)}")
    for effect_name, effect in manager.started_effects.items():
        log.info(f"  - '{effect_name}': {effect.get_effect_name()} (segment {effect.segment_id}, running={effect.running})")
    
    if manager.trigger_entity:
        trigger_desc = f"{manager.trigger_entity}"
        if manager.trigger_attribute:
            trigger_desc += f".{manager.trigger_attribute}"
        log.info(f"Trigger: {trigger_desc}")
    
    if manager.state_provider:
        state_desc = manager.state_provider.entity_id
        if manager.state_provider.attribute:
            state_desc += f".{manager.state_provider.attribute}"
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
