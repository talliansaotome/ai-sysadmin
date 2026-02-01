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
- OpenAI-compatible API on port 40083 for external frontends (OpenWebUI, LibreChat, etc.)
- Separate llama.cpp instances for each model layer (internal only, 127.0.0.1):
  - 127.0.0.1:40080: Trigger model (qwen3:1b)
  - 127.0.0.1:40081: Review model (qwen3:4b)
  - 127.0.0.1:40082: Meta model (qwen3:14b)
- OpenAI API Server (configurable, can be 0.0.0.0:40083 for external access)

## Remaining Work 🔧

### Critical: NixOS Module (`module.nix`)
**This is the most important remaining task**

Replace Ollama service configuration with llama.cpp:
1. Remove ollama options (`ollamaHost`, `ollamaAcceleration`)
2. Add llama.cpp options:
   - `llama-cpp.enable` (default: true)
   - `llama-cpp.models` - list of model configurations
   - `llama-cpp.acceleration` (rocm/cuda/cpu)
3. Replace `ollama.service` with `llama-server` instances (internal only):
   - `llama-trigger.service` (127.0.0.1:40080, small model)
   - `llama-review.service` (127.0.0.1:40081, medium model)
   - `llama-meta.service` (127.0.0.1:40082, large model)
4. Add `ai-sysadmin-api.service` for OpenAI API server (configurable host:port)
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
  OpenAI API Server (0.0.0.0:40083) ← ONLY externally accessible service
         ↓
    Meta Model (Layer 4)
         ↓
  llama.cpp (127.0.0.1:40082) ← Internal only
         ↓
  [System Administration Capabilities]
```

**Security Model:**
- **Internal Services (127.0.0.1)**: All llama.cpp model servers listen only on localhost
  - Trigger model: 127.0.0.1:40080
  - Review model: 127.0.0.1:40081
  - Meta model: 127.0.0.1:40082
- **External Service**: Only the OpenAI API server is exposed (host configurable)
  - Default: 0.0.0.0:40083 or configure specific interface

The key insight: External frontends connect to our OpenAI API server, NOT directly 
to llama.cpp. This gives them access to the full AI sysadmin capabilities, not just
raw LLM inference, while keeping the internal model servers secure.

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
5. Point OpenWebUI/other frontends to port 40083

No data loss - ChromaDB and TimescaleDB remain unchanged.

