#!/usr/bin/env python3
"""
Interactive chat interface with Macha AI agent.
Unified chat/conversation interface using tool-calling architecture.
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from agent import MachaAgent


class MachaChatSession:
    """Interactive chat session with AI agent using tool-calling architecture"""
    
    def __init__(
        self,
        ollama_host: str = "http://localhost:11434",
        model: str = "gpt-oss:latest",
        state_dir: Path = Path("/var/lib/ai-sysadmin"),
        ai_name: str = None,
        enable_tools: bool = True
    ):
        """Initialize chat session with AI agent
        
        Args:
            ollama_host: Ollama API endpoint
            model: Model name to use
            state_dir: State directory for agent
            ai_name: Name of the AI assistant (defaults to hostname)
            enable_tools: Whether to enable tool calling (should always be True)
        """
        self.agent = MachaAgent(
            ollama_host=ollama_host,
            model=model,
            state_dir=state_dir,
            ai_name=ai_name,
            enable_tools=enable_tools,
            use_queue=True,
            priority="INTERACTIVE"
        )
        self.ai_name = self.agent.ai_name  # Store for UI usage
        self.conversation_history: List[Dict[str, str]] = []
        self.session_start = datetime.now().isoformat()
        
    def _auto_diagnose_ollama(self) -> str:
        """Automatically diagnose Ollama issues"""
        diagnostics = []
        
        diagnostics.append("🔍 AUTO-DIAGNOSIS: Investigating Ollama failure...\n")
        
        # Check if Ollama service is running
        try:
            result = subprocess.run(
                ['systemctl', 'is-active', 'ollama.service'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                diagnostics.append("✅ Ollama service is active")
            else:
                diagnostics.append(f"❌ Ollama service is NOT active: {result.stdout.strip()}")
                # Get service status
                status_result = subprocess.run(
                    ['systemctl', 'status', 'ollama.service', '--no-pager', '-l'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                diagnostics.append(f"\nService status:\n```\n{status_result.stdout[-500:]}\n```")
        except Exception as e:
            diagnostics.append(f"⚠️  Could not check service status: {e}")
        
        # Check memory usage
        try:
            result = subprocess.run(['free', '-h'], capture_output=True, text=True, timeout=5)
            lines = result.stdout.split('\n')
            for line in lines[:3]:  # First 3 lines
                diagnostics.append(f"  {line}")
        except Exception as e:
            diagnostics.append(f"⚠️  Could not check memory: {e}")
        
        # Check which models are loaded
        try:
            import requests
            response = requests.get(f"{self.agent.ollama_host}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get('models', [])
                diagnostics.append(f"\n📦 Loaded models ({len(models)}):")
                for model in models:
                    name = model.get('name', 'unknown')
                    size = model.get('size', 0) / (1024**3)
                    is_current = "← TARGET" if name == self.agent.model else ""
                    diagnostics.append(f"  • {name} ({size:.1f} GB) {is_current}")
                
                # Check if target model is loaded
                model_names = [m.get('name') for m in models]
                if self.agent.model not in model_names:
                    diagnostics.append(f"\n❌ TARGET MODEL NOT LOADED: {self.agent.model}")
                    diagnostics.append(f"   Available models: {', '.join(model_names)}")
            else:
                diagnostics.append(f"❌ Ollama API returned {response.status_code}")
        except Exception as e:
            diagnostics.append(f"⚠️  Could not query Ollama API: {e}")
        
        # Check recent Ollama logs
        try:
            result = subprocess.run(
                ['journalctl', '-u', 'ollama.service', '-n', '10', '--no-pager'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.stdout:
                diagnostics.append(f"\n📋 Recent Ollama logs (last 10 lines):\n```\n{result.stdout}\n```")
        except Exception as e:
            diagnostics.append(f"⚠️  Could not check logs: {e}")
        
        return "\n".join(diagnostics)
    
    def process_message(self, user_message: str, verbose: bool = False) -> str:
        """Process a user message and return Macha's response
        
        Args:
            user_message: The user's message
            verbose: Whether to show detailed token counts
            
        Returns:
            Macha's response
        """
        
        # Add user message to history
        self.conversation_history.append({
            'role': 'user',
            'message': user_message,
            'timestamp': datetime.now().isoformat()
        })
        
        # Build chat messages for tool-calling API
        messages = []
        
        # Query relevant knowledge based on user message
        knowledge_context = self.agent._query_relevant_knowledge(user_message, limit=3)
        
        # Add recent conversation history (last 15 messages to stay within context limits)
        recent_history = self.conversation_history[-15:]
        for entry in recent_history:
            content = entry['message']
            # Truncate very long messages (e.g., command outputs)
            if len(content) > 3000:
                content = content[:1500] + "\n... [message truncated] ...\n" + content[-1500:]
            # Add knowledge context to last user message if available
            if entry == recent_history[-1] and knowledge_context:
                content += knowledge_context
            messages.append({
                "role": entry['role'],
                "content": content
            })
        
        if verbose:
            # Estimate tokens for debugging
            total_chars = sum(len(json.dumps(m)) for m in messages)
            estimated_tokens = total_chars // 4
            print(f"[Context: {estimated_tokens:,} tokens, {len(messages)} messages]")
        
        try:
            # Use tool-aware chat API - this handles all tool calling automatically
            # Note: tool definitions are retrieved internally by _query_ollama_with_tools
            ai_response = self.agent._query_ollama_with_tools(messages)
            
        except Exception as e:
            error_msg = (
                f"❌ CRITICAL: Failed to communicate with Ollama inference engine\n\n"
                f"Error Type: {type(e).__name__}\n"
                f"Error Message: {str(e)}\n\n"
            )
            # Auto-diagnose the issue
            diagnostics = self._auto_diagnose_ollama()
            return error_msg + "\n" + diagnostics
        
        if not ai_response:
            error_msg = (
                f"❌ Empty response from Ollama inference engine\n\n"
                f"The request succeeded but returned no data. This usually means:\n"
                f"  • The model ({self.agent.model}) is still loading\n"
                f"  • Ollama ran out of memory during generation\n"
                f"  • The prompt was too large for the context window\n\n"
            )
            # Auto-diagnose the issue
            diagnostics = self._auto_diagnose_ollama()
            return error_msg + "\n" + diagnostics
        
        # Add response to history
        self.conversation_history.append({
            'role': 'assistant',
            'message': ai_response,
            'timestamp': datetime.now().isoformat()
        })
        
        return ai_response
    
    def run_interactive(self):
        """Run the interactive chat session"""
        print("=" * 70)
        print(f"🌐 {self.ai_name.upper()} INTERACTIVE CHAT")
        print("=" * 70)
        print("Type your message and press Enter. Commands:")
        print("  /exit or /quit - End the chat session")
        print("  /clear - Clear conversation history")
        print("  /history - Show conversation history")
        print("  /debug - Show Ollama connection status")
        print("=" * 70)
        print()
        
        while True:
            try:
                # Get user input
                user_input = input("\n💬 YOU: ").strip()
                
                if not user_input:
                    continue
                
                # Handle special commands
                if user_input.lower() in ['/exit', '/quit']:
                    print("\n👋 Ending chat session. Goodbye!")
                    break
                
                elif user_input.lower() == '/clear':
                    self.conversation_history.clear()
                    print("🧹 Conversation history cleared.")
                    continue
                
                elif user_input.lower() == '/history':
                    print("\n" + "=" * 70)
                    print("CONVERSATION HISTORY")
                    print("=" * 70)
                    for entry in self.conversation_history:
                        role = entry['role'].upper()
                        msg = entry['message'][:100] + "..." if len(entry['message']) > 100 else entry['message']
                        print(f"{role}: {msg}")
                    print("=" * 70)
                    continue
                
                elif user_input.lower() == '/debug':
                    print("\n" + "=" * 70)
                    print(f"{self.ai_name.upper()} ARCHITECTURE & STATUS")
                    print("=" * 70)
                    
                    print("\n🏗️  SYSTEM ARCHITECTURE:")
                    print(f"  Hostname: macha.coven.systems")
                    print(f"  Service: macha-autonomous.service (systemd)")
                    print(f"  Working Directory: /var/lib/ai-sysadmin")
                    
                    print("\n👤 EXECUTION CONTEXT:")
                    current_user = os.getenv('USER') or os.getenv('USERNAME') or 'unknown'
                    print(f"  Current User: {current_user}")
                    print(f"  UID: {os.getuid()}")
                    
                    # Check if user has sudo access
                    try:
                        result = subprocess.run(['sudo', '-n', 'true'], 
                                              capture_output=True, timeout=1)
                        if result.returncode == 0:
                            print(f"  Sudo Access: ✓ Yes (passwordless)")
                        else:
                            print(f"  Sudo Access: ⚠ Requires password")
                    except:
                        print(f"  Sudo Access: ❌ No")
                    
                    print(f"  Note: Chat runs as invoking user (you), using macha's tools")
                    
                    print("\n🧠 INFERENCE ENGINE:")
                    print(f"  Backend: Ollama")
                    print(f"  Host: {self.agent.ollama_host}")
                    print(f"  Model: {self.agent.model}")
                    print(f"  Service: ollama.service (systemd)")
                    print(f"  Queue Worker: ollama-queue-worker.service")
                    
                    print("\n💾 DATABASE:")
                    print(f"  Backend: ChromaDB")
                    print(f"  State: {self.agent.state_dir}")
                    
                    print("\n🔍 OLLAMA STATUS:")
                    # Try to query Ollama status
                    try:
                        import requests
                        # Check if Ollama is running
                        response = requests.get(f"{self.agent.ollama_host}/api/tags", timeout=5)
                        if response.status_code == 200:
                            models = response.json().get('models', [])
                            print(f"  Status: ✓ Running")
                            print(f"  Loaded models: {len(models)}")
                            for model in models:
                                name = model.get('name', 'unknown')
                                size = model.get('size', 0) / (1024**3)  # GB
                                is_current = "← ACTIVE" if name == self.agent.model else ""
                                print(f"    • {name} ({size:.1f} GB) {is_current}")
                        else:
                            print(f"  Status: ❌ Error (HTTP {response.status_code})")
                    except Exception as e:
                        print(f"  Status: ❌ Cannot connect: {e}")
                        print(f"  Hint: Check 'systemctl status ollama.service'")
                    
                    print("\n🛠️  TOOLS:")
                    print(f"  Enabled: {self.agent.enable_tools}")
                    if self.agent.enable_tools:
                        print(f"  Available tools: {len(self.agent.tools.get_tool_definitions())}")
                        print(f"  Architecture: Centralized command_patterns.py")
                    
                    print("\n💡 CONVERSATION:")
                    print(f"  History: {len(self.conversation_history)} messages")
                    print(f"  Session started: {self.session_start}")
                    
                    print("=" * 70)
                    continue
                
                # Process the message
                print(f"\n🤖 {self.ai_name.upper()}: ", end='', flush=True)
                response = self.process_message(user_input, verbose=False)
                print(response)
                
            except KeyboardInterrupt:
                print("\n\n👋 Chat interrupted. Use /exit to quit properly.")
                continue
            except EOFError:
                print("\n\n👋 Ending chat session. Goodbye!")
                break
            except Exception as e:
                print(f"\n❌ Error: {e}")
                import traceback
                traceback.print_exc()
                continue
    
    def ask_once(self, question: str, verbose: bool = True) -> str:
        """Ask a single question and return the response (for macha-ask command)
        
        Args:
            question: The question to ask
            verbose: Whether to show detailed context information
            
        Returns:
            Macha's response
        """
        response = self.process_message(question, verbose=verbose)
        return response
    
    def explain_action(self, action_index: int) -> str:
        """Explain a pending action from the approval queue"""
        # Get action from approval queue
        approval_queue_file = self.agent.state_dir / "approval_queue.json"
        
        if not approval_queue_file.exists():
            return "Error: No approval queue found."
        
        try:
            with open(approval_queue_file, 'r') as f:
                queue = json.load(f)
            
            if not (0 <= action_index < len(queue)):
                return f"Error: Action #{action_index} not found in approval queue (queue has {len(queue)} items)."
            
            action_item = queue[action_index]
        except Exception as e:
            return f"Error reading approval queue: {e}"
        
        action = action_item.get("action", {})
        context = action_item.get("context", {})
        timestamp = action_item.get("timestamp", "unknown")
        
        # Build explanation prompt
        prompt = f"""You are {self.ai_name}, explaining a proposed system action to the user.

ACTION DETAILS:
- Proposed Action: {action.get('proposed_action', 'N/A')}
- Action Type: {action.get('action_type', 'N/A')}
- Risk Level: {action.get('risk_level', 'N/A')}
- Diagnosis: {action.get('diagnosis', 'N/A')}
- Commands to execute: {', '.join(action.get('commands', []))}
- Timestamp: {timestamp}

SYSTEM CONTEXT:
{json.dumps(context, indent=2)}

Please provide a clear, concise explanation of:
1. What problem was detected
2. What this action will do to fix it
3. Why this approach was chosen
4. Any potential risks or side effects
5. Expected outcome

Be conversational and helpful. Use plain language, not technical jargon unless necessary."""

        try:
            response = self.agent._query_ollama(prompt, temperature=0.7)
            return response
        except Exception as e:
            return f"Error generating explanation: {e}"
    
    def answer_action_followup(self, action_index: int, user_question: str) -> str:
        """Answer a follow-up question about a pending action"""
        # Get action from approval queue
        approval_queue_file = self.agent.state_dir / "approval_queue.json"
        
        if not approval_queue_file.exists():
            return "Error: No approval queue found."
        
        try:
            with open(approval_queue_file, 'r') as f:
                queue = json.load(f)
            
            if not (0 <= action_index < len(queue)):
                return f"Error: Action #{action_index} not found."
            
            action_item = queue[action_index]
        except Exception as e:
            return f"Error reading approval queue: {e}"
        
        action = action_item.get("action", {})
        context = action_item.get("context", {})
        
        # Build follow-up prompt
        prompt = f"""You are {self.ai_name}, answering a follow-up question about a proposed action.

ACTION SUMMARY:
- Proposed: {action.get('proposed_action', 'N/A')}
- Type: {action.get('action_type', 'N/A')}
- Risk: {action.get('risk_level', 'N/A')}
- Diagnosis: {action.get('diagnosis', 'N/A')}
- Commands: {', '.join(action.get('commands', []))}

SYSTEM CONTEXT:
{json.dumps(context, indent=2)[:2000]}

USER'S QUESTION:
{user_question}

Please answer the user's question clearly and honestly. If you're uncertain about something, say so. Focus on helping them make an informed decision about whether to approve this action."""

        try:
            response = self.agent._query_ollama(prompt, temperature=0.7)
            return response
        except Exception as e:
            return f"Error: {e}"


def main():
    """Main entry point for macha-chat"""
    
    # Check for --discuss flag (used by macha-approve discuss)
    if "--discuss" in sys.argv:
        try:
            discuss_index = sys.argv.index("--discuss")
            if discuss_index + 1 >= len(sys.argv):
                print("Error: --discuss requires an action number", file=sys.stderr)
                sys.exit(1)
            
            action_number = int(sys.argv[discuss_index + 1])
            
            session = MachaChatSession()
            
            # Check if this is a follow-up question or initial explanation
            if "--follow-up" in sys.argv:
                followup_index = sys.argv.index("--follow-up")
                if followup_index + 1 >= len(sys.argv):
                    print("Error: --follow-up requires a question", file=sys.stderr)
                    sys.exit(1)
                
                # Get the rest of the arguments as the question
                question = " ".join(sys.argv[followup_index + 1:])
                response = session.answer_action_followup(action_number, question)
                print(response)
            else:
                # Initial explanation
                explanation = session.explain_action(action_number)
                print(explanation)
            
            return
            
        except (ValueError, IndexError) as e:
            print(f"Error: Invalid action number: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    
    # Normal interactive chat mode
    session = MachaChatSession()
    session.run_interactive()


def ask_main():
    """Entry point for macha-ask"""
    if len(sys.argv) < 2:
        print("Usage: macha-ask <question>", file=sys.stderr)
        sys.exit(1)
    
    question = " ".join(sys.argv[1:])
    session = MachaChatSession()
    
    response = session.ask_once(question, verbose=True)
    
    print("\n" + "=" * 60)
    print(f"{session.ai_name.upper()}:")
    print("=" * 60)
    print(response)
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
