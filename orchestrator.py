#!/usr/bin/env python3
"""
Orchestrator - Main control loop for Macha's autonomous system
"""

import json
import time
import signal
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

from monitor import SystemMonitor
from agent import MachaAgent
from executor import SafeExecutor
from notifier import GotifyNotifier
from context_db import ContextDatabase
from remote_monitor import RemoteMonitor
from config_parser import ConfigParser
from system_discovery import SystemDiscovery
from issue_tracker import IssueTracker
from git_context import GitContext
from typing import List


class MachaOrchestrator:
    """Main orchestrator for autonomous system maintenance"""
    
    def __init__(
        self,
        check_interval: int = 300,  # 5 minutes
        autonomy_level: str = "suggest",
        state_dir: Path = Path("/var/lib/ai-sysadmin"),
        config_file: Path = Path("/etc/ai-sysadmin/config.json"),
        remote_systems: list = None
    ):
        self.check_interval = check_interval
        self.autonomy_level = autonomy_level
        self.state_dir = state_dir
        self.config_file = config_file
        self.running = False
        self.remote_systems = remote_systems or []
        
        # Set log file early so _log() works
        self.log_file = self.state_dir / "orchestrator.log"
        
        # Load config if exists
        self._load_config()
        
        # Initialize context database first
        try:
            self.context_db = ContextDatabase()
        except Exception as e:
            self._log(f"Warning: Could not connect to ChromaDB: {e}")
            self._log("Continuing without context database")
            self.context_db = None
        
        # Initialize config parser
        self.config_parser = None
        if self.context_db and self.config_repo:
            try:
                self.config_parser = ConfigParser(self.config_repo)
            except Exception as e:
                self._log(f"Warning: Could not initialize config parser: {e}")
        
        # Initialize git context
        self.git_context = None
        if self.config_parser:
            try:
                # Use the same local repo path as config_parser
                local_repo_path = Path("/var/lib/ai-sysadmin/config-repo")
                if local_repo_path.exists():
                    self.git_context = GitContext(repo_path=str(local_repo_path))
                    self._log(f"Git context initialized for {local_repo_path}")
                else:
                    self._log(f"Warning: Config repo not found at {local_repo_path}")
            except Exception as e:
                self._log(f"Warning: Could not initialize git context: {e}")
        
        # Initialize components
        self.monitor = SystemMonitor(state_dir)
        self.agent = MachaAgent(
            ollama_host=self.ollama_host,
            model=self.model,
            state_dir=state_dir,
            context_db=self.context_db,
            config_repo=self.config_repo,
            config_branch=self.config_branch,
            ai_name=self.ai_name,
            use_queue=True,
            priority="AUTONOMOUS"
        )
        self.executor = SafeExecutor(
            state_dir=state_dir,
            autonomy_level=self.autonomy_level,
            agent=self.agent
        )
        self.notifier = GotifyNotifier()
        self.discovery = SystemDiscovery(domain="coven.systems")
        self.issue_tracker = IssueTracker(
            context_db=self.context_db,
            log_dir=str(state_dir / "logs")
        ) if self.context_db else None
        
        # Initialize system registry
        if self.context_db:
            try:
                self._initialize_system_registry()
            except Exception as e:
                self._log(f"Warning: Could not initialize system registry: {e}")
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _load_config(self):
        """Load configuration from file"""
        import os
        import socket
        
        self.ollama_host = "http://localhost:11434"  # Default
        self.model = "gpt-oss:latest"  # Default
        self.ai_name = socket.gethostname().split('.')[0]  # Default to short hostname
        
        # Try to get flake URL from NH_FLAKE environment variable (set by nh tool)
        nh_flake = os.environ.get("NH_FLAKE", "")
        if nh_flake:
            self.config_repo = nh_flake
            self.config_branch = "main"  # NH doesn't specify branch
        else:
            self.config_repo = "git+https://git.coven.systems/lily/nixos-servers"
            self.config_branch = "main"
        
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    self.check_interval = config.get("check_interval", self.check_interval)
                    self.autonomy_level = config.get("autonomy_level", self.autonomy_level)
                    self.ollama_host = config.get("ollama_host", self.ollama_host)
                    self.model = config.get("model", self.model)
                    self.ai_name = config.get("ai_name", self.ai_name)
                    # Config file can override NH_FLAKE
                    self.config_repo = config.get("config_repo", self.config_repo)
                    self.config_branch = config.get("config_branch", self.config_branch)
                    self._log(f"Loaded config: ai_name={self.ai_name}, model={self.model}, ollama_host={self.ollama_host}, repo={self.config_repo}")
            except Exception as e:
                self._log(f"Failed to load config: {e}")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self._log(f"Received signal {signum}, shutting down gracefully...")
        self.running = False
    
    def _log(self, message: str):
        """Log a message"""
        timestamp = datetime.now().isoformat()
        log_line = f"[{timestamp}] {message}"
        print(log_line)
        
        with open(self.log_file, 'a') as f:
            f.write(log_line + '\n')
    
    def _initialize_system_registry(self):
        """Initialize the system registry in ChromaDB"""
        if not self.context_db:
            return
        
        import socket
        hostname = socket.gethostname()
        
        # Add FQDN
        fqdn = f"{hostname}.coven.systems"
        
        # Register self (Macha) - discover local services
        local_services = self._discover_local_services()
        self._log(f"Registering {fqdn} with repo={self.config_repo}, branch={self.config_branch}")
        self.context_db.register_system(
            hostname=fqdn,
            system_type="workstation",
            services=local_services,
            capabilities=["ai-inference", "system-orchestration", "log-aggregation"],
            metadata={"role": "controller", "local": True},
            config_repo=self.config_repo,
            config_branch=self.config_branch,
            os_type="nixos"
        )
        
        # Register remote systems and discover their services
        for remote in self.remote_systems:
            remote_services = self._discover_remote_services(remote)
            self.context_db.register_system(
                hostname=remote,
                system_type="server",
                services=remote_services,
                capabilities=[],
                config_repo=self.config_repo,
                config_branch=self.config_branch,
                os_type="nixos"  # Assume NixOS for now, will be detected during auto-discovery
                )
            
        self._log("System registry initialized")
        
        # Parse and store configuration files
        self._parse_and_store_configs()
    
    def _discover_local_services(self) -> List[str]:
        """Discover services running on local system"""
        import subprocess
        
        services = set()
        try:
            # Get all active services
            result = subprocess.run(
                ["systemctl", "list-units", "--type=service", "--state=running", "--no-pager", "--no-legend"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line.strip():
                        # Extract service name (first column)
                        service_name = line.split()[0].replace('.service', '')
                        
                        # Filter to interesting application services
                        if any(keyword in service_name.lower() for keyword in [
                            'ollama', 'chroma', 'autonomous', 'gotify', 'nextcloud',
                            'prowlarr', 'radarr', 'sonarr', 'whisparr', 'lidarr', 'readarr',
                            'sabnzbd', 'transmission', 'calibre', 'gpclient'
                        ]):
                            services.add(service_name)
                            
        except Exception as e:
            self._log(f"Warning: Could not discover local services: {e}")
        
        return sorted(services)
    
    def _discover_remote_services(self, hostname: str) -> List[str]:
        """Discover services running on remote system via journal"""
        if not hasattr(self, 'journal_monitor'):
            from journal_monitor import JournalMonitor
            self.journal_monitor = JournalMonitor()
        
        try:
            services = self.journal_monitor.get_active_services(hostname)
            self._log(f"Discovered {len(services)} services on {hostname}: {', '.join(services[:5])}")
            return services
        except Exception as e:
            self._log(f"Warning: Could not discover services on {hostname}: {e}")
            return []
    
    def _update_service_registry(self):
        """Periodically update the service registry with current running services"""
        if not self.context_db:
            return
        
        import socket
        hostname = socket.gethostname()
        fqdn = f"{hostname}.coven.systems"
        
        # Update local services
        local_services = self._discover_local_services()
        self.context_db.register_system(
            hostname=fqdn,
            system_type="workstation",
            services=local_services,
            capabilities=["ai-inference", "system-orchestration", "log-aggregation"],
            metadata={"role": "controller", "local": True},
            config_repo=self.config_repo,
            config_branch=self.config_branch,
            os_type="nixos"
        )
        
        # Update remote systems
        for remote in self.remote_systems:
            remote_services = self._discover_remote_services(remote)
            if remote_services:
                self.context_db.register_system(
                    hostname=remote,
                    system_type="server",
                    services=remote_services,
                    capabilities=[],
                    config_repo=self.config_repo,
                    config_branch=self.config_branch,
                    os_type="nixos"  # Will be updated by auto-discovery
                )
    
    def _discover_new_systems(self):
        """Discover new systems from journal logs and register them"""
        if not self.context_db or not self.discovery:
            return
        
        try:
            # Get known systems from database
            known_hostnames = self.context_db.get_known_hostnames()
            
            # Discover systems from journal (last 10 minutes)
            discovered = self.discovery.discover_from_journal(since_minutes=10)
            
            # Filter to new systems only
            new_systems = [h for h in discovered if h not in known_hostnames]
            
            if not new_systems:
                return
            
            self._log(f"🔍 Discovered {len(new_systems)} new system(s): {', '.join(new_systems)}")
            
            # Get systems defined in flake for comparison
            flake_systems = []
            if self.config_parser:
                try:
                    flake_systems = self.config_parser.get_systems_from_flake()
                    self._log(f"Flake defines {len(flake_systems)} systems: {', '.join(flake_systems)}")
                except Exception as e:
                    self._log(f"Could not get flake systems: {e}")
            
            # Process each new system separately
            for hostname in new_systems:
                try:
                    self._log(f"📡 Analyzing new system: {hostname}")
                    
                    # Check if system is defined in flake
                    short_hostname = hostname.split('.')[0]  # Get 'rhiannon' from 'rhiannon.coven.systems'
                    in_flake = short_hostname in flake_systems
                    
                    if in_flake:
                        self._log(f"  ✓ System IS defined in flake as '{short_hostname}'")
                    else:
                        self._log(f"  ⚠ System NOT found in flake (unmanaged)")
                    
                    # Detect OS type
                    os_type = self.discovery.detect_os_type(hostname)
                    self._log(f"  OS detected: {os_type.upper()}")
                    
                    # Profile the system
                    profile = self.discovery.profile_system(hostname, os_type)
                    
                    # Determine role
                    role = self.discovery.get_system_role(profile)
                    self._log(f"  Role: {role}")
                    self._log(f"  Services: {len(profile['services'])} discovered")
                    
                    # Register in database
                    self.context_db.register_system(
                        hostname=hostname,
                        system_type=role,
                        services=profile['services'],
                        capabilities=profile['capabilities'],
                        metadata={
                            'discovered_at': profile['discovered_at'],
                            'hardware': profile.get('hardware', {}),
                            'auto_discovered': True,
                            'in_flake': in_flake,
                            'flake_name': short_hostname if in_flake else None
                        },
                        config_repo=self.config_repo if (os_type == 'nixos' and in_flake) else "",
                        config_branch=self.config_branch if (os_type == 'nixos' and in_flake) else "",
                        os_type=os_type
                    )
                    
                    # Send notification (with flake info)
                    if self.notifier:
                        message = (
                            f"🔍 New System Auto-Discovered\n\n"
                            f"Hostname: {hostname}\n"
                            f"OS: {os_type.upper()}\n"
                            f"Role: {role}\n"
                            f"Services: {len(profile['services'])} detected\n"
                            f"In Flake: {'✓ Yes' if in_flake else '✗ No (unmanaged)'}\n\n"
                            f"System has been registered and analyzed.\n"
                            f"Use 'macha-systems' to view all registered systems."
                        )
                        self.notifier.send(
                            title="🌐 Macha: New System Discovered",
                            message=message,
                            priority=self.notifier.PRIORITY_MEDIUM
                        )
                    
                    # Run separate analysis for this system (include flake status)
                    profile['in_flake'] = in_flake
                    profile['flake_name'] = short_hostname if in_flake else None
                    self._analyze_new_system(hostname, profile)
                    
                except Exception as e:
                    self._log(f"❌ Error processing {hostname}: {e}")
                    
        except Exception as e:
            self._log(f"Error during system discovery: {e}")
    
    def _analyze_new_system(self, hostname: str, profile: Dict[str, Any]):
        """Run a focused analysis on a newly discovered system"""
        try:
            self._log(f"🧠 Running AI analysis of {hostname}...")
            
            # Gather system context from ChromaDB
            system_context = self.context_db.get_system_context(hostname)
            
            # Create analysis prompt focused on this specific system
            in_flake = profile.get('in_flake', False)
            flake_name = profile.get('flake_name', '')
            
            flake_status = ""
            if in_flake:
                flake_status = f"\n✓ This system IS defined in the flake as '{flake_name}'"
                flake_status += f"\n  You can review its intended configuration at: systems/{flake_name}.nix"
                flake_status += f"\n  Compare actual vs expected to identify drift."
            else:
                flake_status = f"\n⚠ This system is NOT in the flake (unmanaged system)"
                flake_status += f"\n  You cannot manage its NixOS configuration directly."
            
            analysis = self.agent._create_analysis_prompt({
                'hostname': hostname,
                'os_type': profile['os_type'],
                'services': profile['services'],
                'capabilities': profile['capabilities'],
                'hardware': profile.get('hardware', {}),
                'discovered_at': profile['discovered_at'],
                'in_flake': in_flake,
                'flake_name': flake_name
            }, system_context)
            
            # Get AI analysis
            response = self.agent._query_ollama(
                f"You have discovered a new system in your infrastructure. "
                f"Review its profile and provide initial observations.\n\n"
                f"{flake_status}\n\n{analysis}",
                model=self.agent.model
            )
            
            if response:
                self._log(f"📝 AI Analysis for {hostname}:")
                self._log(response[:500])  # Log first 500 chars
                
                # Store this as a decision/observation
                self.context_db.record_decision({
                    'type': 'system_discovery',
                    'hostname': hostname,
                    'analysis': response,
                    'profile': profile
                })
            
        except Exception as e:
            self._log(f"Warning: Could not analyze {hostname}: {e}")
    
    def _parse_and_store_configs(self):
        """Parse repository and store config files in ChromaDB"""
        if not self.config_parser or not self.context_db:
            return
        
        try:
            self._log("Parsing configuration repository...")
            
            # Ensure repository is up to date
            if not self.config_parser.ensure_repo():
                self._log("Warning: Could not update config repository")
                return
            
            # Get systems from flake
            systems = self.config_parser.get_systems_from_flake()
            self._log(f"Found {len(systems)} systems in flake: {', '.join(systems)}")
            
            # For each system, get its config files
            for system_name in systems:
                fqdn = f"{system_name}.coven.systems"
                
                config = self.config_parser.get_system_config(system_name)
                if not config['main_file']:
                    continue
                
                # Update system with list of config files
                self.context_db.update_system_config_files(fqdn, config['all_files'])
                
                # Store each config file in ChromaDB
                for file_path in config['all_files']:
                    content = self.config_parser.read_file_content(file_path)
                    if content:
                        # Determine category from path
                        category = "unknown"
                        if file_path.startswith("apps/"):
                            category = "apps"
                        elif file_path.startswith("systems/"):
                            category = "systems"
                        elif file_path.startswith("osconfigs/"):
                            category = "osconfigs"
                        elif file_path.startswith("users/"):
                            category = "users"
                        
                        self.context_db.store_config_file(
                            file_path=file_path,
                            content=content,
                            category=category,
                            systems_using=[fqdn]
                        )
            
            self._log(f"Configuration parsing complete")
            
        except Exception as e:
            self._log(f"Error parsing configs: {e}")
            import traceback
            self._log(traceback.format_exc())
    
    def _log_metrics(self, data: Dict[str, Any]):
        """Log key metrics in a structured format for easy parsing"""
        res = data.get("resources", {})
        systemd = data.get("systemd", {})
        logs = data.get("logs", {})
        disk = data.get("disk", {})
        
        self._log("KEY METRICS:")
        self._log(f"  CPU Usage: {res.get('cpu_percent', 0):.1f}%")
        self._log(f"  Memory Usage: {res.get('memory_percent', 0):.1f}%")
        self._log(f"  Load Average: {res.get('load_average', {}).get('1min', 0):.2f}")
        self._log(f"  Failed Services: {systemd.get('failed_count', 0)}")
        self._log(f"  Errors (1h): {logs.get('error_count_1h', 0)}")
        
        # Disk usage for critical partitions
        for part in disk.get("partitions", []):
            if part.get("mountpoint") in ["/", "/home", "/var"]:
                self._log(f"  Disk {part['mountpoint']}: {part.get('percent_used', 0):.1f}% used")
        
        # Network status
        net = data.get("network", {})
        internet_status = "✅ Connected" if net.get("internet_reachable") else "❌ Offline"
        self._log(f"  Internet: {internet_status}")
    
    def _review_open_issues(self, system_hostname: str):
        """Review all open issues for this system and log status"""
        if not self.issue_tracker:
            return
        
        open_issues = self.issue_tracker.list_issues(
            hostname=system_hostname,
            status="open"
        )
        
        if not open_issues:
            self._log("No open issues in tracker")
            return
        
        self._log(f"\n{'='*60}")
        self._log(f"OPEN ISSUES REVIEW ({len(open_issues)} active)")
        self._log(f"{'='*60}")
        
        for issue in open_issues:
            issue_id = issue['issue_id'][:8]  # Short ID
            age_hours = self._calculate_issue_age(issue['created_at'])
            inv_count = len(issue.get('investigations', []))
            action_count = len(issue.get('actions', []))
            
            self._log(f"\n  Issue {issue_id}: {issue['title']}")
            self._log(f"    Severity: {issue['severity'].upper()}")
            self._log(f"    Status: {issue['status']}")
            self._log(f"    Age: {age_hours:.1f} hours")
            self._log(f"    Activity: {inv_count} investigations, {action_count} actions")
            self._log(f"    Description: {issue['description'][:100]}...")
        
        self._log(f"{'='*60}\n")
    
    def _track_or_update_issue(
        self,
        system_hostname: str,
        issue_description: str,
        severity: str = "medium"
    ) -> str:
        """
        Find or create an issue for this problem.
        Returns the issue_id.
        """
        if not self.issue_tracker:
            return None
        
        # Try to find existing issue
        title = issue_description[:100]  # Use first 100 chars as title
        existing = self.issue_tracker.find_similar_issue(
            hostname=system_hostname,
            title=title,
            description=issue_description
        )
        
        if existing:
            issue_id = existing['issue_id']
            self._log(f"Linked to existing issue: {issue_id[:8]}")
            return issue_id
        
        # Create new issue
        issue_id = self.issue_tracker.create_issue(
            hostname=system_hostname,
            title=title,
            description=issue_description,
            severity=severity,
            source="auto-detected"
        )
        
        self._log(f"Created new issue: {issue_id[:8]}")
        self.notifier.notify_issue_created(
            issue_id[:8],
            title,
            severity
        )
        
        return issue_id
    
    def _link_action_to_issue(
        self,
        issue_id: str,
        fix_proposal: Dict[str, Any],
        execution_result: Dict[str, Any]
    ):
        """Link an investigation or fix action to an issue"""
        if not self.issue_tracker or not issue_id:
            return
        
        action_type = fix_proposal.get('action_type', 'unknown')
        
        if action_type == 'investigation':
            self.issue_tracker.update_issue(
                issue_id,
                status="investigating",
                investigation={
                    "commands": fix_proposal.get('commands', []),
                    "output": execution_result.get('output', ''),
                    "success": execution_result.get('success', False),
                    "diagnosis": fix_proposal.get('diagnosis', '')
                }
            )
        else:
            self.issue_tracker.update_issue(
                issue_id,
                status="fixing",
                action={
                    "proposed_action": fix_proposal.get('proposed_action', ''),
                    "commands": fix_proposal.get('commands', []),
                    "output": execution_result.get('output', ''),
                    "success": execution_result.get('success', False),
                    "risk_level": fix_proposal.get('risk_level', 'unknown')
                }
            )
    
    def _auto_resolve_fixed_issues(self, system_hostname: str, detected_problems: List[str]):
        """Auto-resolve issues that are no longer detected"""
        if not self.issue_tracker:
            return
        
        resolved_count = self.issue_tracker.auto_resolve_if_fixed(
            system_hostname,
            detected_problems
        )
        
        if resolved_count > 0:
            self._log(f"\n✅ Auto-resolved {resolved_count} issue(s) (problems no longer detected)")
    
    def _calculate_issue_age(self, created_at: str) -> float:
        """Calculate age of issue in hours"""
        try:
            from datetime import datetime
            created = datetime.fromisoformat(created_at)
            now = datetime.utcnow()
            delta = now - created
            return delta.total_seconds() / 3600
        except:
            return 0
    
    def run_once(self) -> Dict[str, Any]:
        """Run one maintenance cycle"""
        self._log("=== Starting maintenance cycle ===")
        
        # Get system hostname
        import socket
        hostname = socket.gethostname()
        system_hostname = f"{hostname}.coven.systems"
        
        # Review open issues before starting new checks
        self._review_open_issues(system_hostname)
        
        # Discover new systems from journal logs
        self._discover_new_systems()
        
        # Update service registry periodically (every 10th cycle to avoid overhead)
        if not hasattr(self, '_cycle_count'):
            self._cycle_count = 0
        self._cycle_count += 1
        
        if self._cycle_count % 10 == 1:  # First cycle and every 10th
            self._update_service_registry()
        
        # Refresh configuration repository every 3 cycles (~15 min) to keep git context current
        # This ensures git_context has up-to-date information about recent config changes
        if self._cycle_count % 3 == 1 and self.config_parser:
            try:
                self._log("Refreshing configuration repository...")
                if self.config_parser.ensure_repo():
                    self._log("✓ Configuration repository updated")
                    # Reinitialize git_context if it exists to pick up fresh data
                    if self.git_context:
                        local_repo_path = Path("/var/lib/ai-sysadmin/config-repo")
                        self.git_context = GitContext(repo_path=str(local_repo_path))
                else:
                    self._log("⚠ Could not refresh configuration repository")
            except Exception as e:
                self._log(f"⚠ Error refreshing config repo: {e}")
        
        # Step 1: Monitor system
        self._log("Collecting system health data...")
        monitoring_data = self.monitor.collect_all()
        self.monitor.save_snapshot(monitoring_data)
        
        # Print detailed summary
        summary = self.monitor.get_summary(monitoring_data)
        self._log(f"\n{'='*60}")
        self._log("SYSTEM HEALTH SUMMARY")
        self._log(f"{'='*60}")
        self._log(summary)
        self._log(f"{'='*60}\n")
        
        # Log key metrics for easy grepping
        self._log_metrics(monitoring_data)
        
        # Step 2: Analyze with AI (with system context including git)
        self._log("\nAnalyzing system state with AI...")
        import socket
        hostname = socket.gethostname()
        fqdn = f"{hostname}.coven.systems"
        analysis = self.agent.analyze_system_state(
            monitoring_data,
            system_hostname=fqdn,
            git_context=self.git_context if hasattr(self, 'git_context') else None
        )
        
        # Check if analysis was skipped due to queue already being busy
        if isinstance(analysis, str) and "already in progress" in analysis.lower():
            self._log("⏭️  Analysis skipped - autonomous check already in queue")
            return
        
        self._log(f"\n{'='*60}")
        self._log("AI ANALYSIS RESULTS")
        self._log(f"{'='*60}")
        self._log(f"Overall Status: {analysis.get('status', 'unknown').upper()}")
        self._log(f"Assessment: {analysis.get('overall_assessment', 'No assessment')}")
        
        # Log detected issues
        issues = analysis.get('issues', [])
        if issues:
            self._log(f"\nDetected {len(issues)} issue(s):")
            for i, issue in enumerate(issues, 1):
                severity = issue.get('severity', 'unknown')
                category = issue.get('category', 'unknown')
                description = issue.get('description', 'No description')
                requires_action = issue.get('requires_action', False)
                action_flag = "⚠️ ACTION REQUIRED" if requires_action else "ℹ️ Informational"
                
                self._log(f"\n  Issue #{i}:")
                self._log(f"    Severity: {severity.upper()}")
                self._log(f"    Category: {category}")
                self._log(f"    Description: {description}")
                self._log(f"    {action_flag}")
        else:
            self._log("\n✅ No issues detected")
        
        # Log recommended actions
        recommended_actions = analysis.get('recommended_actions', [])
        if recommended_actions:
            self._log(f"\nRecommended Actions ({len(recommended_actions)}):")
            for action in recommended_actions:
                self._log(f"  - {action}")
        
        self._log(f"{'='*60}\n")
        
        # Send health summary notification for critical states
        status = analysis.get('status', 'unknown')
        if status == 'intervention_required':
            self.notifier.notify_health_summary(
                analysis.get('overall_assessment', 'System requires intervention'),
                status
            )
        
        # Step 3: Handle issues
        results = []
        issues_requiring_action = [
            issue for issue in analysis.get("issues", [])
            if issue.get("requires_action", False)
        ]
        
        if issues_requiring_action:
            self._log(f"Found {len(issues_requiring_action)} issues requiring action")
            
            for issue in issues_requiring_action:
                self._log(f"\n{'─'*60}")
                self._log(f"Addressing issue: {issue['description']}")
                
                # Track or update issue in tracker
                issue_id = self._track_or_update_issue(
                    system_hostname,
                    issue['description'],
                    severity=issue.get('severity', 'medium')
                )
                
                # Notify about critical issues
                if issue.get('severity') == 'critical':
                    self.notifier.notify_critical_issue(
                        issue['description'],
                        f"Category: {issue.get('category', 'unknown')}"
                    )
                
                # Check for recent investigations of this issue
                previous_investigations = []
                if self.context_db:
                    previous_investigations = self.context_db.get_recent_investigations(
                        issue["description"],
                        system_hostname,
                        hours=24
                    )
                
                # Get fix proposal from AI
                if previous_investigations:
                    self._log(f"Found {len(previous_investigations)} previous investigation(s) for this issue")
                    self._log("Requesting AI fix proposal with investigation history...")
                else:
                    self._log("Requesting AI fix proposal...")
                
                fix_proposal = self.agent.propose_fix(
                    issue["description"],
                    {
                        "monitoring_data": monitoring_data,
                        "issue": issue,
                        "previous_investigations": previous_investigations
                    }
                )
                
                # Log detailed fix proposal
                self._log(f"\nAI FIX PROPOSAL:")
                self._log(f"  Diagnosis: {fix_proposal.get('diagnosis', 'No diagnosis')}")
                self._log(f"  Proposed Action: {fix_proposal.get('proposed_action', 'No proposal')}")
                self._log(f"  Action Type: {fix_proposal.get('action_type', 'unknown')}")
                self._log(f"  Risk Level: {fix_proposal.get('risk_level', 'unknown').upper()}")
                
                if fix_proposal.get('commands'):
                    self._log(f"  Commands to execute:")
                    for cmd in fix_proposal.get('commands', []):
                        self._log(f"    - {cmd}")
                
                if fix_proposal.get('reasoning'):
                    self._log(f"  Reasoning: {fix_proposal.get('reasoning')}")
                
                if fix_proposal.get('rollback_plan'):
                    self._log(f"  Rollback Plan: {fix_proposal.get('rollback_plan')}")
                
                # Execute or queue the fix
                self._log("\nExecuting action...")
                execution_result = self.executor.execute_action(
                    fix_proposal,
                    monitoring_data
                )
                
                # Log execution result
                self._log(f"\nEXECUTION RESULT:")
                self._log(f"  Status: {execution_result.get('status', 'unknown').upper()}")
                self._log(f"  Executed: {'Yes' if execution_result.get('executed') else 'No'}")
                
                if execution_result.get('reason'):
                    self._log(f"  Reason: {execution_result.get('reason')}")
                
                if execution_result.get('success') is not None:
                    success_icon = "✅" if execution_result.get('success') else "❌"
                    self._log(f"  Success: {success_icon} {execution_result.get('success')}")
                
                if execution_result.get("output"):
                    self._log(f"  Output: {execution_result['output']}")
                
                if execution_result.get("error"):
                    self._log(f"  Error: {execution_result['error']}")
                
                # Link action to issue
                self._link_action_to_issue(issue_id, fix_proposal, execution_result)
                
                # Store investigation results in ChromaDB
                if (fix_proposal.get('action_type') == 'investigation' and 
                    execution_result.get('executed') and 
                    execution_result.get('output') and
                    self.context_db):
                    
                    try:
                        self.context_db.store_investigation(
                            system=system_hostname,
                            issue_description=issue["description"],
                            commands=fix_proposal.get('commands', []),
                            output=execution_result['output']
                        )
                        self._log("Investigation results stored in database")
                    except Exception as e:
                        self._log(f"Warning: Could not store investigation: {e}")
                
                # If this was an investigation that succeeded, analyze the results and propose actual fix
                if (fix_proposal.get('action_type') == 'investigation' and 
                    execution_result.get('executed') and 
                    execution_result.get('success') and
                    execution_result.get('output')):
                    
                    self._log("\n" + "="*60)
                    self._log("INVESTIGATION COMPLETE - Analyzing results...")
                    self._log("="*60)
                    
                    # Build context with investigation results
                    investigation_context = {
                        "original_issue": issue["description"],
                        "investigation_output": execution_result['output'],
                        "monitoring_data": monitoring_data,
                        "issue": issue
                    }
                    
                    # Ask AI to propose actual fix based on investigation
                    self._log("Requesting AI to propose fix based on investigation findings...")
                    actual_fix_proposal = self.agent.propose_fix(
                        f"Based on investigation of: {issue['description']}\n\nInvestigation output:\n{execution_result['output'][:1000]}",
                        investigation_context
                    )
                    
                    # Log the new fix proposal
                    self._log(f"\nFIX PROPOSAL BASED ON INVESTIGATION:")
                    self._log(f"  Diagnosis: {actual_fix_proposal.get('diagnosis', 'No diagnosis')}")
                    self._log(f"  Proposed Action: {actual_fix_proposal.get('proposed_action', 'No proposal')}")
                    self._log(f"  Action Type: {actual_fix_proposal.get('action_type', 'unknown')}")
                    self._log(f"  Risk Level: {actual_fix_proposal.get('risk_level', 'unknown').upper()}")
                    
                    if actual_fix_proposal.get('commands'):
                        self._log(f"  Commands to execute:")
                        for cmd in actual_fix_proposal.get('commands', []):
                            self._log(f"    - {cmd}")
                    
                    # Only proceed with non-investigation actions
                    if actual_fix_proposal.get('action_type') != 'investigation':
                        self._log("\nExecuting follow-up action...")
                        followup_result = self.executor.execute_action(
                            actual_fix_proposal,
                            monitoring_data
                        )
                        
                        self._log(f"\nFOLLOW-UP EXECUTION RESULT:")
                        self._log(f"  Status: {followup_result.get('status', 'unknown').upper()}")
                        self._log(f"  Executed: {'Yes' if followup_result.get('executed') else 'No'}")
                        
                        if followup_result.get('status') == 'queued_for_approval':
                            self.notifier.notify_action_queued(
                                actual_fix_proposal.get('proposed_action', 'Unknown action'),
                                actual_fix_proposal.get('risk_level', 'unknown')
                            )
                        elif followup_result.get('executed'):
                            self.notifier.notify_action_executed(
                                actual_fix_proposal.get('proposed_action', 'Unknown action'),
                                followup_result.get('success', False)
                            )
                        
                        # Store the follow-up result instead
                        execution_result = followup_result
                    else:
                        self._log("\nAI still recommends investigation - no further action taken.")
                
                # Send notification based on execution result
                if execution_result.get('status') == 'queued_for_approval':
                    self.notifier.notify_action_queued(
                        fix_proposal.get('proposed_action', 'Unknown action'),
                        fix_proposal.get('risk_level', 'unknown')
                    )
                elif execution_result.get('executed'):
                    self.notifier.notify_action_executed(
                        fix_proposal.get('proposed_action', 'Unknown action'),
                        execution_result.get('success', False),
                        execution_result.get('output', '')
                    )
                
                results.append({
                    "issue": issue,
                    "proposal": fix_proposal,
                    "execution": execution_result
                })
        else:
            self._log("No issues requiring immediate action")
        
        # Final summary
        self._log(f"\n{'='*60}")
        self._log("MAINTENANCE CYCLE COMPLETE")
        self._log(f"{'='*60}")
        self._log(f"Status: {analysis.get('status', 'unknown').upper()}")
        self._log(f"Issues Found: {len(issues)}")
        self._log(f"Actions Taken: {len(results)}")
        if results:
            executed = sum(1 for r in results if r.get('execution', {}).get('executed'))
            queued = sum(1 for r in results if r.get('execution', {}).get('status') == 'queued_for_approval')
            self._log(f"  - Executed: {executed}")
            self._log(f"  - Queued for approval: {queued}")
        
        # Auto-resolve issues that are no longer detected
        detected_problems = [issue['description'] for issue in analysis.get('issues', [])]
        self._auto_resolve_fixed_issues(system_hostname, detected_problems)
        
        self._log(f"Next check in: {self.check_interval} seconds")
        self._log(f"{'='*60}\n")
        
        return {
            "timestamp": datetime.now().isoformat(),
            "monitoring": monitoring_data,
            "analysis": analysis,
            "actions": results
        }
    
    def run_continuous(self):
        """Run continuous maintenance loop"""
        self._log(f"Starting Macha Autonomous System Maintenance")
        self._log(f"Autonomy level: {self.autonomy_level}")
        self._log(f"Check interval: {self.check_interval} seconds")
        self._log(f"State directory: {self.state_dir}")
        
        self.running = True
        
        while self.running:
            try:
                cycle_result = self.run_once()
                
                # Wait for next cycle
                if self.running:
                    self._log(f"Waiting {self.check_interval} seconds until next check...")
                    time.sleep(self.check_interval)
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                self._log(f"ERROR in maintenance cycle: {e}")
                import traceback
                self._log(traceback.format_exc())
                
                # Wait a bit before retrying after error
                if self.running:
                    time.sleep(60)
        
        self._log("Macha Autonomous System Maintenance stopped")
    
    def run_daemon(self):
        """Run as a background daemon"""
        # TODO: Proper daemonization
        self.run_continuous()


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Macha Autonomous System Maintenance")
    parser.add_argument(
        "--mode",
        choices=["once", "continuous", "daemon"],
        default="once",
        help="Run mode"
    )
    parser.add_argument(
        "--autonomy",
        choices=["observe", "suggest", "auto-safe", "auto-full"],
        default="suggest",
        help="Autonomy level"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=300,
        help="Check interval in seconds (for continuous mode)"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("/etc/macha-autonomous/config.json"),
        help="Config file path"
    )
    
    args = parser.parse_args()
    
    orchestrator = MachaOrchestrator(
        check_interval=args.interval,
        autonomy_level=args.autonomy,
        config_file=args.config
    )
    
    if args.mode == "once":
        result = orchestrator.run_once()
        print(json.dumps(result, indent=2))
    elif args.mode == "continuous":
        orchestrator.run_continuous()
    elif args.mode == "daemon":
        orchestrator.run_daemon()


if __name__ == "__main__":
    main()
