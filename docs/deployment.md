# Deployment to VPS

Run **Actions -> Deploy to VPS -> Run workflow -> main**.
Everything is in `.github/workflows/deploy.yml`: build the image, transfer it
over SSH, load it on the VPS, write `.env`, and restart the service using the
existing `docker-compose.yml`. No registry or separate deployment scripts.

The VPS needs Docker with either `docker compose` or `docker-compose`, Bash,
and enough space for the image archive. The SSH user needs permission to run
Docker and write to the deployment directory.

## GitHub settings

Add repository **Secrets** in **Settings -> Secrets and variables -> Actions**:

| Secret | Value |
| --- | --- |
| `VPS_SSH_KEY` | Dedicated private SSH key without a passphrase |
| `VPS_KNOWN_HOSTS` | Verified host key entries; use `[host]:port` for a non-default port |
| `MAX_TOKEN` | MAX session token |
| `TG_BOT_TOKEN` | Telegram bot token |

Verify the SSH host key fingerprint against the VPS before saving it.

Add repository **Variables**:

| Variable | Value |
| --- | --- |
| `VPS_HOST` | VPS hostname or IP |
| `VPS_USER` | SSH user |
| `VPS_PORT` | SSH port, default `22` |
| `MAX_DEVICE_ID` | MAX device ID |
| `DEPLOY_PATH` | Absolute installation path without spaces, e.g. `/opt/max2tg` |
| `DEPLOY_PROJECT` | Existing Compose project name |
| `DOCKER_PLATFORM` | `linux/amd64` (default) or `linux/arm64`, matching the VPS |
| `TG_CHAT_ID` | Telegram supergroup ID |
| `MAX_IGNORE_CHAT_IDS` | Optional comma-separated ignored chat IDs |
| `DEBUG` | Default `false` |
| `REPLY_ENABLED` | Default `true` |

Use the same path and project name as the existing installation to preserve
the `state/` and `logs/` directories and replace the existing container rather
than start a second bridge. Find the project name in the current installation:

```bash
docker inspect "$(docker compose ps -q max2tg)" \
  --format '{{ index .Config.Labels "com.docker.compose.project" }}'
```

## Behavior

Each deployment completely replaces `.env` with the seven application settings
listed above, with permissions `600`. Any additional settings in the old file
are removed. Credentials are not baked into the image or printed in the log.
Favorites always uses `chatId=0`; `MAX_FAVORITES_CHAT_ID` is not needed.

The workflow uploads the existing compose file and runs the loaded
`max2tg-bridge:latest` image with `--no-build --force-recreate`. It automatically
selects the available Compose command and checks container health using
`docker inspect` for up to 180 seconds. On failure the workflow reports an
error; there is no automatic rollback. The image archive is deleted after a
successful deployment. Application data is not deleted.

For logs on the VPS:

```bash
cd /opt/max2tg
docker compose -p max2tg logs -f max2tg
```

Replace the path and project name with your settings. Use Actions for updates;
`up --build` would build from the VPS checkout again.
If the server uses standalone Compose, replace `docker compose` with
`docker-compose` in the commands above.
