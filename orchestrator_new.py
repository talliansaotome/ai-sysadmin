#!/usr/bin/env python3
"""
New Orchestrator - Coordinates all four layers of the AI system

Layer 1: Trigger Monitor - Detects events requiring attention
Layer 2: Context Manager - Manages rolling context window
Layer 3: Review Model - Continuous analysis with small model
Layer 4: Meta Model - On-demand deep analysis and user interaction
"""

import json
import time
import signal
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

from trigger_monitor import TriggerMonitor
from context_manager import ContextManager
from review_model import ReviewModel
from meta_model import MetaModel
from executor import SafeExecutor
from notifier import GotifyNotifier
from context_db import ContextDatabase
from timeseries_db import TimeSeriesDB
from sar_integration import SarIntegration


class NewOrchestrator:
    """
    Main orchestrator for the four-layer AI system architecture
    
    Architecture:
    - Layer 1 (Trigger Monitor): Runs frequently, detects critical events
    - Layer 2 (Context Manager): Maintains rolling context window
    - Layer 3 (Review Model): Runs periodically (30-60s), analyzes trends
    - Layer 4 (Meta Model): On-demand only, for complex issues or user chat
    """
    
    def __init__(
        self,
        trigger_interval: int = 30,  # Layer 1: Every 30 seconds
        review_interval: int = 60,   # Layer 3: Every 60 seconds
        autonomy_level: str = "suggest",
        state_dir: Path = Path("/var/lib/ai-sysadmin"),
        config_file: Path = Path("/etc/ai-sysadmin/config.json"),
        context_size: int = 131072,  # 128K tokens
        trigger_model: str = "qwen3:1b",
        review_model: str = "qwen3:4b",
        meta_model: str = "qwen3:14b",
        ollama_host: str = "http://localhost:11434",
        use_trigger_model: bool = True
    ):
        """
        Initialize the orchestrator
        
        Args:
            trigger_interval: Seconds between trigger checks
            review_interval: Seconds between review runs
            autonomy_level: observe/suggest/auto-safe/auto-full
            state_dir: State directory
            config_file: Configuration file path
            context_size: Maximum context size in tokens
            trigger_model: Small model for log classification
            review_model: Model for continuous review
            meta_model: Large model for complex analysis
            ollama_host: Ollama API endpoint
            use_trigger_model: Whether to use AI for trigger classification
        """
        self.trigger_interval = trigger_interval
        self.review_interval = review_interval
        self.autonomy_level = autonomy_level
        self.state_dir = state_dir
        self.config_file = config_file
        self.running = False
        
        # Set log file early
        self.log_file = self.state_dir / "orchestrator.log"
        
        # Load config if exists
        self._load_config()
        
        # Initialize databases
        self._log("Initializing databases...")
        try:
            self.context_db = ContextDatabase()
        except Exception as e:
            self._log(f"Warning: Could not connect to ChromaDB: {e}")
            self.context_db = None
        
        try:
            self.timeseries_db = TimeSeriesDB()
        except Exception as e:
            self._log(f"Warning: Could not connect to TimescaleDB: {e}")
            self.timeseries_db = None
        
        # Initialize Layer 2: Context Manager
        self._log("Initializing context manager...")
        self.context_manager = ContextManager(
            context_size=context_size,
            state_dir=state_dir
        )
        
        # Initialize Layer 1: Trigger Monitor
        self._log("Initializing trigger monitor...")
        self.trigger_monitor = TriggerMonitor(
            state_dir=state_dir,
            small_model=trigger_model,
            use_model=use_trigger_model,
            ollama_host=ollama_host
        )
        
        # Initialize executor
        self._log("Initializing executor...")
        self.executor = SafeExecutor(
            state_dir=state_dir,
            autonomy_level=autonomy_level
        )
        
        # Initialize Layer 3: Review Model
        self._log("Initializing review model...")
        self.review_model = ReviewModel(
            model=review_model,
            ollama_host=ollama_host,
            context_manager=self.context_manager,
            executor=self.executor,
            state_dir=state_dir,
            autonomy_level=autonomy_level
        )
        
        # Layer 4: Meta Model (initialized on-demand)
        self.meta_model_config = {
            'model': meta_model,
            'ollama_host': ollama_host,
            'state_dir': state_dir,
            'context_db': self.context_db
        }
        self.meta_model = None  # Created on-demand
        
        # Notifications
        self.notifier = GotifyNotifier()
        
        # SAR integration
        self.sar = SarIntegration()
        
        # Tracking
        self.last_trigger_check = 0
        self.last_review_check = 0
        self.cycle_count = 0
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        self._log("Orchestrator initialized successfully")
    
    def _load_config(self):
        """Load configuration from file"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    self._log(f"Loaded config from {self.config_file}")
                    # Override with config file values if present
                    self.trigger_interval = config.get("trigger_interval", self.trigger_interval)
                    self.review_interval = config.get("review_interval", self.review_interval)
            except Exception as e:
                self._log(f"Failed to load config: {e}")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self._log(f"Received signal {signum}, shutting down gracefully...")
        self.running = False
    
    def _log(self, message: str):
        """Log a message"""
        timestamp = datetime.now().isoformat()
        log_line = f"[{timestamp}] {message}"
        print(log_line)
        
        try:
            with open(self.log_file, 'a') as f:
                f.write(log_line + '\n')
        except:
            pass  # Fail silently if can't write to log
    
    def run_cycle(self) -> Dict[str, Any]:
        """
        Run one orchestration cycle
        
        Returns:
            Cycle results
        """
        self.cycle_count += 1
        now = time.time()
        
        cycle_result = {
            'cycle': self.cycle_count,
            'timestamp': datetime.utcnow().isoformat(),
            'layer1_triggered': False,
            'layer3_ran': False,
            'layer4_escalated': False
        }
        
        # Layer 1: Trigger Monitor (runs frequently)
        if (now - self.last_trigger_check) >= self.trigger_interval:
            self._log(f"[Cycle {self.cycle_count}] Running Layer 1: Trigger Monitor")
            triggers = self._run_layer1()
            cycle_result['layer1_triggers'] = len(triggers)
            cycle_result['layer1_triggered'] = len(triggers) > 0
            self.last_trigger_check = now
            
            # Store metrics in TimescaleDB
            if self.timeseries_db:
                self._store_current_metrics()
        
        # Layer 3: Review Model (runs periodically)
        if (now - self.last_review_check) >= self.review_interval:
            self._log(f"[Cycle {self.cycle_count}] Running Layer 3: Review Model")
            review_result = self._run_layer3()
            cycle_result['layer3_ran'] = True
            cycle_result['layer3_result'] = review_result
            self.last_review_check = now
            
            # Check if we should escalate to Layer 4
            if review_result.get('escalation_recommended', False):
                self._log(f"[Cycle {self.cycle_count}] Escalating to Layer 4: Meta Model")
                meta_result = self._run_layer4(
                    escalation_reason=review_result.get('escalation_reason', 'Complex issue detected')
                )
                cycle_result['layer4_escalated'] = True
                cycle_result['layer4_result'] = meta_result
        
        return cycle_result
    
    def _run_layer1(self) -> list:
        """
        Run Layer 1: Trigger Monitor
        
        Returns:
            List of triggered events
        """
        # Check all triggers
        triggers = self.trigger_monitor.check_all()
        
        if triggers:
            self._log(f"  Layer 1: Detected {len(triggers)} trigger(s)")
            
            # Add triggers to context
            self.context_manager.add_events(triggers, source='trigger')
            
            # Log severe triggers
            for trigger in triggers:
                severity = trigger.get('severity', 'unknown')
                if severity in ['critical', 'high']:
                    self._log(f"    [{severity.upper()}] {trigger.get('message', 'No message')}")
                    
                    # Send notification for critical triggers
                    if severity == 'critical' and self.notifier:
                        self.notifier.notify_critical_issue(
                            trigger.get('message', 'Critical trigger'),
                            f"Type: {trigger.get('trigger_type', 'unknown')}"
                        )
        
        return triggers
    
    def _run_layer3(self) -> Dict[str, Any]:
        """
        Run Layer 3: Review Model
        
        Returns:
            Review results
        """
        try:
            # Determine what triggered this review
            triggered_by = "periodic"
            if self.trigger_monitor.should_trigger_review(
                self.trigger_monitor.get_event_buffer()[-10:]
            ):
                triggered_by = "triggers"
            
            # Run review
            result = self.review_model.review_system_state(triggered_by=triggered_by)
            
            # Log key findings
            status = result.get('status', 'unknown')
            issues = result.get('issues', [])
            
            self._log(f"  Layer 3: Status={status}, Issues={len(issues)}")
            
            if issues:
                for issue in issues[:3]:  # Log first 3
                    severity = issue.get('severity', 'unknown')
                    description = issue.get('description', 'No description')
                    self._log(f"    [{severity.upper()}] {description}")
            
            return result
        
        except Exception as e:
            self._log(f"  Layer 3: Error - {e}")
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def _run_layer4(self, escalation_reason: str) -> Dict[str, Any]:
        """
        Run Layer 4: Meta Model (on-demand)
        
        Args:
            escalation_reason: Why we're escalating
        
        Returns:
            Meta model results
        """
        try:
            # Initialize meta model if needed
            if self.meta_model is None:
                self._log("  Layer 4: Initializing meta model...")
                self.meta_model = MetaModel(**self.meta_model_config)
            
            # Get full context for meta model
            context_text = self.context_manager.get_context_window(
                include_sar=True,
                include_metrics=True
            )
            
            # Create escalation prompt
            prompt = f"""You are the senior AI system administrator. The review model has escalated this issue for your analysis.

ESCALATION REASON: {escalation_reason}

CURRENT SYSTEM CONTEXT:
{context_text}

Please provide:
1. Deep analysis of the situation
2. Root cause assessment
3. Recommended actions with risk levels
4. Long-term preventive measures

Respond in JSON format."""

            # Query meta model
            self._log("  Layer 4: Querying meta model...")
            response = self.meta_model._query_ollama(prompt, model=self.meta_model.model)
            
            if response:
                self._log(f"  Layer 4: Received response ({len(response)} chars)")
                
                # Add to context
                self.context_manager.add_event({
                    'type': 'meta_analysis',
                    'escalation_reason': escalation_reason,
                    'response_length': len(response),
                    'summary': response[:200]  # First 200 chars
                }, source='meta')
                
                # Notify about escalation
                if self.notifier:
                    self.notifier.send(
                        title="🧠 Meta Model Analysis",
                        message=f"Escalation: {escalation_reason}\n\nAnalysis complete. Check logs for details.",
                        priority=self.notifier.PRIORITY_HIGH
                    )
                
                return {
                    'success': True,
                    'response': response,
                    'escalation_reason': escalation_reason
                }
            else:
                self._log("  Layer 4: No response from meta model")
                return {
                    'success': False,
                    'error': 'No response from meta model'
                }
        
        except Exception as e:
            self._log(f"  Layer 4: Error - {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _store_current_metrics(self):
        """Store current system metrics in TimescaleDB"""
        if not self.timeseries_db:
            return
        
        try:
            import socket
            import psutil
            
            hostname = f"{socket.gethostname()}.coven.systems"
            
            metrics = {
                'cpu_percent': psutil.cpu_percent(interval=0.1),
                'memory_percent': psutil.virtual_memory().percent,
                'disk_percent': psutil.disk_usage('/').percent,
                'load_avg_1min': psutil.getloadavg()[0],
                'load_avg_5min': psutil.getloadavg()[1],
                'load_avg_15min': psutil.getloadavg()[2]
            }
            
            self.timeseries_db.store_metrics(hostname, metrics)
        
        except Exception as e:
            self._log(f"Warning: Could not store metrics: {e}")
    
    def run_continuous(self):
        """Run continuous orchestration loop"""
        self._log("="*70)
        self._log("Starting AI Sysadmin Orchestrator (4-Layer Architecture)")
        self._log(f"Autonomy level: {self.autonomy_level}")
        self._log(f"Layer 1 interval: {self.trigger_interval}s")
        self._log(f"Layer 3 interval: {self.review_interval}s")
        self._log(f"State directory: {self.state_dir}")
        self._log("="*70)
        
        self.running = True
        
        # Validate context size
        if self.context_manager:
            self.context_manager.validate_context_size(131072)  # Assuming 128K model
        
        while self.running:
            try:
                cycle_result = self.run_cycle()
                
                # Brief sleep between cycles (Layer 1 interval determines actual timing)
                if self.running:
                    time.sleep(1)
            
            except KeyboardInterrupt:
                break
            except Exception as e:
                self._log(f"ERROR in orchestration cycle: {e}")
                import traceback
                self._log(traceback.format_exc())
                
                # Wait before retrying after error
                if self.running:
                    time.sleep(60)
        
        self._log("Orchestrator stopped")
    
    def run_once(self):
        """Run one complete check cycle (for manual/testing)"""
        self._log("Running single orchestration cycle...")
        result = self.run_cycle()
        self._log(f"Cycle complete: {json.dumps(result, indent=2)}")
        return result


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="AI Sysadmin Orchestrator (4-Layer Architecture)")
    parser.add_argument(
        "--mode",
        choices=["once", "continuous"],
        default="continuous",
        help="Run mode"
    )
    parser.add_argument(
        "--autonomy",
        choices=["observe", "suggest", "auto-safe", "auto-full"],
        default="suggest",
        help="Autonomy level"
    )
    parser.add_argument(
        "--trigger-interval",
        type=int,
        default=30,
        help="Trigger check interval in seconds"
    )
    parser.add_argument(
        "--review-interval",
        type=int,
        default=60,
        help="Review model interval in seconds"
    )
    parser.add_argument(
        "--context-size",
        type=int,
        default=131072,
        help="Context window size in tokens"
    )
    
    args = parser.parse_args()
    
    orchestrator = NewOrchestrator(
        trigger_interval=args.trigger_interval,
        review_interval=args.review_interval,
        autonomy_level=args.autonomy,
        context_size=args.context_size
    )
    
    if args.mode == "once":
        result = orchestrator.run_once()
        print(json.dumps(result, indent=2))
    else:
        orchestrator.run_continuous()


if __name__ == "__main__":
    main()

