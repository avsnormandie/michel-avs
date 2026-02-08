#!/usr/bin/env python3
"""
Brain Dashboard - Statistics and monitoring for Michel's brain

Usage:
    brain_dashboard.py stats           # Full statistics
    brain_dashboard.py health          # Health check
    brain_dashboard.py logs [--lines N] [--level LEVEL]
    brain_dashboard.py activity [--days N]
    brain_dashboard.py export [--format json|md]

Provides monitoring and statistics for Michel's brain.
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Paths
LOG_DIR = Path(os.environ.get('MICHEL_LOG_DIR', os.path.expanduser('~/michel-avs/logs')))
DB_PATH = Path(os.environ.get('BRAIN_DB_PATH', os.path.expanduser('~/michel-avs/skills/avs-brain/brain.db')))
BACKUP_DIR = Path(os.environ.get('BRAIN_BACKUP_DIR', os.path.expanduser('~/michel-avs/backups')))

LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'brain_dashboard.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('brain_dashboard')


def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def cmd_stats(args):
    """Get full brain statistics"""
    conn = get_db()
    cursor = conn.cursor()

    stats = {
        'timestamp': datetime.now().isoformat(),
        'database': {},
        'memories': {},
        'sync': {},
        'storage': {}
    }

    # Database info
    stats['database']['path'] = str(DB_PATH)
    stats['database']['size_kb'] = DB_PATH.stat().st_size // 1024 if DB_PATH.exists() else 0

    # Memory counts by type
    cursor.execute("""
        SELECT type, COUNT(*) as count
        FROM memories
        WHERE consolidated_into IS NULL
        GROUP BY type
    """)
    stats['memories']['by_type'] = {row['type']: row['count'] for row in cursor.fetchall()}

    # Total active memories
    cursor.execute("SELECT COUNT(*) FROM memories WHERE consolidated_into IS NULL")
    stats['memories']['total'] = cursor.fetchone()[0]

    # Consolidated memories
    cursor.execute("SELECT COUNT(*) FROM memories WHERE consolidated_into IS NOT NULL")
    stats['memories']['consolidated'] = cursor.fetchone()[0]

    # Average importance
    cursor.execute("SELECT AVG(importance) FROM memories WHERE consolidated_into IS NULL")
    avg_imp = cursor.fetchone()[0]
    stats['memories']['avg_importance'] = round(avg_imp, 1) if avg_imp else 0

    # Memories by importance range
    cursor.execute("""
        SELECT
            CASE
                WHEN importance >= 70 THEN 'high (sync)'
                WHEN importance >= 40 THEN 'medium'
                ELSE 'low'
            END as range,
            COUNT(*) as count
        FROM memories
        WHERE consolidated_into IS NULL
        GROUP BY range
    """)
    stats['memories']['by_importance'] = {row['range']: row['count'] for row in cursor.fetchall()}

    # Link stats
    cursor.execute("SELECT COUNT(*) FROM links")
    stats['memories']['links'] = cursor.fetchone()[0]

    # Embedding coverage
    cursor.execute("SELECT COUNT(*) FROM embeddings")
    embeddings_count = cursor.fetchone()[0]
    stats['memories']['embeddings'] = embeddings_count
    if stats['memories']['total'] > 0:
        stats['memories']['embedding_coverage'] = round(embeddings_count / stats['memories']['total'] * 100, 1)

    # Sync stats
    cursor.execute("SELECT COUNT(*) FROM memories WHERE synced_at IS NOT NULL")
    stats['sync']['synced'] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM memories WHERE synced_at IS NULL AND importance >= 70")
    stats['sync']['pending'] = cursor.fetchone()[0]

    cursor.execute("SELECT MAX(synced_at) FROM memories")
    last_sync = cursor.fetchone()[0]
    stats['sync']['last_sync'] = last_sync

    # Recent activity (last 7 days)
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    cursor.execute("SELECT COUNT(*) FROM memories WHERE created_at > ?", (week_ago,))
    stats['memories']['created_last_week'] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM memories WHERE accessed_at > ?", (week_ago,))
    stats['memories']['accessed_last_week'] = cursor.fetchone()[0]

    # Storage
    stats['storage']['db_size_kb'] = stats['database']['size_kb']

    # Backup info
    if BACKUP_DIR.exists():
        backups = list(BACKUP_DIR.glob('brain_*.db'))
        stats['storage']['backups'] = len(backups)
        if backups:
            latest = max(backups, key=lambda p: p.stat().st_mtime)
            stats['storage']['last_backup'] = datetime.fromtimestamp(latest.stat().st_mtime).isoformat()
            stats['storage']['backup_size_kb'] = sum(b.stat().st_size for b in backups) // 1024

    conn.close()

    print(json.dumps(stats, indent=2, ensure_ascii=False))
    return 0


def cmd_health(args):
    """Health check"""
    health = {
        'timestamp': datetime.now().isoformat(),
        'status': 'healthy',
        'checks': {}
    }

    # Database check
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM memories")
        count = cursor.fetchone()[0]
        health['checks']['database'] = {'status': 'ok', 'memories': count}
        conn.close()
    except Exception as e:
        health['checks']['database'] = {'status': 'error', 'error': str(e)}
        health['status'] = 'unhealthy'

    # Log directory check
    if LOG_DIR.exists() and LOG_DIR.is_dir():
        health['checks']['logs'] = {'status': 'ok', 'path': str(LOG_DIR)}
    else:
        health['checks']['logs'] = {'status': 'warning', 'message': 'Log directory missing'}

    # Backup check
    if BACKUP_DIR.exists():
        backups = list(BACKUP_DIR.glob('brain_*.db'))
        if backups:
            latest = max(backups, key=lambda p: p.stat().st_mtime)
            age_hours = (datetime.now() - datetime.fromtimestamp(latest.stat().st_mtime)).total_seconds() / 3600
            if age_hours > 48:
                health['checks']['backup'] = {'status': 'warning', 'message': f'Last backup {age_hours:.0f}h ago'}
            else:
                health['checks']['backup'] = {'status': 'ok', 'last': latest.name}
        else:
            health['checks']['backup'] = {'status': 'warning', 'message': 'No backups found'}
    else:
        health['checks']['backup'] = {'status': 'warning', 'message': 'Backup directory missing'}

    # Pending sync check
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM memories WHERE synced_at IS NULL AND importance >= 70")
        pending = cursor.fetchone()[0]
        if pending > 10:
            health['checks']['sync'] = {'status': 'warning', 'pending': pending}
        else:
            health['checks']['sync'] = {'status': 'ok', 'pending': pending}
        conn.close()
    except:
        pass

    # Overall status
    if any(c.get('status') == 'error' for c in health['checks'].values()):
        health['status'] = 'unhealthy'
    elif any(c.get('status') == 'warning' for c in health['checks'].values()):
        health['status'] = 'degraded'

    print(json.dumps(health, indent=2))
    return 0 if health['status'] == 'healthy' else 1


def cmd_logs(args):
    """View recent logs"""
    log_files = [
        'brain.log',
        'brain_maintenance.log',
        'brain_cron.log',
        'brain_entities.log',
        'brain_web.log'
    ]

    lines = []

    for log_file in log_files:
        log_path = LOG_DIR / log_file
        if log_path.exists():
            try:
                with open(log_path, 'r') as f:
                    file_lines = f.readlines()
                    # Filter by level if specified
                    if args.level:
                        file_lines = [l for l in file_lines if args.level.upper() in l]
                    lines.extend(file_lines[-args.lines:])
            except Exception as e:
                logger.error(f"Failed to read {log_file}: {e}")

    # Sort by timestamp and take last N
    lines.sort()
    lines = lines[-args.lines:]

    output = {
        'success': True,
        'lines': len(lines),
        'logs': [l.strip() for l in lines]
    }

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


def cmd_activity(args):
    """Show activity over time"""
    conn = get_db()
    cursor = conn.cursor()

    days = args.days
    activity = {
        'period_days': days,
        'daily': []
    }

    for i in range(days, -1, -1):
        date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        next_date = (datetime.now() - timedelta(days=i-1)).strftime('%Y-%m-%d')

        cursor.execute("""
            SELECT COUNT(*) FROM memories
            WHERE created_at >= ? AND created_at < ?
        """, (date, next_date))
        created = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) FROM memories
            WHERE accessed_at >= ? AND accessed_at < ?
        """, (date, next_date))
        accessed = cursor.fetchone()[0]

        activity['daily'].append({
            'date': date,
            'created': created,
            'accessed': accessed
        })

    # Totals
    cursor.execute(f"""
        SELECT COUNT(*) FROM memories
        WHERE created_at >= date('now', '-{days} days')
    """)
    activity['total_created'] = cursor.fetchone()[0]

    cursor.execute(f"""
        SELECT COUNT(*) FROM memories
        WHERE accessed_at >= date('now', '-{days} days')
    """)
    activity['total_accessed'] = cursor.fetchone()[0]

    conn.close()

    print(json.dumps(activity, indent=2))
    return 0


def cmd_export(args):
    """Export brain data"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, type, title, content, importance, tags, created_at, synced_at
        FROM memories
        WHERE consolidated_into IS NULL
        ORDER BY importance DESC, created_at DESC
    """)

    memories = []
    for row in cursor.fetchall():
        memories.append({
            'id': row['id'],
            'type': row['type'],
            'title': row['title'],
            'content': row['content'],
            'importance': row['importance'],
            'tags': json.loads(row['tags']) if row['tags'] else [],
            'created_at': row['created_at'],
            'synced': row['synced_at'] is not None
        })

    conn.close()

    if args.format == 'md':
        # Markdown export
        lines = ["# Michel Brain Export", f"*{datetime.now().isoformat()}*", "", f"**{len(memories)} memories**", ""]

        # Group by type
        by_type = {}
        for mem in memories:
            t = mem['type']
            if t not in by_type:
                by_type[t] = []
            by_type[t].append(mem)

        for mem_type, mems in sorted(by_type.items()):
            lines.append(f"## {mem_type.title()} ({len(mems)})")
            lines.append("")
            for mem in mems[:20]:  # Limit per type
                synced = " [synced]" if mem['synced'] else ""
                lines.append(f"### {mem['title']}{synced}")
                lines.append(f"*Importance: {mem['importance']}*")
                lines.append("")
                lines.append(mem['content'][:500])
                lines.append("")

        print('\n'.join(lines))
    else:
        # JSON export
        print(json.dumps({
            'exported_at': datetime.now().isoformat(),
            'count': len(memories),
            'memories': memories
        }, indent=2, ensure_ascii=False))

    return 0


def main():
    parser = argparse.ArgumentParser(description='Brain Dashboard')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    subparsers.add_parser('stats', help='Full statistics')
    subparsers.add_parser('health', help='Health check')

    p_logs = subparsers.add_parser('logs', help='View logs')
    p_logs.add_argument('--lines', type=int, default=50, help='Number of lines')
    p_logs.add_argument('--level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], help='Filter by level')

    p_activity = subparsers.add_parser('activity', help='Activity report')
    p_activity.add_argument('--days', type=int, default=7, help='Number of days')

    p_export = subparsers.add_parser('export', help='Export brain')
    p_export.add_argument('--format', choices=['json', 'md'], default='json', help='Export format')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    commands = {
        'stats': cmd_stats,
        'health': cmd_health,
        'logs': cmd_logs,
        'activity': cmd_activity,
        'export': cmd_export
    }

    return commands[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
