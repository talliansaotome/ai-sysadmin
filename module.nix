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

  # Model Downloader Script
  modelDownloaderScript = pkgs.writeScriptBin "${cfg.aiName}-seed-models" ''
    #!${pythonEnv}/bin/python3
    import os
    import sys
    import json
    import requests
    from pathlib import Path

    CONFIG_PATH = Path("/etc/ai-sysadmin/config.json")
    
    # Mapping of common models to URLs
    MODEL_URLS = {
        "qwen3-1b": "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q8_0.gguf",
        "qwen3-4b": "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q8_0.gguf",
        "qwen3-14b": "https://huggingface.co/bartowski/Qwen2.5-14B-Instruct-GGUF/resolve/main/Qwen2.5-14B-Instruct-Q4_K_M.gguf",
        "qwen3:1b": "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q8_0.gguf",
        "qwen3:4b": "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q8_0.gguf",
        "qwen3:14b": "https://huggingface.co/bartowski/Qwen2.5-14B-Instruct-GGUF/resolve/main/Qwen2.5-14B-Instruct-Q4_K_M.gguf"
    }

    def download_model(name, model_dir):
        # Resolve URL
        url = MODEL_URLS.get(name)
        if not url:
            print(f"Unknown model: {name}. No download URL mapped.")
            return False
        
        # Ensure name ends in .gguf for the file
        filename = name if name.endswith(".gguf") else f"{name}.gguf"
        filename = filename.replace(":", "-") # Safe filename
        path = model_dir / filename
        
        if path.exists():
            print(f"Model {filename} already exists at {path}")
            return True
        
        print(f"Downloading {filename} from {url}...")
        try:
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = (downloaded / total_size) * 100
                            print(f"\rProgress: {percent:.1f}% ({downloaded}/{total_size} bytes)", end="")
            
            print(f"\nSuccessfully downloaded {filename}")
            return True
        except Exception as e:
            print(f"\nError downloading {filename}: {e}")
            if path.exists():
                path.unlink()
            return False

    def main():
        if not CONFIG_PATH.exists():
            print(f"Config not found at {CONFIG_PATH}")
            return

        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
        
        model_dir = Path(config.get("model_dir", "/var/lib/ai-sysadmin/models"))
        model_dir.mkdir(parents=True, exist_ok=True)
        
        # Get models from all layers
        models_to_download = set()
        for key in ["trigger_model", "review_model", "meta_model"]:
            if config.get(key):
                models_to_download.add(config[key])
        
        print(f"Synchronizing models to {model_dir}: {', '.join(models_to_download)}")
        
        success = True
        for model in models_to_download:
            if not download_model(model, model_dir):
                success = False
        
        if not success:
            sys.exit(1)

    if __name__ == "__main__":
        main()
  '';
  
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
      default = "http://127.0.0.1:40080/v1";
      description = "LLM backend URL for Layer 1";
    };

    reviewModel = mkOption {
      type = types.str;
      default = "qwen3:4b";
      description = "Model for continuous analysis in Layer 3";
    };

    reviewBackend = mkOption {
      type = types.str;
      default = "http://127.0.0.1:40081/v1";
      description = "LLM backend URL for Layer 3";
    };

    metaModel = mkOption {
      type = types.str;
      default = "qwen3:14b";
      description = "Large model for complex analysis in Layer 4";
    };

    metaBackend = mkOption {
      type = types.str;
      default = "http://127.0.0.1:40082/v1";
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
      default = "Brighid";
      example = "MyAI";
      description = ''
        Name of the AI assistant.
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
        default = 40084;
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
        default = 40085;
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
      after = [ "network.target" "ai-sysadmin-model-downloader.service" ];
      wants = [ "ai-sysadmin-model-downloader.service" ];
      wantedBy = [ "multi-user.target" ];
      serviceConfig = {
        ExecStart = "${pkgs.llama-cpp}/bin/llama-server --model ${cfg.modelDir}/${cfg.triggerModel}.gguf --port 40080 --host 127.0.0.1 --ctx-size 4096 --n-gpu-layers 99 --threads ${toString cfg.threads}";
        Restart = "on-failure";
        User = userName;
        Group = groupName;
      };
    };

    systemd.services.llama-review = mkIf cfg.llama-cpp.enable {
      description = "Llama.cpp Review Model Server";
      after = [ "network.target" "ai-sysadmin-model-downloader.service" ];
      wants = [ "ai-sysadmin-model-downloader.service" ];
      wantedBy = [ "multi-user.target" ];
      serviceConfig = {
        ExecStart = "${pkgs.llama-cpp}/bin/llama-server --model ${cfg.modelDir}/${cfg.reviewModel}.gguf --port 40081 --host 127.0.0.1 --ctx-size 32768 --n-gpu-layers 99 --threads ${toString cfg.threads}";
        Restart = "on-failure";
        User = userName;
        Group = groupName;
      };
    };

    systemd.services.llama-meta = mkIf cfg.llama-cpp.enable {
      description = "Llama.cpp Meta Model Server";
      after = [ "network.target" "ai-sysadmin-model-downloader.service" ];
      wants = [ "ai-sysadmin-model-downloader.service" ];
      wantedBy = [ "multi-user.target" ];
      serviceConfig = {
        ExecStart = "${pkgs.llama-cpp}/bin/llama-server --model ${cfg.modelDir}/${cfg.metaModel}.gguf --port 40082 --host 127.0.0.1 --ctx-size ${toString cfg.contextSize} --n-gpu-layers 99 --threads ${toString cfg.threads}";
        Restart = "on-failure";
        User = userName;
        Group = groupName;
      };
    };

    systemd.services.ai-sysadmin-model-downloader = {
      description = "AI Sysadmin Model Downloader";
      after = [ "network-online.target" ];
      wants = [ "network-online.target" ];
      serviceConfig = {
        Type = "oneshot";
        ExecStart = "${modelDownloaderScript}/bin/${cfg.aiName}-seed-models";
        User = userName;
        Group = groupName;
        RemainAfterExit = true;
      };
    };

    # OpenAI API Server for Meta Model
    systemd.services.ai-sysadmin-api = {
      description = "AI Sysadmin OpenAI-Compatible API Server";
      after = [ "network.target" "llama-meta.service" ];
      wantedBy = [ "multi-user.target" ];
      serviceConfig = {
        ExecStart = "${pythonEnv}/bin/python3 ${./.}/openai_api_server.py --port 40083";
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
    
    environment.systemPackages = with pkgs; [
      mainScript
      python313
      python313Packages.pip
      python313Packages.chromadb.pythonModule
      
      # The Unified Brighid CLI
      (pkgs.writeScriptBin "brighid" ''
        #!${pkgs.bash}/bin/bash
        
        # Disable ChromaDB .env searching globally for the CLI
        export CHROMA_ENV_FILE="/dev/null"
        export ANONYMIZED_TELEMETRY="False"
        
        # Helper to run python scripts as the AI user
        run_ai_tool() {
          local script=$1
          shift
          # Change to state directory to avoid permission issues with .env discovery in CWD
          cd ${stateDir}
          sudo -u ${userName} ${pkgs.coreutils}/bin/env \
            PYTHONPATH=${toString ./.} \
            CHROMA_ENV_FILE="/dev/null" \
            ANONYMIZED_TELEMETRY="False" \
            ${pythonEnv}/bin/python3 ${./.}/$script "$@"
        }

        case "$1" in
          run)
            shift
            # Run the continuous orchestrator
            run_ai_tool orchestrator.py --mode continuous --autonomy ${cfg.autonomyLevel} "$@"
            ;;
          check)
            shift
            # Run a single orchestration cycle
            run_ai_tool orchestrator.py --mode once --autonomy ${cfg.autonomyLevel} "$@"
            ;;
          chat)
            shift
            # Interactive chat
            run_ai_tool chat.py "$@"
            ;;
          ask)
            shift
            if [ $# -eq 0 ]; then
              echo "Usage: brighid ask <your question>"
              exit 1
            fi
            run_ai_tool chat.py --ask "$@"
            ;;
          approve)
            shift
            case "$1" in
              list)
                run_ai_tool executor.py queue
                ;;
              discuss)
                ACTION_ID="$2"
                if [ -z "$ACTION_ID" ]; then echo "Usage: brighid approve discuss <ID>"; exit 1; fi
                echo "==================================================================="
                echo "Interactive Discussion with Brighid about Action #$ACTION_ID"
                echo "==================================================================="
                run_ai_tool chat.py --discuss "$ACTION_ID"
                echo ""
                echo "==================================================================="
                echo "Ask follow-up questions, or type 'approve' / 'reject' / 'exit'."
                echo "==================================================================="
                while true; do
                  echo -n "You: "
                  read -r USER_INPUT
                  if [ "$USER_INPUT" = "exit" ] || [ "$USER_INPUT" = "quit" ] || [ -z "$USER_INPUT" ]; then break;
                  elif [ "$USER_INPUT" = "approve" ]; then run_ai_tool executor.py approve "$ACTION_ID"; break;
                  elif [ "$USER_INPUT" = "reject" ]; then run_ai_tool executor.py reject "$ACTION_ID"; break;
                  fi
                  echo -n "Brighid: "
                  run_ai_tool chat.py --discuss "$ACTION_ID" --follow-up "$USER_INPUT"
                done
                ;;
              approve|reject)
                CMD=$1
                ID=$2
                if [ -z "$ID" ]; then echo "Usage: brighid approve $CMD <ID>"; exit 1; fi
                run_ai_tool executor.py "$CMD" "$ID"
                ;;
              *)
                echo "Usage: brighid approve [list|discuss <ID>|approve <ID>|reject <ID>]"
                ;;
            esac
            ;;
          logs)
            shift
            case "$1" in
              orchestrator) sudo tail -f ${stateDir}/orchestrator.log ;;
              decisions) sudo tail -f ${stateDir}/decisions.jsonl ;;
              actions) sudo tail -f ${stateDir}/actions.jsonl ;;
              service) journalctl -u ${mainServiceName}.service -f ;;
              *) echo "Usage: brighid logs [orchestrator|decisions|actions|service]" ;;
            esac
            ;;
          issues)
            shift
            # Issue tracker sub-commands
            PYTHONPATH=${toString ./.} run_ai_tool -c "
from issue_tracker import IssueTracker
from context_db import ContextDatabase
import sys
db = ContextDatabase()
tracker = IssueTracker(db)
# ... issue tracker logic here ...
" "$@"
            ;;
          knowledge)
            shift
            # Knowledge base sub-commands
            run_ai_tool -c "from context_db import ContextDatabase; # ... logic ..." "$@"
            ;;
          systems)
            shift
            run_ai_tool -c "from context_db import ContextDatabase; db=ContextDatabase(); print(db.get_all_systems())"
            ;;
          config)
            shift
            case "$1" in
              search) shift; run_ai_tool -c "from context_db import ContextDatabase; db=ContextDatabase(); print(db.query_config_files('$1'))" ;;
              read) shift; run_ai_tool -c "from context_db import ContextDatabase; db=ContextDatabase(); print(db.get_config_file('$1')['content'])" ;;
              *) echo "Usage: brighid config [search|read]" ;;
            esac
            ;;
          notify)
            shift
            export GOTIFY_URL="${cfg.gotifyUrl}"
            export GOTIFY_TOKEN="${cfg.gotifyToken}"
            run_ai_tool notifier.py "$@"
            ;;
          *)
            echo "Brighid - AI System Administrator"
            echo "Usage: brighid <command> [args]"
            echo ""
            echo "Commands:"
            echo "  run        - Start orchestrator (continuous)"
            echo "  check      - Run single check cycle"
            echo "  chat       - Interactive chat"
            echo "  ask        - Single question"
            echo "  approve    - Manage pending actions"
            echo "  logs       - View AI or system logs"
            echo "  issues     - Manage tracked issues"
            echo "  knowledge  - Manage knowledge base"
            echo "  systems    - List known systems"
            echo "  config     - Search/read Nix configs"
            echo "  notify     - Send test notification"
            ;;
        esac
      '')
    ];
  };
}
