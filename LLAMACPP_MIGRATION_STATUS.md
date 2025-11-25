# llama.cpp Migration Status

## Completed ✅

### Core Backend
- ✅ Created `llm_backend.py` - Unified abstraction for llama.cpp and Ollama
- ✅ Created `openai_api_server.py` - OpenAI-compatible API exposing Meta Model
- ✅ Updated `trigger_monitor.py` to use LLM backend
- ✅ Updated `review_model.py` to use LLM backend  
- ✅ Updated `meta_model.py` to use LLM backend
- ✅ Updated `agent.py` for legacy support
- ✅ Updated `orchestrator_new.py` with separate backend URLs

### Key Features
- OpenAI-compatible API on port 8083 for external frontends (OpenWebUI, LibreChat, etc.)
- Separate llama.cpp instances for each model layer:
  - Port 8080: Trigger model (qwen3:1b)
  - Port 8081: Review model (qwen3:4b)
  - Port 8082: Meta model (qwen3:14b)

## Remaining Work 🔧

### Critical: NixOS Module (`module.nix`)
**This is the most important remaining task**

Replace Ollama service configuration with llama.cpp:
1. Remove ollama options (`ollamaHost`, `ollamaAcceleration`)
2. Add llama.cpp options:
   - `llama-cpp.enable` (default: true)
   - `llama-cpp.models` - list of model configurations
   - `llama-cpp.acceleration` (rocm/cuda/cpu)
3. Replace `ollama.service` with `llama-server` instances:
   - `llama-trigger.service` (port 8080, small model)
   - `llama-review.service` (port 8081, medium model)
   - `llama-meta.service` (port 8082, large model)
4. Add `ai-sysadmin-api.service` for OpenAI API server (port 8083)
5. Update python dependencies (add `openai` package)

### Code Cleanup
- Remove `ollama_queue.py` and `ollama_worker.py`
- Remove queue-related systemd service (`${cfg.aiName}-ollama-worker.service`)
- Update Python imports that reference old queue system

### Documentation
- Update `README.md` with llama.cpp setup instructions
- Update `ARCHITECTURE.md` with new inference platform details
- Create `OPENWEBUI_INTEGRATION.md` guide
- Update installation instructions

### Testing
- Test trigger → review → meta → action workflow
- Test OpenAI API server with external frontend
- Verify model loading and context management
- Test autonomy levels

## Architecture Notes

### Why llama.cpp over Ollama?
1. **Production Ready**: More stable for production deployments
2. **OpenAI API**: Native OpenAI-compatible API support
3. **Third-Party Integration**: Works with any OpenAI-compatible frontend
4. **Flexibility**: Better control over model loading and configuration

### API Hierarchy
```
External Frontend (e.g., OpenWebUI)
         ↓
  OpenAI API Server (port 8083)
         ↓
    Meta Model (Layer 4)
         ↓
  [System Administration Capabilities]
```

The key insight: External frontends connect to our OpenAI API server, NOT directly 
to llama.cpp. This gives them access to the full AI sysadmin capabilities, not just
raw LLM inference.

## Next Steps

1. **HIGH PRIORITY**: Complete `module.nix` update
   - This enables NixOS deployment of the new architecture
   - Without this, the system cannot be deployed

2. **MEDIUM**: Remove queue system files
   - Cleanup old code
   - Remove complexity

3. **LOW**: Documentation updates
   - Help users understand the new system
   - Integration guides

## Migration Path

For existing deployments:
1. Switch to `llama-cpp-backend` branch
2. Update `module.nix` configuration
3. Rebuild NixOS system
4. llama.cpp will replace Ollama
5. Point OpenWebUI/other frontends to port 8083

No data loss - ChromaDB and TimescaleDB remain unchanged.

