#!/usr/bin/env python3
"""
Brain Monitoring - Server health monitoring and alerts

Usage:
    brain_monitoring.py check SERVER [--alert]
    brain_monitoring.py check-all [--alert]
    brain_monitoring.py status
    brain_monitoring.py report [--send]
    brain_monitoring.py add SERVER --host HOST [--port PORT] [--type ssh|http|https|ping|port]
    brain_monitoring.py remove SERVER

Monitors server health and sends alerts via Telegram.
"""

import argparse
import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

# Setup logging
LOG_DIR = Path(os.environ.get('MICHEL_LOG_DIR', os.path.expanduser('~/michel-avs/logs')))
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'brain_monitoring.log'),
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger('brain_monitoring')

# Configuration
CONFIG_DIR = Path(os.environ.get('MICHEL_CONFIG_DIR', os.path.expanduser('~/michel-avs/config')))
SERVERS_FILE = CONFIG_DIR / 'servers.json'
HISTORY_FILE = LOG_DIR / 'monitoring_history.jsonl'
LAST_STATE_FILE = CONFIG_DIR / 'monitoring_last_state.json'
AVS_INTRANET_URL = os.environ.get('AVS_INTRANET_URL', 'https://intra.avstech.fr')
AVS_API_KEY = os.environ.get('AVS_API_KEY', '')

# Default servers to monitor
DEFAULT_SERVERS = {
    'web-server-avs': {
        'host': '141.95.154.151',
        'port': 443,
        'type': 'https',
        'url': 'https://intra.avstech.fr',
        'description': 'Intranet AVS + sites web'
    },
    'logics-db-server': {
        'host': '54.38.46.25',
        'port': 22,
        'type': 'port',
        'description': 'HFSQL + PostgreSQL'
    },
    'logics-save-server': {
        'host': '51.255.65.118',
        'port': 2111,
        'type': 'port',
        'description': 'Backup RAID 10'
    },
    'api-server': {
        'host': '51.178.18.80',
        'port': 443,
        'type': 'https',
        'url': 'https://api.logics-cloud.fr',
        'description': "Logic's Cloud API (Directus)"
    },
    'n8n': {
        'host': 'n8n.avstech.fr',
        'port': 443,
        'type': 'https',
        'url': 'https://n8n.avstech.fr',
        'description': 'Automatisation n8n'
    }
}

# Local systemd services to check
LOCAL_SERVICES = ['michel-avs', 'rclone-gdrive']
SYSTEM_SERVICES = ['ssh-tunnel']


def load_servers():
    """Load server configuration"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if SERVERS_FILE.exists():
        with open(SERVERS_FILE, 'r') as f:
            return json.load(f)
    save_servers(DEFAULT_SERVERS)
    return DEFAULT_SERVERS.copy()


def save_servers(servers):
    """Save server configuration"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(SERVERS_FILE, 'w') as f:
        json.dump(servers, f, indent=2, ensure_ascii=False)


def load_last_state():
    """Load last known state of each server"""
    if LAST_STATE_FILE.exists():
        with open(LAST_STATE_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_last_state(state):
    """Save current state for change detection"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LAST_STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def append_history(entry):
    """Append a check result to history"""
    with open(HISTORY_FILE, 'a') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')


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


def send_alert(message):
    """Send alert via Telegram"""
    logger.warning(f"ALERT: {message}")
    api_request('michel', method='POST', data={
        'message': message,
        'from': 'Monitoring'
    })


# --- Check functions ---

def check_port(host, port, timeout=5):
    """Check if a TCP port is open"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def check_http(url, timeout=10):
    """Check HTTP(S) URL responds"""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Michel-Monitor/1.0'})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status < 500
    except urllib.error.HTTPError as e:
        return e.code < 500
    except Exception:
        return False


def check_ping(host, timeout=5):
    """Check if host responds to ICMP ping"""
    try:
        result = subprocess.run(
            ['ping', '-c', '1', '-W', str(timeout), host],
            capture_output=True, timeout=timeout + 2
        )
        return result.returncode == 0
    except Exception:
        return False


def check_systemd_service(name, user=True):
    """Check if a systemd service is active"""
    try:
        cmd = ['systemctl']
        if user:
            cmd.append('--user')
        cmd.extend(['is-active', f'{name}.service'])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return result.stdout.strip() == 'active'
    except Exception:
        return False


def get_local_resources():
    """Get GK41 disk, RAM, CPU info"""
    resources = {}

    # Disk usage (root partition)
    try:
        total, used, free = shutil.disk_usage('/')
        resources['disk'] = {
            'total_gb': round(total / (1024**3), 1),
            'used_gb': round(used / (1024**3), 1),
            'free_gb': round(free / (1024**3), 1),
            'percent': round(used / total * 100, 1)
        }
    except Exception:
        resources['disk'] = {'error': 'unavailable'}

    # RAM
    try:
        with open('/proc/meminfo', 'r') as f:
            meminfo = {}
            for line in f:
                parts = line.split(':')
                if len(parts) == 2:
                    key = parts[0].strip()
                    val = int(parts[1].strip().split()[0])  # kB
                    meminfo[key] = val
            total = meminfo.get('MemTotal', 0)
            available = meminfo.get('MemAvailable', 0)
            used = total - available
            resources['ram'] = {
                'total_mb': round(total / 1024),
                'used_mb': round(used / 1024),
                'available_mb': round(available / 1024),
                'percent': round(used / total * 100, 1) if total > 0 else 0
            }
    except Exception:
        resources['ram'] = {'error': 'unavailable'}

    # Load average
    try:
        with open('/proc/loadavg', 'r') as f:
            parts = f.read().strip().split()
            resources['load'] = {
                '1min': float(parts[0]),
                '5min': float(parts[1]),
                '15min': float(parts[2])
            }
    except Exception:
        resources['load'] = {'error': 'unavailable'}

    return resources


# --- Server check ---

def check_server(name, config):
    """Check a single server, return result dict"""
    host = config.get('host', '')
    port = config.get('port', 443)
    check_type = config.get('type', 'https')
    url = config.get('url', '')

    start = datetime.now()

    if check_type in ('http', 'https'):
        target_url = url or f"{'https' if check_type == 'https' else 'http'}://{host}"
        success = check_http(target_url)
    elif check_type == 'ping':
        success = check_ping(host)
    else:  # port, ssh
        success = check_port(host, port)

    elapsed_ms = round((datetime.now() - start).total_seconds() * 1000)

    return {
        'name': name,
        'host': host,
        'port': port,
        'type': check_type,
        'status': 'up' if success else 'down',
        'response_ms': elapsed_ms,
        'timestamp': datetime.now().isoformat()
    }


# --- Commands ---

def cmd_check(args):
    """Check a specific server"""
    servers = load_servers()
    if args.server not in servers:
        print(json.dumps({'success': False, 'error': f'Server not found: {args.server}'}))
        return 1

    result = check_server(args.server, servers[args.server])

    if result['status'] == 'down' and args.alert:
        desc = servers[args.server].get('description', args.server)
        send_alert(f"❌ {args.server} DOWN\n{desc}\nHost: {result['host']}:{result['port']}")

    print(json.dumps({'success': True, 'check': result}, indent=2))
    return 0 if result['status'] == 'up' else 1


def cmd_check_all(args):
    """Check all servers + local services + resources"""
    servers = load_servers()
    last_state = load_last_state()
    new_state = {}

    # Check remote servers
    server_results = []
    for name, config in servers.items():
        result = check_server(name, config)
        server_results.append(result)
        new_state[name] = result['status']

    # Check local services
    service_results = []
    for svc in LOCAL_SERVICES:
        active = check_systemd_service(svc, user=True)
        service_results.append({'name': svc, 'status': 'active' if active else 'inactive', 'scope': 'user'})
        new_state[f'svc:{svc}'] = 'active' if active else 'inactive'

    for svc in SYSTEM_SERVICES:
        active = check_systemd_service(svc, user=False)
        service_results.append({'name': svc, 'status': 'active' if active else 'inactive', 'scope': 'system'})
        new_state[f'svc:{svc}'] = 'active' if active else 'inactive'

    # Local resources
    resources = get_local_resources()

    # Build output
    servers_up = sum(1 for r in server_results if r['status'] == 'up')
    servers_down = sum(1 for r in server_results if r['status'] == 'down')
    services_active = sum(1 for s in service_results if s['status'] == 'active')
    services_inactive = sum(1 for s in service_results if s['status'] != 'active')

    output = {
        'success': True,
        'timestamp': datetime.now().isoformat(),
        'servers': {
            'total': len(server_results),
            'up': servers_up,
            'down': servers_down,
            'checks': server_results
        },
        'services': {
            'total': len(service_results),
            'active': services_active,
            'inactive': services_inactive,
            'checks': service_results
        },
        'resources': resources
    }

    # Alerting: only when state changes (UP -> DOWN or active -> inactive)
    if args.alert:
        alerts = []
        for key, current in new_state.items():
            previous = last_state.get(key)
            if previous and previous in ('up', 'active') and current in ('down', 'inactive'):
                if key.startswith('svc:'):
                    alerts.append(f"🔴 Service {key[4:]} est INACTIF")
                else:
                    desc = servers.get(key, {}).get('description', key)
                    alerts.append(f"🔴 {key} DOWN ({desc})")

            # Also alert on recovery
            if previous and previous in ('down', 'inactive') and current in ('up', 'active'):
                if key.startswith('svc:'):
                    alerts.append(f"🟢 Service {key[4:]} est revenu")
                else:
                    alerts.append(f"🟢 {key} est revenu UP")

        if alerts:
            send_alert("🚨 Changement d'etat infra\n\n" + "\n".join(alerts))

        # Alert on high resource usage
        disk_pct = resources.get('disk', {}).get('percent', 0)
        ram_pct = resources.get('ram', {}).get('percent', 0)
        if disk_pct > 90:
            send_alert(f"💾 Disque GK41 a {disk_pct}% !")
        if ram_pct > 90:
            send_alert(f"🧠 RAM GK41 a {ram_pct}% !")

    # Save state and history
    save_last_state(new_state)
    append_history(output)

    print(json.dumps(output, indent=2))
    return 0 if servers_down == 0 and services_inactive == 0 else 1


def cmd_status(args):
    """Show monitoring configuration"""
    servers = load_servers()
    output = {
        'success': True,
        'config_file': str(SERVERS_FILE),
        'history_file': str(HISTORY_FILE),
        'servers': len(servers),
        'monitored_servers': list(servers.keys()),
        'local_services': LOCAL_SERVICES + SYSTEM_SERVICES
    }
    print(json.dumps(output, indent=2))
    return 0


def cmd_report(args):
    """Generate a human-readable monitoring report"""
    servers = load_servers()

    # Check all servers
    server_results = []
    for name, config in servers.items():
        result = check_server(name, config)
        server_results.append(result)

    # Check services
    service_results = []
    for svc in LOCAL_SERVICES:
        active = check_systemd_service(svc, user=True)
        service_results.append((svc, active))
    for svc in SYSTEM_SERVICES:
        active = check_systemd_service(svc, user=False)
        service_results.append((svc, active))

    # Resources
    resources = get_local_resources()

    # Build text report
    now = datetime.now().strftime('%d/%m/%Y %H:%M')
    lines = [f"📊 Rapport monitoring — {now}", ""]

    # Servers
    lines.append("🖥 Serveurs")
    all_up = True
    for r in server_results:
        icon = "✅" if r['status'] == 'up' else "❌"
        desc = servers.get(r['name'], {}).get('description', '')
        ms = f" ({r['response_ms']}ms)" if r['status'] == 'up' else ""
        lines.append(f"  {icon} {r['name']}{ms}")
        if desc:
            lines.append(f"      {desc}")
        if r['status'] != 'up':
            all_up = False
    lines.append("")

    # Services
    lines.append("⚙️ Services GK41")
    for name, active in service_results:
        icon = "✅" if active else "❌"
        lines.append(f"  {icon} {name}")
    lines.append("")

    # Resources
    lines.append("📈 Ressources GK41")
    disk = resources.get('disk', {})
    if 'percent' in disk:
        bar = _progress_bar(disk['percent'])
        lines.append(f"  💾 Disque: {bar} {disk['percent']}% ({disk['free_gb']} Go libre)")

    ram = resources.get('ram', {})
    if 'percent' in ram:
        bar = _progress_bar(ram['percent'])
        lines.append(f"  🧠 RAM: {bar} {ram['percent']}% ({ram['available_mb']} Mo dispo)")

    load = resources.get('load', {})
    if '1min' in load:
        lines.append(f"  ⚡ Load: {load['1min']} / {load['5min']} / {load['15min']}")

    report_text = "\n".join(lines)

    if args.send:
        send_alert(report_text)
        logger.info("Report sent to Telegram")

    print(report_text)
    return 0 if all_up else 1


def _progress_bar(percent, width=10):
    """Simple text progress bar"""
    filled = int(width * percent / 100)
    return "█" * filled + "░" * (width - filled)


def cmd_add(args):
    """Add a server to monitor"""
    servers = load_servers()
    servers[args.server] = {
        'host': args.host,
        'port': args.port or 443,
        'type': args.type or 'https',
        'description': args.description or args.server
    }
    save_servers(servers)
    print(json.dumps({'success': True, 'message': f'Server {args.server} added', 'server': servers[args.server]}, indent=2))
    return 0


def cmd_remove(args):
    """Remove a server from monitoring"""
    servers = load_servers()
    if args.server not in servers:
        print(json.dumps({'success': False, 'error': f'Server not found: {args.server}'}))
        return 1
    del servers[args.server]
    save_servers(servers)
    print(json.dumps({'success': True, 'message': f'Server {args.server} removed'}))
    return 0


def main():
    parser = argparse.ArgumentParser(description='Brain Monitoring - Server Health')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # check
    p_check = subparsers.add_parser('check', help='Check a server')
    p_check.add_argument('server', help='Server name')
    p_check.add_argument('--alert', action='store_true', help='Send alert if down')

    # check-all
    p_all = subparsers.add_parser('check-all', help='Check all servers + services + resources')
    p_all.add_argument('--alert', action='store_true', help='Send alerts on state changes')

    # status
    subparsers.add_parser('status', help='Show monitoring config')

    # report
    p_report = subparsers.add_parser('report', help='Generate human-readable report')
    p_report.add_argument('--send', action='store_true', help='Send report via Telegram')

    # add
    p_add = subparsers.add_parser('add', help='Add server to monitor')
    p_add.add_argument('server', help='Server name')
    p_add.add_argument('--host', required=True, help='Host/IP')
    p_add.add_argument('--port', type=int, help='Port (default: 443)')
    p_add.add_argument('--type', choices=['ssh', 'http', 'https', 'ping', 'port'], help='Check type')
    p_add.add_argument('--description', help='Server description')

    # remove
    p_remove = subparsers.add_parser('remove', help='Remove server')
    p_remove.add_argument('server', help='Server name')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    commands = {
        'check': cmd_check,
        'check-all': cmd_check_all,
        'status': cmd_status,
        'report': cmd_report,
        'add': cmd_add,
        'remove': cmd_remove
    }

    return commands[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
