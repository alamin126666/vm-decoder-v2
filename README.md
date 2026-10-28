# 😈 VM Decoder Bot

Telegram bot that automatically decodes VM-protected HTML files.

## Deploy to Railway

### Step 1: Get Bot Token
1. Open Telegram → search @BotFather
2. Send `/newbot`
3. Follow instructions → copy the token

### Step 2: Deploy to Railway
1. Go to [railway.app](https://railway.app)
2. Click **"New Project"**
3. Click **"Deploy from GitHub repo"**
4. Upload/push this folder to GitHub first
5. Connect the repo
6. Add environment variables:
   - `BOT_TOKEN` = your bot token
   - `ADMIN_IDS` = your Telegram user ID (optional)
7. Railway auto-deploys!

### Step 3: Use the Bot
Send your encrypted HTML file to the bot and follow the steps!

## How it works

```
Encrypted HTML
     ↓
Step 1: Static decode (outer layer)
     ↓  
Step 2: Anti-debug patches (6 blocks removed)
     ↓
Step 3: CDP capture script inject
     ↓
Playwright Chromium auto-runs (/cdp mode)
     ↓
100% runtime capture via Chrome DevTools Protocol
     ↓
Clean decoded HTML output
```

## Commands
- `/start` — Start
- `/cdp` — Auto CDP mode (no manual browser needed!)
- `/reset` — Reset state
- `/status` — Check current status
