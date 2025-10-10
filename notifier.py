#!/usr/bin/env python3
"""
Gotify Notifier - Send notifications to Gotify server
"""

import requests
import os
from typing import Optional
from datetime import datetime


class GotifyNotifier:
    """Send notifications to Gotify server"""
    
    # Priority levels
    PRIORITY_LOW = 2
    PRIORITY_MEDIUM = 5
    PRIORITY_HIGH = 8
    
    def __init__(
        self,
        gotify_url: Optional[str] = None,
        gotify_token: Optional[str] = None
    ):
        """
        Initialize Gotify notifier
        
        Args:
            gotify_url: URL to Gotify server (e.g. http://rhiannon:8181)
            gotify_token: Application token from Gotify
        """
        self.gotify_url = gotify_url or os.environ.get("GOTIFY_URL", "")
        self.gotify_token = gotify_token or os.environ.get("GOTIFY_TOKEN", "")
        self.enabled = bool(self.gotify_url and self.gotify_token)
        
    def send(
        self,
        title: str,
        message: str,
        priority: int = PRIORITY_MEDIUM,
        extras: Optional[dict] = None
    ) -> bool:
        """
        Send a notification to Gotify
        
        Args:
            title: Notification title
            message: Notification message
            priority: Priority level (2=low, 5=medium, 8=high)
            extras: Optional extra data
            
        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            return False
            
        try:
            url = f"{self.gotify_url}/message"
            headers = {
                "Authorization": f"Bearer {self.gotify_token}",
                "Content-Type": "application/json"
            }
            
            data = {
                "title": title,
                "message": message,
                "priority": priority,
            }
            
            if extras:
                data["extras"] = extras
            
            response = requests.post(
                url,
                json=data,
                headers=headers,
                timeout=10
            )
            
            return response.status_code == 200
            
        except Exception as e:
            # Fail silently - don't crash if Gotify is unavailable
            print(f"Warning: Failed to send Gotify notification: {e}")
            return False
    
    def notify_critical_issue(self, issue_description: str, details: str = ""):
        """Send high-priority notification for critical issues"""
        message = f"⚠️ Critical Issue Detected\n\n{issue_description}"
        if details:
            message += f"\n\nDetails:\n{details}"
        
        return self.send(
            title="🚨 Macha: Critical Issue",
            message=message,
            priority=self.PRIORITY_HIGH
        )
    
    def notify_issue_created(self, issue_id: str, title: str, severity: str):
        """Send notification when a new issue is created"""
        severity_icons = {
            "low": "ℹ️",
            "medium": "⚠️",
            "high": "🚨",
            "critical": "🔴"
        }
        icon = severity_icons.get(severity, "⚠️")
        
        priority_map = {
            "low": self.PRIORITY_LOW,
            "medium": self.PRIORITY_MEDIUM,
            "high": self.PRIORITY_HIGH,
            "critical": self.PRIORITY_HIGH
        }
        priority = priority_map.get(severity, self.PRIORITY_MEDIUM)
        
        message = f"{icon} New Issue Tracked\n\nID: {issue_id}\nSeverity: {severity.upper()}\n\n{title}"
        
        return self.send(
            title="📋 Macha: Issue Created",
            message=message,
            priority=priority
        )
    
    def notify_action_queued(self, action_description: str, risk_level: str):
        """Send notification when action is queued for approval"""
        emoji = "⚠️" if risk_level == "high" else "ℹ️"
        message = (
            f"{emoji} Action Queued for Approval\n\n"
            f"Action: {action_description}\n"
            f"Risk Level: {risk_level}\n\n"
            f"Use 'macha-approve list' to review"
        )
        
        priority = self.PRIORITY_HIGH if risk_level == "high" else self.PRIORITY_MEDIUM
        
        return self.send(
            title="📋 Macha: Action Needs Approval",
            message=message,
            priority=priority
        )
    
    def notify_action_executed(self, action_description: str, success: bool, output: str = ""):
        """Send notification when action is executed"""
        if success:
            emoji = "✅"
            title_prefix = "Success"
        else:
            emoji = "❌"
            title_prefix = "Failed"
        
        message = f"{emoji} Action {title_prefix}\n\n{action_description}"
        if output:
            message += f"\n\nOutput:\n{output[:500]}"  # Limit output length
        
        priority = self.PRIORITY_HIGH if not success else self.PRIORITY_LOW
        
        return self.send(
            title=f"{emoji} Macha: Action {title_prefix}",
            message=message,
            priority=priority
        )
    
    def notify_service_failure(self, service_name: str, details: str = ""):
        """Send notification for service failures"""
        message = f"🔴 Service Failed: {service_name}"
        if details:
            message += f"\n\nDetails:\n{details}"
        
        return self.send(
            title="🔴 Macha: Service Failure",
            message=message,
            priority=self.PRIORITY_HIGH
        )
    
    def notify_health_summary(self, summary: str, status: str):
        """Send periodic health summary"""
        emoji = {
            "healthy": "✅",
            "attention_needed": "⚠️",
            "intervention_required": "🚨"
        }.get(status, "ℹ️")
        
        priority = {
            "healthy": self.PRIORITY_LOW,
            "attention_needed": self.PRIORITY_MEDIUM,
            "intervention_required": self.PRIORITY_HIGH
        }.get(status, self.PRIORITY_MEDIUM)
        
        return self.send(
            title=f"{emoji} Macha: Health Check",
            message=summary,
            priority=priority
        )
    
    def send_system_discovered(
        self,
        hostname: str,
        os_type: str,
        role: str,
        services_count: int
    ):
        """Send notification when a new system is discovered"""
        message = (
            f"🔍 New System Auto-Discovered\n\n"
            f"Hostname: {hostname}\n"
            f"OS: {os_type.upper()}\n"
            f"Role: {role}\n"
            f"Services: {services_count} detected\n\n"
            f"System has been registered and analyzed.\n"
            f"Use 'macha-systems' to view all registered systems."
        )
        
        return self.send(
            title="🌐 Macha: New System Discovered",
            message=message,
            priority=self.PRIORITY_MEDIUM
        )


if __name__ == "__main__":
    import sys
    
    # Test the notifier
    if len(sys.argv) < 3:
        print("Usage: notifier.py <title> <message> [priority]")
        print("Example: notifier.py 'Test' 'This is a test message' 5")
        sys.exit(1)
    
    title = sys.argv[1]
    message = sys.argv[2]
    priority = int(sys.argv[3]) if len(sys.argv) > 3 else GotifyNotifier.PRIORITY_MEDIUM
    
    notifier = GotifyNotifier()
    
    if not notifier.enabled:
        print("Error: Gotify not configured (GOTIFY_URL and GOTIFY_TOKEN required)")
        sys.exit(1)
    
    success = notifier.send(title, message, priority)
    
    if success:
        print("✅ Notification sent successfully")
    else:
        print("❌ Failed to send notification")
        sys.exit(1)

