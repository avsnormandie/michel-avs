#!/usr/bin/env python3
"""
Brain Cron - Scheduled tasks for Michel

Usage:
    brain_cron.py sync              # Sync with AVS KB
    brain_cron.py maintenance       # Run maintenance tasks
    brain_cron.py check-emails      # Check for urgent emails
    brain_cron.py check-calendar    # Check upcoming events
    brain_cron.py check-tickets     # Check assigned tickets
    brain_cron.py heartbeat         # Full heartbeat (all checks)
    brain_cron.py backup            # Backup brain database

Designed to be run via systemd timer or cron.
"""

import argparse
import json
import logging
import os
import shutil
import sqlite3
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path

# Setup logging
LOG_DIR = Path(os.environ.get('MICHEL_LOG_DIR', os.path.expanduser('~/michel-avs/logs')))
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'brain_cron.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('brain_cron')

# Configuration
DB_PATH = Path(os.environ.get('BRAIN_DB_PATH', os.path.expanduser('~/michel-avs/skills/avs-brain/brain.db')))
BACKUP_DIR = Path(os.environ.get('BRAIN_BACKUP_DIR', os.path.expanduser('~/michel-avs/backups')))
AVS_INTRANET_URL = os.environ.get('AVS_INTRANET_URL', 'https://intra.avstech.fr')
AVS_API_KEY = os.environ.get('AVS_API_KEY', '')
TELEGRAM_ENABLED = os.environ.get('TELEGRAM_ENABLED', 'true').lower() == 'true'


def api_request(endpoint, method='GET', data=None):
    """Make API request to AVS Intranet"""
    if not AVS_API_KEY:
        return {'success': False, 'error': 'AVS_API_KEY not configured'}

    url = f"{AVS_INTRANET_URL}/api/external/{endpoint}"

    headers = {
        'Content-Type': 'application/json; charset=utf-8',
        'X-API-Key': AVS_API_KEY
    }

    req_data = json.dumps(data).encode('utf-8') if data else None

    try:
        req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else ''
        try:
            return json.loads(error_body)
        except:
            return {'success': False, 'error': str(e)}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def send_notification(message, priority='normal'):
    """Send notification via Telegram (if enabled)"""
    if not TELEGRAM_ENABLED:
        logger.info(f"[Notification] {message}")
        return

    try:
        result = api_request('michel', method='POST', data={
            'message': message,
            'priority': priority
        })
        logger.info(f"Notification sent: {message[:50]}...")
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")


def cmd_sync(args):
    """Sync with AVS Knowledge Base"""
    logger.info("Starting AVS KB sync...")

    # Import brain.py sync function
    scripts_dir = Path(__file__).parent
    sys.path.insert(0, str(scripts_dir))

    try:
        from brain import cmd_sync as brain_sync
        # Create args object
        class SyncArgs:
            direction = 'both'
            force = False

        result = brain_sync(SyncArgs())
        logger.info("AVS KB sync completed")
        return result
    except Exception as e:
        logger.error(f"Sync failed: {e}")
        return 1


def cmd_maintenance(args):
    """Run maintenance tasks"""
    logger.info("Starting maintenance tasks...")

    scripts_dir = Path(__file__).parent

    try:
        from brain_maintenance import cmd_full
        class MaintenanceArgs:
            dry_run = False

        result = cmd_full(MaintenanceArgs())
        logger.info("Maintenance completed")
        return result
    except Exception as e:
        logger.error(f"Maintenance failed: {e}")
        return 1


def cmd_check_emails(args):
    """Check for urgent emails"""
    logger.info("Checking emails...")

    result = api_request('gmail/unread?label=IMPORTANT&limit=5')

    if not result.get('success', True):
        logger.error(f"Failed to check emails: {result.get('error')}")
        return 1

    emails = result.get('emails', [])
    urgent = [e for e in emails if e.get('priority') == 'high' or 'urgent' in e.get('subject', '').lower()]

    if urgent:
        subjects = [e.get('subject', 'Sans sujet')[:50] for e in urgent[:3]]
        send_notification(
            f"📧 {len(urgent)} email(s) urgent(s):\n" + "\n".join(f"• {s}" for s in subjects),
            priority='high'
        )

    output = {
        'success': True,
        'total_unread': len(emails),
        'urgent': len(urgent)
    }
    print(json.dumps(output, indent=2))
    return 0


def cmd_check_calendar(args):
    """Check upcoming calendar events"""
    logger.info("Checking calendar...")

    # Get events for next 24 hours
    result = api_request('calendar/events?hours=24')

    if not result.get('success', True):
        logger.error(f"Failed to check calendar: {result.get('error')}")
        return 1

    events = result.get('events', [])

    # Find events in next 2 hours
    now = datetime.now()
    soon = []
    for event in events:
        try:
            start = datetime.fromisoformat(event.get('start', '').replace('Z', '+00:00'))
            if start.tzinfo:
                start = start.replace(tzinfo=None)
            if now < start < now + timedelta(hours=2):
                soon.append(event)
        except:
            pass

    if soon:
        event_list = [f"• {e.get('title', 'Event')} ({e.get('start', '')[:16]})" for e in soon[:3]]
        send_notification(
            f"📅 {len(soon)} evenement(s) dans les 2h:\n" + "\n".join(event_list),
            priority='normal'
        )

    output = {
        'success': True,
        'events_24h': len(events),
        'events_soon': len(soon)
    }
    print(json.dumps(output, indent=2))
    return 0


def cmd_check_tickets(args):
    """Check assigned tickets"""
    logger.info("Checking tickets...")

    result = api_request('tickets?status=open&assignedToMe=true&limit=10')

    if not result.get('success', True):
        logger.error(f"Failed to check tickets: {result.get('error')}")
        return 1

    tickets = result.get('tickets', [])

    # Filter urgent/high priority
    urgent = [t for t in tickets if t.get('priority') in ['urgent', 'high']]

    if urgent:
        ticket_list = [f"• [{t.get('priority', '?').upper()}] {t.get('title', 'Ticket')[:40]}" for t in urgent[:3]]
        send_notification(
            f"🎫 {len(urgent)} ticket(s) urgent(s):\n" + "\n".join(ticket_list),
            priority='high'
        )

    output = {
        'success': True,
        'open_tickets': len(tickets),
        'urgent_tickets': len(urgent)
    }
    print(json.dumps(output, indent=2))
    return 0


def cmd_heartbeat(args):
    """Full heartbeat - run all checks"""
    logger.info("Running full heartbeat...")

    results = {
        'timestamp': datetime.now().isoformat(),
        'checks': {}
    }

    # Check emails (silently, only notify if urgent)
    try:
        email_result = api_request('gmail/unread?label=IMPORTANT&limit=5')
        results['checks']['emails'] = {
            'status': 'ok',
            'unread': len(email_result.get('emails', []))
        }
    except Exception as e:
        results['checks']['emails'] = {'status': 'error', 'error': str(e)}

    # Check calendar
    try:
        cal_result = api_request('calendar/events?hours=24')
        results['checks']['calendar'] = {
            'status': 'ok',
            'events': len(cal_result.get('events', []))
        }
    except Exception as e:
        results['checks']['calendar'] = {'status': 'error', 'error': str(e)}

    # Check tickets
    try:
        ticket_result = api_request('tickets?status=open&assignedToMe=true')
        results['checks']['tickets'] = {
            'status': 'ok',
            'open': len(ticket_result.get('tickets', []))
        }
    except Exception as e:
        results['checks']['tickets'] = {'status': 'error', 'error': str(e)}

    # Check brain stats
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM memories WHERE consolidated_into IS NULL")
        memory_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM memories WHERE synced_at IS NULL AND importance >= 70")
        pending_sync = cursor.fetchone()[0]
        conn.close()

        results['checks']['brain'] = {
            'status': 'ok',
            'memories': memory_count,
            'pending_sync': pending_sync
        }
    except Exception as e:
        results['checks']['brain'] = {'status': 'error', 'error': str(e)}

    # Save heartbeat result
    heartbeat_file = LOG_DIR / 'last_heartbeat.json'
    with open(heartbeat_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(json.dumps(results, indent=2))
    logger.info("Heartbeat complete")
    return 0


def cmd_backup(args):
    """Backup brain database"""
    logger.info("Starting backup...")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    # Create timestamped backup
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f"brain_{timestamp}.db"
    backup_path = BACKUP_DIR / backup_name

    try:
        shutil.copy2(DB_PATH, backup_path)
        logger.info(f"Backup created: {backup_path}")

        # Clean old backups (keep last 7)
        backups = sorted(BACKUP_DIR.glob('brain_*.db'), reverse=True)
        for old_backup in backups[7:]:
            old_backup.unlink()
            logger.info(f"Deleted old backup: {old_backup}")

        # Get backup size
        size_kb = backup_path.stat().st_size // 1024

        output = {
            'success': True,
            'backup_path': str(backup_path),
            'size_kb': size_kb,
            'backups_kept': min(len(backups), 7)
        }
        print(json.dumps(output, indent=2))
        return 0

    except Exception as e:
        logger.error(f"Backup failed: {e}")
        print(json.dumps({'success': False, 'error': str(e)}))
        return 1


def main():
    parser = argparse.ArgumentParser(description='Brain Cron - Scheduled Tasks')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    subparsers.add_parser('sync', help='Sync with AVS KB')
    subparsers.add_parser('maintenance', help='Run maintenance tasks')
    subparsers.add_parser('check-emails', help='Check for urgent emails')
    subparsers.add_parser('check-calendar', help='Check upcoming events')
    subparsers.add_parser('check-tickets', help='Check assigned tickets')
    subparsers.add_parser('heartbeat', help='Full heartbeat')
    subparsers.add_parser('backup', help='Backup brain database')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    commands = {
        'sync': cmd_sync,
        'maintenance': cmd_maintenance,
        'check-emails': cmd_check_emails,
        'check-calendar': cmd_check_calendar,
        'check-tickets': cmd_check_tickets,
        'heartbeat': cmd_heartbeat,
        'backup': cmd_backup
    }

    return commands[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
