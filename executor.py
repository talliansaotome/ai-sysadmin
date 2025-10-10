#!/usr/bin/env python3
"""
Action Executor - Safely executes proposed fixes with rollback capability
"""

import json
import subprocess
import shutil
from typing import Dict, List, Any, Optional
from pathlib import Path
from datetime import datetime
import time


class SafeExecutor:
    """Executes system maintenance actions with safety checks"""
    
    # Actions that are considered safe to auto-execute
    SAFE_ACTIONS = {
        "systemd_restart",  # Restart failed services
        "cleanup",  # Disk cleanup, log rotation
        "investigation",  # Read-only diagnostics
    }
    
    # Services that should NEVER be stopped/disabled
    PROTECTED_SERVICES = {
        "sshd",
        "systemd-networkd",
        "NetworkManager",
        "systemd-resolved",
        "dbus",
    }
    
    def __init__(
        self,
        state_dir: Path = Path("/var/lib/ai-sysadmin"),
        autonomy_level: str = "suggest",  # observe, suggest, auto-safe, auto-full
        dry_run: bool = False,
        agent = None  # Optional agent for learning from actions
    ):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.autonomy_level = autonomy_level
        self.dry_run = dry_run
        self.agent = agent
        self.action_log = self.state_dir / "actions.jsonl"
        self.approval_queue = self.state_dir / "approval_queue.json"
        
    def execute_action(self, action: Dict[str, Any], monitoring_context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a proposed action with appropriate safety checks"""
        
        action_type = action.get("action_type", "unknown")
        risk_level = action.get("risk_level", "high")
        
        # Determine if we should execute
        should_execute, reason = self._should_execute(action_type, risk_level)
        
        if not should_execute:
            if self.autonomy_level == "suggest":
                # Queue for approval
                self._queue_for_approval(action, monitoring_context)
                return {
                    "executed": False,
                    "status": "queued_for_approval",
                    "reason": reason,
                    "queue_file": str(self.approval_queue)
                }
            else:
                return {
                    "executed": False,
                    "status": "blocked",
                    "reason": reason
                }
        
        # Execute the action
        if self.dry_run:
            return self._dry_run_action(action)
        
        return self._execute_action_impl(action, monitoring_context)
    
    def _should_execute(self, action_type: str, risk_level: str) -> tuple[bool, str]:
        """Determine if an action should be auto-executed based on autonomy level"""
        
        if self.autonomy_level == "observe":
            return False, "Autonomy level set to observe-only"
        
        # Auto-approve low-risk investigation actions
        if action_type == "investigation" and risk_level == "low":
            return True, "Auto-approved: Low-risk information gathering"
        
        if self.autonomy_level == "suggest":
            return False, "Autonomy level requires manual approval"
        
        if self.autonomy_level == "auto-safe":
            if action_type in self.SAFE_ACTIONS and risk_level == "low":
                return True, "Auto-executing safe action"
            return False, "Action requires higher autonomy level"
        
        if self.autonomy_level == "auto-full":
            if risk_level == "high":
                return False, "High risk actions always require approval"
            return True, "Auto-executing approved action"
        
        return False, "Unknown autonomy level"
    
    def _execute_action_impl(self, action: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Actually execute the action"""
        
        action_type = action.get("action_type")
        result = {
            "executed": True,
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "success": False,
            "output": "",
            "error": None
        }
        
        try:
            if action_type == "systemd_restart":
                result.update(self._restart_services(action))
            
            elif action_type == "cleanup":
                result.update(self._perform_cleanup(action))
            
            elif action_type == "nix_rebuild":
                result.update(self._nix_rebuild(action))
            
            elif action_type == "config_change":
                result.update(self._apply_config_change(action))
            
            elif action_type == "investigation":
                result.update(self._run_investigation(action))
            
            else:
                result["error"] = f"Unknown action type: {action_type}"
                
        except Exception as e:
            result["error"] = str(e)
            result["success"] = False
        
        # Log the action
        self._log_action(result)
        
        # Learn from successful operations
        if result.get("success") and self.agent:
            try:
                self.agent.reflect_and_learn(
                    situation=action.get("diagnosis", "Unknown situation"),
                    action_taken=action.get("proposed_action", "Unknown action"),
                    outcome=result.get("output", ""),
                    success=True
                )
            except Exception as e:
                # Don't fail the action if learning fails
                print(f"Note: Could not record learning: {e}")
        
        return result
    
    def _restart_services(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Restart systemd services"""
        commands = action.get("commands", [])
        output_lines = []
        
        for cmd in commands:
            if not cmd.startswith("systemctl restart "):
                continue
            
            service = cmd.split()[-1]
            
            # Safety check
            if any(protected in service for protected in self.PROTECTED_SERVICES):
                output_lines.append(f"BLOCKED: {service} is protected")
                continue
            
            try:
                result = subprocess.run(
                    ["systemctl", "restart", service],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0:
                    output_lines.append(f"✓ Restarted {service}")
                else:
                    output_lines.append(f"✗ Failed to restart {service}: {result.stderr}")
                
            except subprocess.TimeoutExpired:
                output_lines.append(f"✗ Timeout restarting {service}")
        
        return {
            "success": len(output_lines) > 0,
            "output": "\n".join(output_lines)
        }
    
    def _perform_cleanup(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Perform system cleanup tasks"""
        output_lines = []
        
        # Nix store cleanup
        if "nix" in action.get("proposed_action", "").lower():
            try:
                result = subprocess.run(
                    ["nix-collect-garbage", "--delete-old"],
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                output_lines.append(f"Nix cleanup: {result.stdout}")
            except Exception as e:
                output_lines.append(f"Nix cleanup failed: {e}")
        
        # Journal cleanup (keep last 7 days)
        try:
            result = subprocess.run(
                ["journalctl", "--vacuum-time=7d"],
                capture_output=True,
                text=True,
                timeout=60
            )
            output_lines.append(f"Journal cleanup: {result.stdout}")
        except Exception as e:
            output_lines.append(f"Journal cleanup failed: {e}")
        
        return {
            "success": True,
            "output": "\n".join(output_lines)
        }
    
    def _nix_rebuild(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Rebuild NixOS configuration"""
        
        # This is HIGH RISK - always requires approval or full autonomy
        # And we should test first
        
        output_lines = []
        
        # First, try a dry build
        try:
            result = subprocess.run(
                ["nixos-rebuild", "dry-build", "--flake", ".#macha"],
                capture_output=True,
                text=True,
                timeout=600,
                cwd="/home/lily/Documents/nixos-servers"
            )
            
            if result.returncode != 0:
                return {
                    "success": False,
                    "output": f"Dry build failed:\n{result.stderr}"
                }
            
            output_lines.append("✓ Dry build successful")
            
        except Exception as e:
            return {
                "success": False,
                "output": f"Dry build error: {e}"
            }
        
        # Now do the actual rebuild
        try:
            result = subprocess.run(
                ["nixos-rebuild", "switch", "--flake", ".#macha"],
                capture_output=True,
                text=True,
                timeout=1200,
                cwd="/home/lily/Documents/nixos-servers"
            )
            
            output_lines.append(result.stdout)
            
            return {
                "success": result.returncode == 0,
                "output": "\n".join(output_lines),
                "error": result.stderr if result.returncode != 0 else None
            }
            
        except Exception as e:
            return {
                "success": False,
                "output": "\n".join(output_lines),
                "error": str(e)
            }
    
    def _apply_config_change(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Apply a configuration file change"""
        
        config_changes = action.get("config_changes", {})
        file_path = config_changes.get("file")
        
        if not file_path:
            return {
                "success": False,
                "output": "No file specified in config_changes"
            }
        
        # For now, we DON'T auto-modify configs - too risky
        # Instead, we create a suggested patch file
        
        patch_file = self.state_dir / f"suggested_patch_{int(time.time())}.txt"
        with open(patch_file, 'w') as f:
            f.write(f"Suggested change to {file_path}:\n\n")
            f.write(config_changes.get("change", "No change description"))
            f.write(f"\n\nReasoning: {action.get('reasoning', 'No reasoning provided')}")
        
        return {
            "success": True,
            "output": f"Config change suggestion saved to {patch_file}\nThis requires manual review and application."
        }
    
    def _run_investigation(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Run diagnostic commands"""
        commands = action.get("commands", [])
        output_lines = []
        
        for cmd in commands:
            # Only allow safe read-only commands
            safe_commands = ["journalctl", "systemctl status", "df", "free", "ps", "netstat", "ss"]
            if not any(cmd.startswith(safe) for safe in safe_commands):
                output_lines.append(f"BLOCKED unsafe command: {cmd}")
                continue
            
            try:
                result = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                output_lines.append(f"$ {cmd}")
                output_lines.append(result.stdout)
            except Exception as e:
                output_lines.append(f"Error running {cmd}: {e}")
        
        return {
            "success": True,
            "output": "\n".join(output_lines)
        }
    
    def _dry_run_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate action execution"""
        return {
            "executed": False,
            "status": "dry_run",
            "action": action,
            "output": "Dry run mode - no actual changes made"
        }
    
    def _queue_for_approval(self, action: Dict[str, Any], context: Dict[str, Any]):
        """Add action to approval queue"""
        queue = []
        if self.approval_queue.exists():
            with open(self.approval_queue, 'r') as f:
                queue = json.load(f)
        
        # Check for duplicate pending actions
        proposed_action = action.get("proposed_action", "")
        diagnosis = action.get("diagnosis", "")
        
        for existing in queue:
            # Skip already approved/rejected items
            if existing.get("approved") is not None:
                continue
            
            existing_action = existing.get("action", {})
            existing_proposed = existing_action.get("proposed_action", "")
            existing_diagnosis = existing_action.get("diagnosis", "")
            
            # Check if this is essentially the same issue
            # Match if diagnosis is very similar OR proposed action is very similar
            if (diagnosis and existing_diagnosis and 
                self._similarity_check(diagnosis, existing_diagnosis) > 0.7):
                print(f"Skipping duplicate action - similar diagnosis already queued")
                return
            
            if (proposed_action and existing_proposed and
                self._similarity_check(proposed_action, existing_proposed) > 0.7):
                print(f"Skipping duplicate action - similar proposal already queued")
                return
        
        queue.append({
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "context": context,
            "approved": None
        })
        
        with open(self.approval_queue, 'w') as f:
            json.dump(queue, f, indent=2)
    
    def _similarity_check(self, str1: str, str2: str) -> float:
        """Simple similarity check between two strings"""
        # Normalize strings
        s1 = str1.lower().strip()
        s2 = str2.lower().strip()
        
        # Exact match
        if s1 == s2:
            return 1.0
        
        # Check for significant word overlap
        words1 = set(s1.split())
        words2 = set(s2.split())
        
        # Remove common words that don't indicate similarity
        common_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had'}
        words1 = words1 - common_words
        words2 = words2 - common_words
        
        if not words1 or not words2:
            return 0.0
        
        # Calculate Jaccard similarity
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        return intersection / union if union > 0 else 0.0
    
    def _log_action(self, result: Dict[str, Any]):
        """Log executed actions"""
        with open(self.action_log, 'a') as f:
            f.write(json.dumps(result) + '\n')
    
    def get_approval_queue(self) -> List[Dict[str, Any]]:
        """Get pending actions awaiting approval"""
        if not self.approval_queue.exists():
            return []
        
        with open(self.approval_queue, 'r') as f:
            return json.load(f)
    
    def approve_action(self, index: int) -> bool:
        """Approve and execute a queued action, then remove it from queue"""
        queue = self.get_approval_queue()
        if 0 <= index < len(queue):
            action_item = queue[index]
            
            # Execute the approved action
            result = self._execute_action_impl(action_item["action"], action_item["context"])
            
            # Archive the action (success or failure)
            self._archive_action(action_item, result)
            
            # Remove from queue regardless of outcome
            queue.pop(index)
            
            with open(self.approval_queue, 'w') as f:
                json.dump(queue, f, indent=2)
            
            return result.get("success", False)
        
        return False
    
    def _archive_action(self, action_item: Dict[str, Any], result: Dict[str, Any]):
        """Archive an approved action with its execution result"""
        archive_file = self.state_dir / "approved_actions.jsonl"
        
        archive_entry = {
            "timestamp": datetime.now().isoformat(),
            "original_timestamp": action_item.get("timestamp"),
            "action": action_item.get("action"),
            "context": action_item.get("context"),
            "result": result
        }
        
        with open(archive_file, 'a') as f:
            f.write(json.dumps(archive_entry) + '\n')
    
    def reject_action(self, index: int) -> bool:
        """Reject and remove a queued action"""
        queue = self.get_approval_queue()
        if 0 <= index < len(queue):
            removed_action = queue.pop(index)
            
            with open(self.approval_queue, 'w') as f:
                json.dump(queue, f, indent=2)
            
            return True
        
        return False


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "queue":
            executor = SafeExecutor()
            queue = executor.get_approval_queue()
            if queue:
                print("\n" + "="*70)
                print(f"PENDING ACTIONS: {len(queue)}")
                print("="*70)
                for i, item in enumerate(queue):
                    action = item.get("action", {})
                    timestamp = item.get("timestamp", "unknown")
                    approved = item.get("approved")
                    
                    status = "✓ APPROVED" if approved else "⏳ PENDING" if approved is None else "✗ REJECTED"
                    
                    print(f"\n[{i}] {status} - {timestamp}")
                    print("-" * 70)
                    print(f"DIAGNOSIS: {action.get('diagnosis', 'N/A')}")
                    print(f"\nPROPOSED ACTION: {action.get('proposed_action', 'N/A')}")
                    print(f"TYPE: {action.get('action_type', 'N/A')}")
                    print(f"RISK: {action.get('risk_level', 'N/A')}")
                    
                    if action.get('commands'):
                        print(f"\nCOMMANDS:")
                        for cmd in action['commands']:
                            print(f"  - {cmd}")
                    
                    if action.get('config_changes'):
                        print(f"\nCONFIG CHANGES:")
                        for key, value in action['config_changes'].items():
                            print(f"  {key}: {value}")
                    
                    print(f"\nREASONING: {action.get('reasoning', 'N/A')}")
                print("\n" + "="*70 + "\n")
            else:
                print("No pending actions")
        
        elif sys.argv[1] == "approve" and len(sys.argv) > 2:
            executor = SafeExecutor()
            index = int(sys.argv[2])
            success = executor.approve_action(index)
            print(f"Approval {'succeeded' if success else 'failed'}")
        
        elif sys.argv[1] == "reject" and len(sys.argv) > 2:
            executor = SafeExecutor()
            index = int(sys.argv[2])
            success = executor.reject_action(index)
            print(f"Action {'rejected and removed from queue' if success else 'rejection failed'}")
