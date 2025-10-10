#!/usr/bin/env python3
"""
Tool Definitions - Functions that the AI can call to interact with the system
"""

import subprocess
import json
import os
from typing import Dict, Any, List, Optional
from pathlib import Path
from command_patterns import transform_ssh_command


class SysadminTools:
    """Collection of tools for system administration tasks"""
    
    def __init__(self, safe_mode: bool = True):
        """
        Initialize sysadmin tools
        
        Args:
            safe_mode: If True, restricts dangerous operations
        """
        self.safe_mode = safe_mode
        self.allowed_commands = [
            'systemctl', 'journalctl', 'free', 'df', 'uptime',
            'ps', 'top', 'ip', 'ss', 'cat', 'ls', 'grep',
            'ping', 'dig', 'nslookup', 'curl', 'wget',
            'lscpu', 'lspci', 'lsblk', 'lshw', 'dmidecode',
            'ssh', 'scp',  # Remote access to other systems in infrastructure
            'nh', 'nixos-rebuild',  # NixOS system management
            'reboot', 'shutdown', 'poweroff',  # System power management
            'logger'  # Logging for notifications
        ]
    
    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """
        Return tool definitions in Ollama's format
        
        Returns:
            List of tool definitions with JSON schema
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": "execute_command",
                    "description": "Execute a shell command on the system. Use this to run system commands, check status, or gather information. Returns command output.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "The shell command to execute (e.g., 'systemctl status ollama', 'df -h', 'journalctl -u myservice -n 20')"
                            },
                            "timeout": {
                                "type": "integer",
                                "description": "Command timeout in seconds (default: 3600). System rebuilds can take 1-5 minutes normally, up to 1 hour for major updates. Be patient!",
                                "default": 3600
                            }
                        },
                        "required": ["command"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read the contents of a file from the filesystem. Use this to inspect configuration files, logs, or other text files.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Absolute path to the file to read (e.g., '/etc/nixos/configuration.nix', '/var/log/syslog')"
                            },
                            "max_lines": {
                                "type": "integer",
                                "description": "Maximum number of lines to read (default: 500)",
                                "default": 500
                            }
                        },
                        "required": ["file_path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_service_status",
                    "description": "Check the status of a systemd service. Returns whether the service is active, enabled, and recent log entries.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "service_name": {
                                "type": "string",
                                "description": "Name of the systemd service (e.g., 'ollama.service', 'nginx', 'sshd')"
                            }
                        },
                        "required": ["service_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "view_logs",
                    "description": "View systemd journal logs. Can filter by unit, time period, or priority.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "unit": {
                                "type": "string",
                                "description": "Systemd unit name to filter logs (e.g., 'ollama.service')"
                            },
                            "lines": {
                                "type": "integer",
                                "description": "Number of recent log lines to return (default: 50)",
                                "default": 50
                            },
                            "priority": {
                                "type": "string",
                                "description": "Filter by priority: emerg, alert, crit, err, warning, notice, info, debug",
                                "enum": ["emerg", "alert", "crit", "err", "warning", "notice", "info", "debug"]
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_system_metrics",
                    "description": "Get current system resource metrics including CPU, memory, disk, and load average.",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_hardware_info",
                    "description": "Get detailed hardware information including CPU model, GPU, network interfaces, storage devices, and memory specs. Returns comprehensive hardware inventory.",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_gpu_metrics",
                    "description": "Get GPU temperature, utilization, clock speeds, and power usage. Works with AMD and NVIDIA GPUs. Returns current GPU metrics.",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_directory",
                    "description": "List contents of a directory. Returns file names, sizes, and permissions.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "directory_path": {
                                "type": "string",
                                "description": "Absolute path to the directory (e.g., '/etc', '/var/log')"
                            },
                            "show_hidden": {
                                "type": "boolean",
                                "description": "Include hidden files (starting with dot)",
                                "default": False
                            }
                        },
                        "required": ["directory_path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_network",
                    "description": "Test network connectivity to a host. Can use ping or HTTP check.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "host": {
                                "type": "string",
                                "description": "Hostname or IP address to check (e.g., 'google.com', '8.8.8.8')"
                            },
                            "method": {
                                "type": "string",
                                "description": "Test method to use",
                                "enum": ["ping", "http"],
                                "default": "ping"
                            }
                        },
                        "required": ["host"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "retrieve_cached_output",
                    "description": "Retrieve full cached output from a previous tool call. Use this when you need to see complete data that was summarized earlier. The cache_id is shown in hierarchical summaries.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "cache_id": {
                                "type": "string",
                                "description": "Cache ID from a previous tool summary (e.g., 'view_logs_20251006_103045')"
                            },
                            "max_chars": {
                                "type": "integer",
                                "description": "Maximum characters to return (default: 10000 for focused analysis)",
                                "default": 10000
                            }
                        },
                        "required": ["cache_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "send_notification",
                    "description": "Send a notification to the user via Gotify. Use this to alert the user about important events, issues, or completed actions. Choose appropriate priority based on urgency.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {
                                "type": "string",
                                "description": "Notification title (brief, e.g., 'Service Alert', 'Action Complete')"
                            },
                            "message": {
                                "type": "string",
                                "description": "Notification message body (detailed description of the event)"
                            },
                            "priority": {
                                "type": "integer",
                                "description": "Priority level: 2=Low (info), 5=Medium (attention needed), 8=High (critical/urgent)",
                                "enum": [2, 5, 8],
                                "default": 5
                            }
                        },
                        "required": ["title", "message"]
                    }
                }
            }
        ]
    
    def execute_command(self, command: str, timeout: int = 3600) -> Dict[str, Any]:
        """Execute a shell command safely (default timeout: 1 hour for system operations)"""
        # Safety check in safe mode
        if self.safe_mode:
            cmd_base = command.split()[0] if command.strip() else ""
            if cmd_base not in self.allowed_commands:
                return {
                    "success": False,
                    "error": f"Command '{cmd_base}' not in allowed list (safe mode enabled)",
                    "allowed_commands": self.allowed_commands
                }
        
        # Automatically configure SSH commands using centralized command_patterns
        # See command_patterns.py for the single source of truth
        command = transform_ssh_command(command)
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            return {
                "success": result.returncode == 0,
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "command": command
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": f"Command timed out after {timeout} seconds",
                "command": command
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "command": command
            }
    
    def read_file(self, file_path: str, max_lines: int = 500) -> Dict[str, Any]:
        """Read a file safely"""
        try:
            path = Path(file_path)
            
            if not path.exists():
                return {
                    "success": False,
                    "error": f"File not found: {file_path}"
                }
            
            if not path.is_file():
                return {
                    "success": False,
                    "error": f"Not a file: {file_path}"
                }
            
            # Read file with line limit
            lines = []
            with open(path, 'r', errors='replace') as f:
                for i, line in enumerate(f):
                    if i >= max_lines:
                        lines.append(f"\n... truncated after {max_lines} lines ...")
                        break
                    lines.append(line.rstrip('\n'))
            
            return {
                "success": True,
                "content": '\n'.join(lines),
                "path": file_path,
                "lines_read": len(lines)
            }
        except PermissionError:
            return {
                "success": False,
                "error": f"Permission denied: {file_path}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def check_service_status(self, service_name: str) -> Dict[str, Any]:
        """Check systemd service status"""
        # Ensure .service suffix
        if not service_name.endswith('.service'):
            service_name = f"{service_name}.service"
        
        # Get service status
        status_result = self.execute_command(f"systemctl status {service_name}")
        is_active_result = self.execute_command(f"systemctl is-active {service_name}")
        is_enabled_result = self.execute_command(f"systemctl is-enabled {service_name}")
        
        # Get recent logs
        logs_result = self.execute_command(f"journalctl -u {service_name} -n 10 --no-pager")
        
        return {
            "service": service_name,
            "active": is_active_result.get("stdout", "").strip() == "active",
            "enabled": is_enabled_result.get("stdout", "").strip() == "enabled",
            "status_output": status_result.get("stdout", ""),
            "recent_logs": logs_result.get("stdout", "")
        }
    
    def view_logs(
        self,
        unit: Optional[str] = None,
        lines: int = 50,
        priority: Optional[str] = None
    ) -> Dict[str, Any]:
        """View systemd journal logs"""
        cmd_parts = ["journalctl", "--no-pager"]
        
        if unit:
            cmd_parts.extend(["-u", unit])
        
        cmd_parts.extend(["-n", str(lines)])
        
        if priority:
            cmd_parts.extend(["-p", priority])
        
        command = " ".join(cmd_parts)
        result = self.execute_command(command)
        
        return {
            "logs": result.get("stdout", ""),
            "unit": unit,
            "lines": lines,
            "priority": priority
        }
    
    def get_system_metrics(self) -> Dict[str, Any]:
        """Get current system metrics"""
        # CPU and load
        uptime_result = self.execute_command("uptime")
        # Memory
        free_result = self.execute_command("free -h")
        # Disk
        df_result = self.execute_command("df -h")
        
        return {
            "uptime": uptime_result.get("stdout", ""),
            "memory": free_result.get("stdout", ""),
            "disk": df_result.get("stdout", "")
        }
    
    def get_hardware_info(self) -> Dict[str, Any]:
        """Get comprehensive hardware information"""
        hardware = {}
        
        # CPU info (use nix-shell for util-linux)
        cpu_result = self.execute_command("nix-shell -p util-linux --run lscpu")
        if cpu_result.get("success"):
            hardware["cpu"] = cpu_result.get("stdout", "")
        
        # Memory details
        mem_result = self.execute_command("free -h")
        if mem_result.get("success"):
            hardware["memory"] = mem_result.get("stdout", "")
        
        # GPU info (lspci for AMD/NVIDIA) - use nix-shell for pciutils
        gpu_result = self.execute_command("nix-shell -p pciutils --run \"lspci | grep -i 'vga\\|3d\\|display'\"")
        if gpu_result.get("success"):
            hardware["gpu"] = gpu_result.get("stdout", "")
        
        # Detailed GPU
        lspci_detailed = self.execute_command("nix-shell -p pciutils --run \"lspci -v | grep -A 20 -i 'vga\\|3d\\|display'\"")
        if lspci_detailed.get("success"):
            hardware["gpu_detailed"] = lspci_detailed.get("stdout", "")
        
        # Network interfaces
        net_result = self.execute_command("ip link show")
        if net_result.get("success"):
            hardware["network_interfaces"] = net_result.get("stdout", "")
        
        # Network addresses
        addr_result = self.execute_command("ip addr show")
        if addr_result.get("success"):
            hardware["network_addresses"] = addr_result.get("stdout", "")
        
        # Storage devices (use nix-shell for util-linux)
        storage_result = self.execute_command("nix-shell -p util-linux --run \"lsblk -o NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE\"")
        if storage_result.get("success"):
            hardware["storage"] = storage_result.get("stdout", "")
        
        # PCI devices (comprehensive)
        pci_result = self.execute_command("nix-shell -p pciutils --run lspci")
        if pci_result.get("success"):
            hardware["pci_devices"] = pci_result.get("stdout", "")
        
        # USB devices
        usb_result = self.execute_command("nix-shell -p usbutils --run lsusb")
        if usb_result.get("success"):
            hardware["usb_devices"] = usb_result.get("stdout", "")
        
        # DMI/SMBIOS info (motherboard, system)
        dmi_result = self.execute_command("cat /sys/class/dmi/id/board_name /sys/class/dmi/id/board_vendor 2>/dev/null")
        if dmi_result.get("success"):
            hardware["motherboard"] = dmi_result.get("stdout", "")
        
        return hardware
    
    def get_gpu_metrics(self) -> Dict[str, Any]:
        """Get GPU metrics (temperature, utilization, clocks, power)"""
        metrics = {}
        
        # Try AMD GPU via sysfs (DRM/hwmon)
        try:
            # Find GPU hwmon directory
            import glob
            hwmon_dirs = glob.glob("/sys/class/drm/card*/device/hwmon/hwmon*")
            
            if hwmon_dirs:
                hwmon_path = hwmon_dirs[0]
                amd_metrics = {}
                
                # Temperature
                temp_files = glob.glob(f"{hwmon_path}/temp*_input")
                for temp_file in temp_files:
                    try:
                        with open(temp_file, 'r') as f:
                            temp_millidegrees = int(f.read().strip())
                            temp_celsius = temp_millidegrees / 1000
                            label = temp_file.split('/')[-1].replace('_input', '')
                            amd_metrics[f"{label}_celsius"] = temp_celsius
                    except:
                        pass
                
                # GPU busy percent (utilization)
                gpu_busy_file = f"{hwmon_path.replace('/hwmon/hwmon', '')}/gpu_busy_percent"
                try:
                    with open(gpu_busy_file, 'r') as f:
                        amd_metrics["gpu_utilization_percent"] = int(f.read().strip())
                except:
                    pass
                
                # Power usage
                power_files = glob.glob(f"{hwmon_path}/power*_average")
                for power_file in power_files:
                    try:
                        with open(power_file, 'r') as f:
                            power_microwatts = int(f.read().strip())
                            power_watts = power_microwatts / 1000000
                            amd_metrics["power_watts"] = power_watts
                    except:
                        pass
                
                # Clock speeds
                sclk_file = f"{hwmon_path.replace('/hwmon/hwmon', '')}/pp_dpm_sclk"
                try:
                    with open(sclk_file, 'r') as f:
                        sclk_data = f.read()
                        amd_metrics["gpu_clocks"] = sclk_data.strip()
                except:
                    pass
                
                if amd_metrics:
                    metrics["amd_gpu"] = amd_metrics
        except Exception as e:
            metrics["amd_sysfs_error"] = str(e)
        
        # Try rocm-smi for AMD
        rocm_result = self.execute_command("nix-shell -p rocmPackages.rocm-smi --run 'rocm-smi --showtemp --showuse --showpower'")
        if rocm_result.get("success"):
            metrics["rocm_smi"] = rocm_result.get("stdout", "")
        
        # Try nvidia-smi for NVIDIA
        nvidia_result = self.execute_command("nix-shell -p linuxPackages.nvidia_x11 --run 'nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,power.draw,clocks.gr --format=csv'")
        if nvidia_result.get("success") and "NVIDIA" in nvidia_result.get("stdout", ""):
            metrics["nvidia_smi"] = nvidia_result.get("stdout", "")
        
        # Fallback: try sensors command
        if not metrics.get("amd_gpu") and not metrics.get("nvidia_smi"):
            sensors_result = self.execute_command("nix-shell -p lm_sensors --run sensors")
            if sensors_result.get("success"):
                metrics["sensors"] = sensors_result.get("stdout", "")
        
        return metrics
    
    def list_directory(
        self,
        directory_path: str,
        show_hidden: bool = False
    ) -> Dict[str, Any]:
        """List directory contents"""
        cmd = f"ls -lh"
        if show_hidden:
            cmd += "a"
        cmd += f" {directory_path}"
        
        result = self.execute_command(cmd)
        
        return {
            "success": result.get("success", False),
            "directory": directory_path,
            "listing": result.get("stdout", ""),
            "error": result.get("error")
        }
    
    def check_network(self, host: str, method: str = "ping") -> Dict[str, Any]:
        """Check network connectivity"""
        if method == "ping":
            cmd = f"ping -c 3 -W 2 {host}"
        elif method == "http":
            cmd = f"curl -I -m 5 {host}"
        else:
            return {
                "success": False,
                "error": f"Unknown method: {method}"
            }
        
        result = self.execute_command(cmd, timeout=10)
        
        return {
            "host": host,
            "method": method,
            "reachable": result.get("success", False),
            "output": result.get("stdout", ""),
            "error": result.get("stderr", "")
        }
    
    def retrieve_cached_output(self, cache_id: str, max_chars: int = 10000) -> Dict[str, Any]:
        """Retrieve full cached output from a previous tool call"""
        cache_dir = Path("/var/lib/ai-sysadmin/tool_cache")
        cache_file = cache_dir / f"{cache_id}.txt"
        
        if not cache_file.exists():
            return {
                "success": False,
                "error": f"Cache file not found: {cache_id}",
                "hint": "Check that the cache_id matches exactly what was shown in the summary"
            }
        
        try:
            content = cache_file.read_text()
            
            # Truncate if still too large for context
            if len(content) > max_chars:
                half = max_chars // 2
                content = (
                    content[:half] + 
                    f"\n... [SHOWING {max_chars} of {len(content)} chars] ...\n" +
                    content[-half:]
                )
            
            return {
                "success": True,
                "cache_id": cache_id,
                "size": len(cache_file.read_text()),  # Original size
                "content": content
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to read cache: {str(e)}"
            }
    
    def send_notification(self, title: str, message: str, priority: int = 5) -> Dict[str, Any]:
        """Send a notification to the user via Gotify using macha-notify command"""
        try:
            # Use the macha-notify command which handles Gotify integration
            result = subprocess.run(
                ['macha-notify', title, message, str(priority)],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                return {
                    "success": True,
                    "title": title,
                    "message": message,
                    "priority": priority,
                    "output": result.stdout.strip() if result.stdout else "Notification sent successfully"
                }
            else:
                return {
                    "success": False,
                    "error": f"macha-notify failed: {result.stderr.strip() if result.stderr else 'Unknown error'}",
                    "hint": "Check if Gotify is configured (gotifyUrl and gotifyToken in module config)"
                }
        except FileNotFoundError:
            return {
                "success": False,
                "error": "macha-notify command not found",
                "hint": "This should not happen - macha-notify is installed by the module"
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Notification send timeout (10s)"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Unexpected error sending notification: {str(e)}"
            }
    
    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool by name with given arguments"""
        tool_map = {
            "execute_command": self.execute_command,
            "read_file": self.read_file,
            "check_service_status": self.check_service_status,
            "view_logs": self.view_logs,
            "get_system_metrics": self.get_system_metrics,
            "get_hardware_info": self.get_hardware_info,
            "get_gpu_metrics": self.get_gpu_metrics,
            "list_directory": self.list_directory,
            "check_network": self.check_network,
            "retrieve_cached_output": self.retrieve_cached_output,
            "send_notification": self.send_notification
        }
        
        tool_func = tool_map.get(tool_name)
        if not tool_func:
            return {
                "success": False,
                "error": f"Unknown tool: {tool_name}"
            }
        
        try:
            return tool_func(**arguments)
        except Exception as e:
            return {
                "success": False,
                "error": f"Tool execution failed: {str(e)}",
                "tool": tool_name,
                "arguments": arguments
            }

