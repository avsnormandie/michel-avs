# Michel - Assistant IA AVS Technologies

Michel est le fork AVS de [Clawdbot/OpenClaw](https://github.com/clawdbot/clawdbot), personnalisÃ© pour les besoins internes d'AVS Technologies.

## Architecture

```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚                    GK41 Mini-PC                             â”‚
â”‚                   (192.168.2.26)                            â”‚
â”‚  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”   â”‚
â”‚  â”‚                   Michel                             â”‚   â”‚
â”‚  â”‚  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”   â”‚   â”‚
â”‚  â”‚  â”‚ Clawdbot  â”‚  â”‚  Skills   â”‚  â”‚   Plugins     â”‚   â”‚   â”‚
â”‚  â”‚  â”‚   Core    â”‚  â”‚   AVS     â”‚  â”‚   Custom      â”‚   â”‚   â”‚
â”‚  â”‚  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜   â”‚   â”‚
â”‚  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜   â”‚
â”‚                           â”‚                                 â”‚
â”‚                  Reverse SSH Tunnel                         â”‚
â”‚                     (port 7912)                             â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                            â”‚
                            â–¼
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚              web-server-avs (141.95.154.151)                â”‚
â”‚  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”   â”‚
â”‚  â”‚              Intranet AVS                            â”‚   â”‚
â”‚  â”‚  /api/external/ssh  â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–º GK41        â”‚   â”‚
â”‚  â”‚  /api/external/michel â—„â”€â”€â”€â”€â”€ Telegram Bot           â”‚   â”‚
â”‚  â”‚  /api/external/knowledge â—„â”€â”€ Base de connaissances  â”‚   â”‚
â”‚  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜   â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

## Personnalisations AVS

### 1. Compaction Guard (P1)
Protection contre la perte de contexte lors de la compaction automatique.

```javascript
// Intercepte l'Ã©vÃ©nement session_before_compact
// Sauvegarde automatique vers la base de connaissances AVS
```

**Status**: ðŸ”„ En cours

### 2. Context Monitor (P2)
Script externe surveillant l'utilisation du contexte.

- **Seuil warning** : 70%
- **Seuil critique** : 85%
- **Actions** : Alerte Telegram + sauvegarde KB

**Status**: âœ… ImplÃ©mentÃ© (`~/michel-workspace/scripts/context-monitor.sh`)

### 3. Tool Result Limiter (P6)
Limite automatique des rÃ©sultats d'outils volumineux.

**Status**: ðŸ“‹ PlanifiÃ©

### 4. Commande /compact (P7)
Commande manuelle pour dÃ©clencher la compaction avec sauvegarde prÃ©alable.

**Status**: ðŸ“‹ PlanifiÃ©

## Installation

```bash
# Sur le GK41
cd /home/michel
git clone https://github.com/avsnormandie/michel-avs.git
cd michel-avs
pnpm install
pnpm build
```

## Configuration

### Variables d'environnement
```bash
# ~/.bashrc ou ~/.profile
export AVS_API_KEY="avs_xxx..."
export AVS_INTRANET_URL="https://intra.avstech.fr"
```

### Vault AVS
Michel utilise le Vault AVS pour rÃ©cupÃ©rer ses credentials de maniÃ¨re sÃ©curisÃ©e :

```bash
curl -X GET "https://intra.avstech.fr/api/external/vault/api_key_michel" \
  -H "Authorization: Bearer <vault_password>"
```

## Versioning

Ce projet suit [Semantic Versioning](https://semver.org/).

- **MAJOR** : Changements incompatibles avec l'upstream Clawdbot
- **MINOR** : Nouvelles fonctionnalitÃ©s AVS
- **PATCH** : Corrections de bugs

### Mise Ã  jour depuis l'upstream

```bash
git remote add upstream https://github.com/clawdbot/clawdbot.git
git fetch upstream
git merge upstream/main --no-edit
# RÃ©soudre les conflits si nÃ©cessaire
```

## Contact

- **Repo** : https://github.com/avsnormandie/michel-avs
- **Issues** : https://github.com/avsnormandie/michel-avs/issues
- **Intranet** : https://intra.avstech.fr/knowledge (rechercher "Michel")
