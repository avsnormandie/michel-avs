---
name: avs-brain
description: "Cerveau de Michel avec memoire persistante, emails Gmail, transcription audio, analyse images/PDF, calendrier, monitoring serveurs, rapports automatiques."
metadata:
  openclaw:
    emoji: "🧠"
    requires:
      bins: ["python3"]
    tools:
      - name: brain_remember
        description: "Memoriser une information importante"
        command: "python3 scripts/brain.py remember --title '{title}' --content '{content}' --type {type} --importance {importance}"
      - name: brain_search
        description: "Rechercher dans le cerveau"
        command: "python3 scripts/brain.py search '{query}' --limit {limit}"
      - name: brain_stats
        description: "Statistiques du cerveau"
        command: "python3 scripts/brain.py stats"
      - name: brain_sync
        description: "Synchroniser avec AVS KB"
        command: "python3 scripts/brain.py sync --direction {direction}"
      - name: email_check
        description: "Verifier les emails Gmail"
        command: "python3 scripts/brain_email.py check --unread-only --limit {limit}"
      - name: email_send
        description: "Envoyer un email"
        command: "python3 scripts/brain_email.py send --to '{to}' --subject '{subject}' --body '{body}'"
      - name: calendar_today
        description: "Evenements du jour"
        command: "python3 scripts/brain_meetings.py today"
      - name: server_status
        description: "Etat des serveurs"
        command: "python3 scripts/brain_monitoring.py status"
---

# AVS Brain - Cerveau de Michel

## Outils disponibles

### 1. Memoire (brain.py)

```bash
scripts/brain.py remember --title "Titre" --content "Contenu" --type concept --importance 70
scripts/brain.py search "query" --limit 10
scripts/brain.py link --from mem_xxx --to mem_yyy --type related_to
scripts/brain.py forget mem_xxx --reason "Raison"
scripts/brain.py sync --direction both
scripts/brain.py stats
```

### 2. Emails Gmail (brain_email.py)

```bash
scripts/brain_email.py draft --to "email@example.com" --subject "Sujet" --body "Contenu"
scripts/brain_email.py send --to "email@example.com" --subject "Sujet" --body "Contenu"
scripts/brain_email.py reply EMAIL_ID --body "Reponse"
scripts/brain_email.py check --unread-only --limit 10
scripts/brain_email.py search "query" --limit 20
scripts/brain_email.py read EMAIL_ID
```

### 3. Transcription Audio (brain_voice.py)

```bash
scripts/brain_voice.py transcribe FICHIER_AUDIO
scripts/brain_voice.py transcribe-url "https://url/audio.mp3"
scripts/brain_voice.py summarize FICHIER_AUDIO
```

### 4. Analyse Images (brain_vision.py)

```bash
scripts/brain_vision.py analyze IMAGE_FILE
scripts/brain_vision.py ocr IMAGE_FILE
scripts/brain_vision.py describe IMAGE_FILE
```

### 5. Analyse PDF/Factures (brain_invoices.py)

```bash
scripts/brain_invoices.py analyze FICHIER_PDF
scripts/brain_invoices.py extract FICHIER_PDF --type invoice|contract|quote
scripts/brain_invoices.py grenke FICHIER_PDF
```

### 6. Calendrier (brain_meetings.py)

```bash
scripts/brain_meetings.py today
scripts/brain_meetings.py upcoming --days 7
scripts/brain_meetings.py past --days 7
```

### 7. Monitoring Serveurs (brain_monitoring.py)

```bash
scripts/brain_monitoring.py check web-server-avs
scripts/brain_monitoring.py check-all
scripts/brain_monitoring.py status
```

### 8. Rapports (brain_reports.py)

```bash
scripts/brain_reports.py weekly
scripts/brain_reports.py monthly
scripts/brain_reports.py activity --days 7
```

### 9. Recherche Web (brain_web.py)

```bash
scripts/brain_web.py search "query" --limit 5
scripts/brain_web.py fetch "https://url" --extract text|links|all
```

## Configuration

Variables dans ~/.config/michel/env:

- BRAIN_DB_PATH=/home/michel/michel-avs/skills/avs-brain/data/brain.db
- AVS_INTRANET_URL=https://intra.avstech.fr
- AVS_INTRANET_API_KEY=avs_xxx
- GEMINI_API_KEY=xxx
- ANTHROPIC_API_KEY=xxx
