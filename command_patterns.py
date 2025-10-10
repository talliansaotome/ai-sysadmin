#!/usr/bin/env python3
"""
Command Execution Patterns - SINGLE SOURCE OF TRUTH

DO NOT DUPLICATE THESE PATTERNS ELSEWHERE.
All command execution must use these functions to ensure consistency.

Pattern Rules:
1. SSH keys are ALWAYS explicit: -i /var/lib/ai-sysadmin/.ssh/id_ed25519
2. Remote commands ALWAYS use sudo: ssh user@host sudo command
3. Local commands run as the macha user (no sudo prefix needed when already macha)
"""

from typing import List, Dict, Any
import subprocess

# ============================================================================
# CONSTANTS - DO NOT MODIFY WITHOUT UPDATING DESIGN.MD
# ============================================================================

SSH_KEY_PATH = "/var/lib/ai-sysadmin/.ssh/id_ed25519"
SSH_OPTIONS = ["-o", "StrictHostKeyChecking=no"]
REMOTE_USER = "macha"

# ============================================================================
# SSH COMMAND CONSTRUCTION
# ============================================================================

def build_ssh_command(hostname: str, remote_command: str, timeout: int = 30) -> List[str]:
    """
    Build SSH command with correct patterns.
    
    Args:
        hostname: Target hostname (e.g., 'rhiannon')
        remote_command: Command to execute on remote host
        timeout: Command timeout in seconds
        
    Returns:
        List of command arguments ready for subprocess
        
    Example:
        >>> build_ssh_command("rhiannon", "systemctl status ollama")
        ['ssh', '-i', '/var/lib/ai-sysadmin/.ssh/id_ed25519', '-o', 'StrictHostKeyChecking=no',
         '-o', 'ConnectTimeout=10', 'macha@rhiannon', 'sudo systemctl status ollama']
    """
    cmd = [
        "ssh",
        "-i", SSH_KEY_PATH,
        *SSH_OPTIONS,
        "-o", "ConnectTimeout=10",
        f"{REMOTE_USER}@{hostname}",
        f"sudo {remote_command}"
    ]
    return cmd


def build_scp_command(hostname: str, source: str, dest: str, remote_to_local: bool = True) -> List[str]:
    """
    Build SCP command with correct patterns.
    
    Args:
        hostname: Target hostname
        source: Source path
        dest: Destination path
        remote_to_local: If True, copy from remote to local (default)
        
    Returns:
        List of command arguments ready for subprocess
    """
    if remote_to_local:
        source_spec = f"{REMOTE_USER}@{hostname}:{source}"
        dest_spec = dest
    else:
        source_spec = source
        dest_spec = f"{REMOTE_USER}@{hostname}:{dest}"
    
    cmd = [
        "scp",
        "-i", SSH_KEY_PATH,
        *SSH_OPTIONS,
        source_spec,
        dest_spec
    ]
    return cmd


# ============================================================================
# COMMAND TRANSFORMATION (for tools.py)
# ============================================================================

def transform_ssh_command(command: str) -> str:
    """
    Transform simplified SSH commands to full format.
    
    Converts: "ssh hostname command args"
    To: "ssh -i /path/to/key -o StrictHostKeyChecking=no macha@hostname sudo command args"
    
    Args:
        command: User-provided command string
        
    Returns:
        Transformed command string with proper SSH options
        
    Note:
        This is used by tools.py execute_command for string-based commands.
        For new code, prefer build_ssh_command() which returns a list.
    """
    if not command.strip().startswith('ssh '):
        return command
    
    parts = command.split(maxsplit=2)
    if len(parts) < 2:
        return command
    
    # Check if already has @ (already transformed)
    if '@' in parts[1]:
        return command
    
    hostname = parts[1]
    remaining = parts[2] if len(parts) > 2 else ''
    
    ssh_opts = f"-i {SSH_KEY_PATH} -o StrictHostKeyChecking=no"
    
    if remaining:
        return f"ssh {ssh_opts} {REMOTE_USER}@{hostname} sudo {remaining}"
    else:
        return f"ssh {ssh_opts} {REMOTE_USER}@{hostname}"


# ============================================================================
# EXECUTION HELPERS
# ============================================================================

def execute_ssh_command(
    hostname: str,
    command: str,
    timeout: int = 30,
    capture_output: bool = True
) -> Dict[str, Any]:
    """
    Execute command on remote host via SSH.
    
    Args:
        hostname: Target hostname
        command: Command to execute (will be prefixed with sudo automatically)
        timeout: Command timeout in seconds
        capture_output: Whether to capture stdout/stderr
        
    Returns:
        Dict with keys: success, stdout, stderr, exit_code
    """
    ssh_cmd = build_ssh_command(hostname, command, timeout)
    
    try:
        result = subprocess.run(
            ssh_cmd,
            capture_output=capture_output,
            text=True,
            timeout=timeout
        )
        
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout if capture_output else "",
            "stderr": result.stderr if capture_output else "",
            "exit_code": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Command timed out after {timeout}s",
            "exit_code": -1
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "exit_code": -1
        }


# ============================================================================
# VALIDATION
# ============================================================================

def validate_patterns():
    """
    Self-test to ensure patterns are correct.
    Run this in tests to catch accidental modifications.
    """
    # Test SSH command construction
    cmd = build_ssh_command("testhost", "echo test")
    assert "-i" in cmd, "SSH key flag missing"
    assert SSH_KEY_PATH in cmd, "SSH key path missing"
    assert "macha@testhost" in cmd, "Remote user@host missing"
    assert "sudo echo test" in cmd, "sudo prefix missing"
    
    # Test command transformation
    transformed = transform_ssh_command("ssh rhiannon systemctl status ollama")
    assert SSH_KEY_PATH in transformed, "Key path not added"
    assert "macha@rhiannon" in transformed, "User not added"
    assert "sudo systemctl" in transformed, "sudo not added"
    
    print("✓ Command patterns validated")


if __name__ == "__main__":
    # Run self-tests
    validate_patterns()
    
    # Show examples
    print("\nExample SSH command:")
    print(build_ssh_command("rhiannon", "systemctl status ollama"))
    
    print("\nExample transformation:")
    print(transform_ssh_command("ssh alexander df -h"))

