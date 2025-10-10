#!/usr/bin/env python3
"""
Journal Monitor - Monitor remote systems via centralized journald
"""

import json
import subprocess
from typing import Dict, List, Any, Optional, Set
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict


class JournalMonitor:
    """Monitor systems via centralized journald logs"""
    
    def __init__(self, domain: str = "coven.systems"):
        """
        Initialize journal monitor
        
        Args:
            domain: Domain suffix for FQDNs
        """
        self.domain = domain
        self.known_hosts: Set[str] = set()
        
    def _run_journalctl(self, args: List[str], timeout: int = 30) -> tuple[bool, str, str]:
        """
        Run journalctl command
        
        Args:
            args: Arguments to journalctl
            timeout: Timeout in seconds
            
        Returns:
            (success, stdout, stderr)
        """
        try:
            cmd = ["journalctl"] + args
            
            result = subprocess.run(
                cmd,
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
    
    def discover_hosts(self) -> List[str]:
        """
        Discover hosts reporting to centralized journal
        
        Returns:
            List of discovered FQDNs
        """
        success, output, _ = self._run_journalctl([
            "--output=json",
            "--since=1 day ago",
            "-n", "10000"
        ])
        
        if not success:
            return []
        
        hosts = set()
        for line in output.split('\n'):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                hostname = entry.get('_HOSTNAME', '')
                
                # Ensure FQDN format
                if hostname and not hostname.endswith(f'.{self.domain}'):
                    if '.' not in hostname:
                        hostname = f"{hostname}.{self.domain}"
                
                if hostname:
                    hosts.add(hostname)
                    
            except json.JSONDecodeError:
                continue
        
        self.known_hosts = hosts
        return sorted(hosts)
    
    def collect_resources(self, hostname: str, since: str = "5 minutes ago") -> Dict[str, Any]:
        """
        Collect resource usage from journal entries
        
        This extracts CPU/memory info from systemd service messages
        """
        # For now, return empty - we'll primarily use this for service/log monitoring
        # Resource metrics could be added if systems log them
        return {
            "cpu_percent": 0,
            "memory_percent": 0,
            "load_average": {"1min": 0, "5min": 0, "15min": 0}
        }
    
    def collect_systemd_status(self, hostname: str, since: str = "5 minutes ago") -> Dict[str, Any]:
        """
        Collect systemd service status from journal
        
        Args:
            hostname: FQDN of the system
            since: Time range to check
            
        Returns:
            Dictionary with failed service information
        """
        # Query for systemd service failures
        success, output, _ = self._run_journalctl([
            f"_HOSTNAME={hostname}",
            "--priority=err",
            "--unit=*.service",
            f"--since={since}",
            "--output=json"
        ])
        
        if not success:
            return {"failed_count": 0, "failed_services": []}
        
        failed_services = {}
        for line in output.split('\n'):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                unit = entry.get('_SYSTEMD_UNIT', '')
                if unit and unit.endswith('.service'):
                    service_name = unit.replace('.service', '')
                    if service_name not in failed_services:
                        failed_services[service_name] = {
                            "unit": unit,
                            "message": entry.get('MESSAGE', ''),
                            "timestamp": entry.get('__REALTIME_TIMESTAMP', '')
                        }
            except json.JSONDecodeError:
                continue
        
        return {
            "failed_count": len(failed_services),
            "failed_services": list(failed_services.values())
        }
    
    def collect_log_errors(self, hostname: str, since: str = "1 hour ago") -> Dict[str, Any]:
        """
        Collect error logs from journal
        
        Args:
            hostname: FQDN of the system
            since: Time range to check
            
        Returns:
            Dictionary with error log information
        """
        success, output, _ = self._run_journalctl([
            f"_HOSTNAME={hostname}",
            "--priority=err",
            f"--since={since}",
            "--output=json"
        ])
        
        if not success:
            return {"error_count_1h": 0, "recent_errors": []}
        
        errors = []
        error_count = 0
        
        for line in output.split('\n'):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                error_count += 1
                
                if len(errors) < 10:  # Keep last 10 errors
                    errors.append({
                        "message": entry.get('MESSAGE', ''),
                        "unit": entry.get('_SYSTEMD_UNIT', 'unknown'),
                        "priority": entry.get('PRIORITY', ''),
                        "timestamp": entry.get('__REALTIME_TIMESTAMP', '')
                    })
                    
            except json.JSONDecodeError:
                continue
        
        return {
            "error_count_1h": error_count,
            "recent_errors": errors
        }
    
    def collect_disk_usage(self, hostname: str) -> Dict[str, Any]:
        """
        Collect disk usage - Note: This would require systems to log disk metrics
        For now, returns empty. Could be enhanced if systems periodically log disk usage
        """
        return {"partitions": []}
    
    def collect_network_status(self, hostname: str, since: str = "5 minutes ago") -> Dict[str, Any]:
        """
        Check network connectivity based on recent journal activity
        
        If we see recent logs from a host, it's reachable
        """
        success, output, _ = self._run_journalctl([
            f"_HOSTNAME={hostname}",
            f"--since={since}",
            "-n", "1",
            "--output=json"
        ])
        
        # If we got recent logs, network is working
        internet_reachable = bool(success and output.strip())
        
        return {
            "internet_reachable": internet_reachable,
            "last_seen": datetime.now().isoformat() if internet_reachable else None
        }
    
    def collect_all(self, hostname: str) -> Dict[str, Any]:
        """
        Collect all monitoring data for a host from journal
        
        Args:
            hostname: FQDN of the system to monitor
            
        Returns:
            Complete monitoring data
        """
        # First check if we have recent logs from this host
        net_status = self.collect_network_status(hostname)
        
        if not net_status.get("internet_reachable"):
            return {
                "hostname": hostname,
                "reachable": False,
                "error": "No recent journal entries from this host"
            }
        
        return {
            "hostname": hostname,
            "reachable": True,
            "source": "journal",
            "resources": self.collect_resources(hostname),
            "systemd": self.collect_systemd_status(hostname),
            "disk": self.collect_disk_usage(hostname),
            "network": net_status,
            "logs": self.collect_log_errors(hostname),
        }
    
    def get_summary(self, data: Dict[str, Any]) -> str:
        """Generate human-readable summary from journal data"""
        hostname = data.get("hostname", "unknown")
        
        if not data.get("reachable", False):
            return f"❌ {hostname}: {data.get('error', 'Unreachable')}"
        
        lines = [f"System: {hostname} (via journal)"]
        
        # Services
        systemd = data.get("systemd", {})
        failed_count = systemd.get("failed_count", 0)
        if failed_count > 0:
            lines.append(f"Services: {failed_count} failed")
            for svc in systemd.get("failed_services", [])[:3]:
                lines.append(f"  - {svc.get('unit', 'unknown')}")
        else:
            lines.append("Services: No recent failures")
        
        # Network
        net = data.get("network", {})
        last_seen = net.get("last_seen")
        if last_seen:
            lines.append(f"Last seen: {last_seen}")
        
        # Logs
        logs = data.get("logs", {})
        error_count = logs.get("error_count_1h", 0)
        if error_count > 0:
            lines.append(f"Recent logs: {error_count} errors in last hour")
        
        return "\n".join(lines)
    
    def get_active_services(self, hostname: str, since: str = "1 hour ago") -> List[str]:
        """
        Get list of active services on a host by looking at journal entries
        
        This helps with auto-discovery of what's running on each system
        """
        success, output, _ = self._run_journalctl([
            f"_HOSTNAME={hostname}",
            f"--since={since}",
            "--output=json",
            "-n", "1000"
        ])
        
        if not success:
            return []
        
        services = set()
        for line in output.split('\n'):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                unit = entry.get('_SYSTEMD_UNIT', '')
                if unit and unit.endswith('.service'):
                    # Extract service name
                    service = unit.replace('.service', '')
                    # Filter out common system services, focus on application services
                    if service not in ['systemd-journald', 'systemd-logind', 'sshd', 'dbus']:
                        services.add(service)
            except json.JSONDecodeError:
                continue
        
        return sorted(services)


if __name__ == "__main__":
    import sys
    
    monitor = JournalMonitor()
    
    # Discover hosts
    print("Discovering hosts from journal...")
    hosts = monitor.discover_hosts()
    print(f"Found {len(hosts)} hosts:")
    for host in hosts:
        print(f"  - {host}")
    
    # Monitor first host if available
    if hosts:
        hostname = hosts[0]
        print(f"\nMonitoring {hostname}...")
        data = monitor.collect_all(hostname)
        
        print("\n" + "="*60)
        print(monitor.get_summary(data))
        print("="*60)
        
        # Discover services
        print(f"\nActive services on {hostname}:")
        services = monitor.get_active_services(hostname)
        for svc in services[:10]:
            print(f"  - {svc}")

