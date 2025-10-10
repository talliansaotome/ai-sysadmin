#!/usr/bin/env python3
"""
System Monitor - Collects health data from Macha
"""

import json
import subprocess
import psutil
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any


class SystemMonitor:
    """Monitors system health and collects diagnostic data"""
    
    def __init__(self, state_dir: Path = Path("/var/lib/ai-sysadmin")):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        
    def collect_all(self) -> Dict[str, Any]:
        """Collect all system health data"""
        return {
            "timestamp": datetime.now().isoformat(),
            "systemd": self.check_systemd_services(),
            "resources": self.check_resources(),
            "disk": self.check_disk_usage(),
            "logs": self.check_recent_errors(),
            "nixos": self.check_nixos_status(),
            "network": self.check_network(),
            "boot": self.check_boot_status(),
        }
    
    def check_systemd_services(self) -> Dict[str, Any]:
        """Check status of all systemd services"""
        try:
            # Get failed services
            result = subprocess.run(
                ["systemctl", "--failed", "--no-pager", "--output=json"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            failed_services = []
            if result.returncode == 0 and result.stdout:
                try:
                    failed_services = json.loads(result.stdout)
                except json.JSONDecodeError:
                    pass
            
            # Get all services status
            result = subprocess.run(
                ["systemctl", "list-units", "--type=service", "--no-pager", "--output=json"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            all_services = []
            if result.returncode == 0 and result.stdout:
                try:
                    all_services = json.loads(result.stdout)
                except json.JSONDecodeError:
                    pass
            
            return {
                "failed_count": len(failed_services),
                "failed_services": failed_services,
                "total_services": len(all_services),
                "active_services": [s for s in all_services if s.get("active") == "active"],
            }
        except Exception as e:
            return {"error": str(e)}
    
    def check_resources(self) -> Dict[str, Any]:
        """Check CPU, RAM, and system resources"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            load_avg = psutil.getloadavg()
            
            return {
                "cpu_percent": cpu_percent,
                "cpu_count": psutil.cpu_count(),
                "memory_percent": memory.percent,
                "memory_available_gb": memory.available / (1024**3),
                "memory_total_gb": memory.total / (1024**3),
                "load_average": {
                    "1min": load_avg[0],
                    "5min": load_avg[1],
                    "15min": load_avg[2],
                },
                "swap_percent": psutil.swap_memory().percent,
            }
        except Exception as e:
            return {"error": str(e)}
    
    def check_disk_usage(self) -> Dict[str, Any]:
        """Check disk usage for all mounted filesystems"""
        try:
            partitions = psutil.disk_partitions()
            disk_info = []
            
            for partition in partitions:
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    disk_info.append({
                        "device": partition.device,
                        "mountpoint": partition.mountpoint,
                        "fstype": partition.fstype,
                        "percent_used": usage.percent,
                        "total_gb": usage.total / (1024**3),
                        "used_gb": usage.used / (1024**3),
                        "free_gb": usage.free / (1024**3),
                    })
                except PermissionError:
                    continue
            
            return {"partitions": disk_info}
        except Exception as e:
            return {"error": str(e)}
    
    def check_recent_errors(self) -> Dict[str, Any]:
        """Check recent system logs for errors"""
        try:
            # Get errors from the last hour
            result = subprocess.run(
                ["journalctl", "-p", "err", "--since", "1 hour ago", "--no-pager", "-o", "json"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            errors = []
            if result.returncode == 0 and result.stdout:
                for line in result.stdout.strip().split('\n'):
                    if line:
                        try:
                            errors.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            
            return {
                "error_count_1h": len(errors),
                "recent_errors": errors[-50:],  # Last 50 errors
            }
        except Exception as e:
            return {"error": str(e)}
    
    def check_nixos_status(self) -> Dict[str, Any]:
        """Check NixOS generation and system info"""
        try:
            # Get current generation
            result = subprocess.run(
                ["nixos-version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            version = result.stdout.strip() if result.returncode == 0 else "unknown"
            
            # Get generation list
            result = subprocess.run(
                ["nix-env", "--list-generations", "-p", "/nix/var/nix/profiles/system"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            generations = result.stdout.strip() if result.returncode == 0 else ""
            
            return {
                "version": version,
                "generations": generations,
                "nix_store_size": self._get_nix_store_size(),
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _get_nix_store_size(self) -> str:
        """Get Nix store size"""
        try:
            result = subprocess.run(
                ["du", "-sh", "/nix/store"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                return result.stdout.split()[0]
        except:
            pass
        return "unknown"
    
    def check_network(self) -> Dict[str, Any]:
        """Check network connectivity"""
        try:
            # Check if we can reach the internet
            result = subprocess.run(
                ["ping", "-c", "1", "-W", "2", "8.8.8.8"],
                capture_output=True,
                timeout=5
            )
            internet_up = result.returncode == 0
            
            # Get network interfaces
            interfaces = {}
            for iface, addrs in psutil.net_if_addrs().items():
                interfaces[iface] = [
                    {"family": addr.family.name, "address": addr.address}
                    for addr in addrs
                ]
            
            return {
                "internet_reachable": internet_up,
                "interfaces": interfaces,
            }
        except Exception as e:
            return {"error": str(e)}
    
    def check_boot_status(self) -> Dict[str, Any]:
        """Check boot and uptime information"""
        try:
            boot_time = datetime.fromtimestamp(psutil.boot_time())
            uptime_seconds = time.time() - psutil.boot_time()
            
            return {
                "boot_time": boot_time.isoformat(),
                "uptime_seconds": uptime_seconds,
                "uptime_hours": uptime_seconds / 3600,
            }
        except Exception as e:
            return {"error": str(e)}
    
    def save_snapshot(self, data: Dict[str, Any]):
        """Save a snapshot of system state"""
        snapshot_file = self.state_dir / f"snapshot_{int(time.time())}.json"
        with open(snapshot_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        # Keep only last 100 snapshots
        snapshots = sorted(self.state_dir.glob("snapshot_*.json"))
        for old_snapshot in snapshots[:-100]:
            old_snapshot.unlink()
    
    def get_summary(self, data: Dict[str, Any]) -> str:
        """Generate human-readable summary of system state"""
        lines = []
        lines.append(f"=== System Health Summary ({data['timestamp']}) ===\n")
        
        # Resources
        res = data.get("resources", {})
        lines.append(f"CPU: {res.get('cpu_percent', 0):.1f}%")
        lines.append(f"Memory: {res.get('memory_percent', 0):.1f}% ({res.get('memory_available_gb', 0):.1f}GB free)")
        lines.append(f"Load: {res.get('load_average', {}).get('1min', 0):.2f}")
        
        # Disk
        disk = data.get("disk", {})
        for part in disk.get("partitions", [])[:5]:  # Top 5 partitions
            lines.append(f"Disk {part['mountpoint']}: {part['percent_used']:.1f}% used ({part['free_gb']:.1f}GB free)")
        
        # Systemd
        systemd = data.get("systemd", {})
        failed = systemd.get("failed_count", 0)
        if failed > 0:
            lines.append(f"\n⚠️  WARNING: {failed} failed services!")
            for svc in systemd.get("failed_services", [])[:5]:
                lines.append(f"  - {svc.get('unit', 'unknown')}")
        
        # Errors
        logs = data.get("logs", {})
        error_count = logs.get("error_count_1h", 0)
        if error_count > 0:
            lines.append(f"\n⚠️  {error_count} errors in last hour")
        
        # Network
        net = data.get("network", {})
        if not net.get("internet_reachable", True):
            lines.append("\n⚠️  WARNING: No internet connectivity!")
        
        return "\n".join(lines)


if __name__ == "__main__":
    monitor = SystemMonitor()
    data = monitor.collect_all()
    monitor.save_snapshot(data)
    print(monitor.get_summary(data))
    print(f"\nFull data saved to {monitor.state_dir}")
