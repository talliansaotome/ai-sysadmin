#!/usr/bin/env python3
"""
Trigger Monitor - Layer 1: Lightweight continuous monitoring
Watches for critical events and triggers reviews
"""

import json
import subprocess
import time
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional, Callable
from pathlib import Path
import psutil
from collections import deque


class TriggerMonitor:
    """Lightweight monitoring that triggers reviews based on conditions"""
    
    # Critical log patterns that should trigger immediate review
    CRITICAL_PATTERNS = [
        (r'kernel:.*panic', 'critical', 'Kernel panic detected'),
        (r'Out of memory', 'critical', 'OOM condition detected'),
        (r'segfault', 'high', 'Segmentation fault detected'),
        (r'Failed to start', 'high', 'Service failed to start'),
        (r'FAILED', 'medium', 'Service failure'),
        (r'error.*authentication', 'medium', 'Authentication error'),
        (r'Connection refused', 'low', 'Connection refused'),
        (r'timeout', 'low', 'Timeout detected'),
    ]
    
    # Systemd units to always monitor
    CRITICAL_SERVICES = [
        'sshd', 'systemd-networkd', 'NetworkManager',
        'systemd-resolved', 'dbus', 'systemd-journald'
    ]
    
    def __init__(
        self,
        state_dir: Path = Path("/var/lib/ai-sysadmin"),
        thresholds: Dict[str, float] = None,
        small_model: str = "qwen3:1b",
        use_model: bool = True,
        llm_backend = None,
        backend_url: str = "http://127.0.0.1:40080/v1"
    ):
        """
        Initialize trigger monitor
        
        Args:
            state_dir: Directory for state storage
            thresholds: Metric thresholds for triggering
            small_model: Small model for log classification
            use_model: Whether to use AI model for classification
            llm_backend: LLM backend instance (will be created if not provided)
            backend_url: LLM backend URL (for llama.cpp)
        """
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        
        # Default thresholds
        self.thresholds = thresholds or {
            'cpu_percent': 90.0,
            'memory_percent': 85.0,
            'disk_percent': 90.0,
            'error_log_rate': 10.0,  # errors per minute
            'load_per_cpu': 2.0,  # load average per CPU core
        }
        
        self.small_model = small_model
        self.use_model = use_model
        
        # Setup LLM backend
        if llm_backend:
            self.llm_backend = llm_backend
        else:
            from llm_backend import LlamaCppBackend
            self.llm_backend = LlamaCppBackend(base_url=backend_url)
        
        # Event tracking
        self.event_buffer = deque(maxlen=1000)  # Rolling buffer of events
        self.last_journal_cursor = None
        self.last_trigger_times = {}  # Debounce triggers
        
        # Statistics
        self.stats = {
            'checks_performed': 0,
            'triggers_fired': 0,
            'patterns_matched': 0,
            'model_classifications': 0
        }
    
    def check_all(self) -> List[Dict[str, Any]]:
        """
        Run all checks and return triggered events
        
        Returns:
            List of trigger events
        """
        self.stats['checks_performed'] += 1
        triggers = []
        
        # Check system metrics
        metric_triggers = self._check_metrics()
        triggers.extend(metric_triggers)
        
        # Check systemd services
        service_triggers = self._check_services()
        triggers.extend(service_triggers)
        
        # Check journal logs
        log_triggers = self._check_journal_logs()
        triggers.extend(log_triggers)
        
        # Update statistics
        self.stats['triggers_fired'] += len(triggers)
        
        # Add to event buffer
        for trigger in triggers:
            self.event_buffer.append(trigger)
        
        return triggers
    
    def _check_metrics(self) -> List[Dict[str, Any]]:
        """Check system metrics against thresholds"""
        triggers = []
        
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            if cpu_percent > self.thresholds['cpu_percent']:
                if self._should_trigger('cpu_high'):
                    triggers.append({
                        'type': 'metric_threshold',
                        'trigger_type': 'cpu_high',
                        'severity': 'medium',
                        'value': cpu_percent,
                        'threshold': self.thresholds['cpu_percent'],
                        'message': f"CPU usage {cpu_percent:.1f}% exceeds threshold {self.thresholds['cpu_percent']:.1f}%",
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    })
            
            # Memory usage
            memory = psutil.virtual_memory()
            if memory.percent > self.thresholds['memory_percent']:
                if self._should_trigger('memory_high'):
                    triggers.append({
                        'type': 'metric_threshold',
                        'trigger_type': 'memory_high',
                        'severity': 'medium',
                        'value': memory.percent,
                        'threshold': self.thresholds['memory_percent'],
                        'message': f"Memory usage {memory.percent:.1f}% exceeds threshold {self.thresholds['memory_percent']:.1f}%",
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    })
            
            # Disk usage
            disk = psutil.disk_usage('/')
            if disk.percent > self.thresholds['disk_percent']:
                if self._should_trigger('disk_high'):
                    triggers.append({
                        'type': 'metric_threshold',
                        'trigger_type': 'disk_high',
                        'severity': 'high',
                        'value': disk.percent,
                        'threshold': self.thresholds['disk_percent'],
                        'message': f"Disk usage {disk.percent:.1f}% exceeds threshold {self.thresholds['disk_percent']:.1f}%",
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    })
            
            # Load average
            load_avg = psutil.getloadavg()[0]  # 1-minute load
            cpu_count = psutil.cpu_count()
            load_per_cpu = load_avg / cpu_count if cpu_count else load_avg
            
            if load_per_cpu > self.thresholds['load_per_cpu']:
                if self._should_trigger('load_high'):
                    triggers.append({
                        'type': 'metric_threshold',
                        'trigger_type': 'load_high',
                        'severity': 'medium',
                        'value': load_per_cpu,
                        'threshold': self.thresholds['load_per_cpu'],
                        'message': f"Load average per CPU {load_per_cpu:.2f} exceeds threshold {self.thresholds['load_per_cpu']:.2f}",
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    })
        
        except Exception as e:
            print(f"Error checking metrics: {e}")
        
        return triggers
    
    def _check_services(self) -> List[Dict[str, Any]]:
        """Check critical systemd services"""
        triggers = []
        
        try:
            for service in self.CRITICAL_SERVICES:
                # Check if service exists first
                exists_check = subprocess.run(
                    ["systemctl", "list-unit-files", f"{service}.service"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if f"{service}.service" not in exists_check.stdout:
                    continue  # Service not found on this system, skip it
                
                # Check service status
                result = subprocess.run(
                    ["systemctl", "is-active", service],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                status = result.stdout.strip()
                
                if status not in ['active', 'activating']:
                    if self._should_trigger(f'service_{service}_failed'):
                        triggers.append({
                            'type': 'service_failure',
                            'trigger_type': 'service_failed',
                            'severity': 'critical',
                            'service': service,
                            'status': status,
                            'message': f"Critical service {service} is {status}",
                            'timestamp': datetime.now(timezone.utc).isoformat()
                        })
        
        except Exception as e:
            print(f"Error checking services: {e}")
        
        return triggers
    
    def _check_journal_logs(self) -> List[Dict[str, Any]]:
        """Check systemd journal for critical patterns"""
        triggers = []
        
        try:
            # Get recent journal entries
            cmd = ["journalctl", "-n", "100", "--output=json", "--no-pager"]
            
            # If we have a cursor, get entries after it
            if self.last_journal_cursor:
                cmd.extend(["--after-cursor", self.last_journal_cursor])
            else:
                # First run, get last 5 minutes
                cmd.extend(["--since", "5 minutes ago"])
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                return triggers
            
            # Parse journal entries
            entries = []
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    entries.append(entry)
                except json.JSONDecodeError:
                    continue
            
            # Update cursor to last entry
            if entries:
                self.last_journal_cursor = entries[-1].get('__CURSOR')
            
            # Check each entry against patterns
            for entry in entries:
                message = entry.get('MESSAGE', '')
                
                # Pattern matching
                for pattern, severity, description in self.CRITICAL_PATTERNS:
                    if re.search(pattern, message, re.IGNORECASE):
                        self.stats['patterns_matched'] += 1
                        
                        trigger_key = f"pattern_{pattern[:20]}"
                        if self._should_trigger(trigger_key, debounce_seconds=60):
                            trigger = {
                                'type': 'log_pattern',
                                'trigger_type': 'pattern_match',
                                'severity': severity,
                                'pattern': pattern,
                                'description': description,
                                'message': message[:200],  # Truncate
                                'unit': entry.get('SYSLOG_IDENTIFIER', ''),
                                'timestamp': datetime.now(timezone.utc).isoformat()
                            }
                            
                            # Use small model to classify if enabled
                            if self.use_model:
                                classification = self._classify_log_with_model(message, entry)
                                if classification:
                                    trigger['ai_classification'] = classification
                            
                            triggers.append(trigger)
            
            # Check error rate
            error_count = sum(1 for e in entries if e.get('PRIORITY', '7') <= '3')  # err, crit, alert, emerg
            if error_count > self.thresholds['error_log_rate']:
                if self._should_trigger('error_rate_high'):
                    triggers.append({
                        'type': 'error_rate',
                        'trigger_type': 'high_error_rate',
                        'severity': 'medium',
                        'error_count': error_count,
                        'threshold': self.thresholds['error_log_rate'],
                        'message': f"High error rate: {error_count} errors in recent logs",
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    })
        
        except Exception as e:
            print(f"Error checking journal logs: {e}")
        
        return triggers
    
    def _classify_log_with_model(self, message: str, entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Use small model to classify log severity and extract information"""
        try:
            self.stats['model_classifications'] += 1
            
            # Prepare context
            unit = entry.get('SYSLOG_IDENTIFIER', 'unknown')
            priority = entry.get('PRIORITY', '6')
            
            prompt = f"""Analyze this system log entry and provide:
1. Severity (critical/high/medium/low)
2. Category (system/service/security/network/disk/other)
3. Brief summary (one line)
4. Recommended action (if any)

Log entry:
Unit: {unit}
Priority: {priority}
Message: {message[:500]}

Respond in JSON format."""

            # Use LLM backend abstraction
            response_text = self.llm_backend.generate(
                prompt=prompt,
                model=self.small_model,
                temperature=0.3,
                max_tokens=200
            )
            
            if response_text and not response_text.startswith("Error:"):
                # Try to extract JSON from response
                try:
                    # Look for JSON in the response
                    json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                    if json_match:
                        classification = json.loads(json_match.group())
                        return classification
                except:
                    pass
                
                # Fallback: parse as text
                return {
                    'raw_response': response_text[:200],
                    'model': self.small_model
                }
        
        except Exception as e:
            print(f"Error classifying log with model: {e}")
        
        return None
    
    def _should_trigger(self, trigger_key: str, debounce_seconds: int = 300) -> bool:
        """
        Check if we should trigger based on debounce timing
        
        Args:
            trigger_key: Unique identifier for this trigger type
            debounce_seconds: Minimum seconds between triggers of same type
        
        Returns:
            True if trigger should fire
        """
        now = datetime.now(timezone.utc)
        
        if trigger_key not in self.last_trigger_times:
            self.last_trigger_times[trigger_key] = now
            return True
        
        last_trigger = self.last_trigger_times[trigger_key]
        if (now - last_trigger).total_seconds() >= debounce_seconds:
            self.last_trigger_times[trigger_key] = now
            return True
        
        return False
    
    def get_event_buffer(self) -> List[Dict[str, Any]]:
        """Get recent events from buffer"""
        return list(self.event_buffer)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get monitoring statistics"""
        return {
            **self.stats,
            'buffer_size': len(self.event_buffer),
            'tracked_triggers': len(self.last_trigger_times)
        }
    
    def should_trigger_review(self, triggers: List[Dict[str, Any]]) -> bool:
        """
        Determine if triggers warrant a review model run
        
        Args:
            triggers: List of triggered events
        
        Returns:
            True if review should be triggered
        """
        if not triggers:
            return False
        
        # Critical triggers always warrant review
        critical_count = sum(1 for t in triggers if t.get('severity') == 'critical')
        if critical_count > 0:
            return True
        
        # High severity with multiple occurrences
        high_count = sum(1 for t in triggers if t.get('severity') == 'high')
        if high_count >= 2:
            return True
        
        # Many medium severity issues
        medium_count = sum(1 for t in triggers if t.get('severity') == 'medium')
        if medium_count >= 3:
            return True
        
        return False
    
    def format_triggers_for_context(self, triggers: List[Dict[str, Any]]) -> str:
        """Format triggers for context manager"""
        if not triggers:
            return "No triggers detected."
        
        lines = [f"Detected {len(triggers)} trigger(s):", ""]
        
        # Group by severity
        by_severity = {}
        for trigger in triggers:
            severity = trigger.get('severity', 'unknown')
            by_severity.setdefault(severity, []).append(trigger)
        
        for severity in ['critical', 'high', 'medium', 'low']:
            if severity in by_severity:
                lines.append(f"{severity.upper()} ({len(by_severity[severity])}):")
                for trigger in by_severity[severity][:5]:  # Limit to 5 per severity
                    lines.append(f"  - {trigger.get('message', 'No message')}")
                if len(by_severity[severity]) > 5:
                    lines.append(f"  ... and {len(by_severity[severity]) - 5} more")
                lines.append("")
        
        return "\n".join(lines)


if __name__ == "__main__":
    # Test the trigger monitor
    monitor = TriggerMonitor(use_model=False)  # Disable model for testing
    
    print("Running trigger monitor check...")
    triggers = monitor.check_all()
    
    print(f"\nFound {len(triggers)} triggers:")
    for trigger in triggers:
        print(f"  [{trigger['severity'].upper()}] {trigger['message']}")
    
    print(f"\nStatistics: {monitor.get_statistics()}")
    print(f"\nShould trigger review: {monitor.should_trigger_review(triggers)}")

