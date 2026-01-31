#!/usr/bin/env python3
"""
Context Manager - Layer 2: Manages context window with token-based limits
Integrates ChromaDB for semantic search and TimescaleDB for metrics
"""

import json
import tiktoken
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from pathlib import Path
from collections import deque

from context_db import ContextDatabase
from timeseries_db import TimeSeriesDB
from sar_integration import SarIntegration


class ContextManager:
    """Manages rolling context window with token limits and compression"""
    
    def __init__(
        self,
        context_size: int = 131072,  # Default: 128K tokens
        state_dir: Path = Path("/var/lib/ai-sysadmin"),
        chroma_host: str = "localhost",
        chroma_port: int = 8000,
        timescale_params: Dict[str, Any] = None
    ):
        """
        Initialize context manager
        
        Args:
            context_size: Maximum context size in tokens
            state_dir: Directory for state storage
            chroma_host: ChromaDB host
            chroma_port: ChromaDB port
            timescale_params: TimescaleDB connection parameters
        """
        self.context_size = context_size
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        
        # Token counter (using tiktoken for accurate counting)
        try:
            self.encoding = tiktoken.get_encoding("cl100k_base")  # GPT-4 encoding
        except:
            print("Warning: tiktoken not available, using approximate token counting")
            self.encoding = None
        
        # Initialize databases
        try:
            self.context_db = ContextDatabase(host=chroma_host, port=chroma_port)
        except Exception as e:
            print(f"Warning: Could not initialize ChromaDB: {e}")
            self.context_db = None
        
        try:
            ts_params = timescale_params or {}
            self.timeseries_db = TimeSeriesDB(**ts_params)
        except Exception as e:
            print(f"Warning: Could not initialize TimescaleDB: {e}")
            self.timeseries_db = None
        
        # SAR integration
        self.sar = SarIntegration()
        
        # Rolling context buffer
        self.context_entries = deque(maxlen=10000)  # Max entries before compression
        self.current_token_count = 0
        
        # Compression tracking
        self.compression_stats = {
            'total_compressions': 0,
            'tokens_saved': 0,
            'entries_compressed': 0
        }
        
        # Load existing context if available
        self._load_context()
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text"""
        if self.encoding:
            return len(self.encoding.encode(text))
        else:
            # Approximate: ~4 characters per token
            return len(text) // 4
    
    def add_event(self, event: Dict[str, Any], source: str = "trigger") -> bool:
        """
        Add an event to the context
        
        Args:
            event: Event dictionary
            source: Source of the event (trigger, review, meta, user)
        
        Returns:
            True if added successfully
        """
        # Create context entry
        entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'source': source,
            'event': event,
            'compressed': False
        }
        
        # Serialize and count tokens
        entry_text = json.dumps(entry)
        entry_tokens = self.count_tokens(entry_text)
        entry['token_count'] = entry_tokens
        
        # Check if we need to compress old entries
        if self.current_token_count + entry_tokens > self.context_size:
            self._compress_old_entries(target_tokens=self.context_size // 2)
        
        # Add to buffer
        self.context_entries.append(entry)
        self.current_token_count += entry_tokens
        
        # Store in appropriate database
        self._store_event_in_databases(event, source)
        
        return True
    
    def add_events(self, events: List[Dict[str, Any]], source: str = "trigger"):
        """Add multiple events"""
        for event in events:
            self.add_event(event, source)
    
    def get_context_window(self, include_sar: bool = True, 
                          include_metrics: bool = True,
                          max_tokens: Optional[int] = None) -> str:
        """
        Get current context window as formatted text
        
        Args:
            include_sar: Include SAR data
            include_metrics: Include recent metrics from TimescaleDB
            max_tokens: Maximum tokens (defaults to context_size)
        
        Returns:
            Formatted context string
        """
        if max_tokens is None:
            max_tokens = self.context_size
        
        sections = []
        token_count = 0
        
        # 1. System information header
        header = self._get_system_header()
        header_tokens = self.count_tokens(header)
        sections.append(header)
        token_count += header_tokens
        
        # 2. Recent metrics from TimescaleDB (if enabled)
        if include_metrics and self.timeseries_db:
            metrics_section = self._get_metrics_summary()
            metrics_tokens = self.count_tokens(metrics_section)
            if token_count + metrics_tokens < max_tokens:
                sections.append(metrics_section)
                token_count += metrics_tokens
        
        # 3. SAR data (if enabled)
        if include_sar and self.sar.check_sar_available():
            sar_section = self.sar.format_for_context(hours=1)
            sar_tokens = self.count_tokens(sar_section)
            if token_count + sar_tokens < max_tokens:
                sections.append(sar_section)
                token_count += sar_tokens
        
        # 4. Recent context entries (newest first, up to token limit)
        entries_section = ["Recent Events:", ""]
        remaining_tokens = max_tokens - token_count
        
        for entry in reversed(self.context_entries):
            if entry['token_count'] > remaining_tokens:
                break
            
            # Format entry
            timestamp = entry['timestamp']
            source = entry['source']
            event = entry['event']
            compressed = entry.get('compressed', False)
            
            if compressed:
                entry_text = f"[{timestamp}] [{source}] {event.get('summary', 'Compressed event')}"
            else:
                entry_text = f"[{timestamp}] [{source}] {json.dumps(event, indent=2)}"
            
            entries_section.append(entry_text)
            entries_section.append("")
            remaining_tokens -= entry['token_count']
        
        sections.append("\n".join(entries_section))
        
        # 5. Statistics footer
        footer = self._get_context_stats()
        sections.append(footer)
        
        return "\n\n".join(sections)
    
    def _get_system_header(self) -> str:
        """Get system information header"""
        import socket
        hostname = socket.gethostname()
        now = datetime.utcnow().isoformat()
        
        return f"""=== AI System Administrator Context ===
Hostname: {hostname}
Timestamp: {now}
Context Window: {self.current_token_count}/{self.context_size} tokens
Active Entries: {len(self.context_entries)}
"""
    
    def _get_metrics_summary(self) -> str:
        """Get recent metrics summary from TimescaleDB"""
        import socket
        hostname = socket.gethostname()
        
        try:
            # Get latest metrics
            latest = self.timeseries_db.query_latest_metrics(hostname)
            
            if not latest:
                return "Recent Metrics: No data available"
            
            lines = ["Recent System Metrics:"]
            for metric_name, data in latest.items():
                value = data.get('value', 0)
                unit = data.get('unit', '')
                time_ago = datetime.utcnow() - data['time']
                lines.append(f"  {metric_name}: {value:.1f}{unit} ({time_ago.seconds}s ago)")
            
            return "\n".join(lines)
        except Exception as e:
            return f"Recent Metrics: Error retrieving data - {e}"
    
    def _get_context_stats(self) -> str:
        """Get context statistics"""
        stats = [
            "=== Context Statistics ===",
            f"Total entries: {len(self.context_entries)}",
            f"Current tokens: {self.current_token_count}",
            f"Max tokens: {self.context_size}",
            f"Utilization: {(self.current_token_count / self.context_size * 100):.1f}%",
            f"Compressions performed: {self.compression_stats['total_compressions']}",
            f"Tokens saved: {self.compression_stats['tokens_saved']}"
        ]
        return "\n".join(stats)
    
    def _compress_old_entries(self, target_tokens: int):
        """
        Compress old entries to free up token space
        
        Args:
            target_tokens: Target token count after compression
        """
        print(f"Compressing old entries to reach {target_tokens} tokens...")
        
        tokens_to_free = self.current_token_count - target_tokens
        if tokens_to_free <= 0:
            return
        
        # Find old entries to compress
        entries_to_compress = []
        tokens_freed = 0
        
        for entry in self.context_entries:
            if entry.get('compressed', False):
                continue  # Already compressed
            
            # Don't compress very recent entries (last 10 minutes)
            entry_time = datetime.fromisoformat(entry['timestamp'])
            if (datetime.utcnow() - entry_time).total_seconds() < 600:
                continue
            
            entries_to_compress.append(entry)
            tokens_freed += entry['token_count']
            
            if tokens_freed >= tokens_to_free:
                break
        
        # Compress entries using rule-based summarization
        for entry in entries_to_compress:
            compressed_summary = self._create_entry_summary(entry)
            
            original_tokens = entry['token_count']
            entry['event'] = {'summary': compressed_summary}
            entry['compressed'] = True
            
            # Recalculate token count
            new_text = json.dumps(entry)
            new_tokens = self.count_tokens(new_text)
            entry['token_count'] = new_tokens
            
            tokens_saved = original_tokens - new_tokens
            self.current_token_count -= tokens_saved
            
            self.compression_stats['tokens_saved'] += tokens_saved
            self.compression_stats['entries_compressed'] += 1
        
        self.compression_stats['total_compressions'] += 1
        
        print(f"Compressed {len(entries_to_compress)} entries, freed {tokens_freed} tokens")
    
    def _create_entry_summary(self, entry: Dict[str, Any]) -> str:
        """Create a compressed summary of an entry"""
        event = entry.get('event', {})
        event_type = event.get('type', 'unknown')
        
        # Rule-based summarization based on event type
        if event_type == 'metric_threshold':
            trigger_type = event.get('trigger_type', 'unknown')
            value = event.get('value', 0)
            return f"{trigger_type}: {value:.1f}"
        
        elif event_type == 'log_pattern':
            severity = event.get('severity', 'unknown')
            description = event.get('description', 'unknown')
            return f"Log: {severity} - {description}"
        
        elif event_type == 'service_failure':
            service = event.get('service', 'unknown')
            status = event.get('status', 'unknown')
            return f"Service {service}: {status}"
        
        else:
            # Generic summary
            message = event.get('message', '')
            if message:
                return message[:100]  # Truncate
            return f"{event_type} event"
    
    def _store_event_in_databases(self, event: Dict[str, Any], source: str):
        """Store event in appropriate databases for long-term storage"""
        import socket
        hostname = socket.gethostname()
        
        event_type = event.get('type', 'unknown')
        
        # Store in TimescaleDB based on event type
        if self.timeseries_db:
            try:
                if event_type == 'metric_threshold':
                    # Store as metric
                    metric_name = event.get('trigger_type', 'unknown')
                    value = event.get('value', 0)
                    self.timeseries_db.store_metrics(hostname, {
                        metric_name: {'value': value, 'unit': ''}
                    })
                
                elif event_type == 'log_pattern':
                    # Store as log event
                    severity = event.get('severity', 'unknown')
                    message = event.get('message', '')
                    unit = event.get('unit', '')
                    self.timeseries_db.store_log_event(
                        hostname, severity, message, unit
                    )
                
                # Always store as trigger event
                self.timeseries_db.store_trigger_event(
                    hostname,
                    event_type,
                    event.get('message', ''),
                    metadata={'source': source, 'event': event}
                )
            except Exception as e:
                print(f"Error storing event in TimescaleDB: {e}")
    
    def query_similar_events(self, event_description: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Query for similar historical events using ChromaDB"""
        if not self.context_db:
            return []
        
        try:
            # Use ChromaDB to find similar past issues
            similar = self.context_db.find_similar_issues(event_description, n_results=limit)
            return similar
        except Exception as e:
            print(f"Error querying similar events: {e}")
            return []
    
    def get_metric_trends(self, metric_name: str, hours: int = 24) -> Dict[str, Any]:
        """Get metric trends from TimescaleDB"""
        if not self.timeseries_db:
            return {}
        
        import socket
        hostname = socket.gethostname()
        
        try:
            stats = self.timeseries_db.get_metric_statistics(hostname, metric_name, hours)
            return stats or {}
        except Exception as e:
            print(f"Error getting metric trends: {e}")
            return {}
    
    def _save_context(self):
        """Save current context to disk"""
        context_file = self.state_dir / "context_buffer.json"
        
        try:
            data = {
                'entries': list(self.context_entries),
                'token_count': self.current_token_count,
                'stats': self.compression_stats,
                'saved_at': datetime.utcnow().isoformat()
            }
            
            with open(context_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving context: {e}")
    
    def _load_context(self):
        """Load context from disk"""
        context_file = self.state_dir / "context_buffer.json"
        
        if not context_file.exists():
            return
        
        try:
            with open(context_file, 'r') as f:
                data = json.load(f)
            
            self.context_entries = deque(data.get('entries', []), maxlen=10000)
            self.current_token_count = data.get('token_count', 0)
            self.compression_stats = data.get('stats', self.compression_stats)
            
            print(f"Loaded context: {len(self.context_entries)} entries, {self.current_token_count} tokens")
        except Exception as e:
            print(f"Error loading context: {e}")
    
    def clear_context(self):
        """Clear the context buffer"""
        self.context_entries.clear()
        self.current_token_count = 0
        self._save_context()
    
    def validate_context_size(self, model_context_size: int) -> bool:
        """
        Validate that configured context size is appropriate for the model
        
        Args:
            model_context_size: Model's maximum context size
        
        Returns:
            True if valid
        """
        if self.context_size > model_context_size:
            print(f"Warning: Configured context size ({self.context_size}) exceeds model capacity ({model_context_size})")
            print(f"Reducing context size to {model_context_size}")
            self.context_size = model_context_size
            return False
        
        # Reserve at least 25% for response generation
        recommended_max = int(model_context_size * 0.75)
        if self.context_size > recommended_max:
            print(f"Warning: Context size ({self.context_size}) leaves little room for response")
            print(f"Recommended maximum: {recommended_max} (75% of model capacity)")
            return False
        
        return True


if __name__ == "__main__":
    # Test context manager
    manager = ContextManager(context_size=8192)  # Small size for testing
    
    # Add some test events
    test_events = [
        {
            'type': 'metric_threshold',
            'trigger_type': 'cpu_high',
            'severity': 'medium',
            'value': 92.5,
            'message': 'CPU usage exceeds threshold'
        },
        {
            'type': 'log_pattern',
            'severity': 'high',
            'description': 'Service failed to start',
            'message': 'Failed to start nginx.service'
        }
    ]
    
    for event in test_events:
        manager.add_event(event, source="test")
    
    # Get context window
    context = manager.get_context_window()
    print(context)
    print(f"\nToken count: {manager.count_tokens(context)}")

