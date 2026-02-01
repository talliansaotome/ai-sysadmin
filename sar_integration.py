#!/usr/bin/env python3
"""
SAR Integration - Parse and store system activity reports
"""

import subprocess
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional


class SarIntegration:
    """Parse and integrate sar (System Activity Report) data"""
    
    def __init__(self):
        """Initialize SAR integration"""
        pass
    
    def check_sar_available(self) -> bool:
        """Check if sar command is available"""
        try:
            result = subprocess.run(
                ["which", "sar"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except:
            return False
    
    def get_cpu_usage(self, hours: int = 1) -> List[Dict[str, Any]]:
        """Get CPU usage statistics from sar"""
        try:
            # sar -u: CPU utilization
            # -s: start time (hours ago)
            start_time = datetime.now(timezone.utc) - timedelta(hours=hours)
            start_str = start_time.strftime("%H:%M:%S")
            
            result = subprocess.run(
                ["sar", "-u", "-s", start_str],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                return []
            
            return self._parse_sar_output(result.stdout, [
                'user', 'nice', 'system', 'iowait', 'steal', 'idle'
            ])
        except Exception as e:
            print(f"Error getting CPU usage from sar: {e}")
            return []
    
    def get_memory_usage(self, hours: int = 1) -> List[Dict[str, Any]]:
        """Get memory usage statistics from sar"""
        try:
            start_time = datetime.now(timezone.utc) - timedelta(hours=hours)
            start_str = start_time.strftime("%H:%M:%S")
            
            result = subprocess.run(
                ["sar", "-r", "-s", start_str],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                return []
            
            return self._parse_sar_output(result.stdout, [
                'kbmemfree', 'kbavail', 'kbmemused', 'memused',
                'kbbuffers', 'kbcached', 'kbcommit', 'commit'
            ])
        except Exception as e:
            print(f"Error getting memory usage from sar: {e}")
            return []
    
    def get_disk_io(self, hours: int = 1) -> List[Dict[str, Any]]:
        """Get disk I/O statistics from sar"""
        try:
            start_time = datetime.now(timezone.utc) - timedelta(hours=hours)
            start_str = start_time.strftime("%H:%M:%S")
            
            result = subprocess.run(
                ["sar", "-b", "-s", start_str],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                return []
            
            return self._parse_sar_output(result.stdout, [
                'tps', 'rtps', 'wtps', 'bread/s', 'bwrtn/s'
            ])
        except Exception as e:
            print(f"Error getting disk I/O from sar: {e}")
            return []
    
    def get_network_stats(self, hours: int = 1) -> List[Dict[str, Any]]:
        """Get network statistics from sar"""
        try:
            start_time = datetime.now(timezone.utc) - timedelta(hours=hours)
            start_str = start_time.strftime("%H:%M:%S")
            
            result = subprocess.run(
                ["sar", "-n", "DEV", "-s", start_str],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                return []
            
            # Network stats have interface names, so parsing is more complex
            return self._parse_sar_network_output(result.stdout)
        except Exception as e:
            print(f"Error getting network stats from sar: {e}")
            return []
    
    def get_load_average(self, hours: int = 1) -> List[Dict[str, Any]]:
        """Get load average from sar"""
        try:
            start_time = datetime.now(timezone.utc) - timedelta(hours=hours)
            start_str = start_time.strftime("%H:%M:%S")
            
            result = subprocess.run(
                ["sar", "-q", "-s", start_str],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                return []
            
            return self._parse_sar_output(result.stdout, [
                'runq-sz', 'plist-sz', 'ldavg-1', 'ldavg-5', 'ldavg-15', 'blocked'
            ])
        except Exception as e:
            print(f"Error getting load average from sar: {e}")
            return []
    
    def _parse_sar_output(self, output: str, metric_names: List[str]) -> List[Dict[str, Any]]:
        """Parse standard sar output format"""
        results = []
        lines = output.strip().split('\n')
        
        # Find header line (contains metric names)
        header_idx = -1
        for i, line in enumerate(lines):
            if any(metric in line for metric in metric_names):
                header_idx = i
                break
        
        if header_idx == -1:
            return []
        
        # Parse header to get column positions
        header = lines[header_idx].split()
        
        # Skip lines until we find data (after header and blank line)
        for line in lines[header_idx + 1:]:
            line = line.strip()
            
            # Skip empty lines and summary lines
            if not line or line.startswith('Average'):
                continue
            
            # Parse data line
            parts = line.split()
            if len(parts) < 2:
                continue
            
            # First column is usually time (HH:MM:SS) or "Average:"
            time_str = parts[0]
            if time_str == "Average:":
                continue
            
            # Try to parse time
            try:
                # Time format: HH:MM:SS
                time_parts = time_str.split(':')
                if len(time_parts) == 3:
                    hour, minute, second = map(int, time_parts)
                    # Create timestamp for today at this time
                    now = datetime.now(timezone.utc)
                    timestamp = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
                    
                    # If timestamp is in the future, it's from yesterday
                    if timestamp > now:
                        timestamp -= timedelta(days=1)
                else:
                    continue
            except:
                continue
            
            # Parse metric values
            data = {'time': timestamp}
            
            # Match header columns to values (accounting for variable spacing)
            value_idx = 1  # Start after time column
            for col_name in header[1:]:  # Skip first column (time)
                if value_idx < len(parts):
                    try:
                        # Try to convert to float
                        value = float(parts[value_idx])
                        data[col_name] = value
                    except ValueError:
                        # Some columns might have non-numeric values
                        data[col_name] = parts[value_idx]
                    value_idx += 1
            
            results.append(data)
        
        return results
    
    def _parse_sar_network_output(self, output: str) -> List[Dict[str, Any]]:
        """Parse sar network output (has interface names)"""
        results = []
        lines = output.strip().split('\n')
        
        # Find header line
        header_idx = -1
        for i, line in enumerate(lines):
            if 'IFACE' in line or 'rxpck/s' in line:
                header_idx = i
                break
        
        if header_idx == -1:
            return []
        
        header = lines[header_idx].split()
        
        for line in lines[header_idx + 1:]:
            line = line.strip()
            
            if not line or line.startswith('Average'):
                continue
            
            parts = line.split()
            if len(parts) < 3:
                continue
            
            time_str = parts[0]
            if time_str == "Average:":
                continue
            
            # Parse time
            try:
                time_parts = time_str.split(':')
                if len(time_parts) == 3:
                    hour, minute, second = map(int, time_parts)
                    now = datetime.now(timezone.utc)
                    timestamp = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
                    
                    if timestamp > now:
                        timestamp -= timedelta(days=1)
                else:
                    continue
            except:
                continue
            
            # Interface name is second column
            iface = parts[1]
            
            data = {
                'time': timestamp,
                'interface': iface
            }
            
            # Parse remaining values
            value_idx = 2
            for col_name in header[2:]:  # Skip time and IFACE
                if value_idx < len(parts):
                    try:
                        value = float(parts[value_idx])
                        data[col_name] = value
                    except ValueError:
                        data[col_name] = parts[value_idx]
                    value_idx += 1
            
            results.append(data)
        
        return results
    
    def get_comprehensive_summary(self, hours: int = 1) -> Dict[str, Any]:
        """Get comprehensive summary of all sar data"""
        return {
            'cpu': self.get_cpu_usage(hours),
            'memory': self.get_memory_usage(hours),
            'disk_io': self.get_disk_io(hours),
            'network': self.get_network_stats(hours),
            'load': self.get_load_average(hours)
        }
    
    def format_for_context(self, hours: int = 1) -> str:
        """Format sar data for AI context"""
        if not self.check_sar_available():
            return "SAR data not available (sysstat not installed)"
        
        summary = self.get_comprehensive_summary(hours)
        
        lines = [f"System Activity Report (last {hours} hour(s)):", ""]
        
        # CPU summary
        cpu_data = summary['cpu']
        if cpu_data:
            recent_cpu = cpu_data[-10:]  # Last 10 samples
            avg_user = sum(d.get('user', 0) for d in recent_cpu) / len(recent_cpu)
            avg_system = sum(d.get('system', 0) for d in recent_cpu) / len(recent_cpu)
            avg_iowait = sum(d.get('iowait', 0) for d in recent_cpu) / len(recent_cpu)
            avg_idle = sum(d.get('idle', 0) for d in recent_cpu) / len(recent_cpu)
            
            lines.append("CPU Usage (recent average):")
            lines.append(f"  User: {avg_user:.1f}%")
            lines.append(f"  System: {avg_system:.1f}%")
            lines.append(f"  I/O Wait: {avg_iowait:.1f}%")
            lines.append(f"  Idle: {avg_idle:.1f}%")
            lines.append("")
        
        # Load average
        load_data = summary['load']
        if load_data:
            recent_load = load_data[-1]  # Most recent
            lines.append("Load Average (current):")
            lines.append(f"  1-min: {recent_load.get('ldavg-1', 0):.2f}")
            lines.append(f"  5-min: {recent_load.get('ldavg-5', 0):.2f}")
            lines.append(f"  15-min: {recent_load.get('ldavg-15', 0):.2f}")
            lines.append("")
        
        # Memory summary
        mem_data = summary['memory']
        if mem_data:
            recent_mem = mem_data[-1]  # Most recent
            mem_used_pct = recent_mem.get('memused', 0)
            lines.append(f"Memory Usage: {mem_used_pct:.1f}%")
            lines.append("")
        
        # Disk I/O summary
        io_data = summary['disk_io']
        if io_data:
            recent_io = io_data[-10:]
            avg_tps = sum(d.get('tps', 0) for d in recent_io) / len(recent_io)
            avg_read = sum(d.get('bread/s', 0) for d in recent_io) / len(recent_io)
            avg_write = sum(d.get('bwrtn/s', 0) for d in recent_io) / len(recent_io)
            
            lines.append("Disk I/O (recent average):")
            lines.append(f"  Transactions/s: {avg_tps:.1f}")
            lines.append(f"  Read: {avg_read:.1f} blocks/s")
            lines.append(f"  Write: {avg_write:.1f} blocks/s")
            lines.append("")
        
        return "\n".join(lines)


if __name__ == "__main__":
    # Test SAR integration
    sar = SarIntegration()
    
    if sar.check_sar_available():
        print("SAR is available")
        print("\n" + sar.format_for_context(hours=1))
    else:
        print("SAR is not available. Install sysstat package.")

