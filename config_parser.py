#!/usr/bin/env python3
"""
Config Parser - Extract imports and content from NixOS configuration files
"""

import re
import subprocess
from pathlib import Path
from typing import List, Dict, Set, Optional
from datetime import datetime


class ConfigParser:
    """Parse NixOS flake and configuration files"""
    
    def __init__(self, repo_url: str, local_path: Path = Path("/var/lib/ai-sysadmin/config-repo")):
        """
        Initialize config parser
        
        Args:
            repo_url: Git repository URL (e.g., git+https://...)
            local_path: Where to clone/update the repository
        """
        # Strip git+ prefix if present for git commands
        self.repo_url = repo_url.replace("git+", "")
        self.local_path = local_path
        self.local_path.mkdir(parents=True, exist_ok=True)
        
    def ensure_repo(self) -> bool:
        """Clone or update the repository"""
        try:
            if (self.local_path / ".git").exists():
                # Update existing repo
                result = subprocess.run(
                    ["git", "-C", str(self.local_path), "pull"],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                return result.returncode == 0
            else:
                # Clone new repo
                result = subprocess.run(
                    ["git", "clone", self.repo_url, str(self.local_path)],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                return result.returncode == 0
        except Exception as e:
            print(f"Error updating repository: {e}")
            return False
    
    def get_systems_from_flake(self) -> List[str]:
        """Extract system names from flake.nix"""
        flake_path = self.local_path / "flake.nix"
        if not flake_path.exists():
            return []
        
        systems = []
        try:
            content = flake_path.read_text()
            # Match patterns like: "macha" = nixpkgs.lib.nixosSystem
            matches = re.findall(r'"([^"]+)"\s*=\s*nixpkgs\.lib\.nixosSystem', content)
            systems = matches
        except Exception as e:
            print(f"Error parsing flake.nix: {e}")
        
        return systems
    
    def extract_imports(self, nix_file: Path) -> List[str]:
        """Extract imports from a .nix file"""
        if not nix_file.exists():
            return []
        
        imports = []
        try:
            content = nix_file.read_text()
            
            # Find the imports = [ ... ]; block
            imports_match = re.search(
                r'imports\s*=\s*\[(.*?)\];',
                content,
                re.DOTALL
            )
            
            if imports_match:
                imports_block = imports_match.group(1)
                # Extract all paths (relative paths starting with ./ or ../)
                paths = re.findall(r'[./]+[^\s\]]+\.nix', imports_block)
                imports = paths
                
        except Exception as e:
            print(f"Error parsing {nix_file}: {e}")
        
        return imports
    
    def resolve_import_path(self, base_file: Path, import_path: str) -> Optional[Path]:
        """Resolve a relative import path to absolute path within repo"""
        try:
            # Get directory of the base file
            base_dir = base_file.parent
            # Resolve the relative path
            resolved = (base_dir / import_path).resolve()
            # Make sure it's within the repo
            if self.local_path in resolved.parents or resolved == self.local_path:
                return resolved
        except Exception as e:
            print(f"Error resolving import {import_path} from {base_file}: {e}")
        return None
    
    def get_system_config(self, system_name: str) -> Dict[str, any]:
        """
        Get configuration for a specific system
        
        Returns:
            Dict with:
            - main_file: Path to systems/<name>.nix
            - imports: List of imported file paths (relative to repo root)
            - all_files: Set of all .nix files used (including recursive imports)
        """
        main_file = self.local_path / "systems" / f"{system_name}.nix"
        
        if not main_file.exists():
            return {
                "main_file": None,
                "imports": [],
                "all_files": set()
            }
        
        # Track all files (avoid infinite loops)
        all_files = set()
        files_to_process = [main_file]
        processed = set()
        
        while files_to_process:
            current_file = files_to_process.pop(0)
            
            if current_file in processed:
                continue
            processed.add(current_file)
            
            # Get relative path from repo root
            try:
                rel_path = current_file.relative_to(self.local_path)
                all_files.add(str(rel_path))
            except ValueError:
                continue
            
            # Extract imports from this file
            imports = self.extract_imports(current_file)
            
            # Resolve and queue imported files
            for imp in imports:
                resolved = self.resolve_import_path(current_file, imp)
                if resolved and resolved not in processed:
                    files_to_process.append(resolved)
        
        return {
            "main_file": str(main_file.relative_to(self.local_path)),
            "imports": self.extract_imports(main_file),
            "all_files": sorted(all_files)
        }
    
    def read_file_content(self, relative_path: str) -> Optional[str]:
        """Read content of a file by its path relative to repo root"""
        try:
            file_path = self.local_path / relative_path
            if file_path.exists():
                return file_path.read_text()
        except Exception as e:
            print(f"Error reading {relative_path}: {e}")
        return None
    
    def get_all_config_files(self) -> List[Dict[str, str]]:
        """
        Get all .nix files in the repository with their content
        
        Returns:
            List of dicts with:
            - path: relative path from repo root
            - content: file contents
            - category: apps/systems/osconfigs/users based on path
        """
        files = []
        
        # Categories to scan
        categories = {
            "apps": self.local_path / "apps",
            "systems": self.local_path / "systems",
            "osconfigs": self.local_path / "osconfigs",
            "users": self.local_path / "users"
        }
        
        for category, path in categories.items():
            if not path.exists():
                continue
            
            for nix_file in path.rglob("*.nix"):
                try:
                    rel_path = nix_file.relative_to(self.local_path)
                    content = nix_file.read_text()
                    
                    files.append({
                        "path": str(rel_path),
                        "content": content,
                        "category": category
                    })
                except Exception as e:
                    print(f"Error reading {nix_file}: {e}")
        
        return files


if __name__ == "__main__":
    # Test the parser
    import sys
    
    repo_url = "git+https://git.local/lily/nixos-servers"
    parser = ConfigParser(repo_url)
    
    print("Ensuring repository is up to date...")
    if parser.ensure_repo():
        print("✓ Repository ready")
    else:
        print("✗ Failed to update repository")
        sys.exit(1)
    
    print("\nSystems defined in flake:")
    systems = parser.get_systems_from_flake()
    for system in systems:
        print(f"  - {system}")
    
    if len(sys.argv) > 1:
        system_name = sys.argv[1]
        print(f"\nConfiguration for {system_name}:")
        config = parser.get_system_config(system_name)
        
        print(f"  Main file: {config['main_file']}")
        print(f"  Direct imports: {len(config['imports'])}")
        print(f"  All files used: {len(config['all_files'])}")
        
        for f in config['all_files']:
            print(f"    - {f}")

