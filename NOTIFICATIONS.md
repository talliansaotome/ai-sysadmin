# Gotify Notifications Setup

Macha's autonomous system can now send notifications to Gotify on Rhiannon for critical events.

## What Gets Notified

### High Priority (🚨 Priority 8)
- **Critical issues detected** - System problems requiring immediate attention
- **Service failures** - When critical services fail
- **Failed actions** - When an action execution fails
- **Intervention required** - When system status is critical

### Medium Priority (📋 Priority 5)
- **Actions queued for approval** - When medium/high-risk actions need manual review
- **System attention needed** - When system status needs attention

### Low Priority (✅ Priority 2)
- **Successful actions** - When safe actions execute successfully
- **System healthy** - Periodic health check confirmations (if enabled)

## Setup Instructions

### Step 1: Create Gotify Application on Rhiannon

1. Open Gotify web interface on Rhiannon:
   ```bash
   # URL: http://rhiannon:8181 (or use external access)
   ```

2. Log in to Gotify

3. Go to **"Apps"** tab

4. Click **"Create Application"**

5. Name it: `Macha Autonomous System`

6. Copy the generated **Application Token**

### Step 2: Configure Macha

Edit `/home/lily/Documents/gitrepos/nixos-servers/systems/macha.nix`:

```nix
services.macha-autonomous = {
  enable = true;
  autonomyLevel = "suggest";
  checkInterval = 300;
  model = "llama3.1:70b";
  
  # Gotify notifications
  gotifyUrl = "http://rhiannon:8181";
  gotifyToken = "YOUR_TOKEN_HERE";  # Paste the token from Step 1
};
```

### Step 3: Rebuild and Deploy

```bash
cd /home/lily/Documents/gitrepos/nixos-servers
sudo nixos-rebuild switch --flake .#macha
```

### Step 4: Test Notifications

Send a test notification:

```bash
macha-notify "Test" "Macha notifications are working!" 5
```

You should see this notification appear in Gotify on Rhiannon.

## CLI Tools

### Send Test Notification
```bash
macha-notify <title> <message> [priority]

# Examples:
macha-notify "Test" "This is a test" 5
macha-notify "Critical" "This is urgent" 8
macha-notify "Info" "Just FYI" 2
```

Priorities:
- `2` - Low (✅ green)
- `5` - Medium (📋 blue)
- `8` - High (🚨 red)

### Check if Notifications are Enabled

```bash
# View the service environment
systemctl show macha-autonomous.service | grep GOTIFY
```

## Notification Examples

### Critical Issue
```
🚨 Macha: Critical Issue
⚠️ Critical Issue Detected

High disk usage on /var partition (95% full)

Details:
Category: disk
```

### Action Queued for Approval
```
📋 Macha: Action Needs Approval
ℹ️ Action Queued for Approval

Action: Restart failed service: ollama.service
Risk Level: low

Use 'macha-approve list' to review
```

### Action Executed Successfully
```
✅ Macha: Action Success
✅ Action Success

Restart failed service: ollama.service

Output:
Service restarted successfully
```

### Action Failed
```
❌ Macha: Action Failed
❌ Action Failed

Clean up disk space with nix-collect-garbage

Output:
Error: Insufficient permissions
```

## Security Notes

1. **Token Storage**: The Gotify token is stored in the NixOS configuration. Consider using a secrets management solution for production.

2. **Network Access**: Macha needs network access to Rhiannon. Ensure your firewall allows HTTP traffic between them.

3. **Token Scope**: The Gotify token only allows sending messages, not reading or managing Gotify.

## Troubleshooting

### Notifications Not Appearing

1. **Check Gotify is running on Rhiannon:**
   ```bash
   ssh rhiannon systemctl status gotify
   ```

2. **Test connectivity from Macha:**
   ```bash
   curl http://rhiannon:8181/health
   ```

3. **Verify token is set:**
   ```bash
   macha-notify "Test" "Testing" 5
   ```

4. **Check service logs:**
   ```bash
   macha-logs service | grep -i gotify
   ```

### Notification Spam

If you're getting too many notifications, you can:

1. **Disable notifications temporarily:**
   ```nix
   services.macha-autonomous.gotifyUrl = "";  # Empty string disables
   ```

2. **Adjust autonomy level:**
   ```nix
   services.macha-autonomous.autonomyLevel = "auto-safe";  # Fewer approval notifications
   ```

3. **Increase check interval:**
   ```nix
   services.macha-autonomous.checkInterval = 900;  # Check every 15 minutes instead of 5
   ```

## Implementation Details

### Files Modified
- `notifier.py` - Gotify notification client
- `module.nix` - Added configuration options and CLI tool
- `orchestrator.py` - Integrated notifications at decision points
- `macha.nix` - Added Gotify configuration

### Notification Flow
```
Issue Detected → AI Analysis → Decision Made → Notification Sent
                                    ↓
                          Queued or Executed → Notification Sent
```

### Graceful Degradation
- If Gotify is unavailable, the system continues to operate
- Failed notifications are logged but don't crash the service
- Notifications have a 10-second timeout to prevent blocking

## Future Enhancements

Possible improvements:
- [ ] Rate limiting to prevent notification spam
- [ ] Notification grouping (batch similar issues)
- [ ] Custom notification templates
- [ ] Priority-based notification filtering
- [ ] Integration with other notification services (email, SMS)
- [ ] Secrets management for tokens (agenix, sops-nix)

