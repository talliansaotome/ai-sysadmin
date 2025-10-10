#!/usr/bin/env python3
"""
Git Context - Extract context from NixOS configuration repository
"""

import subprocess
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path


class GitContext:
    """Extract context from git repository"""
    
    def __init__(self, repo_path: str = "/etc/nixos"):
        """
        Initialize git context extractor
        
        Args:
            repo_path: Path to the git repository (default: /etc/nixos for NixOS systems)
        """
        self.repo_path = Path(repo_path)
        
    def _run_git(self, args: List[str]) -> tuple[bool, str]:
        """Run git command"""
        try:
            result = subprocess.run(
                ["git", "-C", str(self.repo_path)] + args,
                capture_output=True,
                text=True,
                timeout=10
            )
            return (result.returncode == 0, result.stdout.strip())
        except Exception as e:
            return (False, str(e))
    
    def get_current_branch(self) -> str:
        """Get current git branch"""
        success, output = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        return output if success else "unknown"
    
    def get_remote_url(self) -> str:
        """Get git remote URL"""
        success, output = self._run_git(["remote", "get-url", "origin"])
        return output if success else ""
    
    def get_recent_commits(self, count: int = 10, since: str = "1 week ago") -> List[Dict[str, str]]:
        """
        Get recent commits
        
        Args:
            count: Number of commits to retrieve
            since: Time range (e.g., "1 week ago", "3 days ago")
            
        Returns:
            List of commit dictionaries with hash, author, date, message
        """
        success, output = self._run_git([
            "log",
            f"--since={since}",
            f"-n{count}",
            "--format=%H|%an|%ar|%s"
        ])
        
        if not success:
            return []
        
        commits = []
        for line in output.split('\n'):
            if not line.strip():
                continue
            parts = line.split('|', 3)
            if len(parts) == 4:
                commits.append({
                    "hash": parts[0][:8],  # Short hash
                    "author": parts[1],
                    "date": parts[2],
                    "message": parts[3]
                })
        
        return commits
    
    def get_system_config_files(self, system_name: str) -> List[str]:
        """
        Get configuration files for a specific system
        
        Args:
            system_name: Name of the system (e.g., "macha", "rhiannon")
            
        Returns:
            List of configuration file paths
        """
        system_dir = self.repo_path / "systems" / system_name
        config_files = []
        
        if system_dir.exists():
            # Main config
            if (system_dir.parent / f"{system_name}.nix").exists():
                config_files.append(f"systems/{system_name}.nix")
            
            # System-specific configs
            for config_file in system_dir.rglob("*.nix"):
                config_files.append(str(config_file.relative_to(self.repo_path)))
        
        return config_files
    
    def get_recent_changes_for_system(self, system_name: str, since: str = "1 week ago") -> List[Dict[str, str]]:
        """
        Get recent changes affecting a specific system
        
        Args:
            system_name: Name of the system
            since: Time range
            
        Returns:
            List of commits that affected this system
        """
        config_files = self.get_system_config_files(system_name)
        
        if not config_files:
            return []
        
        # Get commits that touched these files
        file_args = []
        for f in config_files:
            file_args.extend(["--", f])
        
        success, output = self._run_git([
            "log",
            f"--since={since}",
            "-n10",
            "--format=%H|%an|%ar|%s"
        ] + file_args)
        
        if not success:
            return []
        
        commits = []
        for line in output.split('\n'):
            if not line.strip():
                continue
            parts = line.split('|', 3)
            if len(parts) == 4:
                commits.append({
                    "hash": parts[0][:8],
                    "author": parts[1],
                    "date": parts[2],
                    "message": parts[3]
                })
        
        return commits
    
    def get_system_context_summary(self, system_name: str) -> str:
        """
        Get a summary of git context for a system
        
        Args:
            system_name: Name of the system
            
        Returns:
            Human-readable summary
        """
        lines = []
        
        # Repository info
        repo_url = self.get_remote_url()
        branch = self.get_current_branch()
        
        if repo_url:
            lines.append(f"Configuration Repository: {repo_url}")
        lines.append(f"Branch: {branch}")
        
        # Recent changes to this system
        recent_changes = self.get_recent_changes_for_system(system_name, "2 weeks ago")
        
        if recent_changes:
            lines.append(f"\nRecent configuration changes (last 2 weeks):")
            for commit in recent_changes[:5]:
                lines.append(f"  - {commit['date']}: {commit['message']} ({commit['author']})")
        else:
            lines.append("\nNo recent configuration changes")
        
        return "\n".join(lines)
    
    def get_all_managed_systems(self) -> List[str]:
        """
        Get list of all systems managed by this repository
        
        Returns:
            List of system names
        """
        systems = []
        systems_dir = self.repo_path / "systems"
        
        if systems_dir.exists():
            for system_file in systems_dir.glob("*.nix"):
                if system_file.stem not in ["default"]:
                    systems.append(system_file.stem)
        
        return sorted(systems)


if __name__ == "__main__":
    import sys
    
    git = GitContext()
    
    print("Repository:", git.get_remote_url())
    print("Branch:", git.get_current_branch())
    print("\nManaged Systems:")
    for system in git.get_all_managed_systems():
        print(f"  - {system}")
    
    print("\nRecent Commits:")
    for commit in git.get_recent_commits(5):
        print(f"  {commit['hash']}: {commit['message']} - {commit['author']}, {commit['date']}")
    
    if len(sys.argv) > 1:
        system = sys.argv[1]
        print(f"\nContext for {system}:")
        print(git.get_system_context_summary(system))

