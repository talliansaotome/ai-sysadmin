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
        llm_backend = None,
        backend_url: str = "http://127.0.0.1:8082/v1",
        model: str = "qwen3:14b",
        state_dir: Path = Path("/var/lib/ai-sysadmin"),
        context_db = None,
        config_repo: str = "git+https://git.coven.systems/lily/nixos-servers",
        config_branch: str = "main",
        ai_name: str = None,
        enable_tools: bool = True
    ):
        self.model = model
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.decision_log = self.state_dir / "decisions.jsonl"
        self.context_db = context_db
        self.config_repo = config_repo
        self.config_branch = config_branch
        self.enable_tools = enable_tools
        
        # Setup LLM backend
        if llm_backend:
            self.llm_backend = llm_backend
        else:
            from llm_backend import LlamaCppBackend
            self.llm_backend = LlamaCppBackend(base_url=backend_url)
        
        # Set AI name with fallback to short hostname
        if ai_name is None:
            import socket
            ai_name = socket.gethostname().split('.')[0]
        self.ai_name = ai_name
        
        # Generate system prompt with AI name substituted
        self.SYSTEM_PROMPT = self.SYSTEM_PROMPT_TEMPLATE.replace("{AI_NAME}", self.ai_name)
        
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
            response = self._query_llm(prompt, temperature=0.3, timeout=30)
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
        
        response = self._query_llm(prompt)
        
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
        
        response = self._query_llm(prompt)
        
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
    
    def _auto_diagnose_llm(self) -> str:
        """Automatically diagnose LLM backend issues"""
        diagnostics = []
        
        diagnostics.append("=== LLM BACKEND DIAGNOSTIC ===")
        
        # Check if backend is available
        try:
            is_available = self.llm_backend.is_available()
            if is_available:
                diagnostics.append("✅ LLM backend is available")
            else:
                diagnostics.append(f"❌ LLM backend is NOT available")
        except Exception as e:
            diagnostics.append(f"⚠️  Could not check backend status: {e}")
        
        # Check memory usage
        try:
            result = subprocess.run(['free', '-h'], capture_output=True, text=True, timeout=5)
            diagnostics.append(f"\nMemory:\n{result.stdout}")
        except Exception as e:
            diagnostics.append(f"⚠️  Could not check memory: {e}")
        
        diagnostics.append(f"\nConfigured model: {self.model}")
        
        return "\n".join(diagnostics)
    
    def _query_llm(self, prompt: str, temperature: float = 0.3, max_tokens: int = 2000) -> str:
        """Query LLM backend"""
        try:
            response = self.llm_backend.generate(
                prompt=prompt,
                model=self.model,
                system_prompt=self.SYSTEM_PROMPT,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            if response and not response.startswith("Error:"):
                return response
            else:
                print(f"ERROR: LLM backend error: {response}")
                return json.dumps({
                    "error": f"LLM backend error: {response}",
                    "diagnosis": f"Check if model '{self.model}' is available",
                    "action_type": "investigation",
                    "risk_level": "high"
                })
        except Exception as e:
            print(f"ERROR: Failed to query LLM: {str(e)}")
            print(f"Model requested: {self.model}")
            return json.dumps({
                "error": f"Failed to query LLM: {str(e)}",
                "diagnosis": "LLM backend unavailable",
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
                
                summary = self._query_llm(extraction_prompt, temperature=0.1)
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
                
                chunk_summary = self._query_llm(extraction_prompt, temperature=0.1)
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
                
                final_summary = self._query_llm(reduce_prompt, temperature=0.1)
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
    
    def _query_llm_with_tools(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_iterations: int = 30
    ) -> str:
        """
        Query LLM with tool support using simplified prompting.
        Note: llama.cpp doesn't have native tool calling, so we use prompt-based tools.
        
        Args:
            messages: List of chat messages [{"role": "user", "content": "..."}]
            temperature: Generation temperature
            max_iterations: Maximum number of tool-calling iterations
            
        Returns:
            Final text response from the model
        """
        if not self.enable_tools or not self.tools:
            # Fallback to regular query
            user_content = " ".join([m["content"] for m in messages if m["role"] == "user"])
            return self._query_llm(user_content, temperature)
        
        # For now, use simplified approach: describe tools in prompt and parse responses
        # This is a temporary solution until we implement proper function calling
        user_content = " ".join([m["content"] for m in messages if m["role"] == "user"])
        
        tool_definitions = self.tools.get_tool_definitions()
        tools_description = "\n\nAvailable tools:\n" + json.dumps(tool_definitions, indent=2)
        
        enhanced_prompt = f"""{user_content}

{tools_description}

You can use these tools by responding with JSON in this format:
{{"tool": "tool_name", "arguments": {{"arg1": "value1"}}}}

Or respond with regular text if no tools are needed."""
        
        # Simple tool calling loop (simplified from Ollama's native support)
        for iteration in range(max_iterations):
            try:
                response_text = self._query_llm(enhanced_prompt, temperature)
                
                # Check if response contains tool call (simple JSON parsing)
                try:
                    # Try to parse as JSON tool call
                    tool_call = json.loads(response_text)
                    if "tool" in tool_call and "arguments" in tool_call:
                        function_name = tool_call["tool"]
                        arguments = tool_call["arguments"]
                        
                        print(f"  → Tool call: {function_name}({arguments})")
                        
                        # Execute the tool
                        tool_result = self.tools.execute_tool(function_name, arguments)
                        
                        # Process result hierarchically
                        processed_result = self._process_tool_result_hierarchical(function_name, tool_result)
                        
                        # Add result to prompt for next iteration
                        enhanced_prompt = f"""Previous tool call: {function_name}
Result: {processed_result}

Based on this result, what should we do next?
{tools_description}"""
                        continue
                except json.JSONDecodeError:
                    pass
                
                # No tool call, return the response
                return response_text
                
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
