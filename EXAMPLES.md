# Macha Autonomous System - Configuration Examples

## Basic Configurations

### Conservative (Recommended for Start)
```nix
services.macha-autonomous = {
  enable = true;
  autonomyLevel = "suggest";  # Require approval for all actions
  checkInterval = 300;        # Check every 5 minutes
  model = "llama3.1:70b";     # Most capable model
};
```

### Moderate Autonomy
```nix
services.macha-autonomous = {
  enable = true;
  autonomyLevel = "auto-safe";  # Auto-fix safe issues
  checkInterval = 180;          # Check every 3 minutes
  model = "llama3.1:70b";
};
```

### High Autonomy (Experimental)
```nix
services.macha-autonomous = {
  enable = true;
  autonomyLevel = "auto-full";  # Full autonomy
  checkInterval = 300;
  model = "llama3.1:70b";
};
```

### Monitoring Only
```nix
services.macha-autonomous = {
  enable = true;
  autonomyLevel = "observe";  # No actions, just watch
  checkInterval = 60;         # Check every minute
  model = "qwen3:8b-fp16";    # Lighter model is fine for observation
};
```

## Advanced Scenarios

### Using a Smaller Model (Faster, Less Capable)
```nix
services.macha-autonomous = {
  enable = true;
  autonomyLevel = "auto-safe";
  checkInterval = 120;
  model = "qwen3:8b-fp16";  # Faster inference, less reasoning depth
  # or
  # model = "llama3.1:8b";  # Also good for simple tasks
};
```

### High-Frequency Monitoring
```nix
services.macha-autonomous = {
  enable = true;
  autonomyLevel = "auto-safe";
  checkInterval = 60;  # Check every minute
  model = "qwen3:4b-instruct-2507-fp16";  # Lightweight model
};
```

### Remote Ollama (if running Ollama elsewhere)
```nix
services.macha-autonomous = {
  enable = true;
  autonomyLevel = "suggest";
  checkInterval = 300;
  ollamaHost = "http://192.168.1.100:11434";  # Remote Ollama instance
  model = "llama3.1:70b";
};
```

## Manual Testing Workflow

1. **Test with a one-shot run:**
```bash
# Run once in observe mode
macha-check

# Review what it detected
cat /var/lib/macha-autonomous/decisions.jsonl | tail -1 | jq .
```

2. **Enable in suggest mode:**
```nix
services.macha-autonomous = {
  enable = true;
  autonomyLevel = "suggest";
  checkInterval = 300;
  model = "llama3.1:70b";
};
```

3. **Rebuild and start:**
```bash
sudo nixos-rebuild switch --flake .#macha
sudo systemctl status macha-autonomous
```

4. **Monitor for a while:**
```bash
# Watch the logs
journalctl -u macha-autonomous -f

# Or use the helper
macha-logs service
```

5. **Review proposed actions:**
```bash
macha-approve list
```

6. **Graduate to auto-safe when comfortable:**
```nix
services.macha-autonomous.autonomyLevel = "auto-safe";
```

## Scenario-Based Examples

### Media Server (Let it auto-restart services)
```nix
services.macha-autonomous = {
  enable = true;
  autonomyLevel = "auto-safe";  # Auto-restart failed arr apps
  checkInterval = 180;
  model = "llama3.1:70b";
};
```

### Development Machine (Observe only, you want control)
```nix
services.macha-autonomous = {
  enable = true;
  autonomyLevel = "observe";
  checkInterval = 600;  # Check less frequently
  model = "llama3.1:8b";  # Lighter model
};
```

### Critical Production (Suggest only, manual approval)
```nix
services.macha-autonomous = {
  enable = true;
  autonomyLevel = "suggest";
  checkInterval = 120;  # More frequent monitoring
  model = "llama3.1:70b";  # Best reasoning
};
```

### Experimental/Learning (Full autonomy)
```nix
services.macha-autonomous = {
  enable = true;
  autonomyLevel = "auto-full";
  checkInterval = 300;
  model = "llama3.1:70b";
};
```

## Customizing Behavior

### The config file lives at:
`/etc/macha-autonomous/config.json` (auto-generated from NixOS config)

### To modify the AI prompts:
Edit the Python files in `systems/macha-configs/autonomous/`:
- `agent.py` - AI analysis and decision prompts
- `monitor.py` - What data to collect
- `executor.py` - Safety rules and action execution
- `orchestrator.py` - Main control flow

After editing, rebuild:
```bash
sudo nixos-rebuild switch --flake .#macha
sudo systemctl restart macha-autonomous
```

## Integration with Other Services

### Example: Auto-restart specific services
The system will automatically detect and propose restarting failed services.

### Example: Disk cleanup when space is low
Monitor will detect low disk space, AI will propose cleanup, executor will run `nix-collect-garbage`.

### Example: Log analysis
AI analyzes recent error logs and can propose fixes based on error patterns.

## Debugging

### See what the monitor sees:
```bash
sudo -u macha-autonomous python3 /nix/store/.../monitor.py
```

### Test the AI agent:
```bash
sudo -u macha-autonomous python3 /nix/store/.../agent.py test
```

### View all snapshots:
```bash
ls -lh /var/lib/macha-autonomous/snapshot_*.json
cat /var/lib/macha-autonomous/snapshot_$(ls -t /var/lib/macha-autonomous/snapshot_*.json | head -1) | jq .
```

### Check approval queue:
```bash
cat /var/lib/macha-autonomous/approval_queue.json | jq .
```

## Performance Tuning

### Model Choice Impact:

| Model | Speed | Capability | RAM Usage | Best For |
|-------|-------|------------|-----------|----------|
| llama3.1:70b | Slow (~30s) | Excellent | ~40GB | Complex reasoning |
| llama3.1:8b | Fast (~3s) | Good | ~5GB | General use |
| qwen3:8b-fp16 | Fast (~2s) | Good | ~16GB | General use |
| qwen3:4b | Very Fast (~1s) | Moderate | ~8GB | Simple tasks |

### Check Interval Impact:
- 60s: High responsiveness, more resource usage
- 300s (default): Good balance
- 600s: Low overhead, slower detection

### Memory Usage:
- Monitor: ~50MB
- Agent (per query): Depends on model (see above)
- Executor: ~30MB
- Orchestrator: ~20MB

Total continuous overhead: ~100MB + model inference when running

## Security Considerations

### The autonomous user has sudo access to:
- `systemctl restart/status` - Restart services
- `journalctl` - Read logs
- `nix-collect-garbage` - Clean up Nix store

### It CANNOT:
- Modify arbitrary files
- Access user home directories (ProtectHome=true)
- Disable protected services (SSH, networking)
- Make changes without logging

### Audit trail:
All actions are logged in `/var/lib/macha-autonomous/actions.jsonl`

### To revoke access:
Set `enable = false` and rebuild, or stop the service.

## Future: MCP Integration

You already have MCP servers installed:
- `mcp-nixos` - NixOS-specific tools
- `gitea-mcp-server` - Git integration
- `emcee` - General MCP orchestration

Future versions could integrate these for:
- Better NixOS config manipulation
- Git-based config versioning
- More sophisticated tooling

Stay tuned!
