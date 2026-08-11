# Deploy

## Discord app

1. Create an application at https://discord.com/developers/applications
2. Bot → Reset Token → copy token
3. OAuth2 → URL Generator → scopes: `bot`, `applications.commands` → invite to your server

## Server setup

```bash
# clone and enter repo
git clone <repo-url> please-handle && cd please-handle
```

```bash
# python venv + deps
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

```bash
# config
cp .env.example .env
nano .env   # set DISCORD_TOKEN and PRIVILEGED_USERS (comma-separated Discord user IDs)
```

## Run

```bash
# foreground
.venv/bin/python bot.py
```

```bash
# background (simple)
nohup .venv/bin/python bot.py >> bot.log 2>&1 &
```

Optional systemd unit (`/etc/systemd/system/please-handle.service`):

```ini
[Unit]
Description=please-handle Discord bot
After=network.target

[Service]
WorkingDirectory=/path/to/please-handle
ExecStart=/path/to/please-handle/.venv/bin/python bot.py
Restart=always
User=YOUR_USER

[Install]
WantedBy=multi-user.target
```

```bash
# enable + start service
sudo systemctl daemon-reload
sudo systemctl enable --now please-handle
```

## After start

1. In Discord: `/handle enable` in the channel that should get scheduled posts
2. Optional: `/handle schedule` (type `opentasks` or `announce`), `/handle timezone`, `/handle settings`
