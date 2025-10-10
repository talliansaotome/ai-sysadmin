#!/usr/bin/env python3
"""
System Discovery - Auto-discover and profile systems from journal logs
"""

import subprocess
import json
import re
from typing import Dict, List, Set, Optional, Any
from datetime import datetime
from pathlib import Path
from command_patterns import build_ssh_command


class SystemDiscovery:
    """Discover and profile new systems appearing in logs"""
    
    def __init__(self, domain: str = "coven.systems"):
        self.domain = domain
        self.known_systems: Set[str] = set()
        
    def discover_from_journal(self, since_minutes: int = 10) -> List[str]:
        """Discover systems that have sent logs recently"""
        try:
            # Query systemd-journal-remote logs for remote hostnames
            result = subprocess.run(
                ["journalctl", "-u", "systemd-journal-remote.service", 
                 f"--since={since_minutes} minutes ago", "--no-pager"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # Also check journal for _HOSTNAME field (from remote logs)
            result2 = subprocess.run(
                ["journalctl", f"--since={since_minutes} minutes ago",
                 "-o", "json", "--no-pager"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            hostnames = set()
            
            # Parse JSON output for _HOSTNAME field
            for line in result2.stdout.split('\n'):
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    hostname = entry.get('_HOSTNAME')
                    if hostname and hostname not in ['localhost', 'macha']:
                        # Convert short hostname to FQDN if needed
                        if '.' not in hostname:
                            hostname = f"{hostname}.{self.domain}"
                        hostnames.add(hostname)
                except:
                    pass
            
            return list(hostnames)
            
        except Exception as e:
            print(f"Error discovering from journal: {e}")
            return []
    
    def detect_os_type(self, hostname: str) -> str:
        """Detect the operating system of a remote host via SSH"""
        try:
            # Use centralized command pattern - see command_patterns.py
            ssh_cmd = build_ssh_command(hostname, "cat /etc/os-release", timeout=10)
            result = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                os_release = result.stdout.lower()
                
                # Parse os-release
                if 'nixos' in os_release:
                    return 'nixos'
                elif 'ubuntu' in os_release:
                    return 'ubuntu'
                elif 'debian' in os_release:
                    return 'debian'
                elif 'arch' in os_release or 'manjaro' in os_release:
                    return 'arch'
                elif 'fedora' in os_release:
                    return 'fedora'
                elif 'centos' in os_release or 'rhel' in os_release:
                    return 'rhel'
                elif 'alpine' in os_release:
                    return 'alpine'
            
            # Try uname for other systems
            ssh_cmd = build_ssh_command(hostname, "uname -s", timeout=10)
            result = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                uname = result.stdout.strip().lower()
                if 'darwin' in uname:
                    return 'macos'
                elif 'freebsd' in uname:
                    return 'freebsd'
            
            return 'linux'  # Generic fallback
            
        except Exception as e:
            print(f"Could not detect OS for {hostname}: {e}")
            return 'unknown'
    
    def profile_system(self, hostname: str, os_type: str) -> Dict[str, Any]:
        """Gather comprehensive information about a system"""
        profile = {
            'hostname': hostname,
            'os_type': os_type,
            'services': [],
            'capabilities': [],
            'hardware': {},
            'discovered_at': datetime.now().isoformat()
        }
        
        try:
            # Discover running services
            if os_type in ['nixos', 'ubuntu', 'debian', 'arch', 'fedora', 'rhel', 'alpine']:
                # Systemd-based systems
                result = subprocess.run(
                    ["ssh", "-o", "ConnectTimeout=5", hostname,
                     "systemctl list-units --type=service --state=running --no-pager --no-legend"],
                    capture_output=True,
                    text=True,
                    timeout=15
                )
                
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if line.strip():
                            # Extract service name (first column)
                            service = line.split()[0]
                            if service.endswith('.service'):
                                service = service[:-8]  # Remove .service suffix
                            profile['services'].append(service)
            
            # Get hardware info
            result = subprocess.run(
                ["ssh", "-o", "ConnectTimeout=5", hostname,
                 "nproc && free -g | grep Mem | awk '{print $2}'"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if len(lines) >= 2:
                    profile['hardware']['cpu_cores'] = lines[0].strip()
                    profile['hardware']['memory_gb'] = lines[1].strip()
            
            # Detect capabilities based on services
            services_str = ' '.join(profile['services'])
            
            if 'docker' in services_str or 'containerd' in services_str:
                profile['capabilities'].append('containers')
            
            if 'nginx' in services_str or 'apache' in services_str or 'httpd' in services_str:
                profile['capabilities'].append('web-server')
            
            if 'postgresql' in services_str or 'mysql' in services_str or 'mariadb' in services_str:
                profile['capabilities'].append('database')
            
            if 'sshd' in services_str:
                profile['capabilities'].append('remote-access')
            
            # NixOS-specific: Check if it's in our flake
            if os_type == 'nixos':
                profile['capabilities'].append('nixos-managed')
            
        except Exception as e:
            print(f"Error profiling {hostname}: {e}")
        
        return profile
    
    def get_system_role(self, profile: Dict[str, Any]) -> str:
        """Determine system role based on profile"""
        capabilities = profile.get('capabilities', [])
        services = profile.get('services', [])
        
        # Check for specific roles
        if 'ai-inference' in capabilities or 'ollama' in services:
            return 'ai-workstation'
        elif 'web-server' in capabilities:
            return 'web-server'
        elif 'database' in capabilities:
            return 'database-server'
        elif 'containers' in capabilities:
            return 'container-host'
        elif len(services) > 20:
            return 'server'
        elif len(services) > 5:
            return 'workstation'
        else:
            return 'minimal'

