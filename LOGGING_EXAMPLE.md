# Enhanced Logging Example

This shows what the improved journalctl output will look like for Macha's autonomous system.

## Example Output

### Maintenance Cycle Start
```
[2025-10-01T14:30:00] === Starting maintenance cycle ===
[2025-10-01T14:30:00] Collecting system health data...

[2025-10-01T14:30:02] ============================================================
[2025-10-01T14:30:02] SYSTEM HEALTH SUMMARY
[2025-10-01T14:30:02] ============================================================
[2025-10-01T14:30:02] Resources: CPU 25.3%, Memory 45.2%, Load 1.24
[2025-10-01T14:30:02] Disk: 35.6% used (/ partition)
[2025-10-01T14:30:02] Services: 1 failed
[2025-10-01T14:30:02]   - ollama.service (failed)
[2025-10-01T14:30:02] Network: Internet reachable
[2025-10-01T14:30:02] Recent logs: 3 errors in last hour
[2025-10-01T14:30:02] ============================================================

[2025-10-01T14:30:02] KEY METRICS:
[2025-10-01T14:30:02]   CPU Usage: 25.3%
[2025-10-01T14:30:02]   Memory Usage: 45.2%
[2025-10-01T14:30:02]   Load Average: 1.24
[2025-10-01T14:30:02]   Failed Services: 1
[2025-10-01T14:30:02]   Errors (1h): 3
[2025-10-01T14:30:02]   Disk /: 35.6% used
[2025-10-01T14:30:02]   Disk /home: 62.1% used
[2025-10-01T14:30:02]   Disk /var: 28.9% used
[2025-10-01T14:30:02]   Internet: ✅ Connected
```

### AI Analysis Section
```
[2025-10-01T14:30:02] Analyzing system state with AI...

[2025-10-01T14:30:35] ============================================================
[2025-10-01T14:30:35] AI ANALYSIS RESULTS
[2025-10-01T14:30:35] ============================================================
[2025-10-01T14:30:35] Overall Status: ATTENTION_NEEDED
[2025-10-01T14:30:35] Assessment: System has one failed service that should be restarted

[2025-10-01T14:30:35] Detected 1 issue(s):

[2025-10-01T14:30:35]   Issue #1:
[2025-10-01T14:30:35]     Severity: WARNING
[2025-10-01T14:30:35]     Category: services
[2025-10-01T14:30:35]     Description: ollama.service has failed and needs to be restarted
[2025-10-01T14:30:35]     ⚠️ ACTION REQUIRED

[2025-10-01T14:30:35] Recommended Actions (1):
[2025-10-01T14:30:35]   - Restart ollama.service to restore LLM functionality
[2025-10-01T14:30:35] ============================================================
```

### Action Handling Section
```
[2025-10-01T14:30:35] Found 1 issues requiring action

[2025-10-01T14:30:35] ────────────────────────────────────────────────────────────
[2025-10-01T14:30:35] Addressing issue: ollama.service has failed and needs to be restarted
[2025-10-01T14:30:35] Requesting AI fix proposal...

[2025-10-01T14:30:45] AI FIX PROPOSAL:
[2025-10-01T14:30:45]   Diagnosis: ollama.service crashed or failed to start properly
[2025-10-01T14:30:45]   Proposed Action: Restart ollama.service using systemctl
[2025-10-01T14:30:45]   Action Type: systemd_restart
[2025-10-01T14:30:45]   Risk Level: LOW
[2025-10-01T14:30:45]   Commands to execute:
[2025-10-01T14:30:45]     - systemctl restart ollama.service
[2025-10-01T14:30:45]   Reasoning: Restarting the service is a safe, standard troubleshooting step
[2025-10-01T14:30:45]   Rollback Plan: Service will return to failed state if restart doesn't work

[2025-10-01T14:30:45] Executing action...

[2025-10-01T14:30:47] EXECUTION RESULT:
[2025-10-01T14:30:47]   Status: QUEUED_FOR_APPROVAL
[2025-10-01T14:30:47]   Executed: No
[2025-10-01T14:30:47]   Reason: Autonomy level requires manual approval
```

### Cycle Complete Summary
```
[2025-10-01T14:30:47] No issues requiring immediate action

[2025-10-01T14:30:47] ============================================================
[2025-10-01T14:30:47] MAINTENANCE CYCLE COMPLETE
[2025-10-01T14:30:47] ============================================================
[2025-10-01T14:30:47] Status: ATTENTION_NEEDED
[2025-10-01T14:30:47] Issues Found: 1
[2025-10-01T14:30:47] Actions Taken: 1
[2025-10-01T14:30:47]   - Executed: 0
[2025-10-01T14:30:47]   - Queued for approval: 1
[2025-10-01T14:30:47] Next check in: 300 seconds
[2025-10-01T14:30:47] ============================================================
```

## When System is Healthy

```
[2025-10-01T14:35:00] === Starting maintenance cycle ===
[2025-10-01T14:35:00] Collecting system health data...

[2025-10-01T14:35:02] ============================================================
[2025-10-01T14:35:02] SYSTEM HEALTH SUMMARY
[2025-10-01T14:35:02] ============================================================
[2025-10-01T14:35:02] Resources: CPU 12.5%, Memory 38.1%, Load 0.65
[2025-10-01T14:35:02] Disk: 35.6% used (/ partition)
[2025-10-01T14:35:02] Services: All running
[2025-10-01T14:35:02] Network: Internet reachable
[2025-10-01T14:35:02] Recent logs: 0 errors in last hour
[2025-10-01T14:35:02] ============================================================

[2025-10-01T14:35:02] KEY METRICS:
[2025-10-01T14:35:02]   CPU Usage: 12.5%
[2025-10-01T14:35:02]   Memory Usage: 38.1%
[2025-10-01T14:35:02]   Load Average: 0.65
[2025-10-01T14:35:02]   Failed Services: 0
[2025-10-01T14:35:02]   Errors (1h): 0
[2025-10-01T14:35:02]   Disk /: 35.6% used
[2025-10-01T14:35:02]   Internet: ✅ Connected

[2025-10-01T14:35:02] Analyzing system state with AI...

[2025-10-01T14:35:28] ============================================================
[2025-10-01T14:35:28] AI ANALYSIS RESULTS
[2025-10-01T14:35:28] ============================================================
[2025-10-01T14:35:28] Overall Status: HEALTHY
[2025-10-01T14:35:28] Assessment: System is operating normally with no issues detected

[2025-10-01T14:35:28] ✅ No issues detected
[2025-10-01T14:35:28] ============================================================

[2025-10-01T14:35:28] No issues requiring immediate action

[2025-10-01T14:35:28] ============================================================
[2025-10-01T14:35:28] MAINTENANCE CYCLE COMPLETE
[2025-10-01T14:35:28] ============================================================
[2025-10-01T14:35:28] Status: HEALTHY
[2025-10-01T14:35:28] Issues Found: 0
[2025-10-01T14:35:28] Actions Taken: 0
[2025-10-01T14:35:28] Next check in: 300 seconds
[2025-10-01T14:35:28] ============================================================
```

## Viewing Logs

### Follow live logs
```bash
journalctl -u macha-autonomous.service -f
```

### See only AI decisions
```bash
journalctl -u macha-autonomous.service | grep "AI ANALYSIS"
```

### See only execution results
```bash
journalctl -u macha-autonomous.service | grep "EXECUTION RESULT"
```

### See key metrics
```bash
journalctl -u macha-autonomous.service | grep "KEY METRICS" -A 10
```

### Filter by status level
```bash
# Only show intervention required
journalctl -u macha-autonomous.service | grep "INTERVENTION_REQUIRED"

# Only show critical issues
journalctl -u macha-autonomous.service | grep "CRITICAL"

# Only show action required
journalctl -u macha-autonomous.service | grep "ACTION REQUIRED"
```

### Summary of last cycle
```bash
journalctl -u macha-autonomous.service | grep "MAINTENANCE CYCLE COMPLETE" -B 5 | tail -6
```

## Benefits of Enhanced Logging

### 1. **Easy to Scan**
Clear section headers with separators make it easy to find what you need

### 2. **Structured Data**
Key metrics are labeled consistently for easy parsing/grepping

### 3. **Complete Context**
Each cycle shows:
- What the system saw
- What the AI thought
- What action was proposed
- What actually happened

### 4. **AI Transparency**
You can see:
- The AI's reasoning for each decision
- Risk assessment for each action
- Rollback plans if something goes wrong

### 5. **Audit Trail**
Everything is logged to journalctl for long-term storage and analysis

### 6. **Troubleshooting**
If something goes wrong, you have complete context:
- System state before the issue
- AI's diagnosis
- Action attempted
- Result of action

