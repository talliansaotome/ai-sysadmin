"""
MCP Server - Model Context Protocol server for AI Sysadmin

Provides context providers and tools for other AI models to interact
with the system administration capabilities.
"""

import json
import os
import socket
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from pathlib import Path

# MCP imports (will need to be installed)
try:
    from mcp.server import Server
    from mcp.types import (
        Resource, Tool, TextContent, ImageContent,
        EmbeddedResource, LoggingLevel
    )
    MCP_AVAILABLE = True
except ImportError:
    print("Warning: MCP library not available. Install with: pip install mcp")
    MCP_AVAILABLE = False

from context_manager import ContextManager
from timeseries_db import TimeSeriesDB
from trigger_monitor import TriggerMonitor
from review_model import ReviewModel
from meta_model import MetaModel
from executor import SafeExecutor


class AISysadminMCPServer:
    """MCP server for AI Sysadmin system"""
    
    def __init__(
        self,
        autonomy_level: str = "suggest",
        state_dir: Path = Path("/var/lib/ai-sysadmin"),
        host: str = "0.0.0.0",
        port: int = 40085
    ):
        """
        Initialize MCP server
        
        Args:
            autonomy_level: Autonomy level (observe, suggest, auto-safe, auto-full)
            state_dir: State directory
            host: Host to bind to
            port: Port to listen on
        """
        if not MCP_AVAILABLE:
            raise RuntimeError("MCP library not available")
        
        self.autonomy_level = autonomy_level
        self.state_dir = state_dir
        self.host = host
        self.port = port
        
        # Initialize components
        self.context_manager = None
        self.timeseries_db = None
        self.trigger_monitor = None
        self.executor = None
        
        try:
            self.context_manager = ContextManager()
            self.timeseries_db = TimeSeriesDB()
            self.trigger_monitor = TriggerMonitor(use_model=False)
            self.executor = SafeExecutor(autonomy_level=autonomy_level)
        except Exception as e:
            print(f"Warning: Could not initialize all components: {e}")
        
        # Create MCP server
        self.server = Server("ai-sysadmin", host=self.host, port=self.port)
        
        # Register resources (context providers)
        self._register_resources()
        
        # Register tools
        self._register_tools()
    
    def _register_resources(self):
        """Register MCP resources (context providers)"""
        
        @self.server.list_resources()
        async def list_resources() -> List[Resource]:
            """List available resources"""
            return [
                Resource(
                    uri="system://status",
                    name="System Status",
                    mimeType="application/json",
                    description="Current system status including metrics and health"
                ),
                Resource(
                    uri="system://context",
                    name="System Context",
                    mimeType="text/plain",
                    description="Current AI context window with recent events"
                ),
                Resource(
                    uri="system://triggers",
                    name="Trigger Events",
                    mimeType="application/json",
                    description="Recent trigger events from monitoring"
                ),
                Resource(
                    uri="system://metrics/history",
                    name="Metrics History",
                    mimeType="application/json",
                    description="Historical system metrics from TimescaleDB"
                ),
                Resource(
                    uri="system://services",
                    name="Service Status",
                    mimeType="application/json",
                    description="Status of all systemd services"
                )
            ]
        
        @self.server.read_resource()
        async def read_resource(uri: str) -> str:
            """Read a specific resource"""
            if uri == "system://status":
                return self._get_system_status()
            
            elif uri == "system://context":
                return self._get_system_context()
            
            elif uri == "system://triggers":
                return self._get_triggers()
            
            elif uri == "system://metrics/history":
                return self._get_metrics_history()
            
            elif uri == "system://services":
                return self._get_services()
            
            else:
                return json.dumps({"error": "Unknown resource"})
    
    def _register_tools(self):
        """Register MCP tools"""
        
        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            """List available tools"""
            tools = [
                Tool(
                    name="query_system_status",
                    description="Query current system status and metrics",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                ),
                Tool(
                    name="query_logs",
                    description="Query system logs for specific patterns",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "pattern": {
                                "type": "string",
                                "description": "Pattern to search for in logs"
                            },
                            "hours": {
                                "type": "integer",
                                "description": "Hours of history to search",
                                "default": 1
                            }
                        },
                        "required": ["pattern"]
                    }
                ),
                Tool(
                    name="check_service",
                    description="Check status of a specific systemd service",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "service_name": {
                                "type": "string",
                                "description": "Name of the service to check"
                            }
                        },
                        "required": ["service_name"]
                    }
                )
            ]
            
            # Add action tools based on autonomy level
            if self.autonomy_level in ["auto-safe", "auto-full"]:
                tools.append(
                    Tool(
                        name="restart_service",
                        description="Restart a systemd service (respects autonomy level)",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "service_name": {
                                    "type": "string",
                                    "description": "Name of the service to restart"
                                }
                            },
                            "required": ["service_name"]
                        }
                    )
                )
            
            return tools
        
        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            """Execute a tool"""
            result = ""
            
            if name == "query_system_status":
                result = self._get_system_status()
            
            elif name == "query_logs":
                pattern = arguments.get("pattern", "")
                hours = arguments.get("hours", 1)
                result = self._query_logs(pattern, hours)
            
            elif name == "check_service":
                service_name = arguments.get("service_name", "")
                result = self._check_service(service_name)
            
            elif name == "restart_service":
                if self.autonomy_level not in ["auto-safe", "auto-full"]:
                    result = json.dumps({
                        "error": "Action not allowed at current autonomy level",
                        "autonomy_level": self.autonomy_level
                    })
                else:
                    service_name = arguments.get("service_name", "")
                    result = self._restart_service(service_name)
            
            else:
                result = json.dumps({"error": "Unknown tool"})
            
            return [TextContent(type="text", text=result)]
    
    # Resource implementation methods
    
    def _get_system_status(self) -> str:
        """Get current system status"""
        import psutil
        
        import socket
        hostname = socket.gethostname()
        
        status = {
            "hostname": hostname,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metrics": {
                "cpu_percent": psutil.cpu_percent(interval=0.5),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_percent": psutil.disk_usage('/').percent,
                "load_average": psutil.getloadavg()
            }
        }
        
        return json.dumps(status, indent=2)
    
    def _get_system_context(self) -> str:
        """Get current AI context"""
        if not self.context_manager:
            return "Context manager not available"
        
        return self.context_manager.get_context_window(
            include_sar=True,
            include_metrics=True
        )
    
    def _get_triggers(self) -> str:
        """Get recent triggers"""
        if not self.trigger_monitor:
            return json.dumps({"error": "Trigger monitor not available"})
        
        triggers = self.trigger_monitor.get_event_buffer()
        stats = self.trigger_monitor.get_statistics()
        
        return json.dumps({
            "triggers": triggers[-20:],  # Last 20
            "statistics": stats
        }, indent=2)
    
    def _get_metrics_history(self) -> str:
        """Get metrics history"""
        if not self.timeseries_db:
            return json.dumps({"error": "TimescaleDB not available"})
        
        import socket
        hostname = socket.gethostname()
        
        try:
            metrics = self.timeseries_db.query_metrics(
                hostname,
                metric_names=['cpu_percent', 'memory_percent', 'disk_percent'],
                interval="15 minutes"
            )
            
            return json.dumps({"metrics": metrics}, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})
    
    def _get_services(self) -> str:
        """Get service status"""
        import subprocess
        
        try:
            result = subprocess.run(
                ["systemctl", "list-units", "--type=service", "--no-pager", "--output=json"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                return result.stdout
            else:
                return json.dumps({"error": "Failed to query services"})
        except Exception as e:
            return json.dumps({"error": str(e)})
    
    # Tool implementation methods
    
    def _query_logs(self, pattern: str, hours: int) -> str:
        """Query system logs"""
        import subprocess
        
        try:
            result = subprocess.run(
                ["journalctl", "-p", "err", "--since", f"{hours} hours ago", 
                 "--no-pager", "--grep", pattern],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                return result.stdout or "No matches found"
            else:
                return f"Error querying logs: {result.stderr}"
        except Exception as e:
            return f"Error: {e}"
    
    def _check_service(self, service_name: str) -> str:
        """Check service status"""
        import subprocess
        
        try:
            result = subprocess.run(
                ["systemctl", "status", service_name, "--no-pager"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            return result.stdout
        except Exception as e:
            return f"Error: {e}"
    
    def _restart_service(self, service_name: str) -> str:
        """Restart a service (respects autonomy level)"""
        if not self.executor:
            return json.dumps({"error": "Executor not available"})
        
        # Create action for executor
        action = {
            "action_type": "systemd_restart",
            "proposed_action": f"Restart service {service_name}",
            "commands": [f"systemctl restart {service_name}"],
            "risk_level": "low"
        }
        
        result = self.executor.execute_action(action, {})
        
        return json.dumps(result, indent=2)
    
    async def run(self):
        """Run the MCP server"""
        await self.server.run()


async def main():
    """Main entry point"""
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="AI Sysadmin MCP Server")
    parser.add_argument(
        "--autonomy",
        choices=["observe", "suggest", "auto-safe", "auto-full"],
        default="suggest",
        help="Autonomy level"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind to"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=40085,
        help="Port to listen on (default 40085)"
    )
    
    args = parser.parse_args()
    
    try:
        server = AISysadminMCPServer(
            autonomy_level=args.autonomy,
            host=args.host,
            port=args.port
        )
        await server.run()
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

