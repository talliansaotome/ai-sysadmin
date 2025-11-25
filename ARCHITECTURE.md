# AI Sysadmin - Four-Layer Architecture

## Overview

The AI Sysadmin system uses a four-layer architecture for efficient, scalable system monitoring and management:

```
┌─────────────────────────────────────────────────────────────┐
│                       Layer 4: Meta Model                    │
│                    (On-Demand Complex Analysis)              │
│                         qwen3:14b                            │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │ Escalation
                              │
┌─────────────────────────────────────────────────────────────┐
│                    Layer 3: Review Model                     │
│               (Periodic Analysis - Every 60s)                │
│                         qwen3:4b                             │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │ Events
                              │
┌─────────────────────────────────────────────────────────────┐
│                   Layer 2: Context Manager                   │
│           (Token-Based Rolling Context Window)               │
│            ChromaDB + TimescaleDB + SAR Data                 │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │ Triggers
                              │
┌─────────────────────────────────────────────────────────────┐
│                  Layer 1: Trigger Monitor                    │
│            (Continuous Monitoring - Every 30s)               │
│        Pattern Matching + Optional qwen3:1b Classifier       │
└─────────────────────────────────────────────────────────────┘
```

## Layer 1: Trigger Monitor

**Purpose:** Lightweight, continuous monitoring that detects events requiring attention

**Runs:** Every 30 seconds (configurable)

**Components:**
- Pattern matching on systemd journal logs
- Metric threshold monitoring (CPU, memory, disk, load)
- Service status checks for critical services
- Optional small AI model (qwen3:1b) for log classification

**Triggers on:**
- Critical log patterns (kernel panic, OOM, segfaults, etc.)
- Metric thresholds exceeded
- Critical service failures
- High error rates

**Output:** Adds trigger events to context manager

## Layer 2: Context Manager

**Purpose:** Maintains a managed rolling context window with token-based limits

**Features:**
- Token counting with tiktoken (accurate for LLM context)
- Automatic compression of old entries when context fills
- Integration with ChromaDB for semantic search
- Integration with TimescaleDB for time-series metrics
- SAR (System Activity Report) data integration

**Storage:**
- **ChromaDB:** Semantic search, RAG, issue history
- **TimescaleDB:** Time-series metrics, trends, statistics
- **Memory Buffer:** Recent events (rolling, compressed as needed)

**Context includes:**
- System information header
- Recent metrics from TimescaleDB
- SAR performance data
- Recent trigger events
- Review model summaries
- Meta model analyses

## Layer 3: Review Model

**Purpose:** Continuous analysis with a small, fast model

**Runs:** Every 60 seconds (configurable)

**Model:** qwen3:4b (or configurable)

**Responsibilities:**
- Holistic analysis of accumulated context
- Pattern detection across subsystems
- Trend identification
- Execute safe, low-risk actions automatically
- Escalate complex issues to Layer 4

**Can Execute:**
- Investigation commands (read-only)
- Service restarts (non-critical)
- Cleanup operations

**Escalates When:**
- Complex multi-system issues detected
- High-severity problems requiring deep analysis
- User-level decisions needed

## Layer 4: Meta Model

**Purpose:** Deep analysis and user interaction

**Runs:** On-demand only when:
1. Review model escalates a complex issue
2. User initiates a chat session
3. High-stakes decisions required

**Model:** qwen3:14b (or configurable)

**Features:**
- Full context window access
- Historical data analysis
- Root cause analysis
- High-stakes decision making
- User-facing explanations

**Capabilities:**
- Access to all historical data (TimescaleDB + ChromaDB)
- Long-term trend analysis
- Complex problem solving
- Detailed explanations and reasoning

## Data Flow

```
1. System Events → Trigger Monitor (Layer 1)
   ↓
2. Trigger Events → Context Manager (Layer 2)
   ↓
3. Context Window → Review Model (Layer 3)
   ↓ (if needed)
4. Escalation → Meta Model (Layer 4)
   ↓
5. Results → Context Manager → User/System
```

## Configuration

### Basic Configuration (module.nix)

```nix
services.ai-sysadmin = {
  enable = true;
  autonomyLevel = "suggest";  # observe|suggest|auto-safe|auto-full
  
  # Layer intervals
  triggerInterval = 30;  # Layer 1 check frequency (seconds)
  reviewInterval = 60;   # Layer 3 analysis frequency (seconds)
  
  # Context management
  contextSize = 131072;  # 128K tokens
  
  # Models for each layer
  triggerModel = "qwen3:1b";   # Layer 1 (optional)
  reviewModel = "qwen3:4b";    # Layer 3
  metaModel = "qwen3:14b";     # Layer 4
  
  # Toggle AI classification in Layer 1
  useTriggerModel = true;  # Set to false for lower resource usage
  
  # TimescaleDB
  timescaledb = {
    enable = true;
    retentionDays = 30;
    port = 5432;
  };
  
  # Web Interface
  webInterface = {
    enable = true;
    port = 8080;
    allowedHosts = [ "localhost" "*.coven.systems" ];
  };
  
  # MCP Server
  mcpServer = {
    enable = true;
    port = 8081;
    respectAutonomy = true;
  };
  
  # SAR/sysstat
  enableSar = true;
  sarCollectFrequency = "*:00/10";  # Every 10 minutes
};
```

### Resource Usage

**Layer 1 (Trigger Monitor):**
- CPU: Minimal (~1-2%)
- Memory: ~50MB
- Model (optional): ~1-2GB VRAM

**Layer 2 (Context Manager):**
- CPU: Minimal
- Memory: ~100MB (context buffer)
- Databases: PostgreSQL (TimescaleDB), ChromaDB

**Layer 3 (Review Model):**
- CPU: Moderate during inference (~30-50%)
- Memory: ~100MB
- Model: ~4-6GB VRAM (qwen3:4b)

**Layer 4 (Meta Model):**
- CPU: High during inference (~80-100%)
- Memory: ~200MB
- Model: ~14-20GB VRAM (qwen3:14b)

**Total (all layers active):**
- Base: ~250MB RAM
- With models loaded: ~20-30GB VRAM (GPU)
- CPU: Mostly idle, spikes during reviews

## Advantages

1. **Efficient Resource Usage:** Layers 1-3 use small models or no AI, reserving the large model for complex issues only

2. **Fast Response:** Layer 1 detects issues within seconds, not minutes

3. **Scalable:** Can handle many systems without overwhelming the large model

4. **Cost-Effective:** Minimizes expensive large-model inference

5. **User-Friendly:** Layer 4 provides detailed explanations when users need them

6. **Historical Analysis:** Time-series database enables trend analysis

7. **Flexible:** Can disable AI in Layer 1 for minimal resource usage

## Interfaces

### Web Interface

- **Port:** 8080 (configurable)
- **Features:**
  - Real-time system metrics
  - Health score visualization
  - Recent events timeline
  - WebSocket for live updates

### MCP Server

- **Port:** 8081 (configurable)
- **Protocol:** Model Context Protocol
- **Features:**
  - Context providers (system status, metrics, logs)
  - Tools (query logs, check services, restart services)
  - Respects autonomy level
  - Enables other AI models to interact with system

### CLI Tools

- `macha-ai` - Main orchestrator
- `macha-chat` - Interactive chat with meta model
- `macha-approve` - Manage approval queue
- `macha-check` - Run one-time system check
- `macha-logs` - View system logs
- `macha-issues` - Issue tracking
- `macha-systems` - View registered systems

## Database Schema

### TimescaleDB Tables

**system_metrics** (hypertable)
- time, hostname, metric_name, value, unit, metadata

**service_status** (hypertable)
- time, hostname, service_name, status, active_state, metadata

**log_events** (hypertable)
- time, hostname, severity, message, unit, metadata

**trigger_events** (hypertable)
- time, hostname, trigger_type, trigger_reason, metadata

### ChromaDB Collections

- **systems:** System registry and metadata
- **relationships:** System dependencies
- **issues:** Issue tracking and history
- **decisions:** AI decisions and outcomes
- **config_files:** NixOS configurations for RAG
- **knowledge:** Operational knowledge base

## Migration from Old Architecture

The old single-model architecture (`orchestrator.py`) is preserved for backward compatibility. The new architecture (`orchestrator_new.py`) is used when enabled via module configuration.

**Key Differences:**
1. Single model → Four-layer model hierarchy
2. Fixed intervals → Configurable per-layer intervals
3. No context management → Token-based context window
4. No time-series DB → TimescaleDB integration
5. Manual only → Web + MCP interfaces

## Performance Tips

1. **Low Resource Mode:** Disable `useTriggerModel` to skip AI in Layer 1

2. **Adjust Intervals:** Increase `triggerInterval` and `reviewInterval` if system is busy

3. **Context Size:** Reduce `contextSize` if running low on RAM

4. **Model Selection:** Use smaller models for Layers 3-4 if VRAM is limited:
   - Layer 3: qwen3:3b instead of qwen3:4b
   - Layer 4: qwen3:8b instead of qwen3:14b

5. **Disable Features:** Turn off web interface or MCP server if not needed

## Troubleshooting

**Layer 1 not triggering:**
- Check `macha-ai-logs service`
- Verify trigger thresholds in code or config
- Check systemd journal permissions

**Layer 3 not running:**
- Verify Ollama is running and accessible
- Check model is downloaded: `ollama list`
- Review orchestrator logs

**Layer 4 escalations not working:**
- Check VRAM availability for large model
- Verify model loaded in Ollama
- Check Ollama queue status

**Database issues:**
- TimescaleDB: Check PostgreSQL service status
- ChromaDB: Verify port 8000 accessible
- Check logs: `journalctl -u postgresql` or `journalctl -u chromadb`

## Future Enhancements

- [ ] Automatic model selection based on available resources
- [ ] Multi-node coordination for distributed systems
- [ ] Advanced trend prediction with ML
- [ ] Integration with external monitoring (Prometheus, Grafana)
- [ ] Mobile app for notifications and approvals
- [ ] Voice interface for meta model interactions

