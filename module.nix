{ config, lib, pkgs, ... }:

with lib;

let
  cfg = config.services.ai-sysadmin;
  
  # Dynamic names based on AI name
  stateDir = "/var/lib/ai-sysadmin";
  userName = "${cfg.aiName}-ai";
  groupName = "${cfg.aiName}-ai";
  mainServiceName = "${cfg.aiName}-ai";
  queueWorkerServiceName = "${cfg.aiName}-ollama-worker";
  
  # Python environment with all dependencies
  pythonEnv = pkgs.python3.withPackages (ps: with ps; [
    requests
    psutil
    chromadb
    psycopg2
    tiktoken
    fastapi
    uvicorn
    websockets
    openai
  ]);
  
  # Main autonomous system package (use dynamic name based on aiName)
  mainScript = pkgs.writeScriptBin "${cfg.aiName}-ai" ''
    #!${pythonEnv}/bin/python3
    import sys
    sys.path.insert(0, "${./.}")
    from orchestrator import main
    main()
  '';
  
  # Config file
  configFile = pkgs.writeText "ai-sysadmin-config.json" (builtins.toJSON {
    ai_name = cfg.aiName;
    autonomy_level = cfg.autonomyLevel;
    config_repo = cfg.configRepo;
    config_branch = cfg.configBranch;
    model_dir = cfg.modelDir;
    # 4-layer architecture model backends
    trigger_backend = cfg.triggerBackend;
    review_backend = cfg.reviewBackend;
    meta_backend = cfg.metaBackend;
    # 4-layer architecture models
    trigger_model = cfg.triggerModel;
    review_model = cfg.reviewModel;
    meta_model = cfg.metaModel;
    # Intervals and sizes
    trigger_interval = cfg.triggerInterval;
    review_interval = cfg.reviewInterval;
    context_size = cfg.contextSize;
    use_trigger_model = cfg.useTriggerModel;
  });

in {
  options.services.ai-sysadmin = {
    enable = mkEnableOption "AI-powered autonomous system administration";
    
    autonomyLevel = mkOption {
      type = types.enum [ "observe" "suggest" "auto-safe" "auto-full" ];
      default = "suggest";
      description = ''
        Level of autonomy for the system:
        - observe: Only monitor and log, no actions
        - suggest: Propose actions, require manual approval
        - auto-safe: Auto-execute low-risk actions (restarts, cleanup)
        - auto-full: Full autonomy with safety limits (still requires approval for high-risk)
      '';
    };
    
    llama-cpp = {
      enable = mkOption {
        type = types.bool;
        default = true;
        description = "Enable llama.cpp for AI inference";
      };

      acceleration = mkOption {
        type = types.nullOr (types.enum [ "rocm" "cuda" "cpu" ]);
        default = "cpu";
        description = "GPU acceleration for llama.cpp";
      };
    };

    triggerModel = mkOption {
      type = types.str;
      default = "qwen3:1b";
      description = "Small model for log classification in Layer 1";
    };

    triggerBackend = mkOption {
      type = types.str;
      default = "http://127.0.0.1:8080/v1";
      description = "LLM backend URL for Layer 1";
    };

    reviewModel = mkOption {
      type = types.str;
      default = "qwen3:4b";
      description = "Model for continuous analysis in Layer 3";
    };

    reviewBackend = mkOption {
      type = types.str;
      default = "http://127.0.0.1:8081/v1";
      description = "LLM backend URL for Layer 3";
    };

    metaModel = mkOption {
      type = types.str;
      default = "qwen3:14b";
      description = "Large model for complex analysis in Layer 4";
    };

    metaBackend = mkOption {
      type = types.str;
      default = "http://127.0.0.1:8082/v1";
      description = "LLM backend URL for Layer 4";
    };

    uid = mkOption {
      type = types.int;
      default = 2501;
      description = "UID for the AI system user (${cfg.aiName}-ai)";
    };
    
    gotifyUrl = mkOption {
      type = types.str;
      default = "";
      example = "http://rhiannon:8181";
      description = "Gotify server URL for notifications (empty to disable)";
    };
    
    gotifyToken = mkOption {
      type = types.str;
      default = "";
      description = "Gotify application token for notifications";
    };
    
    remoteSystems = mkOption {
      type = types.listOf types.str;
      default = [];
      example = [ "rhiannon" "alexander" ];
      description = "List of remote NixOS systems to monitor and maintain";
    };

    configRepo = mkOption {
      type = types.str;
      default = if config.programs.nh.flake != null 
                then config.programs.nh.flake
                else "git+https://git.local/lily/nixos-servers";
      description = "URL of the NixOS configuration repository (auto-detected from programs.nh.flake if available)";
    };

    configBranch = mkOption {
      type = types.str;
      default = "main";
      description = "Branch of the NixOS configuration repository";
    };

    aiName = mkOption {
      type = types.str;
      default = config.networking.hostName;
      defaultText = literalExpression "config.networking.hostName";
      example = "MyAI";
      description = ''
        Name of the AI assistant. Defaults to the system's short hostname.
        This appears in chat interfaces, logs, and system prompts.
      '';
    };

    triggerInterval = mkOption {
      type = types.int;
      default = 30;
      description = "Layer 1: Trigger monitor check interval in seconds";
    };

    reviewInterval = mkOption {
      type = types.int;
      default = 60;
      description = "Layer 3: Review model analysis interval in seconds";
    };

    contextSize = mkOption {
      type = types.int;
      default = 131072;
      description = "Maximum context window size in tokens (default: 128K)";
    };

    modelDir = mkOption {
      type = types.str;
      default = "${stateDir}/models";
      description = "Directory where AI models are stored";
    };

    useTriggerModel = mkOption {
      type = types.bool;
      default = true;
      description = "Whether to use AI model for log classification (disable for lower resource usage)";
    };

    memoryLimit = mkOption {
      type = types.str;
      default = "1G";
      description = "Memory limit for the AI sysadmin service (systemd format)";
    };

    cpuQuota = mkOption {
      type = types.str;
      default = "50%";
      description = "CPU quota for the AI sysadmin service (systemd format)";
    };

    threads = mkOption {
      type = types.int;
      default = 4;
      description = "Number of threads to use for AI inference";
    };

    # === TIMESCALEDB OPTIONS ===

    timescaledb = {
      enable = mkOption {
        type = types.bool;
        default = true;
        description = "Enable TimescaleDB for metrics storage";
      };

      retentionDays = mkOption {
        type = types.int;
        default = 30;
        description = "Days to retain metrics data";
      };

      port = mkOption {
        type = types.int;
        default = 5432;
        description = "PostgreSQL/TimescaleDB port";
      };
    };

    # === WEB INTERFACE OPTIONS ===

    webInterface = {
      enable = mkOption {
        type = types.bool;
        default = false;
        description = "Enable web interface for system monitoring";
      };

      port = mkOption {
        type = types.int;
        default = 8080;
        description = "Web interface port";
      };

      allowedHosts = mkOption {
        type = types.listOf types.str;
        default = [ "localhost" "127.0.0.1" ];
        example = [ "localhost" "*.coven.systems" ];
        description = "Allowed hostnames for web access";
      };
    };

    # === MCP SERVER OPTIONS ===

    mcpServer = {
      enable = mkOption {
        type = types.bool;
        default = false;
        description = "Enable MCP (Model Context Protocol) server";
      };

      port = mkOption {
        type = types.int;
        default = 8081;
        description = "MCP server port";
      };

      respectAutonomy = mkOption {
        type = types.bool;
        default = true;
        description = "Respect autonomy level settings for MCP operations";
      };
    };

    # === SAR/SYSSTAT OPTIONS ===

    enableSar = mkOption {
      type = types.bool;
      default = true;
      description = "Enable sar (System Activity Report) data collection";
    };

    sarCollectFrequency = mkOption {
      type = types.str;
      default = "*:00/10";
      description = "OnCalendar specification for sysstat data collection";
    };
  };
  
  config = mkIf cfg.enable {
    # Create user and group (dynamic based on AI name)
    users.users.${userName} = {
      isSystemUser = true;
      group = groupName;
      uid = cfg.uid;
      description = "AI system administrator (${cfg.aiName})";
      home = stateDir;
      createHome = true;
    };
    
    users.groups.${groupName} = {};
    
    # Git configuration for credential storage
    programs.git = {
      enable = true;
      config = {
        credential.helper = "store";
      };
    };
    
    # ChromaDB service for vector storage
    services.chromadb = {
      enable = true;
      port = 8000;
      dbpath = "/var/lib/chromadb";
    };
    
    # Llama.cpp services for each layer
    systemd.services.llama-trigger = mkIf (cfg.llama-cpp.enable && cfg.useTriggerModel) {
      description = "Llama.cpp Trigger Model Server";
      after = [ "network.target" ];
      wantedBy = [ "multi-user.target" ];
      serviceConfig = {
        ExecStart = "${pkgs.llama-cpp}/bin/llama-server --model ${cfg.modelDir}/${cfg.triggerModel}.gguf --port 8080 --host 127.0.0.1 --ctx-size 4096 --n-gpu-layers 99 --threads ${toString cfg.threads}";
        Restart = "on-failure";
        User = userName;
        Group = groupName;
      };
    };

    systemd.services.llama-review = mkIf cfg.llama-cpp.enable {
      description = "Llama.cpp Review Model Server";
      after = [ "network.target" ];
      wantedBy = [ "multi-user.target" ];
      serviceConfig = {
        ExecStart = "${pkgs.llama-cpp}/bin/llama-server --model ${cfg.modelDir}/${cfg.reviewModel}.gguf --port 8081 --host 127.0.0.1 --ctx-size 32768 --n-gpu-layers 99 --threads ${toString cfg.threads}";
        Restart = "on-failure";
        User = userName;
        Group = groupName;
      };
    };

    systemd.services.llama-meta = mkIf cfg.llama-cpp.enable {
      description = "Llama.cpp Meta Model Server";
      after = [ "network.target" ];
      wantedBy = [ "multi-user.target" ];
      serviceConfig = {
        ExecStart = "${pkgs.llama-cpp}/bin/llama-server --model ${cfg.modelDir}/${cfg.metaModel}.gguf --port 8082 --host 127.0.0.1 --ctx-size ${toString cfg.contextSize} --n-gpu-layers 99 --threads ${toString cfg.threads}";
        Restart = "on-failure";
        User = userName;
        Group = groupName;
      };
    };

    # OpenAI API Server for Meta Model
    systemd.services.ai-sysadmin-api = {
      description = "AI Sysadmin OpenAI-Compatible API Server";
      after = [ "network.target" "llama-meta.service" ];
      wantedBy = [ "multi-user.target" ];
      serviceConfig = {
        ExecStart = "${pythonEnv}/bin/python3 ${./.}/openai_api_server.py --port 8083";
        Restart = "on-failure";
        User = userName;
        Group = groupName;
        WorkingDirectory = stateDir;
      };
      environment = {
        PYTHONPATH = toString ./.;
      };
    };
    
    # Give the user permissions it needs
    security.sudo.extraRules = [{
      users = [ userName ];
      commands = [
        # Local system management
        { command = "${pkgs.systemd}/bin/systemctl restart *"; options = [ "NOPASSWD" ]; }
        { command = "${pkgs.systemd}/bin/systemctl status *"; options = [ "NOPASSWD" ]; }
        { command = "${pkgs.systemd}/bin/journalctl *"; options = [ "NOPASSWD" ]; }
        { command = "${pkgs.nix}/bin/nix-collect-garbage *"; options = [ "NOPASSWD" ]; }
        # Remote system access (uses existing root SSH keys)
        { command = "${pkgs.openssh}/bin/ssh *"; options = [ "NOPASSWD" ]; }
        { command = "${pkgs.openssh}/bin/scp *"; options = [ "NOPASSWD" ]; }
        { command = "${pkgs.nixos-rebuild}/bin/nixos-rebuild *"; options = [ "NOPASSWD" ]; }
      ];
    }];
    
    # Config file
    environment.etc."ai-sysadmin/config.json".source = configFile;
    
    # State directory and tool cache
    systemd.tmpfiles.rules = [
      "d ${stateDir} 0755 ${userName} ${groupName} -"
      "z ${stateDir} 0755 ${userName} ${groupName} -"
      "d ${stateDir}/models 0755 ${userName} ${groupName} -"
      "d ${stateDir}/tool_cache 0777 ${userName} ${groupName} -"
    ];
    
    # Systemd services (dynamic names based on AI name)
    systemd.services."${mainServiceName}" = {
      description = "AI System Administrator (${cfg.aiName})";
      after = [ "network.target" "llama-trigger.service" "llama-review.service" "llama-meta.service" ];
      wants = [ "llama-trigger.service" "llama-review.service" "llama-meta.service" ];
      wantedBy = [ "multi-user.target" ];
      
      serviceConfig = {
        Type = "simple";
        User = userName;
        Group = groupName;
        WorkingDirectory = stateDir;
        ExecStart = "${mainScript}/bin/${cfg.aiName}-ai --mode continuous --autonomy ${cfg.autonomyLevel} --trigger-interval ${toString cfg.triggerInterval} --review-interval ${toString cfg.reviewInterval} --context-size ${toString cfg.contextSize}";
        Restart = "on-failure";
        RestartSec = "30s";
        
        # Security hardening
        PrivateTmp = true;
        NoNewPrivileges = false;  # Need privileges for sudo
        ProtectSystem = "strict";
        ProtectHome = true;
        ReadWritePaths = [ stateDir "${stateDir}/tool_cache" ];
        
        # Resource limits
        MemoryLimit = cfg.memoryLimit;
        CPUQuota = cfg.cpuQuota;
      };
      
      environment = {
        PYTHONPATH = toString ./.;
        GOTIFY_URL = cfg.gotifyUrl;
        GOTIFY_TOKEN = cfg.gotifyToken;
        CHROMA_ENV_FILE = "";  # Prevent ChromaDB from trying to read .env files
        ANONYMIZED_TELEMETRY = "False";  # Disable ChromaDB telemetry
      };
      
      path = [ pkgs.git ];  # Make git available for config parsing
    };
    
    # === NEW SERVICES ===
    
    # TimescaleDB Service
    services.postgresql = mkIf cfg.timescaledb.enable {
      enable = true;
      package = pkgs.postgresql_16.withPackages (ps: [ ps.timescaledb ]);
      ensureDatabases = [ userName ];
      ensureUsers = [{
        name = userName;  # Use hostname-based user (e.g., macha-ai, alexander-ai)
        ensureDBOwnership = true;
      }];
      settings = {
        port = cfg.timescaledb.port;
        shared_preload_libraries = "timescaledb";
      };
      # Allow peer authentication for local connections (no password needed)
      authentication = pkgs.lib.mkOverride 10 ''
        local all all peer
        host all all 127.0.0.1/32 md5
        host all all ::1/128 md5
      '';
    };
        
    # sysstat Service (for sar data)
    services.sysstat = mkIf cfg.enableSar {
      enable = true;
      collect-frequency = cfg.sarCollectFrequency;
    };
    
    # Web Interface Service
    systemd.services."${cfg.aiName}-web" = mkIf cfg.webInterface.enable {
      description = "AI Sysadmin Web Interface";
      after = [ "network.target" "${mainServiceName}.service" ];
      wantedBy = [ "multi-user.target" ];
      
      serviceConfig = {
        Type = "simple";
        User = userName;
        Group = groupName;
        WorkingDirectory = stateDir;
        ExecStart = "${pythonEnv}/bin/python3 ${./.}/web_server.py";
        Restart = "on-failure";
        RestartSec = "10s";
        
        # Security
        PrivateTmp = true;
        NoNewPrivileges = true;
        ProtectSystem = "strict";
        ProtectHome = true;
        ReadWritePaths = [ stateDir ];
        
        # Resource limits
        MemoryLimit = "512M";
        CPUQuota = "25%";
      };
      
      environment = {
        PYTHONPATH = toString ./.;
        PORT = toString cfg.webInterface.port;
        CHROMA_ENV_FILE = "";
        ANONYMIZED_TELEMETRY = "False";
      };
    };
    
    # MCP Server Service
    systemd.services."${cfg.aiName}-mcp" = mkIf cfg.mcpServer.enable {
      description = "AI Sysadmin MCP Server";
      after = [ "network.target" "${mainServiceName}.service" ];
      wantedBy = [ "multi-user.target" ];
      
      serviceConfig = {
        Type = "simple";
        User = userName;
        Group = groupName;
        WorkingDirectory = stateDir;
        ExecStart = "${pythonEnv}/bin/python3 ${./.}/mcp_server.py --autonomy ${cfg.autonomyLevel}";
        Restart = "on-failure";
        RestartSec = "10s";
        
        # Security
        PrivateTmp = true;
        NoNewPrivileges = false;  # May need sudo for actions
        ProtectSystem = "strict";
        ProtectHome = true;
        ReadWritePaths = [ stateDir ];
        
        # Resource limits
        MemoryLimit = "512M";
        CPUQuota = "25%";
      };
      
      environment = {
        PYTHONPATH = toString ./.;
        PORT = toString cfg.mcpServer.port;
        CHROMA_ENV_FILE = "";
        ANONYMIZED_TELEMETRY = "False";
      };
    };
    
    # Open firewall ports if enabled
    networking.firewall.allowedTCPPorts = lib.optionals cfg.webInterface.enable [ cfg.webInterface.port ]
      ++ lib.optionals cfg.mcpServer.enable [ cfg.mcpServer.port ];
    
    # CLI tools for manual control and system packages
    environment.systemPackages = with pkgs; [
      mainScript
      # Python packages for ChromaDB
      python313
      python313Packages.pip
      python313Packages.chromadb.pythonModule
      
      # Tool to check approval queue
      (pkgs.writeScriptBin "${cfg.aiName}-approve" ''
        #!${pkgs.bash}/bin/bash
        if [ "$1" == "list" ]; then
          sudo -u ${userName} ${pythonEnv}/bin/python3 ${./.}/executor.py queue
        elif [ "$1" == "discuss" ] && [ -n "$2" ]; then
          ACTION_ID="$2"
          echo "==================================================================="
          echo "Interactive Discussion with ${cfg.aiName} about Action #$ACTION_ID"
          echo "==================================================================="
          echo ""
          
          # Initial explanation
          sudo -u ${userName} ${pkgs.coreutils}/bin/env CHROMA_ENV_FILE="" ANONYMIZED_TELEMETRY="False" ${pythonEnv}/bin/python3 ${./.}/chat.py --discuss "$ACTION_ID"
          
          echo ""
          echo "==================================================================="
          echo "You can now ask follow-up questions about this action."
          echo "Type 'approve' to approve it, 'reject' to reject it, or 'exit' to quit."
          echo "==================================================================="
          
          # Interactive loop
          while true; do
            echo ""
            echo -n "You: "
            read -r USER_INPUT
            
            # Check for special commands
            if [ "$USER_INPUT" = "exit" ] || [ "$USER_INPUT" = "quit" ] || [ -z "$USER_INPUT" ]; then
              echo "Exiting discussion."
              break
            elif [ "$USER_INPUT" = "approve" ]; then
              echo "Approving action #$ACTION_ID..."
              sudo -u ${userName} ${pythonEnv}/bin/python3 ${./.}/executor.py approve "$ACTION_ID"
              break
            elif [ "$USER_INPUT" = "reject" ]; then
              echo "Rejecting and removing action #$ACTION_ID from queue..."
              sudo -u ${userName} ${pythonEnv}/bin/python3 ${./.}/executor.py reject "$ACTION_ID"
              break
            fi
            
            # Ask the AI the follow-up question in context of the action
            echo ""
            echo -n "${cfg.aiName}: "
            sudo -u ${userName} ${pkgs.coreutils}/bin/env CHROMA_ENV_FILE="" ANONYMIZED_TELEMETRY="False" ${pythonEnv}/bin/python3 ${./.}/chat.py --discuss "$ACTION_ID" --follow-up "$USER_INPUT"
            echo ""
          done
        elif [ "$1" == "approve" ] && [ -n "$2" ]; then
          sudo -u ${userName} ${pythonEnv}/bin/python3 ${./.}/executor.py approve "$2"
        elif [ "$1" == "reject" ] && [ -n "$2" ]; then
          sudo -u ${userName} ${pythonEnv}/bin/python3 ${./.}/executor.py reject "$2"
        else
          echo "Usage:"
          echo "  ${cfg.aiName}-approve list          - Show pending actions"
          echo "  ${cfg.aiName}-approve discuss <N>   - Discuss action number N with ${cfg.aiName} (interactive)"
          echo "  ${cfg.aiName}-approve approve <N>   - Approve action number N"
          echo "  ${cfg.aiName}-approve reject <N>    - Reject and remove action number N from queue"
        fi
      '')
      
      # Tool to run manual check
      (pkgs.writeScriptBin "${cfg.aiName}-check" ''
        #!${pkgs.bash}/bin/bash
        sudo -u ${userName} sh -c 'cd ${stateDir} && CHROMA_ENV_FILE="" ANONYMIZED_TELEMETRY="False" ${mainScript}/bin/${cfg.aiName}-ai --mode once --autonomy ${cfg.autonomyLevel}'
      '')
      
      # Tool to view logs
      (pkgs.writeScriptBin "${cfg.aiName}-logs" ''
        #!${pkgs.bash}/bin/bash
        case "$1" in
          orchestrator)
            sudo tail -f ${stateDir}/orchestrator.log
            ;;
          decisions)
            sudo tail -f ${stateDir}/decisions.jsonl
            ;;
          actions)
            sudo tail -f ${stateDir}/actions.jsonl
            ;;
          service)
            journalctl -u ${mainServiceName}.service -f
            ;;
          *)
            echo "Usage: ${cfg.aiName}-logs [orchestrator|decisions|actions|service]"
            ;;
        esac
      '')
      
      # Tool to send test notification
      (pkgs.writeScriptBin "${cfg.aiName}-notify" ''
        #!${pkgs.bash}/bin/bash
        if [ -z "$1" ] || [ -z "$2" ]; then
          echo "Usage: ${cfg.aiName}-notify <title> <message> [priority]"
          echo "Example: ${cfg.aiName}-notify 'Test' 'This is a test' 5"
          echo "Priorities: 2 (low), 5 (medium), 8 (high)"
          exit 1
        fi
        
        export GOTIFY_URL="${cfg.gotifyUrl}"
        export GOTIFY_TOKEN="${cfg.gotifyToken}"
        
        ${pythonEnv}/bin/python3 ${./.}/notifier.py "$1" "$2" "''${3:-5}"
      '')
      
      # Tool to query config files
      (pkgs.writeScriptBin "${cfg.aiName}-configs" ''
        #!${pkgs.bash}/bin/bash
        export PYTHONPATH=${toString ./.}
        export CHROMA_ENV_FILE=""
        export ANONYMIZED_TELEMETRY="False"
        
        if [ $# -eq 0 ]; then
          echo "Usage: ${cfg.aiName}-configs <search-query> [system-name]"
          echo "Examples:"
          echo "  ${cfg.aiName}-configs gotify"
          echo "  ${cfg.aiName}-configs 'journald configuration'"
          echo "  ${cfg.aiName}-configs ollama system.example.com"
          exit 1
        fi
        
        QUERY="$1"
        SYSTEM="''${2:-}"
        
        ${pythonEnv}/bin/python3 -c "
from context_db import ContextDatabase
import sys

db = ContextDatabase()
query = sys.argv[1]
system = sys.argv[2] if len(sys.argv) > 2 else None

print(f'Searching for: {query}')
if system:
    print(f'Filtered to system: {system}')
print('='*60)

configs = db.query_config_files(query, system=system, n_results=5)

if not configs:
    print('No matching configuration files found.')
else:
    for i, cfg in enumerate(configs, 1):
        print(f\"\\n{i}. {cfg['path']} (relevance: {cfg['relevance']:.1%})\")
        print(f\"   Category: {cfg['metadata']['category']}\")
        print('   Preview:')
        preview = cfg['content'][:300].replace('\\n', '\\n   ')
            print(f'   {preview}')
        if len(cfg['content']) > 300:
            print('   ... (use ${cfg.aiName}-configs-read to see full file)')
        " "$QUERY" "$SYSTEM"
      '')
      
      # Interactive chat tool (runs as AI user for consistent permissions)
      (pkgs.writeScriptBin "${cfg.aiName}-chat" ''
        #!${pkgs.bash}/bin/bash
        # Run as AI user to ensure access to SSH keys and consistent behavior
        sudo -u ${userName} ${pkgs.coreutils}/bin/env \
          PYTHONPATH=${toString ./.} \
          CHROMA_ENV_FILE="" \
          ANONYMIZED_TELEMETRY="False" \
          ${pythonEnv}/bin/python3 ${./.}/chat.py
      '')
      
      # Tool to read full config file
      (pkgs.writeScriptBin "${cfg.aiName}-configs-read" ''
        #!${pkgs.bash}/bin/bash
        export PYTHONPATH=${toString ./.}
        export CHROMA_ENV_FILE=""
        export ANONYMIZED_TELEMETRY="False"
        
        if [ $# -eq 0 ]; then
          echo "Usage: ${cfg.aiName}-configs-read <file-path>"
          echo "Example: ${cfg.aiName}-configs-read apps/gotify.nix"
          exit 1
        fi
        
        ${pythonEnv}/bin/python3 -c "
from context_db import ContextDatabase
import sys

db = ContextDatabase()
file_path = sys.argv[1]

cfg = db.get_config_file(file_path)

if not cfg:
    print(f'Config file not found: {file_path}')
    sys.exit(1)

print(f'File: {cfg[\"path\"]}')
print(f'Category: {cfg[\"metadata\"][\"category\"]}')
print('='*60)
print(cfg['content'])
        " "$1"
      '')
      
      # Tool to view system registry
      (pkgs.writeScriptBin "${cfg.aiName}-systems" ''
        #!${pkgs.bash}/bin/bash
        export PYTHONPATH=${toString ./.}
        export CHROMA_ENV_FILE=""
        export ANONYMIZED_TELEMETRY="False"
        ${pythonEnv}/bin/python3 -c "
from context_db import ContextDatabase
import json

db = ContextDatabase()
systems = db.get_all_systems()

print('Registered Systems:')
print('='*60)
for system in systems:
    os_type = system.get('os_type', 'unknown').upper()
    print(f\"\\n{system['hostname']} ({system['type']}) [{os_type}]\")
    print(f\"  Config Repo: {system.get('config_repo') or '(not set)'}\")
    print(f\"  Branch: {system.get('config_branch', 'unknown')}\")
    if system.get('services'):
        print(f\"  Services: {', '.join(system['services'][:10])}\")
        if len(system['services']) > 10:
            print(f\"    ... and {len(system['services']) - 10} more\")
    if system.get('capabilities'):
        print(f\"  Capabilities: {', '.join(system['capabilities'])}\")
print('='*60)
        "
      '')
      
      # Tool to ask AI questions (unified with chat, uses ask_main entry point)
      (pkgs.writeScriptBin "${cfg.aiName}-ask" ''
        #!${pkgs.bash}/bin/bash
        if [ $# -eq 0 ]; then
          echo "Usage: ${cfg.aiName}-ask <your question>"
          echo "Example: ${cfg.aiName}-ask Why did you recommend restarting that service?"
          exit 1
        fi
        # Run as AI user with ask_main entry point from chat.py
        sudo -u ${userName} ${pkgs.coreutils}/bin/env PYTHONPATH=${toString ./.} CHROMA_ENV_FILE="" ANONYMIZED_TELEMETRY="False" ${pythonEnv}/bin/python3 -c "from chat import ask_main; ask_main()" "$@"
      '')
      
      # Issue tracking CLI
      (pkgs.writeScriptBin "${cfg.aiName}-issues" ''
        #!${pythonEnv}/bin/python3
        import sys
        import os
        os.environ["CHROMA_ENV_FILE"] = ""
        os.environ["ANONYMIZED_TELEMETRY"] = "False"
        sys.path.insert(0, "${./.}")
        
        from context_db import ContextDatabase
        from issue_tracker import IssueTracker
        from datetime import datetime
        import json
        
        db = ContextDatabase()
        tracker = IssueTracker(db)
        
        def list_issues(show_all=False):
            """List issues"""
            if show_all:
                issues = tracker.list_issues()
            else:
                issues = tracker.list_issues(status="open")
            
            if not issues:
                print("No issues found")
                return
            
            print("="*70)
            print(f"ISSUES: {len(issues)}")
            print("="*70)
            
            for issue in issues:
                issue_id = issue['issue_id'][:8]
                age_hours = (datetime.utcnow() - datetime.fromisoformat(issue['created_at'])).total_seconds() / 3600
                inv_count = len(issue.get('investigations', []))
                action_count = len(issue.get('actions', []))
                
                print(f"\n[{issue_id}] {issue['title']}")
                print(f"  Host: {issue['hostname']}")
                print(f"  Status: {issue['status'].upper()} | Severity: {issue['severity'].upper()}")
                print(f"  Age: {age_hours:.1f}h | Activity: {inv_count} investigations, {action_count} actions")
                print(f"  Source: {issue['source']}")
                if issue.get('resolution'):
                    print(f"  Resolution: {issue['resolution']}")
        
        def show_issue(issue_id):
            """Show detailed issue information"""
            # Find issue by partial ID
            all_issues = tracker.list_issues()
            matching = [i for i in all_issues if i['issue_id'].startswith(issue_id)]
            
            if not matching:
                print(f"Issue {issue_id} not found")
                return
            
            issue = matching[0]
            full_id = issue['issue_id']
            
            print("="*70)
            print(f"ISSUE: {issue['title']}")
            print("="*70)
            print(f"ID: {full_id}")
            print(f"Host: {issue['hostname']}")
            print(f"Status: {issue['status'].upper()}")
            print(f"Severity: {issue['severity'].upper()}")
            print(f"Source: {issue['source']}")
            print(f"Created: {issue['created_at']}")
            print(f"Updated: {issue['updated_at']}")
            print(f"\nDescription:\n{issue['description']}")
            
            investigations = issue.get('investigations', [])
            if investigations:
                print(f"\n{'─'*70}")
                print(f"INVESTIGATIONS ({len(investigations)}):")
                for i, inv in enumerate(investigations, 1):
                    print(f"\n  [{i}] {inv.get('timestamp', 'N/A')}")
                    print(f"  Diagnosis: {inv.get('diagnosis', 'N/A')}")
                    print(f"  Commands: {', '.join(inv.get('commands', []))}")
                    print(f"  Success: {inv.get('success', False)}")
                    if inv.get('output'):
                        print(f"  Output: {inv['output'][:200]}...")
            
            actions = issue.get('actions', [])
            if actions:
                print(f"\n{'─'*70}")
                print(f"ACTIONS ({len(actions)}):")
                for i, action in enumerate(actions, 1):
                    print(f"\n  [{i}] {action.get('timestamp', 'N/A')}")
                    print(f"  Action: {action.get('proposed_action', 'N/A')}")
                    print(f"  Risk: {action.get('risk_level', 'N/A').upper()}")
                    print(f"  Commands: {', '.join(action.get('commands', []))}")
                    print(f"  Success: {action.get('success', False)}")
            
            if issue.get('resolution'):
                print(f"\n{'─'*70}")
                print(f"RESOLUTION:")
                print(f"  {issue['resolution']}")
            
            print("="*70)
        
        def create_issue(description):
            """Create a new issue manually"""
            import socket
            hostname = socket.gethostname()
            
            issue_id = tracker.create_issue(
                hostname=hostname,
                title=description[:100],
                description=description,
                severity="medium",
                source="user-reported"
            )
            
            print(f"Created issue: {issue_id[:8]}")
            print(f"Title: {description[:100]}")
        
        def resolve_issue(issue_id, resolution="Manually resolved"):
            """Mark an issue as resolved"""
            # Find issue by partial ID
            all_issues = tracker.list_issues()
            matching = [i for i in all_issues if i['issue_id'].startswith(issue_id)]
            
            if not matching:
                print(f"Issue {issue_id} not found")
                return
            
            full_id = matching[0]['issue_id']
            success = tracker.resolve_issue(full_id, resolution)
            
            if success:
                print(f"Resolved issue {issue_id[:8]}")
            else:
                print(f"Failed to resolve issue {issue_id}")
        
        def close_issue(issue_id):
            """Archive a resolved issue"""
            # Find issue by partial ID
            all_issues = tracker.list_issues()
            matching = [i for i in all_issues if i['issue_id'].startswith(issue_id)]
            
            if not matching:
                print(f"Issue {issue_id} not found")
                return
            
            full_id = matching[0]['issue_id']
            
            if matching[0]['status'] != 'resolved':
                print(f"Issue {issue_id} must be resolved before closing")
                print(f"Use: ${cfg.aiName}-issues resolve {issue_id}")
                return
            
            success = tracker.close_issue(full_id)
            
            if success:
                print(f"Closed and archived issue {issue_id[:8]}")
            else:
                print(f"Failed to close issue {issue_id}")
        
        # Main CLI
        if len(sys.argv) < 2:
            print("Usage: ${cfg.aiName}-issues <command> [options]")
            print("")
            print("Commands:")
            print("  list               List open issues")
            print("  list --all         List all issues (including resolved/closed)")
            print("  show <id>          Show detailed issue information")
            print("  create <desc>      Create a new issue manually")
            print("  resolve <id>       Mark issue as resolved")
            print("  close <id>         Archive a resolved issue")
            sys.exit(1)
        
        command = sys.argv[1]
        
        if command == "list":
            show_all = "--all" in sys.argv
            list_issues(show_all)
        elif command == "show" and len(sys.argv) >= 3:
            show_issue(sys.argv[2])
        elif command == "create" and len(sys.argv) >= 3:
            description = " ".join(sys.argv[2:])
            create_issue(description)
        elif command == "resolve" and len(sys.argv) >= 3:
            resolution = " ".join(sys.argv[3:]) if len(sys.argv) > 3 else "Manually resolved"
            resolve_issue(sys.argv[2], resolution)
        elif command == "close" and len(sys.argv) >= 3:
            close_issue(sys.argv[2])
        else:
            print(f"Unknown command: {command}")
            sys.exit(1)
      '')
      
      # Knowledge base CLI
      (pkgs.writeScriptBin "${cfg.aiName}-knowledge" ''
        #!${pythonEnv}/bin/python3
        import sys
        import os
        os.environ["CHROMA_ENV_FILE"] = ""
        os.environ["ANONYMIZED_TELEMETRY"] = "False"
        sys.path.insert(0, "${./.}")
        
        from context_db import ContextDatabase
        
        db = ContextDatabase()
        
        def list_topics(category=None):
            """List all knowledge topics"""
            topics = db.list_knowledge_topics(category)
            if not topics:
                print("No knowledge topics found.")
                return
            
            print(f"{'='*70}")
            if category:
                print(f"KNOWLEDGE TOPICS ({category.upper()}):")
            else:
                print(f"KNOWLEDGE TOPICS:")
            print(f"{'='*70}")
            
            for topic in topics:
                print(f"  • {topic}")
            
            print(f"{'='*70}")
        
        def show_topic(topic):
            """Show all knowledge for a topic"""
            items = db.get_knowledge_by_topic(topic)
            if not items:
                print(f"No knowledge found for topic: {topic}")
                return
            
            print(f"{'='*70}")
            print(f"KNOWLEDGE: {topic}")
            print(f"{'='*70}\n")
            
            for item in items:
                print(f"ID: {item['id'][:8]}...")
                print(f"Category: {item['category']}")
                print(f"Source: {item['source']}")
                print(f"Confidence: {item['confidence']}")
                print(f"Created: {item['created_at']}")
                print(f"Times Referenced: {item['times_referenced']}")
                if item.get('tags'):
                    print(f"Tags: {', '.join(item['tags'])}")
                print(f"\nKnowledge:")
                print(f"  {item['knowledge']}\n")
                print(f"{'-'*70}\n")
        
        def search_knowledge(query, category=None):
            """Search knowledge base"""
            items = db.query_knowledge(query, category=category, limit=10)
            if not items:
                print(f"No knowledge found matching: {query}")
                return
            
            print(f"{'='*70}")
            print(f"SEARCH RESULTS: {query}")
            if category:
                print(f"Category Filter: {category}")
            print(f"{'='*70}\n")
            
            for i, item in enumerate(items, 1):
                print(f"[{i}] {item['topic']}")
                print(f"    Category: {item['category']} | Confidence: {item['confidence']}")
                print(f"    {item['knowledge'][:150]}...")
                print()
        
        def add_knowledge(topic, knowledge, category="general"):
            """Add new knowledge"""
            kid = db.store_knowledge(
                topic=topic,
                knowledge=knowledge,
                category=category,
                source="user-provided",
                confidence="high"
            )
            if kid:
                print(f"✓ Added knowledge for topic: {topic}")
                print(f"  ID: {kid[:8]}...")
            else:
                print(f"✗ Failed to add knowledge")
        
        def seed_initial():
            """Seed initial knowledge"""
            print("Seeding initial knowledge from seed_knowledge.py...")
            exec(open("${./.}/seed_knowledge.py").read())
        
        # Main CLI
        if len(sys.argv) < 2:
            print("Usage: ${cfg.aiName}-knowledge <command> [options]")
            print("")
            print("Commands:")
            print("  list                 List all knowledge topics")
            print("  list <category>      List topics in category")
            print("  show <topic>         Show all knowledge for a topic")
            print("  search <query>       Search knowledge base")
            print("  search <query> <cat> Search in specific category")
            print("  add <topic> <text>   Add new knowledge")
            print("  seed                 Seed initial knowledge")
            print("")
            print("Categories: command, pattern, troubleshooting, performance, general")
            sys.exit(1)
        
        command = sys.argv[1]
        
        if command == "list":
            category = sys.argv[2] if len(sys.argv) >= 3 else None
            list_topics(category)
        elif command == "show" and len(sys.argv) >= 3:
            show_topic(sys.argv[2])
        elif command == "search" and len(sys.argv) >= 3:
            query = sys.argv[2]
            category = sys.argv[3] if len(sys.argv) >= 4 else None
            search_knowledge(query, category)
        elif command == "add" and len(sys.argv) >= 4:
            topic = sys.argv[2]
            knowledge = " ".join(sys.argv[3:])
            add_knowledge(topic, knowledge)
        elif command == "seed":
            seed_initial()
        else:
            print(f"Unknown command: {command}")
            sys.exit(1)
      '')
    ];
  };
}
