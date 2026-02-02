# Brighid - AI-Powered Autonomous System Administrator

**Brighid** is an autonomous AI system administrator for NixOS, embodied as a wise and diligent guardian of your system's "hearth." Inspired by the Celtic goddess of wisdom, smithcraft, and healing, she monitors system health, diagnoses issues, and performs maintenance with a focus on safety and declarative configuration.

The project features a robust **4-layer architecture** for efficient monitoring and reasoning, a unified **CLI**, a **Web Dashboard**, and an **MCP Server** for integration with other AI agents.

## 🌟 Key Features

- **4-Layer AI Architecture**:
  - **Layer 1 (Trigger Monitor)**: Continuous, lightweight monitoring (every 30s) using a small 1B parameter model.
  - **Layer 2 (Context Manager)**: Maintains a rolling token window of system state, logs, and metrics.
  - **Layer 3 (Review Model)**: Periodic holistic analysis (every 10m) using a mid-sized 4B parameter model.
  - **Layer 4 (Meta Model)**: Deep analysis and user interaction using a large 14B+ parameter model.
- **Unified CLI**: A single `brighid` command for all operations.
- **Web Dashboard**: Real-time status, metrics, and AI insights.
- **Model Context Protocol (MCP)**: Exposes system state and tools to external agents (like Gemini or Claude).
- **Safety First**: Configurable autonomy levels (`observe`, `suggest`, `auto-safe`, `auto-full`) and strict approval workflows for risky actions.
- **Self-Healing**: Automatically detects and fixes model server issues and common system faults.
- **Declarative & Reproducible**: Fully integrated NixOS module.

## 🚀 Quick Start

### 1. Add to your `flake.nix`

```nix
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    ai-sysadmin.url = "github:talliansaotome/ai-sysadmin";
  };

  outputs = { self, nixpkgs, ai-sysadmin }: {
    nixosConfigurations.yourhost = nixpkgs.lib.nixosSystem {
      modules = [
        ai-sysadmin.nixosModules.default
        {
          services.ai-sysadmin = {
            enable = true;
            aiName = "Brighid";           # The persona name
            autonomyLevel = "suggest";    # Start with 'suggest' mode
            
            # Hardware Acceleration (Recommended)
            llama-cpp.acceleration = "cuda"; # or "rocm" for AMD, or null for CPU
            
            # Enable Interfaces
            webInterface.enable = true;
            mcpServer.enable = true;
          };
        }
      ];
    };
  };
}
```

### 2. Rebuild and Activate

```bash
sudo nixos-rebuild switch --flake .#yourhost
```

Brighid will automatically download the necessary models (Qwen 2.5 series) and start her watch.

## 🛠️ The Unified CLI

Brighid provides a single command for all interactions:

| Command | Description |
| :--- | :--- |
| `brighid chat` | Start an interactive chat session with the Meta Model. |
| `brighid ask "..."` | Ask a single question about the system. |
| `brighid check` | Trigger an immediate analysis cycle (Layer 1 -> Layer 3). |
| `brighid approve list` | Show pending actions requiring approval. |
| `brighid approve discuss <ID>` | Discuss a pending action before approving. |
| `brighid logs` | View logs (`orchestrator`, `service`, `decisions`). |
| `brighid notify` | Send a test notification. |

## 📊 Web Dashboard

Enable the web interface in your config:
```nix
services.ai-sysadmin.webInterface.enable = true;
```

Access the dashboard at **`http://<your-ip>:40084`**.
It provides:
- Real-time system health score.
- Live CPU, Memory, and Disk metrics.
- Recent event log (triggers, log patterns).
- **Latest AI Analysis**: Detailed insights from the Layer 3 Review Model.

## 🔌 Model Context Protocol (MCP)

Brighid acts as an MCP server, allowing other AI agents (like Gemini CLI or Claude Desktop) to query your system status or logs.

**Enable in config:**
```nix
services.ai-sysadmin.mcpServer.enable = true;
```

**Connect via SSH (Remote):**
Configure your client to run:
```bash
ssh user@host "brighid mcp"
```
*(Note: Ensure the `brighid` command is in the path or use the full path)*

## 🧠 Architecture Details

### The 4 Layers
1.  **Trigger Monitor (qwen3:1b)**: Fast pattern matching on logs and metrics. Fires alerts.
2.  **Context Manager**: Aggregates triggers, logs, and timeseries data into a coherent prompt context.
3.  **Review Model (qwen3:4b)**: Periodically reviews the context. "Is the system healthy? What needs attention?"
4.  **Meta Model (qwen3:14b)**: The "Brain." Handles user chat, complex debugging, and root cause analysis.

### Databases
- **ChromaDB**: Vector store for semantic memory (past issues, knowledge base, system facts).
- **TimescaleDB**: Time-series storage for long-term metric trending.

## 🔒 Safety & Permissions

- **User**: Runs as `brighid-ai` (UID 2501).
- **Privileges**: Uses `sudo` rules for specific maintenance commands (`systemctl`, `nixos-rebuild`, etc.).
- **Autonomy**:
  - `suggest`: AI proposes actions, you must `brighid approve` them.
  - `auto-safe`: AI runs low-risk fixes (restart services, clear cache) automatically.
  - `auto-full`: Full autonomy (use with caution).

## License

Licensed under the **Peer Production License (PPL)**.
- ✅ Individuals, Co-ops, Non-profits.
- ❌ Capitalist corporations.