#!/usr/bin/env python3
"""
Review Model - Layer 3: Continuous analysis with small model
Analyzes context holistically and escalates to meta model when needed
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from pathlib import Path

from context_manager import ContextManager
from executor import SafeExecutor


class ReviewModel:
    """Small model for continuous system review"""
    
    def __init__(
        self,
        model: str = "qwen3:4b",
        llm_backend = None,
        backend_url: str = "http://127.0.0.1:8081/v1",
        context_manager: ContextManager = None,
        executor: SafeExecutor = None,
        state_dir: Path = Path("/var/lib/ai-sysadmin"),
        autonomy_level: str = "suggest"
    ):
        """
        Initialize review model
        
        Args:
            model: Small model name (e.g., qwen3:4b)
            llm_backend: LLM backend instance (will be created if not provided)
            backend_url: LLM backend URL (for llama.cpp)
            context_manager: Context manager instance
            executor: Action executor
            state_dir: State directory
            autonomy_level: Autonomy level for actions
        """
        self.model = model
        self.context_manager = context_manager
        self.executor = executor
        self.state_dir = state_dir
        self.autonomy_level = autonomy_level
        
        # Setup LLM backend
        if llm_backend:
            self.llm_backend = llm_backend
        else:
            from llm_backend import LlamaCppBackend
            self.llm_backend = LlamaCppBackend(base_url=backend_url)
        
        # Statistics
        self.stats = {
            'reviews_performed': 0,
            'escalations_to_meta': 0,
            'actions_proposed': 0,
            'actions_executed': 0
        }
        
        # Load or create state
        self.state_file = state_dir / "review_model_state.json"
        self._load_state()
    
    def review_system_state(self, triggered_by: str = "periodic") -> Dict[str, Any]:
        """
        Perform a comprehensive system review
        
        Args:
            triggered_by: What triggered this review (periodic, trigger_monitor, user)
        
        Returns:
            Review results including analysis and recommendations
        """
        self.stats['reviews_performed'] += 1
        
        # Get current context
        if not self.context_manager:
            return {
                'status': 'error',
                'message': 'Context manager not available',
                'timestamp': datetime.utcnow().isoformat()
            }
        
        context_text = self.context_manager.get_context_window(
            include_sar=True,
            include_metrics=True
        )
        
        # Create review prompt
        prompt = self._create_review_prompt(context_text, triggered_by)
        
        # Query model
        analysis = self._query_model(prompt)
        
        if not analysis:
            return {
                'status': 'error',
                'message': 'Failed to get analysis from model',
                'timestamp': datetime.utcnow().isoformat()
            }
        
        # Parse analysis
        review_result = self._parse_analysis(analysis)
        review_result['triggered_by'] = triggered_by
        review_result['timestamp'] = datetime.utcnow().isoformat()
        
        # Add to context
        self.context_manager.add_event({
            'type': 'review_completed',
            'summary': review_result.get('summary', 'Review completed'),
            'status': review_result.get('status', 'normal'),
            'issues_found': len(review_result.get('issues', []))
        }, source='review')
        
        # Determine if we should escalate to meta model
        if review_result.get('should_escalate', False):
            self.stats['escalations_to_meta'] += 1
            review_result['escalation_recommended'] = True
            review_result['escalation_reason'] = review_result.get('escalation_reason', 'Complex issue detected')
        
        # Execute safe actions if autonomy allows
        if review_result.get('safe_actions') and self.executor:
            for action in review_result['safe_actions']:
                if self._is_safe_action(action):
                    self._execute_safe_action(action)
        
        # Save state
        self._save_state()
        
        return review_result
    
    def _create_review_prompt(self, context_text: str, triggered_by: str) -> str:
        """Create prompt for system review"""
        return f"""You are a system administrator AI conducting a routine system review.

Triggered by: {triggered_by}

Current System Context:
{context_text}

Please analyze the system state and provide:

1. Overall Status (normal/degraded/critical)
2. Summary (one paragraph)
3. Issues Detected (list any problems, with severity)
4. Patterns or Trends (what's happening over time?)
5. Safe Actions (actions you can take immediately like restarting services)
6. Should Escalate (true/false - whether to involve the senior AI for complex analysis)
7. Escalation Reason (if escalating, explain why)

Focus on:
- Service health and failures
- Resource usage trends (CPU, memory, disk, I/O)
- Error patterns in logs
- Security concerns
- Performance anomalies

Respond in JSON format with this structure:
{{
  "status": "normal|degraded|critical",
  "summary": "brief summary",
  "issues": [
    {{
      "severity": "low|medium|high|critical",
      "category": "service|resource|security|performance|other",
      "description": "what's wrong",
      "affected_components": ["list"]
    }}
  ],
  "patterns": ["pattern 1", "pattern 2"],
  "safe_actions": [
    {{
      "action_type": "restart_service|cleanup|investigation",
      "description": "what to do",
      "target": "service name or component",
      "risk": "low"
    }}
  ],
  "should_escalate": false,
  "escalation_reason": "explanation if true"
}}
"""
    
    def _query_model(self, prompt: str) -> Optional[str]:
        """Query the small model using LLM backend"""
        try:
            response = self.llm_backend.generate(
                prompt=prompt,
                model=self.model,
                temperature=0.3,
                max_tokens=1000
            )
            
            if response and not response.startswith("Error:"):
                return response
            else:
                print(f"Model query failed: {response}")
                return None
        
        except Exception as e:
            print(f"Error querying model: {e}")
            return None
    
    def _parse_analysis(self, analysis_text: str) -> Dict[str, Any]:
        """Parse model output into structured format"""
        # Try to extract JSON from response
        try:
            import re
            
            # Look for JSON block in response
            json_match = re.search(r'\{.*\}', analysis_text, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                return parsed
        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON from model response: {e}")
        
        # Fallback: create structured response from text
        return {
            'status': 'unknown',
            'summary': analysis_text[:500],  # Truncate
            'issues': [],
            'patterns': [],
            'safe_actions': [],
            'should_escalate': False,
            'raw_response': analysis_text
        }
    
    def _is_safe_action(self, action: Dict[str, Any]) -> bool:
        """Determine if an action is safe to execute"""
        action_type = action.get('action_type', '')
        risk = action.get('risk', 'high')
        
        # Only execute low-risk actions
        if risk != 'low':
            return False
        
        # Check action type against safe list
        safe_action_types = [
            'investigation',  # Read-only commands
            'restart_service',  # Service restarts (non-critical)
            'cleanup'  # Cleanup operations
        ]
        
        return action_type in safe_action_types
    
    def _execute_safe_action(self, action: Dict[str, Any]):
        """Execute a safe action"""
        try:
            self.stats['actions_executed'] += 1
            
            # Convert review action to executor action format
            executor_action = {
                'action_type': action.get('action_type'),
                'proposed_action': action.get('description'),
                'target': action.get('target'),
                'risk_level': 'low',
                'commands': self._generate_commands(action)
            }
            
            # Execute via executor
            result = self.executor.execute_action(executor_action, {})
            
            # Add result to context
            self.context_manager.add_event({
                'type': 'action_executed',
                'action': action,
                'result': result.get('status'),
                'success': result.get('success', False)
            }, source='review')
            
        except Exception as e:
            print(f"Error executing safe action: {e}")
    
    def _generate_commands(self, action: Dict[str, Any]) -> List[str]:
        """Generate commands for an action"""
        action_type = action.get('action_type')
        target = action.get('target', '')
        
        if action_type == 'restart_service':
            return [f"systemctl restart {target}"]
        
        elif action_type == 'investigation':
            # Read-only investigation commands
            return [
                f"systemctl status {target}",
                f"journalctl -u {target} -n 50"
            ]
        
        elif action_type == 'cleanup':
            return [
                "journalctl --vacuum-time=7d",
                "nix-collect-garbage --delete-old"
            ]
        
        return []
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get review model statistics"""
        return {
            **self.stats,
            'model': self.model,
            'autonomy_level': self.autonomy_level
        }
    
    def _save_state(self):
        """Save review model state"""
        try:
            state = {
                'stats': self.stats,
                'last_save': datetime.utcnow().isoformat()
            }
            
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"Error saving state: {e}")
    
    def _load_state(self):
        """Load review model state"""
        if not self.state_file.exists():
            return
        
        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)
            
            self.stats = state.get('stats', self.stats)
        except Exception as e:
            print(f"Error loading state: {e}")


if __name__ == "__main__":
    # Test review model
    from context_manager import ContextManager
    
    context_mgr = ContextManager(context_size=8192)
    
    # Add some test events
    context_mgr.add_event({
        'type': 'metric_threshold',
        'trigger_type': 'cpu_high',
        'severity': 'medium',
        'value': 95.0,
        'message': 'CPU usage is very high'
    }, source='trigger')
    
    review = ReviewModel(
        model="qwen3:4b",
        context_manager=context_mgr
    )
    
    result = review.review_system_state(triggered_by="test")
    print(json.dumps(result, indent=2))

