"""
Standalone CLI version of WLED Effects Service
Allows running and controlling multiple WLED effects from command line
"""

import asyncio
import aiohttp
import sys
import argparse
from pathlib import Path

# Add modules directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "modules"))

from wled.wled_effect_base import WLED_IP, WLED_URL


# ==============================================================================
# STANDALONE COMPONENTS (adapted from wledtaskservice.py)
# ==============================================================================

class StandaloneLogger:
    """Simple console logger"""
    
    def debug(self, msg):
        print(f"[DEBUG] {msg}")
    
    def info(self, msg):
        print(f"[INFO] {msg}")
    
    def warning(self, msg):
        print(f"[WARN] {msg}")
    
    def error(self, msg):
        print(f"[ERROR] {msg}")


class StandaloneStateProvider:
    """Mock state provider for standalone testing"""
    
    def __init__(self, value=50.0):
        self.value = value
    
    async def get_state(self):
        """Return mock state value"""
        return self.value


class StandaloneTaskManager:
    """Task manager for standalone operation"""
    
    def __init__(self):
        self._tasks = {}
        self._spawned_tasks = []
    
    async def sleep(self, duration):
        await asyncio.sleep(duration)
    
    async def create_task(self, name, coro):
        """Create and track a task"""
        if name in self._tasks:
            self._tasks[name].cancel()
        
        task = asyncio.create_task(coro)
        self._tasks[name] = task
        self._spawned_tasks.append(name)
        return task
    
    def kill_task(self, name):
        """Kill a specific task"""
        if name in self._tasks:
            self._tasks[name].cancel()
            if name in self._spawned_tasks:
                self._spawned_tasks.remove(name)
    
    def kill_all_tasks(self):
        """Kill all spawned tasks"""
        killed_count = 0
        for task_name in list(self._spawned_tasks):
            if task_name in self._tasks:
                self._tasks[task_name].cancel()
                killed_count += 1
        self._spawned_tasks.clear()
        return killed_count


class StandaloneHTTPClient:
    """HTTP client for WLED API"""
    
    def __init__(self):
        self.session = None
    
    async def get_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def get_state(self):
        """Get current WLED device state"""
        try:
            session = await self.get_session()
            async with session.get(f"http://{WLED_IP}/json/state", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
        except Exception as e:
            print(f"Error getting device state: {e}")
            return None
    
    async def get_info(self):
        """Get WLED device information"""
        try:
            session = await self.get_session()
            async with session.get(f"http://{WLED_IP}/json/info", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
        except Exception as e:
            print(f"Error getting device info: {e}")
            return None
    
    async def send_command(self, payload, retry_count=2):
        """Send command to WLED"""
        session = await self.get_session()
        
        for attempt in range(retry_count + 1):
            try:
                async with session.post(WLED_URL, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        return True
                    return False
            except asyncio.TimeoutError:
                if attempt < retry_count:
                    await asyncio.sleep(0.1)
                else:
                    print(f"Timeout sending WLED command after {retry_count + 1} attempts")
                    return False
            except Exception as e:
                if attempt < retry_count:
                    await asyncio.sleep(0.1)
                else:
                    print(f"Error sending WLED command: {e}")
                    return False
        return False
    
    async def cleanup(self):
        """Cleanup HTTP session"""
        if self.session:
            await self.session.close()
            self.session = None


class WLEDEffectManagerStandalone:
    """Standalone version of effect manager"""
    
    def __init__(self):
        self.effects = {}  # {effect_name: effect_instance}
        self.effect_counter = 0
        
        # Shared resources
        self.task_mgr = StandaloneTaskManager()
        self.http_client = StandaloneHTTPClient()
        self.logger = StandaloneLogger()
    
    def load_effect_class(self, effect_name):
        """Load effect class by name"""
        effect_map = {
            "Rainbow Wave": ("wled.effects.rainbow_wave", "RainbowWaveEffect"),
            "Segment Fade": ("wled.effects.segment_fade", "SegmentFadeEffect"),
            "Loading": ("wled.effects.loading", "LoadingEffect"),
            "State Sync": ("wled.effects.state_sync", "StateSyncEffect"),
        }
        
        if effect_name not in effect_map:
            self.logger.error(f"Unknown effect: {effect_name}")
            return None
        
        module_path, class_name = effect_map[effect_name]
        
        try:
            # Import dynamically
            parts = module_path.split('.')
            module = __import__(module_path, fromlist=[class_name])
            effect_class = getattr(module, class_name)
            return effect_class
        except Exception as e:
            self.logger.error(f"Failed to load effect {effect_name}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def create_effect(self, effect_type, effect_name=None, state_provider=None, effect_config=None, **kwargs):
        """Create and configure an effect instance"""
        if not effect_name:
            self.effect_counter += 1
            effect_name = f"effect_{self.effect_counter}"
        
        effect_class = self.load_effect_class(effect_type)
        if not effect_class:
            return None
        
        try:
            # Base args
            base_args = [self.task_mgr, self.logger, self.http_client]
            
            # Check if effect requires state provider
            if getattr(effect_class, 'REQUIRES_STATE_PROVIDER', False):
                if state_provider:
                    base_args.append(state_provider)
                else:
                    self.logger.error(f"Effect {effect_type} requires a state_provider")
                    return None
            
            # Create instance
            effect = effect_class(*base_args, **kwargs)
            
            # Apply effect_config if provided
            if effect_config:
                effect.config = effect_config
            
            self.effects[effect_name] = effect
            
            self.logger.info(f"Created effect '{effect_name}': {effect.get_effect_name()} (segment={effect.segment_id})")
            return effect_name
        except Exception as e:
            self.logger.error(f"Failed to create effect: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def start_effect(self, effect_name):
        """Start a specific effect"""
        if effect_name not in self.effects:
            self.logger.error(f"Effect '{effect_name}' not found")
            return False
        
        effect = self.effects[effect_name]
        try:
            await effect.start()
            self.logger.info(f"Started effect '{effect_name}'")
            return True
        except Exception as e:
            self.logger.error(f"Error starting effect '{effect_name}': {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def stop_effect(self, effect_name):
        """Stop a specific effect"""
        if effect_name not in self.effects:
            self.logger.error(f"Effect '{effect_name}' not found")
            return False
        
        effect = self.effects[effect_name]
        try:
            await effect.stop()
            self.logger.info(f"Stopped effect '{effect_name}'")
            return True
        except Exception as e:
            self.logger.error(f"Error stopping effect '{effect_name}': {e}")
            return False
    
    async def run_once_effect(self, effect_name):
        """Run a specific effect once"""
        if effect_name not in self.effects:
            self.logger.error(f"Effect '{effect_name}' not found")
            return False
        
        effect = self.effects[effect_name]
        try:
            await effect.run_once()
            self.logger.info(f"Ran effect '{effect_name}' once")
            return True
        except Exception as e:
            self.logger.error(f"Error running effect '{effect_name}' once: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def stop_all(self):
        """Stop all effects"""
        stopped_count = 0
        for effect_name, effect in list(self.effects.items()):
            try:
                await effect.stop()
                stopped_count += 1
            except Exception as e:
                self.logger.error(f"Error stopping effect '{effect_name}': {e}")
        
        killed_count = self.task_mgr.kill_all_tasks()
        await self.http_client.cleanup()
        
        self.logger.info(f"Stopped {stopped_count} effects, killed {killed_count} tasks")
        return True
    
    def status(self):
        """Show status of all effects"""
        print(f"\n{'='*60}")
        print(f"WLED Effects Status - {len(self.effects)} configured effect(s)")
        print(f"{'='*60}")
        
        if not self.effects:
            print("No effects configured")
            return
        
        for effect_name, effect in self.effects.items():
            print(f"\n[{effect_name}]")
            print(f"  Type: {effect.get_effect_name()}")
            print(f"  Running: {effect.running}")
            print(f"  Instance ID: {effect.instance_id}")
            print(f"  Segment: {effect.segment_id}")
            print(f"  LED Range: {effect.start_led}-{effect.stop_led}")
            print(f"  Brightness: {effect.led_brightness}")


# ==============================================================================
# CLI INTERFACE
# ==============================================================================

async def main():
    parser = argparse.ArgumentParser(
        description="WLED Effects Service - Standalone CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Quick run - configure and start in one command
  python wledtaskservice_standalone.py run --effect "Rainbow Wave" --segment 1
  
  # Run for 30 seconds then stop
  python wledtaskservice_standalone.py run --effect "Segment Fade" --segment 2 --duration 30
  
  # Run effect once (non-continuous)
  python wledtaskservice_standalone.py run --effect "Loading" --segment 0 --once
  
  # Configure with auto-start
  python wledtaskservice_standalone.py configure --effect "Rainbow Wave" --segment 1 --start
  
  # Configure and run once
  python wledtaskservice_standalone.py configure --effect "Segment Fade" --segment 2 --run-once
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Configure command
    configure_parser = subparsers.add_parser('configure', help='Configure a new effect')
    configure_parser.add_argument('--effect', required=True, 
                                   choices=['Rainbow Wave', 'Segment Fade', 'Loading', 'State Sync'],
                                   help='Effect type')
    configure_parser.add_argument('--name', help='Effect name (auto-generated if not provided)')
    configure_parser.add_argument('--segment', type=int, help='Segment ID')
    configure_parser.add_argument('--start-led', type=int, help='Start LED index')
    configure_parser.add_argument('--stop-led', type=int, help='Stop LED index')
    configure_parser.add_argument('--brightness', type=int, help='LED brightness (0-255)')
    configure_parser.add_argument('--no-auto-detect', action='store_true', 
                                   help='Disable auto-detection')
    configure_parser.add_argument('--state-value', type=float, default=50.0,
                                   help='State value for State Sync effect (0-100, default: 50)')
    configure_parser.add_argument('--effect-config', type=str,
                                   help='Effect-specific configuration as JSON string (e.g. \'{"anim_mode":"Single"}\' )')
    configure_parser.add_argument('--start', action='store_true',
                                   help='Start the effect immediately after configuring')
    configure_parser.add_argument('--run-once', action='store_true',
                                   help='Run the effect once immediately after configuring')
    
    # Start command
    start_parser = subparsers.add_parser('start', help='Start an effect')
    start_parser.add_argument('--name', required=True, help='Effect name to start')
    
    # Stop command
    stop_parser = subparsers.add_parser('stop', help='Stop an effect')
    stop_parser.add_argument('--name', required=True, help='Effect name to stop')
    
    # Run once command
    runonce_parser = subparsers.add_parser('run-once', help='Run an effect once')
    runonce_parser.add_argument('--name', required=True, help='Effect name to run')
    
    # Run command (configure + start in one)
    run_parser = subparsers.add_parser('run', help='Configure and start an effect in one command')
    run_parser.add_argument('--effect', required=True, 
                            choices=['Rainbow Wave', 'Segment Fade', 'Loading', 'State Sync'],
                            help='Effect type')
    run_parser.add_argument('--name', help='Effect name (auto-generated if not provided)')
    run_parser.add_argument('--segment', type=int, help='Segment ID')
    run_parser.add_argument('--start-led', type=int, help='Start LED index')
    run_parser.add_argument('--stop-led', type=int, help='Stop LED index')
    run_parser.add_argument('--brightness', type=int, help='LED brightness (0-255)')
    run_parser.add_argument('--no-auto-detect', action='store_true', 
                            help='Disable auto-detection')
    run_parser.add_argument('--state-value', type=float, default=50.0,
                            help='State value for State Sync effect (0-100, default: 50)')
    run_parser.add_argument('--effect-config', type=str,
                            help='Effect-specific configuration as JSON string')
    run_parser.add_argument('--duration', type=float, 
                            help='Run for specified seconds then exit (for continuous effects)')
    run_parser.add_argument('--once', action='store_true',
                            help='Run once instead of continuously')
    
    # Stop all command
    subparsers.add_parser('stop-all', help='Stop all effects')
    
    # Status command
    subparsers.add_parser('status', help='Show status of all effects')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Create manager
    manager = WLEDEffectManagerStandalone()
    
    try:
        if args.command == 'configure':
            # Build kwargs
            kwargs = {
                'auto_detect': not args.no_auto_detect
            }
            if args.segment is not None:
                kwargs['segment_id'] = args.segment
            if args.start_led is not None:
                kwargs['start_led'] = args.start_led
            if args.stop_led is not None:
                kwargs['stop_led'] = args.stop_led
            if args.brightness is not None:
                kwargs['led_brightness'] = args.brightness
            
            # State provider for State Sync
            state_provider = None
            if args.effect == 'State Sync':
                state_provider = StandaloneStateProvider(args.state_value)
            
            # Parse effect config if provided
            effect_config = None
            if args.effect_config:
                try:
                    import json
                    effect_config = json.loads(args.effect_config)
                except Exception as e:
                    print(f"Error parsing effect_config: {e}")
                    sys.exit(1)
            
            effect_name = manager.create_effect(
                args.effect, 
                args.name,
                state_provider=state_provider,
                effect_config=effect_config,
                **kwargs
            )
            
            if effect_name:
                print(f"\n✓ Effect '{effect_name}' configured successfully")
                
                # Auto-start or run-once if requested
                if args.start:
                    await manager.start_effect(effect_name)
                    print(f"✓ Effect '{effect_name}' started")
                    print("\nEffect running... Press Ctrl+C to stop")
                    try:
                        # Keep running until interrupted
                        while True:
                            await asyncio.sleep(1)
                    except KeyboardInterrupt:
                        print("\n\nStopping effect...")
                        await manager.stop_effect(effect_name)
                elif args.run_once:
                    await manager.run_once_effect(effect_name)
                    print(f"✓ Effect '{effect_name}' completed")
            else:
                print("\n✗ Failed to configure effect")
                sys.exit(1)
        
        elif args.command == 'run':
            # Build kwargs
            kwargs = {
                'auto_detect': not args.no_auto_detect
            }
            if args.segment is not None:
                kwargs['segment_id'] = args.segment
            if args.start_led is not None:
                kwargs['start_led'] = args.start_led
            if args.stop_led is not None:
                kwargs['stop_led'] = args.stop_led
            if args.brightness is not None:
                kwargs['led_brightness'] = args.brightness
            
            # State provider for State Sync
            state_provider = None
            if args.effect == 'State Sync':
                state_provider = StandaloneStateProvider(args.state_value)
            
            # Parse effect config if provided
            effect_config = None
            if args.effect_config:
                try:
                    import json
                    effect_config = json.loads(args.effect_config)
                except Exception as e:
                    print(f"Error parsing effect_config: {e}")
                    sys.exit(1)
            
            effect_name = manager.create_effect(
                args.effect, 
                args.name,
                state_provider=state_provider,
                effect_config=effect_config,
                **kwargs
            )
            
            if not effect_name:
                print("\n✗ Failed to configure effect")
                sys.exit(1)
            
            print(f"\n✓ Effect '{effect_name}' configured")
            
            # Run once or continuously
            if args.once:
                await manager.run_once_effect(effect_name)
                print(f"✓ Effect '{effect_name}' completed")
            else:
                await manager.start_effect(effect_name)
                print(f"✓ Effect '{effect_name}' started")
                
                if args.duration:
                    print(f"\nRunning for {args.duration} seconds...")
                    await asyncio.sleep(args.duration)
                    print("\nStopping effect...")
                    await manager.stop_effect(effect_name)
                    print("✓ Complete")
                else:
                    print("\nEffect running... Press Ctrl+C to stop")
                    try:
                        while True:
                            await asyncio.sleep(1)
                    except KeyboardInterrupt:
                        print("\n\nStopping effect...")
                        await manager.stop_effect(effect_name)
        
        elif args.command == 'start':
            # Load effect from persistent state if needed
            # For now, just show error if not configured
            print(f"Starting effect '{args.name}'...")
            print("\nNote: Effect must be configured first in the same session")
            print("Future enhancement: Save/load effect configurations")
        
        elif args.command == 'stop':
            await manager.stop_effect(args.name)
        
        elif args.command == 'run-once':
            await manager.run_once_effect(args.name)
        
        elif args.command == 'stop-all':
            await manager.stop_all()
        
        elif args.command == 'status':
            manager.status()
    
    finally:
        # Cleanup
        await manager.http_client.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)
