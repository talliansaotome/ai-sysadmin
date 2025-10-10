# AI-Powered Autonomous System Administrator

An AI-powered autonomous system administrator for NixOS that monitors system health, diagnoses issues, and can take corrective actions with appropriate approval workflows.

The AI assistant's name is configurable and defaults to your system's hostname, making this software easily distributable and adaptable to any environment.

## Features

- **Autonomous Monitoring**: Continuous health checks with configurable intervals
- **Multi-Host Management**: SSH-based management of multiple NixOS hosts
- **Configurable AI Identity**: AI name defaults to system hostname, fully customizable
- **Tool Calling**: Comprehensive system administration tools via Ollama LLM
- **Queue-Based Architecture**: Serialized LLM requests to prevent resource contention
- **Knowledge Base**: ChromaDB-backed learning system for operational wisdom
- **Approval Workflows**: Safety-first approach with configurable autonomy levels
- **Notification System**: Gotify integration for alerts
- **Multi-OS Support**: Manages NixOS, Ubuntu, Debian, Arch, and other Linux distributions

## Quick Start

### As a NixOS Flake Input

Add to your `flake.nix`:

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
            aiName = "MyAssistant";      # Optional: defaults to hostname
            autonomyLevel = "suggest";    # observe, suggest, auto-safe, auto-full
            checkInterval = 300;          # seconds
            ollamaHost = "http://localhost:11434";
            model = "llama3.1:70b";
            
            # Optional: Gotify notifications
            gotifyUrl = "http://your-gotify-server:8181";
            gotifyToken = "your-token-here";
            
            # Optional: Remote systems to manage
            remoteSystems = [ "server1" "server2" ];
          };
        }
      ];
    };
  };
}
```

### Configuring the AI Name

By default, the AI will be named after your system's short hostname. For example:
- Host `server.example.com` → AI name: `server`
- Host `mybox.local` → AI name: `mybox`

You can override this:

```nix
services.ai-sysadmin.aiName = "HAL";  # Custom name
```

The AI name appears in:
- Chat interfaces
- Log messages
- System prompts
- Notifications

## Configuration Options

### Core Settings

- `aiName` (string, default: hostname) - Name of the AI assistant
- `autonomyLevel` (enum) - Level of autonomy:
  - `observe` - Only monitor and log, no actions
  - `suggest` - Propose actions, require manual approval
  - `auto-safe` - Auto-execute low-risk actions
  - `auto-full` - Full autonomy with safety limits
- `checkInterval` (int, default: 300) - Seconds between health checks
- `ollamaHost` (string) - Ollama API endpoint
- `model` (string) - LLM model to use
- `user` / `group` (string, default: "macha") - Service user/group
- `gotifyUrl` / `gotifyToken` - Notification settings
- `remoteSystems` (list) - Remote hosts to manage
- `configRepo` (string) - NixOS configuration repository URL
- `configBranch` (string, default: "main") - Repository branch

See `module.nix` for complete configuration options.

## CLI Tools

All tools use the configured AI name in their output. Commands are named `{aiName}-<tool>`, for example if your AI is named "hal", you'd use `hal-chat`, `hal-ask`, etc.

- `{aiName}-chat` - Interactive chat interface with the AI
- `{aiName}-ask <question>` - Ask a single question
- `{aiName}-check` - Trigger immediate health check
- `{aiName}-approve` - Approve/discuss pending actions
  - `{aiName}-approve list` - Show pending actions
  - `{aiName}-approve discuss <N>` - Interactive Q&A about action N
  - `{aiName}-approve approve <N>` - Approve action N
  - `{aiName}-approve reject <N>` - Reject action N
- `{aiName}-logs [orchestrator|decisions|actions|service]` - View logs
- `{aiName}-issues` - Query issue database
- `{aiName}-knowledge` - Query/manage knowledge base
- `{aiName}-systems` - List managed systems
- `{aiName}-configs <query>` - Semantic search for config files
- `{aiName}-notify <title> <message> [priority]` - Send notification

## Architecture

### Core Components

- **Agent** (`agent.py`) - Core AI logic with tool calling and dynamic system prompt
- **Orchestrator** (`orchestrator.py`) - Main monitoring loop and system coordination
- **Executor** (`executor.py`) - Safe action execution with approval workflows
- **Queue System** (`ollama_queue.py`, `ollama_worker.py`) - Serialized Ollama requests with priorities
- **Context DB** (`context_db.py`) - ChromaDB for system context, knowledge, and learning
- **Tools** (`tools.py`) - System administration capabilities
- **System Discovery** (`system_discovery.py`) - Automatic discovery of managed systems
- **Issue Tracker** (`issue_tracker.py`) - Track and resolve system issues

### Services

- `{aiName}-ai.service` - Main autonomous monitoring service (e.g., `myserver-ai.service`)
- `{aiName}-ollama-worker.service` - LLM request queue processor
- `chromadb.service` - Vector database for context and knowledge

### State Directories

- `/var/lib/ai-sysadmin/` - Main state directory
- `/var/lib/ai-sysadmin/queues/` - Request queues
- `/var/lib/ai-sysadmin/tool_cache/` - Cached tool outputs
- `/var/lib/ai-sysadmin/logs/` - Log files and archived issues
- `/var/lib/chromadb/` - Vector database storage

## Requirements

- **NixOS** with flakes enabled
- **Ollama** service with a compatible model (e.g., llama3.1:70b, qwen3, gpt-oss)
- **Python 3** with packages: requests, psutil, chromadb
- **ChromaDB** service for vector storage
- (Optional) **Gotify** server for notifications

## Multi-Host Management

The system can manage multiple hosts via SSH:

1. **Discovery**: Automatically discovers systems from journal logs
2. **OS Detection**: Identifies NixOS, Ubuntu, Debian, Arch, macOS, etc.
3. **SSH Management**: Uses `command_patterns.py` for consistent SSH commands
4. **Remote Deployment**: Uses `nh` for NixOS configuration deployment
5. **System Registry**: Tracks all managed systems in ChromaDB

## Safety Features

- **Approval Workflows**: High-risk actions require human approval
- **Command Allow-List**: Only permitted system commands can be executed
- **Critical Service Protection**: Never disables SSH, networking, or boot services
- **Risk-Based Execution**: Automatic execution only for low-risk investigation commands
- **Interactive Discussion**: Ask questions about proposed actions before approving

## Documentation

- `DESIGN.md` - Comprehensive architecture and design documentation
- `EXAMPLES.md` - Usage examples and patterns
- `NOTIFICATIONS.md` - Notification system guide
- `QUICKSTART.md` - Quick start guide
- `SUMMARY.md` - Project summary

## Example Usage

### Interactive Chat

```bash
$ myserver-chat
🌐 MYSERVER INTERACTIVE CHAT
═══════════════════════════════════════════════════════════════════
Type your message and press Enter. Commands:
  /exit or /quit - End the chat session
  /clear - Clear conversation history
  /history - Show conversation history
  /debug - Show Ollama connection status
═══════════════════════════════════════════════════════════════════

💬 YOU: What's the current system load?

🤖 MYSERVER: [AI responds with system information]
```

### Single Question

```bash
$ myserver-ask "Why is the disk usage so high?"
═══════════════════════════════════════════════════════════════════
MYSERVER:
═══════════════════════════════════════════════════════════════════
[AI analyzes disk usage and provides explanation]
```

### Approval Workflow

```bash
$ myserver-approve list
Pending Actions:
  [0] Restart failed service: nginx
      Risk: MEDIUM | Commands: systemctl restart nginx

$ myserver-approve discuss 0
[Interactive discussion about the proposed action]

$ myserver-approve approve 0
Action approved and executed.
```

## Repository

**GitHub**: https://github.com/talliansaotome/ai-sysadmin

## License

This project is licensed under the **Peer Production License (PPL)** - see the [LICENSE](LICENSE) file for details.

The PPL is a copyfarleft license that allows:
- ✅ Worker-owned cooperatives and collectives to use commercially
- ✅ Non-profit organizations to use for any purpose
- ✅ Individuals to use for personal/non-commercial purposes
- ❌ For-profit companies using wage labor to use commercially

For more information about the Peer Production License, see: https://wiki.p2pfoundation.net/Peer_Production_License

## Author

Lily Miller (with assistance from Claude 4.5 Sonnet)
