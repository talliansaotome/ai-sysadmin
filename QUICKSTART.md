# Macha Autonomous System - Quick Start Guide

## What is This?

Macha now has a self-maintenance system that uses local AI (via Ollama) to monitor, analyze, and maintain itself. Think of it as a 24/7 system administrator that watches over Macha.

## How It Works

1. **Monitor**: Every 5 minutes, collects system health data (services, resources, logs, etc.)
2. **Analyze**: Uses llama3.1:70b to analyze the data and detect issues
3. **Act**: Based on autonomy level, either proposes fixes or executes them automatically
4. **Learn**: Logs all decisions and actions for auditing and improvement

## Autonomy Levels

### `observe` - Monitoring Only
- Monitors system health
- Logs everything
- Takes NO actions
- Good for: Testing, learning what the system sees

### `suggest` - Approval Required (DEFAULT)
- Monitors and analyzes
- Proposes fixes
- Requires manual approval before executing
- Good for: Production use, when you want control

### `auto-safe` - Limited Autonomy
- Auto-executes "safe" actions:
  - Restarting failed services
  - Disk cleanup
  - Log rotation
  - Read-only diagnostics
- Asks approval for risky changes
- Good for: Hands-off operation with safety net

### `auto-full` - Full Autonomy
- Auto-executes most actions
- Still requires approval for HIGH RISK actions
- Never touches protected services (SSH, networking, etc.)
- Good for: Experimental, when you trust the system

## Commands

### Check the status
```bash
# View the service status
systemctl status macha-autonomous

# View live logs
macha-logs service

# View AI decision log
macha-logs decisions

# View action execution log
macha-logs actions

# View orchestrator log
macha-logs orchestrator
```

### Run a manual check
```bash
# Run one maintenance cycle now
macha-check
```

### Approval workflow (when autonomyLevel = "suggest")
```bash
# List pending actions awaiting approval
macha-approve list

# Approve action number 0
macha-approve approve 0
```

### Change autonomy level
Edit `/home/lily/Documents/nixos-servers/systems/macha.nix`:
```nix
services.macha-autonomous = {
  enable = true;
  autonomyLevel = "auto-safe";  # Change this
  checkInterval = 300;
  model = "llama3.1:70b";
};
```

Then rebuild:
```bash
sudo nixos-rebuild switch --flake .#macha
```

## What Can It Do?

### Automatically Detects
- Failed systemd services
- High resource usage (CPU, RAM, disk)
- Recent errors in logs
- Network connectivity issues
- Disk space problems
- Boot/uptime anomalies

### Can Propose/Execute
- Restart failed services
- Clean up disk space (nix store, old logs)
- Investigate issues (run diagnostics)
- Propose configuration changes (for manual review)
- NixOS rebuilds (with safety checks)

### Safety Features
- **Protected services**: Never touches SSH, networking, systemd core
- **Dry-run testing**: Tests NixOS rebuilds before applying
- **Action logging**: Every action is logged with context
- **Rollback capability**: Can revert changes
- **Rate limiting**: Won't spam actions
- **Human override**: You can always disable or intervene

## Example Workflow

1. **System detects failed service**
   ```
   Monitor: "ollama.service is failed"
   AI Agent: "The ollama service crashed. Propose restarting it."
   ```

2. **In `suggest` mode (default)**
   ```
   Executor: "Action queued for approval"
   You: Run `macha-approve list`
   You: Review the proposed action
   You: Run `macha-approve approve 0`
   Executor: Restarts the service
   ```

3. **In `auto-safe` mode**
   ```
   Executor: "Low risk action, auto-executing"
   Executor: Restarts the service automatically
   You: Check logs later to see what happened
   ```

## Monitoring the System

All data is stored in `/var/lib/macha-autonomous/`:
- `orchestrator.log` - Main system log
- `decisions.jsonl` - AI analysis decisions (JSON Lines format)
- `actions.jsonl` - Executed actions log
- `snapshot_*.json` - System state snapshots
- `approval_queue.json` - Pending actions

## Tips

1. **Start with `suggest` mode** - Get comfortable with what it proposes
2. **Review the logs** - See what it's detecting and proposing
3. **Graduate to `auto-safe`** - Let it handle routine maintenance
4. **Use `observe` for debugging** - If something seems wrong
5. **Check approval queue regularly** - If using `suggest` mode

## Troubleshooting

### Service won't start
```bash
# Check for errors
journalctl -u macha-autonomous -n 50

# Verify Ollama is running
systemctl status ollama

# Test Ollama manually
curl http://localhost:11434/api/generate -d '{"model": "llama3.1:70b", "prompt": "test"}'
```

### AI making bad decisions
- Switch to `observe` mode to stop actions
- Review `decisions.jsonl` to see reasoning
- File an issue or adjust prompts in `agent.py`

### Want to disable temporarily
```bash
sudo systemctl stop macha-autonomous
```

### Want to disable permanently
Edit `systems/macha.nix`:
```nix
services.macha-autonomous.enable = false;
```
Then rebuild.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Orchestrator                          │
│         (Main loop, runs every 5 minutes)                │
└────────────┬──────────────┬──────────────┬──────────────┘
             │              │              │
         ┌───▼────┐    ┌────▼────┐    ┌────▼─────┐
         │Monitor │    │ Agent   │    │ Executor │
         │        │───▶│  (AI)   │───▶│  (Safe)  │
         └────────┘    └─────────┘    └──────────┘
             │              │              │
         Collects        Analyzes       Executes
         System          Issues         Actions
         Health          w/ LLM         Safely
```

## Future Enhancements

Potential future capabilities:
- Integration with MCP servers (already installed!)
- Predictive maintenance (learning from patterns)
- Self-optimization (tuning configs based on usage)
- Cluster management (if you add more systems)
- Automated backups and disaster recovery
- Security monitoring and hardening
- Performance tuning recommendations

## Philosophy

The goal is a system that maintains itself while being:
1. **Safe** - Never breaks critical functionality
2. **Transparent** - All decisions are logged and explainable
3. **Conservative** - When in doubt, ask for approval
4. **Learning** - Gets better over time
5. **Human-friendly** - Easy to understand and override

Macha is here to help you, not replace you!
