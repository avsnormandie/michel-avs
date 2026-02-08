# Michel - Assistant IA AVS Technologies

Michel est le fork AVS de [Clawdbot/OpenClaw](https://github.com/clawdbot/clawdbot), personnalise pour les besoins internes d'AVS Technologies.

## Architecture

```
+-------------------------------------------------------------+
|                    GK41 Mini-PC                              |
|                   (192.168.2.26)                             |
|  +-------------------------------------------------------+  |
|  |                   Michel                               |  |
|  |  +-----------+  +-----------+  +---------------+       |  |
|  |  | OpenClaw  |  |  Skills   |  |   Plugins     |       |  |
|  |  |   Core    |  |   AVS     |  |   Custom      |       |  |
|  |  +-----------+  +-----------+  +---------------+       |  |
|  |                                                        |  |
|  |  Gateway HTTP/WS :18789                                |  |
|  |  +-- /v1/chat/completions  (OpenAI-compatible, sync)   |  |
|  |  +-- /hooks/agent          (async, fire-and-forget)    |  |
|  |  +-- Telegram Bot          (@michel_avs_bot)           |  |
|  +-------------------------------------------------------+  |
|                          |                                   |
|                 Reverse SSH Tunnel                            |
|                    (port 7912)                                |
+----------------------------+---------------------------------+
                             |
                             v
+-------------------------------------------------------------+
|             web-server-avs (141.95.154.151)                  |
|  +-------------------------------------------------------+  |
|  |              Intranet AVS                              |  |
|  |  /api/external/ssh  -------------------> GK41          |  |
|  |  /api/external/michel <----- Telegram Bot              |  |
|  |  /api/external/knowledge <-- Base de connaissances     |  |
|  +-------------------------------------------------------+  |
+-------------------------------------------------------------+
```

## Communication avec Michel

### 1. Endpoint OpenAI-compatible (recommande)

Methode synchrone : envoi d'un message, reception de la reponse dans la meme requete.

```bash
curl -s -X POST "http://127.0.0.1:18789/v1/chat/completions" \
  -H "Authorization: Bearer michel_avs_2026" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "anthropic/claude-sonnet-4-5",
    "messages": [
      {"role": "user", "content": "Ton message ici"}
    ]
  }'
```

**Reponse** :

```json
{
  "id": "chatcmpl_...",
  "choices": [
    {
      "message": { "role": "assistant", "content": "Reponse de Michel" },
      "finish_reason": "stop"
    }
  ]
}
```

**Config requise** dans `~/.openclaw/openclaw.json` :

```json
{
  "gateway": {
    "http": {
      "endpoints": {
        "chatCompletions": { "enabled": true }
      }
    }
  }
}
```

### 2. Hooks Agent (async)

Envoie un message que Michel traite en arriere-plan. Retourne un `runId` immediatement.

```bash
curl -s -X POST "http://127.0.0.1:18789/hooks/agent" \
  -H "Authorization: Bearer michel_avs_2026" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Ton message",
    "name": "Claude Code",
    "channel": "telegram",
    "to": "8113899151"
  }'
```

**Config requise** :

```json
{
  "hooks": {
    "enabled": true,
    "token": "michel_avs_2026"
  }
}
```

> Note : la delivery de la reponse sur Telegram n'est pas toujours fiable. Preferer l'endpoint `/v1/chat/completions`.

### 3. API Intranet

Envoie un message via l'intranet, qui le transmet sur Telegram avec un `request_id` pour recuperer la reponse.

```bash
# Envoyer
curl -s -X POST "https://intra.avstech.fr/api/external/michel" \
  -H "X-API-Key: ${AVS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"message": "Ton message", "from": "Claude Code"}'

# Recuperer la reponse (polling)
curl -s "https://intra.avstech.fr/api/external/michel?request_id=<id>" \
  -H "X-API-Key: ${AVS_API_KEY}"
```

### 4. CLI (message direct, pas de traitement IA)

Envoie un message Telegram brut de la part du bot (pas de traitement par l'agent IA).

```bash
node openclaw.mjs message send --channel telegram --target 8113899151 -m "message"
```

## Service systemd

```ini
# ~/.config/systemd/user/michel-avs.service
[Service]
WorkingDirectory=/home/michel/michel-avs
ExecStart=/usr/bin/node /home/michel/michel-avs/openclaw.mjs gateway --port 18789
Environment=OPENCLAW_GATEWAY_TOKEN=michel_avs_2026
Environment=ANTHROPIC_API_KEY=sk-ant-api03-...
Environment=AVS_API_KEY=avs_c5fztIGmhectI2J1Bz16vwHAT8Uf4zJl
Environment=AVS_INTRANET_URL=https://intra.avstech.fr
```

```bash
systemctl --user status michel-avs    # Etat
systemctl --user restart michel-avs   # Redemarrer
systemctl --user stop michel-avs      # Arreter
journalctl --user -u michel-avs -f    # Logs en live
```

**Logs detailles** : `/tmp/openclaw/openclaw-YYYY-MM-DD.log`

## Personnalisations AVS

### 1. Compaction Guard (`src/agents/pi-extensions/avs-compaction-guard.ts`)

Protection contre la perte de contexte lors de la compaction automatique.

- Intercepte l'evenement `session_before_compact`
- Sauvegarde le contexte important vers la base de connaissances AVS
- Envoie une alerte Telegram
- Fichiers modifies et lus sont traces

**Status**: En cours

### 2. Response Forwarder (`src/telegram/bot-message-dispatch.ts`)

Redirige les reponses de Michel vers l'API intranet quand le message entrant contient un `[request_id: ...]`.

- Regex : `\[request[_\\]id:\s*(michel_[a-f0-9]+)\]`
- POST vers `/api/external/michel/respond`

### 3. AVS Brain (`skills/avs-brain/`)

Memoire persistante avec embeddings semantiques.

- **brain.db** : SQLite avec 345 memories + embeddings (all-MiniLM-L6-v2)
- **Sync** : pull depuis la KB intranet, push vers la KB
- **Recherche** : semantique + texte, top-k resultats

```bash
python3 skills/avs-brain/scripts/brain.py search "requete"
python3 skills/avs-brain/scripts/brain.py sync --direction pull
python3 skills/avs-brain/scripts/brain.py stats
```

### 4. Context Monitor

Script externe surveillant l'utilisation du contexte.

- **Seuil warning** : 70%
- **Seuil critique** : 85%
- **Actions** : Alerte Telegram + sauvegarde KB

**Status**: Implemente (`~/michel-workspace/scripts/context-monitor.sh`)

## Configuration (`~/.openclaw/openclaw.json`)

```json
{
  "agents": {
    "defaults": {
      "model": { "primary": "anthropic/claude-sonnet-4-5" },
      "workspace": "/home/michel/michel-workspace",
      "compaction": { "mode": "safeguard" },
      "heartbeat": { "every": "30m" },
      "maxConcurrent": 4
    }
  },
  "channels": {
    "telegram": {
      "name": "Michel AVS",
      "enabled": true,
      "dmPolicy": "pairing",
      "streamMode": "partial"
    }
  },
  "hooks": {
    "enabled": true,
    "token": "michel_avs_2026"
  },
  "gateway": {
    "port": 18789,
    "mode": "local",
    "http": {
      "endpoints": {
        "chatCompletions": { "enabled": true }
      }
    }
  },
  "skills": {
    "load": {
      "extraDirs": ["/home/michel/michel-avs/skills"]
    }
  }
}
```

## Vault AVS

Michel utilise le Vault AVS pour recuperer ses credentials de maniere securisee :

```bash
# Lire un secret
curl -s "https://intra.avstech.fr/api/external/vault/<scope>" \
  -H "Authorization: Bearer ${VAULT_PASSWORD}" \
  -H "X-API-Key: ${AVS_API_KEY}"

# Ecrire un secret
curl -s -X POST "https://intra.avstech.fr/api/external/vault/<scope>" \
  -H "Authorization: Bearer ${VAULT_PASSWORD}" \
  -H "X-API-Key: ${AVS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"key": "nom", "value": "valeur"}'
```

## Versioning

Versioning calendaire : `YYYY.M.D` (ex: 2026.2.8)

### Mise a jour depuis l'upstream

```bash
git remote add upstream https://github.com/clawdbot/clawdbot.git
git fetch upstream
git merge upstream/main --no-edit
# Resoudre les conflits si necessaire
```

> Ne pas renommer "openclaw" dans le code interne — casse la sync upstream.

## Contact

- **Repo** : https://github.com/avsnormandie/michel-avs (prive)
- **Issues** : https://github.com/avsnormandie/michel-avs/issues
- **Intranet** : https://intra.avstech.fr/knowledge (rechercher "Michel")
