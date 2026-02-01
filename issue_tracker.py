#!/usr/bin/env python3
"""
Issue Tracker - Internal ticketing system for tracking problems and their resolution
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from pathlib import Path


class IssueTracker:
    """Manages issue lifecycle: detection -> investigation -> resolution"""
    
    def __init__(self, context_db, log_dir: str = "/var/lib/ai-sysadmin/logs"):
        self.context_db = context_db
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.closed_log = self.log_dir / "closed_issues.jsonl"
    
    def create_issue(
        self,
        hostname: str,
        title: str,
        description: str,
        severity: str = "medium",
        source: str = "auto-detected"
    ) -> str:
        """Create a new issue and return its ID"""
        issue_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        
        issue = {
            "issue_id": issue_id,
            "hostname": hostname,
            "title": title,
            "description": description,
            "status": "open",
            "severity": severity,
            "created_at": now,
            "updated_at": now,
            "source": source,
            "investigations": [],
            "actions": [],
            "resolution": None
        }
        
        self.context_db.store_issue(issue)
        return issue_id
    
    def get_issue(self, issue_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve an issue by ID"""
        return self.context_db.get_issue(issue_id)
    
    def update_issue(
        self,
        issue_id: str,
        status: Optional[str] = None,
        investigation: Optional[Dict[str, Any]] = None,
        action: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Update an issue with new information"""
        issue = self.get_issue(issue_id)
        if not issue:
            return False
        
        if status:
            issue["status"] = status
        
        if investigation:
            investigation["timestamp"] = datetime.now(timezone.utc).isoformat()
            issue["investigations"].append(investigation)
        
        if action:
            action["timestamp"] = datetime.now(timezone.utc).isoformat()
            issue["actions"].append(action)
        
        issue["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        self.context_db.update_issue(issue)
        return True
    
    def find_similar_issue(
        self,
        hostname: str,
        title: str,
        description: str = None
    ) -> Optional[Dict[str, Any]]:
        """Find an existing open issue that matches this problem"""
        open_issues = self.list_issues(hostname=hostname, status="open")
        
        # Simple similarity check on title
        title_lower = title.lower()
        for issue in open_issues:
            issue_title_lower = issue.get("title", "").lower()
            
            # Check for keyword overlap
            title_words = set(title_lower.split())
            issue_words = set(issue_title_lower.split())
            
            # If >50% of words overlap, consider it similar
            if len(title_words & issue_words) / max(len(title_words), 1) > 0.5:
                return issue
        
        return None
    
    def list_issues(
        self,
        hostname: Optional[str] = None,
        status: Optional[str] = None,
        severity: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List issues with optional filters"""
        return self.context_db.list_issues(
            hostname=hostname,
            status=status,
            severity=severity
        )
    
    def resolve_issue(self, issue_id: str, resolution: str) -> bool:
        """Mark an issue as resolved with a resolution note"""
        issue = self.get_issue(issue_id)
        if not issue:
            return False
        
        issue["status"] = "resolved"
        issue["resolution"] = resolution
        issue["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        self.context_db.update_issue(issue)
        return True
    
    def close_issue(self, issue_id: str) -> bool:
        """Archive a resolved issue to the closed log"""
        issue = self.get_issue(issue_id)
        if not issue:
            return False
        
        # Can only close resolved issues
        if issue["status"] != "resolved":
            return False
        
        issue["status"] = "closed"
        issue["closed_at"] = datetime.now(timezone.utc).isoformat()
        
        # Archive to closed log
        self._archive_issue(issue)
        
        # Remove from active database
        self.context_db.delete_issue(issue_id)
        
        return True
    
    def get_issue_history(self, issue_id: str) -> Dict[str, Any]:
        """Get full history for an issue (investigations + actions)"""
        issue = self.get_issue(issue_id)
        if not issue:
            return {}
        
        return {
            "issue": issue,
            "investigation_count": len(issue.get("investigations", [])),
            "action_count": len(issue.get("actions", [])),
            "age_hours": self._calculate_age(issue["created_at"]),
            "last_activity": issue["updated_at"]
        }
    
    def auto_resolve_if_fixed(self, hostname: str, detected_problems: List[str]) -> int:
        """
        Auto-resolve open issues if their problems are no longer detected.
        Returns count of auto-resolved issues.
        """
        open_issues = self.list_issues(hostname=hostname, status="open")
        resolved_count = 0
        
        # Convert detected problems to lowercase for comparison
        detected_lower = [p.lower() for p in detected_problems]
        
        for issue in open_issues:
            title_lower = issue.get("title", "").lower()
            desc_lower = issue.get("description", "").lower()
            
            # Check if issue keywords are still in detected problems
            still_present = False
            for detected in detected_lower:
                if any(word in detected for word in title_lower.split()) or \
                   any(word in detected for word in desc_lower.split()):
                    still_present = True
                    break
            
            # If problem is no longer detected, auto-resolve
            if not still_present:
                self.resolve_issue(
                    issue["issue_id"],
                    "Auto-resolved: Problem no longer detected in system monitoring"
                )
                resolved_count += 1
        
        return resolved_count
    
    def _archive_issue(self, issue: Dict[str, Any]):
        """Append closed issue to the archive log"""
        try:
            with open(self.closed_log, "a") as f:
                f.write(json.dumps(issue) + "\n")
        except Exception as e:
            print(f"Failed to archive issue {issue.get('issue_id')}: {e}")
    
    def _calculate_age(self, created_at: str) -> float:
        """Calculate age of issue in hours"""
        try:
            created = datetime.fromisoformat(created_at)
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            delta = now - created
            return delta.total_seconds() / 3600
        except:
            return 0

