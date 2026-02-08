#!/usr/bin/env python3
"""
Brain Reports - Automated weekly/monthly reports

Usage:
    brain_reports.py weekly [--send]
    brain_reports.py monthly [--send]
    brain_reports.py activity [--days N]
    brain_reports.py tickets [--days N]
    brain_reports.py projects

Generates automated activity reports.
"""

import argparse
import json
import logging
import os
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
        logging.FileHandler(LOG_DIR / 'brain_reports.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('brain_reports')

# Configuration
DB_PATH = Path(os.environ.get('BRAIN_DB_PATH', os.path.expanduser('~/michel-avs/skills/avs-brain/data/brain.db')))
AVS_INTRANET_URL = os.environ.get('AVS_INTRANET_URL', 'https://intra.avstech.fr')
AVS_API_KEY = os.environ.get('AVS_API_KEY', '')


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
    except Exception as e:
        return {'success': False, 'error': str(e)}


def get_brain_stats(days=7):
    """Get brain statistics for period"""
    if not DB_PATH.exists():
        return {}

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    stats = {}

    # New memories
    cursor.execute("SELECT COUNT(*) FROM memories WHERE created_at > ?", (cutoff,))
    stats['new_memories'] = cursor.fetchone()[0]

    # Synced memories
    cursor.execute("SELECT COUNT(*) FROM memories WHERE synced_at > ?", (cutoff,))
    stats['synced'] = cursor.fetchone()[0]

    # Total memories
    cursor.execute("SELECT COUNT(*) FROM memories WHERE consolidated_into IS NULL")
    stats['total_memories'] = cursor.fetchone()[0]

    # By type
    cursor.execute("""
        SELECT type, COUNT(*) FROM memories
        WHERE created_at > ? AND consolidated_into IS NULL
        GROUP BY type
    """, (cutoff,))
    stats['by_type'] = {row[0]: row[1] for row in cursor.fetchall()}

    conn.close()
    return stats


def get_ticket_stats(days=7):
    """Get ticket statistics"""
    result = api_request(f'tickets?limit=100')

    if not result.get('tickets'):
        return {}

    tickets = result.get('tickets', [])
    cutoff = datetime.now() - timedelta(days=days)

    stats = {
        'total': len(tickets),
        'open': 0,
        'closed': 0,
        'created_period': 0,
        'resolved_period': 0,
        'by_priority': {'urgent': 0, 'high': 0, 'medium': 0, 'low': 0}
    }

    for t in tickets:
        status = t.get('status', '')
        priority = t.get('priority', 'medium')

        if status in ['open', 'in_progress', 'waiting']:
            stats['open'] += 1
        else:
            stats['closed'] += 1

        if priority in stats['by_priority']:
            stats['by_priority'][priority] += 1

        # Check dates
        created = t.get('createdAt', '')
        if created:
            try:
                created_dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                if created_dt.replace(tzinfo=None) > cutoff:
                    stats['created_period'] += 1
            except:
                pass

        resolved = t.get('resolvedAt', '')
        if resolved:
            try:
                resolved_dt = datetime.fromisoformat(resolved.replace('Z', '+00:00'))
                if resolved_dt.replace(tzinfo=None) > cutoff:
                    stats['resolved_period'] += 1
            except:
                pass

    return stats


def get_project_stats():
    """Get project (sujet) statistics"""
    result = api_request('sujets?limit=50')

    if not result.get('sujets'):
        return {}

    sujets = result.get('sujets', [])

    stats = {
        'total': len(sujets),
        'active': 0,
        'completed': 0,
        'by_status': {}
    }

    for s in sujets:
        status = s.get('status', 'backlog')
        stats['by_status'][status] = stats['by_status'].get(status, 0) + 1

        if status == 'active':
            stats['active'] += 1
        elif status == 'completed':
            stats['completed'] += 1

    return stats


def generate_weekly_report(send=False):
    """Generate weekly activity report"""
    logger.info("Generating weekly report...")

    brain_stats = get_brain_stats(7)
    ticket_stats = get_ticket_stats(7)
    project_stats = get_project_stats()

    # Build markdown report
    now = datetime.now()
    week_start = now - timedelta(days=7)

    report = f"""# Rapport Hebdomadaire - Michel AVS

**Periode**: {week_start.strftime('%d/%m/%Y')} - {now.strftime('%d/%m/%Y')}
**Genere le**: {now.strftime('%d/%m/%Y %H:%M')}

---

## 🧠 Memoire

| Metrique | Valeur |
|----------|--------|
| Nouvelles memoires | {brain_stats.get('new_memories', 0)} |
| Memoires synchronisees | {brain_stats.get('synced', 0)} |
| Total memoires | {brain_stats.get('total_memories', 0)} |

### Par type
"""

    for mem_type, count in brain_stats.get('by_type', {}).items():
        report += f"- **{mem_type}**: {count}\n"

    report += f"""
---

## 🎫 Tickets

| Metrique | Valeur |
|----------|--------|
| Tickets crees | {ticket_stats.get('created_period', 0)} |
| Tickets resolus | {ticket_stats.get('resolved_period', 0)} |
| Tickets ouverts | {ticket_stats.get('open', 0)} |
| Total tickets | {ticket_stats.get('total', 0)} |

### Par priorite
- Urgent: {ticket_stats.get('by_priority', {}).get('urgent', 0)}
- High: {ticket_stats.get('by_priority', {}).get('high', 0)}
- Medium: {ticket_stats.get('by_priority', {}).get('medium', 0)}
- Low: {ticket_stats.get('by_priority', {}).get('low', 0)}

---

## 📋 Projets (Sujets)

| Metrique | Valeur |
|----------|--------|
| Projets actifs | {project_stats.get('active', 0)} |
| Projets termines | {project_stats.get('completed', 0)} |
| Total projets | {project_stats.get('total', 0)} |

### Par statut
"""

    for status, count in project_stats.get('by_status', {}).items():
        report += f"- **{status}**: {count}\n"

    report += """
---

*Rapport genere automatiquement par Michel*
"""

    output = {
        'success': True,
        'period': '7 days',
        'report': report,
        'stats': {
            'brain': brain_stats,
            'tickets': ticket_stats,
            'projects': project_stats
        }
    }

    if send:
        # Send via Telegram
        api_request('michel', method='POST', data={
            'message': f"📊 Rapport hebdomadaire disponible!\n\n• {brain_stats.get('new_memories', 0)} nouvelles memoires\n• {ticket_stats.get('created_period', 0)} tickets crees\n• {ticket_stats.get('resolved_period', 0)} tickets resolus",
            'priority': 'normal'
        })
        output['sent'] = True

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


def generate_monthly_report(send=False):
    """Generate monthly report"""
    logger.info("Generating monthly report...")

    brain_stats = get_brain_stats(30)
    ticket_stats = get_ticket_stats(30)
    project_stats = get_project_stats()

    output = {
        'success': True,
        'period': '30 days',
        'stats': {
            'brain': brain_stats,
            'tickets': ticket_stats,
            'projects': project_stats
        }
    }

    if send:
        api_request('michel', method='POST', data={
            'message': f"📊 Rapport mensuel!\n\nMemoires: {brain_stats.get('new_memories', 0)} nouvelles\nTickets: {ticket_stats.get('created_period', 0)} crees, {ticket_stats.get('resolved_period', 0)} resolus\nProjets actifs: {project_stats.get('active', 0)}",
            'priority': 'normal'
        })
        output['sent'] = True

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


def cmd_activity(args):
    """Activity report"""
    brain_stats = get_brain_stats(args.days)

    output = {
        'success': True,
        'days': args.days,
        'brain': brain_stats
    }

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


def cmd_tickets(args):
    """Ticket report"""
    ticket_stats = get_ticket_stats(args.days)

    output = {
        'success': True,
        'days': args.days,
        'tickets': ticket_stats
    }

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


def cmd_projects(args):
    """Project report"""
    project_stats = get_project_stats()

    output = {
        'success': True,
        'projects': project_stats
    }

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


def main():
    parser = argparse.ArgumentParser(description='Brain Reports - Automated Reports')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # weekly
    p_weekly = subparsers.add_parser('weekly', help='Weekly report')
    p_weekly.add_argument('--send', action='store_true', help='Send notification')

    # monthly
    p_monthly = subparsers.add_parser('monthly', help='Monthly report')
    p_monthly.add_argument('--send', action='store_true', help='Send notification')

    # activity
    p_activity = subparsers.add_parser('activity', help='Activity report')
    p_activity.add_argument('--days', type=int, default=7, help='Days to analyze')

    # tickets
    p_tickets = subparsers.add_parser('tickets', help='Ticket report')
    p_tickets.add_argument('--days', type=int, default=7, help='Days to analyze')

    # projects
    subparsers.add_parser('projects', help='Project report')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == 'weekly':
        return generate_weekly_report(args.send)
    elif args.command == 'monthly':
        return generate_monthly_report(args.send)
    elif args.command == 'activity':
        return cmd_activity(args)
    elif args.command == 'tickets':
        return cmd_tickets(args)
    elif args.command == 'projects':
        return cmd_projects(args)


if __name__ == '__main__':
    sys.exit(main())
