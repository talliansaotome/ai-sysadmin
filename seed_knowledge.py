#!/usr/bin/env python3
"""
Seed initial operational knowledge into Macha's knowledge base
"""

import sys
sys.path.insert(0, '.')

from context_db import ContextDatabase

def seed_knowledge():
    """Add foundational operational knowledge"""
    db = ContextDatabase()
    
    knowledge_items = [
        # nh command knowledge
        {
            "topic": "nh os switch",
            "knowledge": "NixOS rebuild command. Takes 1-5 minutes normally, up to 1 HOUR for major updates with many packages. DO NOT retry if slow - this is normal. Use -u flag to update flake inputs first. Can use --target-host and --hostname for remote deployment.",
            "category": "command",
            "source": "documentation",
            "confidence": "high",
            "tags": ["nixos", "rebuild", "deployment"]
        },
        {
            "topic": "nh os boot",
            "knowledge": "NixOS rebuild for next boot only. Safer than 'switch' for high-risk changes - allows easy rollback. After 'nh os boot', need to reboot for changes to take effect. Use -u to update flake inputs.",
            "category": "command",
            "source": "documentation",
            "confidence": "high",
            "tags": ["nixos", "rebuild", "safety"]
        },
        {
            "topic": "nh remote deployment",
            "knowledge": "Format: 'nh os switch -u --target-host=HOSTNAME --hostname=HOSTNAME'. Builds locally and deploys to remote. Much cleaner than SSH'ing to run commands. Uses root SSH keys for authentication.",
            "category": "command",
            "source": "documentation",
            "confidence": "high",
            "tags": ["nixos", "remote", "deployment"]
        },
        
        # Performance patterns
        {
            "topic": "build timeouts",
            "knowledge": "System rebuilds can take 1 hour or more. Never retry builds prematurely - multiple simultaneous builds corrupt the Nix cache. Default timeout is 3600 seconds (1 hour). Be patient!",
            "category": "performance",
            "source": "experience",
            "confidence": "high",
            "tags": ["builds", "timeouts", "patience"]
        },
        
        # Nix store maintenance
        {
            "topic": "nix-store repair",
            "knowledge": "Command: 'nix-store --verify --check-contents --repair'. Verifies and repairs Nix store integrity. WARNING: Can take HOURS on large stores. Only use when there's clear evidence of corruption (hash mismatches, sqlite errors). This is a LAST RESORT - most build failures are NOT corruption.",
            "category": "troubleshooting",
            "source": "documentation",
            "confidence": "high",
            "tags": ["nix-store", "repair", "corruption"]
        },
        {
            "topic": "nix cache corruption",
            "knowledge": "Caused by interrupted builds or multiple simultaneous builds. Symptoms: hash mismatches, sqlite errors, corrupt database. Solution: 'nix-store --verify --check-contents --repair' but this takes hours. Prevention: Never retry build commands, use proper timeouts.",
            "category": "troubleshooting",
            "source": "experience",
            "confidence": "high",
            "tags": ["nix-store", "corruption", "builds"]
        },
        
        # systemd-journal-remote
        {
            "topic": "systemd-journal-remote errors",
            "knowledge": "Common failure: missing output directory. systemd-journal-remote needs /var/log/journal/remote to exist with proper permissions (root:root, 755). Create it if missing, then restart the service.",
            "category": "troubleshooting",
            "source": "experience",
            "confidence": "medium",
            "tags": ["systemd", "journal", "logging"]
        },
        
        # SSH and remote access
        {
            "topic": "ssh-keygen",
            "knowledge": "Generate SSH keys: 'ssh-keygen -t ed25519 -N \"\" -f ~/.ssh/id_ed25519'. Creates public key at ~/.ssh/id_ed25519.pub and private key at ~/.ssh/id_ed25519. Use -N \"\" for no passphrase.",
            "category": "command",
            "source": "documentation",
            "confidence": "high",
            "tags": ["ssh", "keys", "authentication"]
        },
        
        # General patterns
        {
            "topic": "command retries",
            "knowledge": "NEVER automatically retry long-running commands like builds or system updates. If something times out, check if it's still running before retrying. Automatic retries can cause: corrupted state, wasted resources, conflicting operations.",
            "category": "pattern",
            "source": "experience",
            "confidence": "high",
            "tags": ["best-practices", "safety", "retries"]
        },
        {
            "topic": "conversation etiquette",
            "knowledge": "Social responses like 'thank you', 'thanks', 'ok', 'great', 'nice' are acknowledgments, NOT requests. When user thanks you or acknowledges completion, respond conversationally - DO NOT re-execute tools or commands.",
            "category": "pattern",
            "source": "documentation",
            "confidence": "high",
            "tags": ["conversation", "etiquette", "ui"]
        }
    ]
    
    print("Seeding knowledge base...")
    for item in knowledge_items:
        kid = db.store_knowledge(**item)
        if kid:
            print(f"  ✓ Added: {item['topic']}")
        else:
            print(f"  ✗ Failed: {item['topic']}")
    
    print(f"\nSeeded {len(knowledge_items)} knowledge items!")
    
    # List all topics
    print("\nAvailable knowledge topics:")
    topics = db.list_knowledge_topics()
    for topic in topics:
        print(f"  - {topic}")


if __name__ == "__main__":
    seed_knowledge()

