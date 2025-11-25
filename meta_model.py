#!/usr/bin/env python3
"""
Meta Model - Layer 4: High-level AI for complex analysis and user interaction

This is the main AI model that runs ON-DEMAND only when:
1. The review model escalates a complex issue
2. The user initiates a chat session
3. High-stakes decisions are required

Uses the full context window and has access to all historical data.
"""

import json
import requests
import subprocess
from typing import Dict, List, Any, Optional
from pathlib import Path
from datetime import datetime

from tools import SysadminTools


class MetaModel:
    """
    Meta AI model for high-level system analysis and user interaction
    
    This is Layer 4 of the architecture - the senior AI that handles:
    - Complex multi-system issues requiring deep analysis
    - User-facing conversations and explanations
    - High-risk decision making
    - Long-term trend analysis
    
    Unlike the review model (Layer 3), this model:
    - Runs only on-demand (not continuously)
    - Has access to full context and history
    - Can make high-stakes decisions
    - Provides detailed explanations to users
    """
    
    # Load system prompt template from file (with {AI_NAME} placeholder)
    @staticmethod
    def _load_system_prompt_template() -> str:
        """Load the system prompt template from file"""
        prompt_file = Path(__file__).parent / "system_prompt.txt"
        try:
            return prompt_file.read_text()
        except Exception as e:
            print(f"Warning: Could not load system prompt from {prompt_file}: {e}")
            return "You are {AI_NAME}, an autonomous AI system maintenance agent."
    
    SYSTEM_PROMPT_TEMPLATE = _load_system_prompt_template.__func__()
    
    def __init__(
        self,
        ollama_host: str = "http://localhost:11434",
        model: str = "gpt-oss:20b",
        state_dir: Path = Path("/var/lib/ai-sysadmin"),
        context_db = None,
        config_repo: str = "git+https://git.coven.systems/lily/nixos-servers",
        config_branch: str = "main",
        ai_name: str = None,
        enable_tools: bool = True,
        use_queue: bool = True,
        priority: str = "INTERACTIVE"
    ):
        self.ollama_host = ollama_host
        self.model = model
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.decision_log = self.state_dir / "decisions.jsonl"
        self.context_db = context_db
        self.config_repo = config_repo
        self.config_branch = config_branch
        self.enable_tools = enable_tools
        
        # Set AI name with fallback to short hostname
        if ai_name is None:
            import socket
            ai_name = socket.gethostname().split('.')[0]
        self.ai_name = ai_name
        
        # Generate system prompt with AI name substituted
        self.SYSTEM_PROMPT = self.SYSTEM_PROMPT_TEMPLATE.replace("{AI_NAME}", self.ai_name)
        
        # Queue settings
        self.use_queue = use_queue
        self.priority = priority
        self.ollama_queue = None
        
        if use_queue:
            try:
                from ollama_queue import OllamaQueue, Priority
                self.ollama_queue = OllamaQueue()
                self.priority_level = getattr(Priority, priority, Priority.INTERACTIVE)
            except (PermissionError, OSError):
                # Silently fall back to direct API calls when queue is not accessible
                # (e.g., regular users don't have access to /var/lib/ai-sysadmin/queues)
                self.use_queue = False
            except Exception as e:
                # Log unexpected errors but still fall back gracefully
                import sys
                print(f"Note: Ollama queue unavailable ({type(e).__name__}), using direct API", file=sys.stderr)
                self.use_queue = False
        
        # Initialize tools system
        self.tools = SysadminTools(safe_mode=False) if enable_tools else None
        
        # Tool output cache for hierarchical processing
        self.tool_output_cache = {}
        self.cache_dir = self.state_dir / "tool_cache"
        
        # Only create cache dir if we have write access (running as macha user)
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except (PermissionError, OSError):
            # Running as unprivileged user (macha-chat), use temp dir instead
            import tempfile
            self.cache_dir = Path(tempfile.mkdtemp(prefix="macha_cache_"))
    
    def _query_relevant_knowledge(self, query: str, limit: int = 3) -> str:
        """
        Query knowledge base for relevant information
        
        Returns formatted string of relevant knowledge to include in prompts
        """
        if not self.context_db:
            return ""
        
        try:
            knowledge_items = self.context_db.query_knowledge(query, limit=limit)
            if not knowledge_items:
                return ""
            
            knowledge_text = "\n\nRELEVANT KNOWLEDGE FROM EXPERIENCE:\n"
            for item in knowledge_items:
                knowledge_text += f"\n• {item['topic']} ({item['category']}):\n"
                knowledge_text += f"  {item['knowledge']}\n"
                knowledge_text += f"  [Confidence: {item['confidence']}, Referenced: {item['times_referenced']} times]\n"
            
            return knowledge_text
        except Exception as e:
            print(f"Error querying knowledge: {e}")
            return ""
    
    def store_learning(
        self,
        topic: str,
        knowledge: str,
        category: str = "experience",
        confidence: str = "medium",
        tags: list = None
    ) -> bool:
        """
        Store a learned insight into the knowledge base
        
        Args:
            topic: What this is about
            knowledge: The insight/pattern/learning
            category: Type of knowledge
            confidence: How confident we are
            tags: Optional tags
        
        Returns:
            True if stored successfully
        """
        if not self.context_db:
            return False
        
        try:
            kid = self.context_db.store_knowledge(
                topic=topic,
                knowledge=knowledge,
                category=category,
                source="experience",
                confidence=confidence,
                tags=tags
            )
            if kid:
                print(f"📚 Learned: {topic}")
                return True
            return False
        except Exception as e:
            print(f"Error storing learning: {e}")
            return False
    
    def reflect_and_learn(
        self,
        situation: str,
        action_taken: str,
        outcome: str,
        success: bool
    ) -> None:
        """
        Reflect on an operation and extract learnings to store
        
        Args:
            situation: What was the problem/situation
            action_taken: What action was taken
            outcome: What was the result
            success: Whether it succeeded
        """
        if not self.context_db:
            return
        
        # Only learn from successful operations for now
        if not success:
            return
        
        # Build reflection prompt
        prompt = f"""Based on this successful operation, extract key learnings to remember for the future.

SITUATION:
{situation}

ACTION TAKEN:
{action_taken}

OUTCOME:
{outcome}

Extract 1-2 specific, actionable learnings. For each learning provide:
1. topic: A concise topic name (e.g., "systemd service restart", "disk cleanup procedure")
2. knowledge: The specific insight or pattern (what worked, why, important details)
3. category: One of: command, pattern, troubleshooting, performance

Respond ONLY with valid JSON:
[
  {{
    "topic": "...",
    "knowledge": "...",
    "category": "...",
    "confidence": "medium"
  }}
]
"""
        
        try:
            response = self._query_ollama(prompt, temperature=0.3, timeout=30)
            learnings = json.loads(response)
            
            if isinstance(learnings, list):
                for learning in learnings:
                    if all(k in learning for k in ['topic', 'knowledge', 'category']):
                        self.store_learning(
                            topic=learning['topic'],
                            knowledge=learning['knowledge'],
                            category=learning.get('category', 'experience'),
                            confidence=learning.get('confidence', 'medium')
                        )
        except Exception as e:
            # Reflection is optional - don't fail if it doesn't work
            print(f"Note: Could not extract learnings: {e}")
        
    def analyze_system_state(self, monitoring_data: Dict[str, Any], system_hostname: str = None, git_context=None) -> Dict[str, Any]:
        """Analyze system monitoring data and determine if action is needed"""
        
        # Build context for the AI
        context = self._build_analysis_context(monitoring_data)
        
        # Get system infrastructure context if available
        system_context = ""
        if self.context_db and system_hostname:
            system_context = self.context_db.get_system_context(system_hostname, git_context)
        
        # Ask the AI to analyze
        prompt = self._create_analysis_prompt(context, system_context)
        
        response = self._query_ollama(prompt)
        
        # Parse the AI's response
        analysis = self._parse_analysis_response(response)
        
        # Log the decision
        self._log_decision(monitoring_data, analysis)
        
        return analysis
    
    def propose_fix(self, issue_description: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Propose a fix for a specific issue"""
        
        # Query relevant config files if we have context_db
        relevant_configs = []
        if self.context_db:
            try:
                # Query for config files relevant to the issue
                configs = self.context_db.query_config_files(
                    query=issue_description,
                    n_results=3
                )
                relevant_configs = configs
            except Exception as e:
                print(f"Warning: Could not query config files: {e}")
        
        # Build config context section
        config_context = ""
        if relevant_configs:
            config_context = "\n\nRELEVANT CONFIGURATION FILES:\n"
            for cfg in relevant_configs:
                config_context += f"\n--- {cfg['path']} (relevance: {cfg['relevance']:.2%}) ---\n"
                config_context += cfg['content'][:1000]  # First 1000 chars to avoid token limits
                if len(cfg['content']) > 1000:
                    config_context += "\n... (truncated)"
                config_context += "\n"
        
        # Query relevant knowledge from experience
        knowledge_context = self._query_relevant_knowledge(issue_description, limit=3)
        
        # Build previous investigations context
        previous_inv_context = ""
        if context.get('previous_investigations'):
            previous_inv_context = "\n\nPREVIOUS INVESTIGATIONS (DO NOT REPEAT THESE):\n"
            for i, inv in enumerate(context['previous_investigations'][:3], 1):  # Show up to 3
                previous_inv_context += f"\nInvestigation #{i} ({inv['timestamp']}):\n"
                previous_inv_context += f"Commands: {', '.join(inv['commands'])}\n"
                previous_inv_context += f"Results:\n{inv['output'][:500]}...\n"  # First 500 chars
            previous_inv_context += "\n⚠️  You have already run these investigations. Do NOT propose them again."
            previous_inv_context += "\n⚠️  Based on the investigation results above, propose an ACTUAL FIX, not more investigation.\n"
        
        prompt = f"""{self.SYSTEM_PROMPT}

TASK: PROPOSE FIX
================================================================================

ISSUE TO ADDRESS:
{issue_description}

SYSTEM CONTEXT:
{json.dumps(context, indent=2)}{config_context}{knowledge_context}{previous_inv_context}

REPOSITORY INFO:
- Git Repository: {self.config_repo}
- Branch: {self.config_branch}

YOUR RESPONSE MUST BE VALID JSON:
{{
    "diagnosis": "brief description of what you think is wrong",
    "proposed_action": "specific action to take",
    "action_type": "one of: systemd_restart, nix_rebuild, config_change, cleanup, investigation",
    "risk_level": "one of: low, medium, high",
    "commands": ["list", "of", "shell", "commands"],
    "config_changes": {{
        "file": "path/to/config.nix in the repository",
        "change": "description of change needed"
    }},
    "reasoning": "why this fix should work",
    "rollback_plan": "how to undo if it doesn't work"
}}

RESPOND WITH ONLY THE JSON, NO OTHER TEXT.
"""
        
        response = self._query_ollama(prompt)
        
        try:
            # Try to extract JSON from response
            # LLMs sometimes add extra text, so we need to find the JSON part
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            else:
                return {
                    "diagnosis": "Failed to parse AI response",
                    "proposed_action": "manual investigation required",
                    "action_type": "investigation",
                    "risk_level": "high",
                    "reasoning": "AI response was not in expected format"
                }
        except json.JSONDecodeError:
            return {
                "diagnosis": "Failed to parse AI response",
                "proposed_action": "manual investigation required",
                "action_type": "investigation",
                "risk_level": "high",
                "reasoning": f"Raw response: {response[:500]}"
            }
    
    def _build_analysis_context(self, data: Dict[str, Any]) -> str:
        """Build a concise context string for the AI"""
        lines = []
        
        # System resources
        res = data.get("resources", {})
        lines.append(f"CPU: {res.get('cpu_percent', 0):.1f}%, Memory: {res.get('memory_percent', 0):.1f}%, Load: {res.get('load_average', {}).get('1min', 0):.2f}")
        
        # Disk usage
        disk = data.get("disk", {})
        for part in disk.get("partitions", []):
            if part.get("percent_used", 0) > 80:  # Only mention if >80% full
                lines.append(f"⚠️  Disk {part['mountpoint']}: {part['percent_used']:.1f}% full")
        
        # Failed services
        systemd = data.get("systemd", {})
        if systemd.get("failed_count", 0) > 0:
            lines.append(f"\n⚠️  {systemd['failed_count']} failed systemd services:")
            for svc in systemd.get("failed_services", [])[:10]:
                lines.append(f"  - {svc.get('unit', 'unknown')}: {svc.get('sub', 'unknown')}")
        
        # Recent errors
        logs = data.get("logs", {})
        error_count = logs.get("error_count_1h", 0)
        if error_count > 0:
            lines.append(f"\n{error_count} errors in last hour")
            # Group errors by service
            errors_by_service = {}
            for err in logs.get("recent_errors", [])[:20]:
                svc = err.get("SYSLOG_IDENTIFIER", "unknown")
                errors_by_service[svc] = errors_by_service.get(svc, 0) + 1
            for svc, count in sorted(errors_by_service.items(), key=lambda x: x[1], reverse=True)[:5]:
                lines.append(f"  - {svc}: {count} errors")
        
        # Network
        net = data.get("network", {})
        if not net.get("internet_reachable", True):
            lines.append("\n⚠️  No internet connectivity")
        
        return "\n".join(lines)
    
    def _create_analysis_prompt(self, context: str, system_context: str = "") -> str:
        """Create the analysis prompt for the AI"""
        
        prompt = f"""{self.SYSTEM_PROMPT}

TASK: ANALYZE SYSTEM HEALTH
================================================================================

OBJECTIVE:
Analyze the current system state and determine if any action is needed.
Be thorough but not alarmist. Only recommend action if truly necessary.
"""
        
        if system_context:
            prompt += f"\n\nSYSTEM INFRASTRUCTURE:\n{system_context}"
        
        prompt += f"""

CURRENT SYSTEM STATE:
{context}

YOUR RESPONSE MUST BE VALID JSON:
{{
    "status": "one of: healthy, attention_needed, intervention_required",
    "issues": [
        {{
            "severity": "one of: info, warning, critical",
            "category": "one of: resources, services, disk, network, logs",
            "description": "brief description of the issue",
            "requires_action": true/false
        }}
    ],
    "overall_assessment": "brief summary of system health",
    "recommended_actions": ["list of recommended actions, if any"]
}}

RESPOND WITH ONLY THE JSON, NO OTHER TEXT.
"""
        
        return prompt
    
    def _auto_diagnose_ollama(self) -> str:
        """Automatically diagnose Ollama issues"""
        diagnostics = []
        
        diagnostics.append("=== OLLAMA SELF-DIAGNOSTIC ===")
        
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
        except Exception as e:
            diagnostics.append(f"⚠️  Could not check service status: {e}")
        
        # Check memory usage
        try:
            result = subprocess.run(['free', '-h'], capture_output=True, text=True, timeout=5)
            diagnostics.append(f"\nMemory:\n{result.stdout}")
        except Exception as e:
            diagnostics.append(f"⚠️  Could not check memory: {e}")
        
        # Check which models are loaded
        try:
            response = requests.get(f"{self.ollama_host}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get('models', [])
                diagnostics.append(f"\nLoaded models: {len(models)}")
                for model in models:
                    name = model.get('name', 'unknown')
                    size = model.get('size', 0) / (1024**3)
                    is_target = "← TARGET" if name == self.model else ""
                    diagnostics.append(f"  • {name} ({size:.1f} GB) {is_target}")
                
                # Check if target model is loaded
                model_names = [m.get('name') for m in models]
                if self.model not in model_names:
                    diagnostics.append(f"\n❌ TARGET MODEL NOT LOADED: {self.model}")
                    diagnostics.append(f"   Available: {', '.join(model_names)}")
            else:
                diagnostics.append(f"❌ Ollama API returned {response.status_code}")
        except Exception as e:
            diagnostics.append(f"⚠️  Could not query Ollama API: {e}")
        
        # Check recent Ollama logs
        try:
            result = subprocess.run(
                ['journalctl', '-u', 'ollama.service', '-n', '20', '--no-pager'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.stdout:
                diagnostics.append(f"\nRecent logs:\n{result.stdout}")
        except Exception as e:
            diagnostics.append(f"⚠️  Could not check logs: {e}")
        
        return "\n".join(diagnostics)
    
    def _query_ollama(self, prompt: str, temperature: float = 0.3) -> str:
        """Query Ollama API (with optional queue)"""
        # If queue is enabled, submit to queue and wait
        if self.use_queue and self.ollama_queue:
            try:
                # Check if there's already an AUTONOMOUS request pending/processing
                if self.priority_level.value == 1:  # AUTONOMOUS
                    if self.ollama_queue.has_pending_with_priority(self.priority_level):
                        print("[Queue] Skipping request - AUTONOMOUS check already in queue")
                        return "System check already in progress - skipping duplicate request"
                
                payload = {
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": temperature,
                    "timeout": 120
                }
                
                request_id = self.ollama_queue.submit(
                    request_type="generate",
                    payload=payload,
                    priority=self.priority_level
                )
                
                result = self.ollama_queue.wait_for_result(request_id, timeout=300)
                return result.get("response", "")
            
            except Exception as e:
                print(f"Warning: Queue request failed, falling back to direct: {e}")
                # Fall through to direct query
        
        # Direct query (no queue or queue failed)
        try:
            response = requests.post(
                f"{self.ollama_host}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": temperature,
                },
                timeout=120  # 2 minute timeout for large models
            )
            response.raise_for_status()
            return response.json().get("response", "")
        except requests.exceptions.HTTPError as e:
            error_detail = ""
            try:
                error_detail = f" - {response.text}"
            except:
                pass
            print(f"ERROR: Ollama HTTP error {response.status_code}{error_detail}")
            print(f"Model requested: {self.model}")
            print(f"Ollama host: {self.ollama_host}")
            # Run diagnostics
            diagnostics = self._auto_diagnose_ollama()
            print(diagnostics)
            return json.dumps({
                "error": f"Ollama HTTP {response.status_code}: {str(e)}{error_detail}",
                "diagnosis": f"Ollama API error - check if model '{self.model}' is available",
                "action_type": "investigation",
                "risk_level": "high"
            })
        except Exception as e:
            print(f"ERROR: Failed to query Ollama: {str(e)}")
            print(f"Model requested: {self.model}")
            print(f"Ollama host: {self.ollama_host}")
            # Run diagnostics
            diagnostics = self._auto_diagnose_ollama()
            print(diagnostics)
            return json.dumps({
                "error": f"Failed to query Ollama: {str(e)}",
                "diagnosis": "Ollama API unavailable",
                "action_type": "investigation",
                "risk_level": "high"
            })
    
    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation: ~4 chars per token"""
        return len(text) // 4
    
    def _extract_key_findings(self, tool_name: str, raw_output: str, progress_callback=None) -> str:
        """
        Extract key findings from large tool output using chunked map-reduce.
        Processes large outputs in smaller chunks to prevent Ollama overload.
        """
        output_size = len(raw_output)
        chunk_size = 8000  # ~2000 tokens per chunk, safe size
        
        # Store full output in cache for potential deep dive
        cache_id = f"{tool_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        try:
            cache_file = self.cache_dir / f"{cache_id}.txt"
            cache_file.write_text(raw_output)
        except (PermissionError, OSError):
            # Fallback to temp directory if cache dir not writable
            import tempfile
            cache_file = Path(tempfile.gettempdir()) / f"macha_{cache_id}.txt"
            cache_file.write_text(raw_output)
        
        # If output is small enough, process in one go
        if output_size <= chunk_size:
            try:
                extraction_prompt = f"""Analyze this output from '{tool_name}'.

Extract: key findings, errors/warnings, metrics, actionable insights.

Output:
{raw_output}

Provide concise summary (max 600 chars)."""
                
                summary = self._query_ollama(extraction_prompt, temperature=0.1)
                return f"[Summary of {tool_name}]:\n{summary}\n\n[Full output: {output_size:,} chars cached as {cache_id}]"
            except Exception as e:
                print(f"Warning: Failed to extract findings: {e}")
                return self._simple_truncate(raw_output, 2000)
        
        # Large output: chunk and process with map-reduce
        try:
            chunks = []
            num_chunks = (output_size + chunk_size - 1) // chunk_size
            
            for i in range(0, output_size, chunk_size):
                chunk = raw_output[i:i+chunk_size]
                chunks.append(chunk)
            
            # Phase 1: Map - Summarize each chunk
            chunk_summaries = []
            for idx, chunk in enumerate(chunks):
                chunk_num = idx + 1
                
                # Progress feedback
                if progress_callback:
                    progress_callback(f"  Processing chunk {chunk_num}/{num_chunks}...")
                else:
                    print(f"  → Processing chunk {chunk_num}/{num_chunks}...", flush=True)
                
                extraction_prompt = f"""Analyze chunk {chunk_num}/{num_chunks} from '{tool_name}'.

Extract: key findings, errors/warnings, metrics, insights.

Chunk:
{chunk}

Concise summary (max 400 chars)."""
                
                chunk_summary = self._query_ollama(extraction_prompt, temperature=0.1)
                chunk_summaries.append(f"[Chunk {chunk_num}]: {chunk_summary}")
            
            # Phase 2: Reduce - Combine chunk summaries if many chunks
            if len(chunk_summaries) > 5:
                if progress_callback:
                    progress_callback(f"  Synthesizing {len(chunk_summaries)} chunk summaries...")
                else:
                    print(f"  → Synthesizing {len(chunk_summaries)} chunk summaries...", flush=True)
                
                combined = "\n".join(chunk_summaries)
                reduce_prompt = f"""Synthesize these chunk summaries from '{tool_name}':

{combined}

Provide unified summary (max 800 chars) covering all key points."""
                
                final_summary = self._query_ollama(reduce_prompt, temperature=0.1)
                return f"""[Chunked analysis of {tool_name}]:
{final_summary}

[Processed {num_chunks} chunks, {output_size:,} chars total, cached as {cache_id}]"""
            
            else:
                # Few chunks: just concatenate summaries
                combined_summary = "\n".join(chunk_summaries)
                return f"""[Chunked analysis of {tool_name}]:
{combined_summary}

[Processed {num_chunks} chunks, {output_size:,} chars total, cached as {cache_id}]"""
        
        except Exception as e:
            print(f"Warning: Chunked extraction failed for {tool_name}: {e}")
            return self._simple_truncate(raw_output, 2000)
    
    def _simple_truncate(self, text: str, max_chars: int) -> str:
        """Simple head+tail truncation"""
        if len(text) <= max_chars:
            return text
        
        half = max_chars // 2
        return (
            text[:half] + 
            f"\n... [TRUNCATED: {len(text) - max_chars} chars omitted] ...\n" +
            text[-half:]
        )
    
    def _process_tool_result_hierarchical(self, tool_name: str, result: Any) -> str:
        """
        Intelligently process tool results based on size:
        - Small (< 5KB): Pass through directly
        - Medium (5-20KB): Hierarchical extraction with single-pass summarization
        - Large (> 20KB): Hierarchical extraction with chunked processing
        """
        result_str = json.dumps(result) if not isinstance(result, str) else result
        size = len(result_str)
        
        # Small outputs: pass through directly
        if size < 5000:
            print(f"  [Tool result: {size} chars, passing through]")
            return result_str
        
        # Medium and large outputs: hierarchical extraction with chunking
        else:
            print(f"  [Tool result: {size} chars, extracting key findings...]")
            # _extract_key_findings automatically chunks large outputs
            return self._extract_key_findings(tool_name, result_str)
    
    def _prune_messages(self, messages: List[Dict], max_context_tokens: int = 80000) -> List[Dict]:
        """
        Prune message history to stay within context limits.
        Keeps: system prompt + recent conversation window
        """
        if not messages:
            return messages
        
        # Separate system message from conversation
        system_msg = None
        conversation = []
        
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg
            else:
                conversation.append(msg)
        
        # Calculate current token count
        total_tokens = 0
        if system_msg:
            total_tokens += self._estimate_tokens(system_msg["content"])
        
        for msg in conversation:
            content = msg.get("content", "")
            total_tokens += self._estimate_tokens(str(content))
        
        # If under limit, return as-is
        if total_tokens <= max_context_tokens:
            result = []
            if system_msg:
                result.append(system_msg)
            result.extend(conversation)
            print(f"[Context: {total_tokens:,} tokens, {len(conversation)} messages]")
            return result
        
        # Need to prune - keep sliding window of recent messages
        # Strategy: Keep last 20 messages (10 exchanges) which should be ~40K tokens max
        print(f"[Context pruning: {total_tokens:,} tokens → keeping last 20 messages]")
        
        pruned_conversation = conversation[-20:]
        
        result = []
        if system_msg:
            result.append(system_msg)
        result.extend(pruned_conversation)
        
        # Calculate new token count
        new_tokens = self._estimate_tokens(system_msg["content"]) if system_msg else 0
        for msg in pruned_conversation:
            new_tokens += self._estimate_tokens(str(msg.get("content", "")))
        
        print(f"[Context after pruning: {new_tokens:,} tokens, {len(pruned_conversation)} messages]")
        
        return result
    
    def _query_ollama_with_tools(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_iterations: int = 30
    ) -> str:
        """
        Query Ollama using chat API with tool support.
        Handles tool calls and returns final response.
        
        Args:
            messages: List of chat messages [{"role": "user", "content": "..."}]
            temperature: Generation temperature
            max_iterations: Maximum number of tool-calling iterations (default 30 for complex system operations)
            
        Returns:
            Final text response from the model
        """
        if not self.enable_tools or not self.tools:
            # Fallback to regular query
            user_content = " ".join([m["content"] for m in messages if m["role"] == "user"])
            return self._query_ollama(user_content, temperature)
        
        # Add system message if not present
        if not any(m["role"] == "system" for m in messages):
            messages = [{"role": "system", "content": self.SYSTEM_PROMPT}] + messages
        
        tool_definitions = self.tools.get_tool_definitions()
        
        for iteration in range(max_iterations):
            try:
                # Prune messages before sending to avoid context overflow
                pruned_messages = self._prune_messages(messages, max_context_tokens=80000)
                
                # Use queue if enabled
                if self.use_queue and self.ollama_queue:
                    try:
                        # Check if there's already an AUTONOMOUS request pending/processing
                        if self.priority_level.value == 1:  # AUTONOMOUS
                            if self.ollama_queue.has_pending_with_priority(self.priority_level):
                                print("[Queue] Skipping request - AUTONOMOUS check already in queue")
                                return "System check already in progress - skipping duplicate request"
                        
                        payload = {
                            "model": self.model,
                            "messages": pruned_messages,
                            "stream": False,
                            "temperature": temperature,
                            "tools": tool_definitions,
                            "timeout": 120
                        }
                        
                        request_id = self.ollama_queue.submit(
                            request_type="chat_with_tools",
                            payload=payload,
                            priority=self.priority_level
                        )
                        
                        resp_data = self.ollama_queue.wait_for_result(request_id, timeout=300)
                    
                    except Exception as e:
                        print(f"Warning: Queue request failed, falling back to direct: {e}")
                        # Fall through to direct query
                        response = requests.post(
                            f"{self.ollama_host}/api/chat",
                            json={
                                "model": self.model,
                                "messages": pruned_messages,
                                "stream": False,
                                "temperature": temperature,
                                "tools": tool_definitions
                            },
                            timeout=120
                        )
                        response.raise_for_status()
                        resp_data = response.json()
                else:
                    # Direct query (no queue)
                    response = requests.post(
                        f"{self.ollama_host}/api/chat",
                        json={
                            "model": self.model,
                            "messages": pruned_messages,
                            "stream": False,
                            "temperature": temperature,
                            "tools": tool_definitions
                        },
                        timeout=120
                    )
                    response.raise_for_status()
                    resp_data = response.json()
                
                message = resp_data.get("message", {})
                
                # Check if model wants to call tools
                tool_calls = message.get("tool_calls", [])
                
                if not tool_calls:
                    # No tools to call, return the text response
                    return message.get("content", "")
                
                # Add assistant's message to history
                messages.append(message)
                
                # Execute each tool call
                for tool_call in tool_calls:
                    function_name = tool_call["function"]["name"]
                    arguments = tool_call["function"]["arguments"]
                    
                    print(f"  → Tool call: {function_name}({arguments})")
                    
                    # Execute the tool
                    tool_result = self.tools.execute_tool(function_name, arguments)
                    
                    # Process result hierarchically based on size
                    processed_result = self._process_tool_result_hierarchical(function_name, tool_result)
                    
                    # Add processed result to messages
                    messages.append({
                        "role": "tool",
                        "content": processed_result
                    })
                
                # Continue loop to let model process tool results
                
            except requests.exceptions.HTTPError as e:
                error_body = ""
                try:
                    error_body = response.text
                except:
                    pass
                
                # Check if this is a context length error
                if "context length" in error_body.lower() or "too long" in error_body.lower():
                    print(f"ERROR: Context length exceeded. Attempting recovery...")
                    # Emergency pruning - keep only system + last user message
                    system_msg = next((m for m in messages if m["role"] == "system"), None)
                    last_user_msg = next((m for m in reversed(messages) if m["role"] == "user"), None)
                    
                    if system_msg and last_user_msg:
                        messages = [system_msg, last_user_msg]
                        print(f"[Emergency context reset: keeping only system + last user message]")
                        continue  # Retry with minimal context
                
                print(f"ERROR: Ollama chat API error: {e}")
                diagnostics = self._auto_diagnose_ollama()
                print(diagnostics)
                return json.dumps({
                    "error": f"Ollama chat API error: {str(e)}",
                    "diagnosis": "Failed to communicate with Ollama",
                    "action_type": "investigation",
                    "risk_level": "high"
                })
            except Exception as e:
                print(f"ERROR: Tool calling failed: {e}")
                return json.dumps({
                    "error": f"Tool calling error: {str(e)}",
                    "diagnosis": "Failed during tool execution",
                    "action_type": "investigation",
                    "risk_level": "high"
                })
        
        # If we hit max iterations, return what we have
        return "Maximum tool calling iterations reached. Unable to complete request."
    
    def _parse_analysis_response(self, response: str) -> Dict[str, Any]:
        """Parse the AI's analysis response"""
        import re
        
        # Log the raw response for debugging
        self._log(f"AI raw response (first 1000 chars): {response[:1000]}")
        
        try:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                self._log(f"Successfully parsed AI response: {parsed.get('status', 'unknown')}")
                return parsed
            else:
                self._log("ERROR: No JSON found in AI response")
        except Exception as e:
            self._log(f"ERROR parsing AI response: {e}")
        
        # Fallback
        self._log("Falling back to default response")
        return {
            "status": "healthy",
            "issues": [],
            "overall_assessment": "Unable to parse AI response",
            "recommended_actions": []
        }
    
    def _log(self, message: str):
        """Log a message to the orchestrator log"""
        # This will go to the orchestrator log via print
        print(f"[AGENT] {message}")
    
    def _log_decision(self, monitoring_data: Dict[str, Any], analysis: Dict[str, Any]):
        """Log AI decisions for auditing"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "monitoring_summary": {
                "cpu": monitoring_data.get("resources", {}).get("cpu_percent"),
                "memory": monitoring_data.get("resources", {}).get("memory_percent"),
                "failed_services": monitoring_data.get("systemd", {}).get("failed_count"),
                "error_count": monitoring_data.get("logs", {}).get("error_count_1h"),
            },
            "analysis": analysis,
        }
        
        with open(self.decision_log, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
    
    def get_recent_decisions(self, count: int = 10) -> List[Dict[str, Any]]:
        """Get recent decision history"""
        if not self.decision_log.exists():
            return []
        
        decisions = []
        with open(self.decision_log, 'r') as f:
            for line in f:
                if line.strip():
                    try:
                        decisions.append(json.loads(line))
                    except:
                        pass
        
        return decisions[-count:]


if __name__ == "__main__":
    import sys
    
    # Test the agent
    agent = MachaAgent()
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # Test with sample data
        test_data = {
            "systemd": {"failed_count": 2, "failed_services": [
                {"unit": "test-service.service", "sub": "failed"}
            ]},
            "resources": {"cpu_percent": 25.0, "memory_percent": 45.0, "load_average": {"1min": 1.5}},
            "logs": {"error_count_1h": 10},
            "network": {"internet_reachable": True}
        }
        
        print("Testing agent analysis...")
        analysis = agent.analyze_system_state(test_data)
        print(json.dumps(analysis, indent=2))
        
        if analysis.get("issues"):
            print("\nTesting fix proposal...")
            fix = agent.propose_fix(
                analysis["issues"][0]["description"],
                test_data
            )
            print(json.dumps(fix, indent=2))
