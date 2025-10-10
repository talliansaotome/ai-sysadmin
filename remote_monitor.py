#!/usr/bin/env python3
"""
Remote Monitor - Collect system health data from remote NixOS systems via SSH
"""

import json
import subprocess
from typing import Dict, Any, Optional
from pathlib import Path
from command_patterns import build_ssh_command


class RemoteMonitor:
    """Monitor remote systems via SSH"""
    
    def __init__(self, hostname: str, ssh_user: str = "root"):
        """
        Initialize remote monitor
        
        Args:
            hostname: Remote hostname or IP
            ssh_user: SSH user (default: root for NixOS remote builds)
        """
        self.hostname = hostname
        self.ssh_user = ssh_user
        self.ssh_target = f"{ssh_user}@{hostname}"
        
    def _run_remote_command(self, command: str, timeout: int = 30) -> tuple[bool, str, str]:
        """
        Run a command on the remote system via SSH
        
        Args:
            command: Command to run
            timeout: Timeout in seconds
            
        Returns:
            (success, stdout, stderr)
        """
        try:
            # Use centralized command pattern - see command_patterns.py
            ssh_cmd = build_ssh_command(self.hostname, command, timeout)
            
            result = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            return (
                result.returncode == 0,
                result.stdout.strip(),
                result.stderr.strip()
            )
            
        except subprocess.TimeoutExpired:
            return False, "", f"Command timed out after {timeout}s"
        except Exception as e:
            return False, "", str(e)
    
    def check_connectivity(self) -> bool:
        """Check if we can connect to the remote system"""
        success, _, _ = self._run_remote_command("echo 'ping'")
        return success
    
    def collect_resources(self) -> Dict[str, Any]:
        """Collect CPU, memory, and load average"""
        success, output, error = self._run_remote_command("""
            python3 -c "
import psutil, json
print(json.dumps({
    'cpu_percent': psutil.cpu_percent(interval=1),
    'memory_percent': psutil.virtual_memory().percent,
    'load_average': {
        '1min': psutil.getloadavg()[0],
        '5min': psutil.getloadavg()[1],
        '15min': psutil.getloadavg()[2]
    }
}))
"
        """)
        
        if success:
            try:
                return json.loads(output)
            except json.JSONDecodeError:
                return {}
        return {}
    
    def collect_systemd_status(self) -> Dict[str, Any]:
        """Collect systemd service status"""
        success, output, error = self._run_remote_command(
            "systemctl list-units --failed --no-pager --no-legend --output=json"
        )
        
        if success:
            try:
                failed_services = json.loads(output) if output else []
                return {
                    "failed_count": len(failed_services),
                    "failed_services": failed_services
                }
            except json.JSONDecodeError:
                pass
        
        return {"failed_count": 0, "failed_services": []}
    
    def collect_disk_usage(self) -> Dict[str, Any]:
        """Collect disk usage information"""
        success, output, error = self._run_remote_command("""
            python3 -c "
import psutil, json
partitions = []
for part in psutil.disk_partitions():
    try:
        usage = psutil.disk_usage(part.mountpoint)
        partitions.append({
            'device': part.device,
            'mountpoint': part.mountpoint,
            'fstype': part.fstype,
            'total': usage.total,
            'used': usage.used,
            'free': usage.free,
            'percent_used': usage.percent
        })
    except:
        pass
print(json.dumps({'partitions': partitions}))
"
        """)
        
        if success:
            try:
                return json.loads(output)
            except json.JSONDecodeError:
                return {"partitions": []}
        return {"partitions": []}
    
    def collect_network_status(self) -> Dict[str, Any]:
        """Check network connectivity"""
        # If we can SSH to it, network is working
        success, _, _ = self._run_remote_command("ping -c 1 -W 2 8.8.8.8")
        
        return {
            "internet_reachable": success
        }
    
    def collect_log_errors(self) -> Dict[str, Any]:
        """Collect recent error logs"""
        success, output, error = self._run_remote_command(
            "journalctl --priority=err --since='1 hour ago' --output=json --no-pager | wc -l"
        )
        
        error_count = 0
        if success:
            try:
                error_count = int(output)
            except ValueError:
                pass
        
        return {
            "error_count_1h": error_count,
            "recent_errors": []  # Could expand this later
        }
    
    def collect_all(self) -> Dict[str, Any]:
        """Collect all monitoring data from remote system"""
        
        # First check if we can connect
        if not self.check_connectivity():
            return {
                "hostname": self.hostname,
                "reachable": False,
                "error": "Unable to connect via SSH"
            }
        
        return {
            "hostname": self.hostname,
            "reachable": True,
            "resources": self.collect_resources(),
            "systemd": self.collect_systemd_status(),
            "disk": self.collect_disk_usage(),
            "network": self.collect_network_status(),
            "logs": self.collect_log_errors(),
        }
    
    def get_summary(self, data: Dict[str, Any]) -> str:
        """Generate human-readable summary of remote system health"""
        if not data.get("reachable", False):
            return f"❌ {self.hostname}: Unreachable - {data.get('error', 'Unknown error')}"
        
        lines = [f"System: {self.hostname}"]
        
        # Resources
        res = data.get("resources", {})
        if res:
            lines.append(
                f"Resources: CPU {res.get('cpu_percent', 0):.1f}%, "
                f"Memory {res.get('memory_percent', 0):.1f}%, "
                f"Load {res.get('load_average', {}).get('1min', 0):.2f}"
            )
        
        # Disk
        disk = data.get("disk", {})
        max_usage = 0
        for part in disk.get("partitions", []):
            if part.get("mountpoint") == "/":
                max_usage = part.get("percent_used", 0)
                break
        if max_usage > 0:
            lines.append(f"Disk: {max_usage:.1f}% used (/ partition)")
        
        # Services
        systemd = data.get("systemd", {})
        failed_count = systemd.get("failed_count", 0)
        if failed_count > 0:
            lines.append(f"Services: {failed_count} failed")
            for svc in systemd.get("failed_services", [])[:3]:
                lines.append(f"  - {svc.get('unit', 'unknown')}")
        else:
            lines.append("Services: All running")
        
        # Network
        net = data.get("network", {})
        if net.get("internet_reachable"):
            lines.append("Network: Internet reachable")
        else:
            lines.append("Network: ⚠️ No internet connectivity")
        
        # Logs
        logs = data.get("logs", {})
        error_count = logs.get("error_count_1h", 0)
        if error_count > 0:
            lines.append(f"Recent logs: {error_count} errors in last hour")
        
        return "\n".join(lines)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: remote_monitor.py <hostname>")
        print("Example: remote_monitor.py rhiannon")
        sys.exit(1)
    
    hostname = sys.argv[1]
    monitor = RemoteMonitor(hostname)
    
    print(f"Monitoring {hostname}...")
    data = monitor.collect_all()
    
    print("\n" + "="*60)
    print(monitor.get_summary(data))
    print("="*60)
    print("\nFull data:")
    print(json.dumps(data, indent=2))

