#!/usr/bin/env python3
"""
Web Server - FastAPI backend for web interface
Provides real-time system status and AI summaries
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
import json
import asyncio
import psutil
import socket

# Import our components
from context_manager import ContextManager
from timeseries_db import TimeSeriesDB
from trigger_monitor import TriggerMonitor


app = FastAPI(title="AI Sysadmin Web Interface")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure based on deployment
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state (will be initialized on startup)
context_manager: Optional[ContextManager] = None
timeseries_db: Optional[TimeSeriesDB] = None
trigger_monitor: Optional[TriggerMonitor] = None


@app.on_event("startup")
async def startup_event():
    """Initialize components on startup"""
    global context_manager, timeseries_db, trigger_monitor
    
    try:
        context_manager = ContextManager()
        timeseries_db = TimeSeriesDB()
        trigger_monitor = TriggerMonitor(use_model=False)  # Web server doesn't need model
    except Exception as e:
        print(f"Warning: Could not initialize all components: {e}")


@app.get("/")
async def root():
    """Serve main page"""
    return HTMLResponse(content=get_index_html(), media_type="text/html")


@app.get("/api/status")
async def get_status() -> Dict[str, Any]:
    """Get current system status"""
    import socket
    hostname = socket.gethostname()

    # Get basic metrics
    cpu_percent = psutil.cpu_percent(interval=0.5)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    load_avg = psutil.getloadavg()
    
    # Get service status
    import subprocess
    failed_services = []
    try:
        result = subprocess.run(
            ["systemctl", "--failed", "--no-legend", "--no-pager"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if line:
                    service = line.split()[0]
                    failed_services.append(service)
    except:
        pass
    
    # Overall health score (0-100)
    health_score = 100
    if cpu_percent > 90:
        health_score -= 20
    if memory.percent > 85:
        health_score -= 20
    if disk.percent > 90:
        health_score -= 30
    if failed_services:
        health_score -= len(failed_services) * 10
    health_score = max(0, health_score)
    
    # Determine status
    if health_score >= 80:
        status = "healthy"
    elif health_score >= 50:
        status = "degraded"
    else:
        status = "critical"
    
    return {
        "hostname": hostname,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "health_score": health_score,
        "metrics": {
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "memory_available_gb": memory.available / (1024**3),
            "disk_percent": disk.percent,
            "disk_free_gb": disk.free / (1024**3),
            "load_average": {
                "1min": load_avg[0],
                "5min": load_avg[1],
                "15min": load_avg[2]
            }
        },
        "failed_services": failed_services
    }


@app.get("/api/summary")
async def get_summary() -> Dict[str, Any]:
    """Get AI-generated system summary"""
    if not context_manager:
        return {
            "summary": "Context manager not available",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    # Get recent context
    try:
        context_stats = context_manager.get_context_window(
            include_sar=False,
            include_metrics=False,
            max_tokens=1000  # Brief summary
        )
        
        # Parse out key information
        entries = list(context_manager.context_entries)[-10:]  # Last 10 events
        
        # Summarize recent events
        event_summary = []
        for entry in entries:
            event = entry.get('event', {})
            event_type = event.get('type', 'unknown')
            message = event.get('message', event.get('summary', 'Unknown event'))
            event_summary.append({
                'type': event_type,
                'message': message,
                'timestamp': entry.get('timestamp')
            })
        
        return {
            "summary": "System operational. Recent activity tracked.",
            "recent_events": event_summary,
            "context_stats": {
                "entries": len(context_manager.context_entries),
                "tokens": context_manager.current_token_count,
                "utilization": f"{(context_manager.current_token_count / context_manager.context_size * 100):.1f}%"
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        return {
            "summary": f"Error generating summary: {e}",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


@app.get("/api/metrics/history")
async def get_metrics_history(hours: int = 24) -> Dict[str, Any]:
    """Get historical metrics"""
    if not timeseries_db:
        return {"error": "TimescaleDB not available"}
    
    import socket
    hostname = socket.gethostname()
    try:
        metrics = timeseries_db.query_metrics(
            hostname,
            metric_names=['cpu_percent', 'memory_percent', 'disk_percent'],
            interval="5 minutes"
        )
        
        return {
            "hostname": hostname,
            "period_hours": hours,
            "metrics": metrics
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/triggers")
async def get_triggers() -> Dict[str, Any]:
    """Get recent trigger events"""
    if not trigger_monitor:
        return {"triggers": []}
    
    try:
        triggers = trigger_monitor.get_event_buffer()
        stats = trigger_monitor.get_statistics()
        
        return {
            "triggers": triggers[-50:],  # Last 50 triggers
            "statistics": stats
        }
    except Exception as e:
        return {"error": str(e)}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time updates"""
    await websocket.accept()
    
    try:
        while True:
            # Send status update every 5 seconds
            status = await get_status()
            await websocket.send_json(status)
            await asyncio.sleep(5)
    
    except WebSocketDisconnect:
        print("Client disconnected")


def get_index_html() -> str:
    """Generate HTML for main page"""
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Sysadmin - System Monitor</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f172a;
            color: #e2e8f0;
            padding: 20px;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        
        header {
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 2px solid #1e293b;
        }
        
        h1 {
            font-size: 2rem;
            margin-bottom: 10px;
            color: #60a5fa;
        }
        
        .status-indicator {
            display: inline-block;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.9rem;
            font-weight: 600;
        }
        
        .status-healthy { background: #065f46; color: #d1fae5; }
        .status-degraded { background: #92400e; color: #fef3c7; }
        .status-critical { background: #7f1d1d; color: #fecaca; }
        
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        
        .card {
            background: #1e293b;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        }
        
        .card h2 {
            font-size: 1.2rem;
            margin-bottom: 15px;
            color: #94a3b8;
        }
        
        .metric {
            margin-bottom: 15px;
        }
        
        .metric-label {
            font-size: 0.9rem;
            color: #94a3b8;
            margin-bottom: 5px;
        }
        
        .metric-value {
            font-size: 1.5rem;
            font-weight: 600;
            color: #60a5fa;
        }
        
        .metric-bar {
            height: 8px;
            background: #334155;
            border-radius: 4px;
            overflow: hidden;
            margin-top: 5px;
        }
        
        .metric-bar-fill {
            height: 100%;
            background: #60a5fa;
            transition: width 0.3s ease;
        }
        
        .metric-bar-fill.warning { background: #f59e0b; }
        .metric-bar-fill.critical { background: #ef4444; }
        
        .event-list {
            list-style: none;
        }
        
        .event-item {
            padding: 10px;
            margin-bottom: 8px;
            background: #0f172a;
            border-radius: 5px;
            border-left: 3px solid #60a5fa;
        }
        
        .event-time {
            font-size: 0.8rem;
            color: #64748b;
        }
        
        .loading {
            text-align: center;
            padding: 40px;
            color: #64748b;
        }
        
        footer {
            margin-top: 30px;
            padding-top: 20px;
            border-top: 2px solid #1e293b;
            text-align: center;
            color: #64748b;
            font-size: 0.9rem;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🤖 AI System Administrator</h1>
            <div id="status-badge" class="status-indicator">Loading...</div>
            <div style="margin-top: 10px;">
                <span id="hostname" style="color: #94a3b8;">-</span> | 
                <span id="update-time" style="color: #64748b;">-</span>
            </div>
        </header>
        
        <div class="grid">
            <div class="card">
                <h2>System Metrics</h2>
                <div class="metric">
                    <div class="metric-label">CPU Usage</div>
                    <div class="metric-value" id="cpu-value">-</div>
                    <div class="metric-bar">
                        <div class="metric-bar-fill" id="cpu-bar" style="width: 0%"></div>
                    </div>
                </div>
                <div class="metric">
                    <div class="metric-label">Memory Usage</div>
                    <div class="metric-value" id="memory-value">-</div>
                    <div class="metric-bar">
                        <div class="metric-bar-fill" id="memory-bar" style="width: 0%"></div>
                    </div>
                </div>
                <div class="metric">
                    <div class="metric-label">Disk Usage</div>
                    <div class="metric-value" id="disk-value">-</div>
                    <div class="metric-bar">
                        <div class="metric-bar-fill" id="disk-bar" style="width: 0%"></div>
                    </div>
                </div>
            </div>
            
            <div class="card">
                <h2>System Health</h2>
                <div class="metric">
                    <div class="metric-label">Health Score</div>
                    <div class="metric-value" id="health-score">-</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Load Average (1m)</div>
                    <div class="metric-value" id="load-avg">-</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Failed Services</div>
                    <div class="metric-value" id="failed-services">-</div>
                </div>
            </div>
            
            <div class="card" style="grid-column: span 2;">
                <h2>Recent Events</h2>
                <ul class="event-list" id="event-list">
                    <li class="loading">Loading events...</li>
                </ul>
            </div>
        </div>
        
        <footer>
            AI System Administrator - Autonomous monitoring and maintenance
        </footer>
    </div>
    
    <script>
        let ws = null;
        
        function updateUI(data) {
            // Status badge
            const statusBadge = document.getElementById('status-badge');
            statusBadge.textContent = data.status.toUpperCase();
            statusBadge.className = 'status-indicator status-' + data.status;
            
            // Header info
            document.getElementById('hostname').textContent = data.hostname;
            document.getElementById('update-time').textContent = new Date().toLocaleTimeString();
            
            // Metrics
            const metrics = data.metrics;
            
            updateMetric('cpu', metrics.cpu_percent);
            updateMetric('memory', metrics.memory_percent);
            updateMetric('disk', metrics.disk_percent);
            
            document.getElementById('health-score').textContent = data.health_score + '/100';
            document.getElementById('load-avg').textContent = metrics.load_average['1min'].toFixed(2);
            document.getElementById('failed-services').textContent = data.failed_services.length;
        }
        
        function updateMetric(name, percent) {
            const valueEl = document.getElementById(name + '-value');
            const barEl = document.getElementById(name + '-bar');
            
            valueEl.textContent = percent.toFixed(1) + '%';
            barEl.style.width = percent + '%';
            
            // Color based on threshold
            barEl.className = 'metric-bar-fill';
            if (percent > 90) {
                barEl.classList.add('critical');
            } else if (percent > 75) {
                barEl.classList.add('warning');
            }
        }
        
        async function fetchSummary() {
            try {
                const response = await fetch('/api/summary');
                const data = await response.json();
                
                const eventList = document.getElementById('event-list');
                eventList.innerHTML = '';
                
                if (data.recent_events && data.recent_events.length > 0) {
                    data.recent_events.forEach(event => {
                        const li = document.createElement('li');
                        li.className = 'event-item';
                        li.innerHTML = `
                            <div>${event.message}</div>
                            <div class="event-time">${new Date(event.timestamp).toLocaleString()}</div>
                        `;
                        eventList.appendChild(li);
                    });
                } else {
                    eventList.innerHTML = '<li class="loading">No recent events</li>';
                }
            } catch (error) {
                console.error('Error fetching summary:', error);
            }
        }
        
        function connectWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(protocol + '//' + window.location.host + '/ws');
            
            ws.onmessage = function(event) {
                const data = JSON.parse(event.data);
                updateUI(data);
            };
            
            ws.onclose = function() {
                console.log('WebSocket closed, reconnecting in 5s...');
                setTimeout(connectWebSocket, 5000);
            };
            
            ws.onerror = function(error) {
                console.error('WebSocket error:', error);
            };
        }
        
        // Initialize
        connectWebSocket();
        fetchSummary();
        setInterval(fetchSummary, 30000);  // Update summary every 30s
    </script>
</body>
</html>
    """


if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 40084))
    uvicorn.run(app, host="0.0.0.0", port=port)

