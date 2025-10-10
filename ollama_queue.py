#!/usr/bin/env python3
"""
Ollama Queue Handler - Serializes all LLM requests to prevent resource contention
"""

import json
import time
import fcntl
import signal
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from datetime import datetime
from enum import IntEnum

class Priority(IntEnum):
    """Request priority levels"""
    INTERACTIVE = 0  # User requests (highest priority)
    AUTONOMOUS = 1   # Background maintenance
    BATCH = 2        # Low priority bulk operations

class OllamaQueue:
    """File-based queue for serializing Ollama requests"""
    
    def __init__(self, queue_dir: Path = Path("/var/lib/ai-sysadmin/queues/ollama")):
        self.queue_dir = queue_dir
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        self.pending_dir = self.queue_dir / "pending"
        self.processing_dir = self.queue_dir / "processing"
        self.completed_dir = self.queue_dir / "completed"
        self.failed_dir = self.queue_dir / "failed"
        
        for dir in [self.pending_dir, self.processing_dir, self.completed_dir, self.failed_dir]:
            dir.mkdir(parents=True, exist_ok=True)
        
        self.lock_file = self.queue_dir / "queue.lock"
        self.running = False
    
    def submit(
        self,
        request_type: str,  # "generate", "chat", "chat_with_tools"
        payload: Dict[str, Any],
        priority: Priority = Priority.INTERACTIVE,
        callback: Optional[Callable] = None,
        progress_callback: Optional[Callable] = None
    ) -> str:
        """Submit a request to the queue. Returns request ID."""
        request_id = f"{int(time.time() * 1000000)}_{priority.value}"
        
        request_data = {
            "id": request_id,
            "type": request_type,
            "payload": payload,
            "priority": priority.value,
            "submitted_at": datetime.now().isoformat(),
            "status": "pending"
        }
        
        request_file = self.pending_dir / f"{request_id}.json"
        request_file.write_text(json.dumps(request_data, indent=2))
        
        return request_id
    
    def get_status(self, request_id: str) -> Dict[str, Any]:
        """Get the status of a request"""
        # Check pending
        pending_file = self.pending_dir / f"{request_id}.json"
        if pending_file.exists():
            data = json.loads(pending_file.read_text())
            # Calculate position in queue
            position = self._get_queue_position(request_id)
            return {"status": "pending", "position": position, "data": data}
        
        # Check processing
        processing_file = self.processing_dir / f"{request_id}.json"
        if processing_file.exists():
            data = json.loads(processing_file.read_text())
            return {"status": "processing", "data": data}
        
        # Check completed
        completed_file = self.completed_dir / f"{request_id}.json"
        if completed_file.exists():
            data = json.loads(completed_file.read_text())
            return {"status": "completed", "result": data.get("result"), "data": data}
        
        # Check failed
        failed_file = self.failed_dir / f"{request_id}.json"
        if failed_file.exists():
            data = json.loads(failed_file.read_text())
            return {"status": "failed", "error": data.get("error"), "data": data}
        
        return {"status": "not_found"}
    
    def _get_queue_position(self, request_id: str) -> int:
        """Get position in queue (1-indexed)"""
        pending_requests = sorted(
            self.pending_dir.glob("*.json"),
            key=lambda p: (int(p.stem.split('_')[1]), int(p.stem.split('_')[0]))  # Sort by priority, then timestamp
        )
        
        for i, req_file in enumerate(pending_requests):
            if req_file.stem == request_id:
                return i + 1
        return 0
    
    def has_pending_with_priority(self, priority: Priority) -> bool:
        """Check if there are any pending or processing requests with the given priority"""
        # Check pending requests
        for req_file in self.pending_dir.glob("*.json"):
            try:
                data = json.loads(req_file.read_text())
                if data.get("priority") == priority.value:
                    return True
            except:
                pass
        
        # Check processing requests
        for req_file in self.processing_dir.glob("*.json"):
            try:
                data = json.loads(req_file.read_text())
                if data.get("priority") == priority.value:
                    return True
            except:
                pass
        
        return False
    
    def wait_for_result(
        self,
        request_id: str,
        timeout: int = 300,
        poll_interval: float = 0.5,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """Wait for a request to complete and return the result"""
        start_time = time.time()
        last_status = None
        
        while time.time() - start_time < timeout:
            status = self.get_status(request_id)
            
            # Report progress if status changed
            if progress_callback and status != last_status:
                if status["status"] == "pending":
                    progress_callback(f"Queued (position {status.get('position', '?')})")
                elif status["status"] == "processing":
                    progress_callback("Processing...")
            
            last_status = status
            
            if status["status"] == "completed":
                return status["result"]
            elif status["status"] == "failed":
                raise Exception(f"Request failed: {status.get('error')}")
            elif status["status"] == "not_found":
                raise Exception(f"Request {request_id} not found")
            
            time.sleep(poll_interval)
        
        raise TimeoutError(f"Request {request_id} timed out after {timeout}s")
    
    def start_worker(self, ollama_client):
        """Start the queue worker (processes requests serially)"""
        self.running = True
        self.ollama_client = ollama_client
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._shutdown_handler)
        signal.signal(signal.SIGINT, self._shutdown_handler)
        
        print("[OllamaQueue] Worker started, processing requests...")
        
        while self.running:
            try:
                self._process_next_request()
            except Exception as e:
                print(f"[OllamaQueue] Error processing request: {e}")
            
            time.sleep(0.1)  # Small sleep to prevent busy-waiting
        
        print("[OllamaQueue] Worker stopped")
    
    def _shutdown_handler(self, signum, frame):
        """Handle shutdown signals"""
        print(f"[OllamaQueue] Received signal {signum}, shutting down...")
        self.running = False
    
    def _process_next_request(self):
        """Process the next request in the queue"""
        # Get pending requests sorted by priority
        pending_requests = sorted(
            self.pending_dir.glob("*.json"),
            key=lambda p: (int(p.stem.split('_')[1]), int(p.stem.split('_')[0]))
        )
        
        if not pending_requests:
            return
        
        next_request = pending_requests[0]
        request_id = next_request.stem
        
        # Move to processing
        request_data = json.loads(next_request.read_text())
        request_data["status"] = "processing"
        request_data["started_at"] = datetime.now().isoformat()
        
        processing_file = self.processing_dir / f"{request_id}.json"
        processing_file.write_text(json.dumps(request_data, indent=2))
        next_request.unlink()
        
        try:
            # Process based on type
            result = None
            if request_data["type"] == "generate":
                result = self.ollama_client.generate(request_data["payload"])
            elif request_data["type"] == "chat":
                result = self.ollama_client.chat(request_data["payload"])
            elif request_data["type"] == "chat_with_tools":
                result = self.ollama_client.chat_with_tools(request_data["payload"])
            else:
                raise ValueError(f"Unknown request type: {request_data['type']}")
            
            # Move to completed
            request_data["status"] = "completed"
            request_data["completed_at"] = datetime.now().isoformat()
            request_data["result"] = result
            
            completed_file = self.completed_dir / f"{request_id}.json"
            completed_file.write_text(json.dumps(request_data, indent=2))
            processing_file.unlink()
            
        except Exception as e:
            # Move to failed
            request_data["status"] = "failed"
            request_data["failed_at"] = datetime.now().isoformat()
            request_data["error"] = str(e)
            
            failed_file = self.failed_dir / f"{request_id}.json"
            failed_file.write_text(json.dumps(request_data, indent=2))
            processing_file.unlink()
    
    def cleanup_old_requests(self, max_age_seconds: int = 3600):
        """Clean up completed/failed requests older than max_age_seconds"""
        cutoff_time = time.time() - max_age_seconds
        
        for directory in [self.completed_dir, self.failed_dir]:
            for request_file in directory.glob("*.json"):
                # Extract timestamp from filename
                timestamp = int(request_file.stem.split('_')[0]) / 1000000
                if timestamp < cutoff_time:
                    request_file.unlink()
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """Get queue statistics"""
        return {
            "pending": len(list(self.pending_dir.glob("*.json"))),
            "processing": len(list(self.processing_dir.glob("*.json"))),
            "completed": len(list(self.completed_dir.glob("*.json"))),
            "failed": len(list(self.failed_dir.glob("*.json")))
        }

