# Migration Guide: Old → New 4-Layer Architecture

## Overview

This guide helps you migrate from the old single-model architecture to the new four-layer architecture.

## What Changed

### Removed Dependencies
- **nh tool:** Replaced with standard `nixos-rebuild`
- All `nh os switch` commands → `nixos-rebuild switch --flake .#HOSTNAME`
- All `nh os boot` commands → `nixos-rebuild boot --flake .#HOSTNAME`

### New Components
1. **Layer 1:** Trigger Monitor (continuous, lightweight)
2. **Layer 2:** Context Manager (token-based rolling window)
3. **Layer 3:** Review Model (periodic analysis with small model)
4. **Layer 4:** Meta Model (on-demand, replaces old `agent.py`)

### New Services
- TimescaleDB (PostgreSQL with time-series extension)
- Web Interface (FastAPI + WebSocket)
- MCP Server (Model Context Protocol)
- sysstat/sar (System Activity Report)

### New Files
- `trigger_monitor.py` - Layer 1
- `context_manager.py` - Layer 2
- `review_model.py` - Layer 3
- `meta_model.py` - Layer 4 (replaces `agent.py`)
- `orchestrator_new.py` - New orchestrator
- `timeseries_db.py` - TimescaleDB integration
- `sar_integration.py` - SAR data parsing
- `web_server.py` - Web interface
- `mcp_server.py` - MCP server

## Migration Steps

### 1. Update Your Branch

```bash
cd /path/to/ai-sysadmin
git checkout refactor-multilayer
git pull origin refactor-multilayer
```

### 2. Update Module Configuration

**Old Configuration:**
```nix
services.ai-sysadmin = {
  enable = true;
  autonomyLevel = "suggest";
  checkInterval = 300;
  model = "gpt-oss:20b";
};
```

**New Configuration:**
```nix
services.ai-sysadmin = {
  enable = true;
  autonomyLevel = "suggest";
  
  # Layer intervals (NEW)
  triggerInterval = 30;   # Layer 1: Every 30s
  reviewInterval = 60;    # Layer 3: Every 60s
  
  # Models for each layer (NEW)
  triggerModel = "qwen3:1b";   # Optional, for log classification
  reviewModel = "qwen3:4b";    # Continuous analysis
  metaModel = "qwen3:14b";     # Complex analysis (replaces old 'model')
  
  # Context management (NEW)
  contextSize = 131072;  # 128K tokens
  
  # Optional: Use AI in Layer 1 (NEW)
  useTriggerModel = true;  # Set false for lower resource usage
  
  # TimescaleDB (NEW)
  timescaledb = {
    enable = true;
    retentionDays = 30;
  };
  
  # Web Interface (NEW)
  webInterface = {
    enable = true;
    port = 8080;
  };
  
  # MCP Server (NEW)
  mcpServer = {
    enable = false;  # Enable if you want MCP
    port = 8081;
  };
  
  # SAR integration (NEW)
  enableSar = true;
  
  # Legacy compatibility
  checkInterval = 300;  # Still used for backwards compat
  model = "gpt-oss:20b";  # Mapped to metaModel
};
```

### 3. Download New Models

The new architecture uses different models for different layers:

```bash
# Layer 1 (optional, for log classification)
ollama pull qwen3:1b

# Layer 3 (continuous review)
ollama pull qwen3:4b

# Layer 4 (complex analysis)
ollama pull qwen3:14b
```

**Note:** You can use different models by configuring `triggerModel`, `reviewModel`, and `metaModel` options.

### 4. Enable PostgreSQL/TimescaleDB

TimescaleDB is now required for metrics storage. It will be automatically enabled if `timescaledb.enable = true` (default).

**Manual verification:**
```bash
sudo systemctl status postgresql
sudo -u postgres psql -d ai_sysadmin -c "SELECT * FROM timescaledb_information.hypertables;"
```

### 5. Enable sysstat (for SAR data)

```bash
# Automatically enabled with enableSar = true
sudo systemctl status sysstat
sudo systemctl status sysstat-collect.timer
```

### 6. Rebuild System

```bash
cd /path/to/nixos-config
nixos-rebuild switch --flake .#HOSTNAME
```

### 7. Verify Services

```bash
# Main orchestrator
sudo systemctl status macha-ai

# Ollama queue worker
sudo systemctl status macha-ollama-worker

# Web interface (if enabled)
sudo systemctl status macha-web

# MCP server (if enabled)
sudo systemctl status macha-mcp

# Databases
sudo systemctl status chromadb
sudo systemctl status postgresql
```

### 8. Check Logs

```bash
# Orchestrator log
sudo tail -f /var/lib/ai-sysadmin/orchestrator.log

# Systemd logs
journalctl -u macha-ai -f
```

### 9. Access Web Interface

If enabled:
```
http://localhost:8080
```

## Configuration Mapping

| Old Option | New Option(s) | Notes |
|------------|---------------|-------|
| `checkInterval` | `triggerInterval`, `reviewInterval` | Split into two layers |
| `model` | `metaModel` | Still supported for compatibility |
| N/A | `triggerModel` | New: small model for log classification |
| N/A | `reviewModel` | New: model for continuous review |
| N/A | `contextSize` | New: token-based context limit |
| N/A | `timescaledb.*` | New: time-series database |
| N/A | `webInterface.*` | New: web UI |
| N/A | `mcpServer.*` | New: MCP protocol |
| N/A | `enableSar` | New: SAR integration |

## Breaking Changes

### 1. No More `nh` Tool

**Before:**
```bash
nh os switch
nh os boot
nh os switch --target-host=rhiannon
```

**After:**
```bash
nixos-rebuild switch --flake .#HOSTNAME
nixos-rebuild boot --flake .#HOSTNAME
nixos-rebuild switch --flake .#rhiannon --target-host=rhiannon
```

### 2. System Prompt Changes

The `system_prompt.txt` file has been updated to use `nixos-rebuild` instead of `nh`. If you have custom prompts, update them accordingly.

### 3. Knowledge Base Updates

If you have stored knowledge about `nh` commands in the knowledge base, you should update them:

```bash
# Run this on the system
macha-ai --update-knowledge
```

Or manually via `seed_knowledge.py`.

### 4. Different Service Names

If you have monitoring or scripts referencing the old service:
- Old: `macha-autonomous.service`
- New: `macha-ai.service` (configurable via `aiName`)

## Rollback Plan

If you need to rollback:

```bash
cd /path/to/ai-sysadmin
git checkout main  # or your previous branch

cd /path/to/nixos-config
# Update your configuration to point to main branch
nixos-rebuild switch --flake .#HOSTNAME
```

## Performance Comparison

**Old Architecture:**
- Single large model running periodically
- No context management
- High VRAM usage even when idle
- Slower response to critical issues

**New Architecture:**
- Four-layer model hierarchy
- Token-based context management
- Efficient resource usage (models loaded on-demand)
- Fast response (Layer 1 runs every 30s)
- Better scalability

**Expected Resource Usage:**
- Memory: Similar (~250MB base)
- VRAM: More efficient (models loaded as needed)
- CPU: Similar average, better burst handling
- Disk: More (TimescaleDB adds ~1-5GB over time)

## Testing the Migration

### 1. Trigger a Test Event

```bash
# Generate a high CPU load
stress-ng --cpu 4 --timeout 60s

# Check if Layer 1 detected it
sudo macha-logs service | grep "Layer 1"
```

### 2. Verify Context Management

```bash
# View current context
sudo -u macha-ai python3 -c "
from context_manager import ContextManager
cm = ContextManager()
print(cm.get_context_window())
"
```

### 3. Test Review Model

The review model runs every 60 seconds. Watch for analysis in logs:

```bash
journalctl -u macha-ai -f | grep "Layer 3"
```

### 4. Test Meta Model Escalation

Create a complex issue that triggers escalation:

```bash
# Stop a critical service
sudo systemctl stop sshd

# Watch for escalation
journalctl -u macha-ai -f | grep "Layer 4"

# Restore service
sudo systemctl start sshd
```

### 5. Test Web Interface

Visit `http://localhost:8080` and verify:
- System metrics display
- Real-time updates
- Recent events

## Common Issues

### Issue: TimescaleDB not starting

**Solution:**
```bash
sudo systemctl status postgresql
sudo journalctl -u postgresql

# Check if TimescaleDB extension is available
sudo -u postgres psql -c "SELECT * FROM pg_available_extensions WHERE name='timescaledb';"
```

### Issue: Models not loading

**Solution:**
```bash
# Check Ollama service
sudo systemctl status ollama

# List available models
ollama list

# Pull missing models
ollama pull qwen3:1b
ollama pull qwen3:4b
ollama pull qwen3:14b
```

### Issue: Web interface not accessible

**Solution:**
```bash
# Check if service is running
sudo systemctl status macha-web

# Check firewall
sudo ss -tlnp | grep 8080

# Check logs
journalctl -u macha-web -f
```

### Issue: High resource usage

**Solutions:**
1. Disable AI in Layer 1: `useTriggerModel = false;`
2. Increase intervals: `triggerInterval = 60; reviewInterval = 300;`
3. Use smaller models: `reviewModel = "qwen3:3b"; metaModel = "qwen3:8b";`
4. Reduce context size: `contextSize = 65536;  # 64K instead of 128K`

## Getting Help

1. Check logs: `macha-logs service`
2. Check architecture docs: `ARCHITECTURE.md`
3. Review configuration: `/etc/ai-sysadmin/config.json`
4. Test individual components:
   - `python3 trigger_monitor.py`
   - `python3 review_model.py`
   - `python3 web_server.py`

## FAQ

**Q: Do I need all four layers?**
A: No, but Layer 1 and Layer 2 are essential. Layer 3 can be disabled by setting a very high `reviewInterval`. Layer 4 is on-demand only.

**Q: Can I use the old architecture?**
A: Yes, the old `orchestrator.py` is still available. Don't pull the `refactor-multilayer` branch.

**Q: What if I don't have enough VRAM?**
A: Use smaller models or disable `useTriggerModel`. Minimum: ~6GB VRAM for qwen3:4b (Layer 3 only).

**Q: Can I use different models?**
A: Yes! Configure `triggerModel`, `reviewModel`, and `metaModel` to any Ollama-compatible model.

**Q: Do I need the web interface?**
A: No, it's optional. Set `webInterface.enable = false;` if you don't need it.

**Q: What about remote systems?**
A: Remote monitoring still works the same way via SSH. The orchestrator can monitor multiple systems.

