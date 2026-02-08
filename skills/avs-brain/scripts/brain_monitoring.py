#!/usr/bin/env python3
"""
Brain Monitoring - Server health monitoring and alerts

Usage:
    brain_monitoring.py check SERVER [--alert]
    brain_monitoring.py check-all [--alert]
    brain_monitoring.py status
    brain_monitoring.py add SERVER --host HOST [--port PORT] [--type ssh|http|ping]
    brain_monitoring.py remove SERVER

Monitors server health and sends alerts via Telegram.
"""

import argparse
import json
import logging
import os
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
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('brain_monitoring')

# Configuration
CONFIG_PATH = Path(os.environ.get('MICHEL_CONFIG_DIR', os.path.expanduser('~/michel-avs/config')))
SERVERS_FILE = CONFIG_PATH / 'servers.json'
AVS_INTRANET_URL = os.environ.get('AVS_INTRANET_URL', 'https://intra.avstech.fr')
AVS_API_KEY = os.environ.get('AVS_API_KEY', '')

# Default servers to monitor
DEFAULT_SERVERS = {
    'web-server-avs': {
        'host': '141.95.154.151',
        'port': 443,
        'type': 'https',
        'description': 'AVS Web Server'
    },
    'intranet': {
        'host': 'intra.avstech.fr',
        'port': 443,
        'type': 'https',
        'description': 'Intranet AVS'
    },
    'api-server': {
        'host': 'api.logics-cloud.fr',
        'port': 443,
        'type': 'https',
        'description': 'Logic\'s Cloud API'
    }
}


def load_servers():
    """Load server configuration"""
    CONFIG_PATH.mkdir(parents=True, exist_ok=True)

    if SERVERS_FILE.exists():
        with open(SERVERS_FILE, 'r') as f:
            return json.load(f)

    # Initialize with defaults
    save_servers(DEFAULT_SERVERS)
    return DEFAULT_SERVERS


def save_servers(servers):
    """Save server configuration"""
    CONFIG_PATH.mkdir(parents=True, exist_ok=True)
    with open(SERVERS_FILE, 'w') as f:
        json.dump(servers, f, indent=2)


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


def send_alert(message, priority='high'):
    """Send alert via Telegram"""
    logger.warning(f"ALERT: {message}")
    api_request('michel', method='POST', data={
        'message': f"🚨 ALERTE SERVEUR\n\n{message}",
        'priority': priority
    })


def check_ping(host):
    """Check if host responds to ping"""
    try:
        # Use socket for cross-platform
        socket.setdefaulttimeout(5)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, 80))
        return True
    except:
        return False


def check_port(host, port):
    """Check if port is open"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception as e:
        logger.error(f"Port check error: {e}")
        return False


def check_http(host, port=443, https=True):
    """Check HTTP(S) response"""
    protocol = 'https' if https else 'http'
    url = f"{protocol}://{host}"

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Michel-Monitor/1.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status == 200
    except urllib.error.HTTPError as e:
        # Some errors are OK (401, 403)
        return e.code in [200, 401, 403, 301, 302]
    except Exception as e:
        logger.error(f"HTTP check error: {e}")
        return False


def check_server(name, config, send_alert_on_fail=False):
    """Check a single server"""
    host = config.get('host')
    port = config.get('port', 443)
    check_type = config.get('type', 'https')

    logger.info(f"Checking {name} ({host}:{port})...")

    result = {
        'name': name,
        'host': host,
        'port': port,
        'type': check_type,
        'timestamp': datetime.now().isoformat(),
        'status': 'unknown',
        'response_time': None
    }

    start = datetime.now()

    if check_type == 'ping':
        success = check_ping(host)
    elif check_type == 'http':
        success = check_http(host, port, https=False)
    elif check_type == 'https':
        success = check_http(host, port, https=True)
    else:  # ssh or port
        success = check_port(host, port)

    end = datetime.now()
    result['response_time'] = (end - start).total_seconds() * 1000  # ms

    if success:
        result['status'] = 'up'
        logger.info(f"{name}: UP ({result['response_time']:.0f}ms)")
    else:
        result['status'] = 'down'
        logger.error(f"{name}: DOWN")
        if send_alert_on_fail:
            send_alert(f"❌ {name} ({host}) est DOWN!\nType: {check_type}\nPort: {port}")

    return result


def cmd_check(args):
    """Check a specific server"""
    servers = load_servers()

    if args.server not in servers:
        print(json.dumps({'success': False, 'error': f'Server not found: {args.server}'}))
        return 1

    result = check_server(args.server, servers[args.server], args.alert)

    output = {
        'success': True,
        'check': result
    }

    print(json.dumps(output, indent=2))
    return 0 if result['status'] == 'up' else 1


def cmd_check_all(args):
    """Check all servers"""
    servers = load_servers()
    results = []
    all_up = True

    for name, config in servers.items():
        result = check_server(name, config, args.alert)
        results.append(result)
        if result['status'] != 'up':
            all_up = False

    output = {
        'success': True,
        'timestamp': datetime.now().isoformat(),
        'all_up': all_up,
        'total': len(results),
        'up': sum(1 for r in results if r['status'] == 'up'),
        'down': sum(1 for r in results if r['status'] == 'down'),
        'checks': results
    }

    print(json.dumps(output, indent=2))
    return 0 if all_up else 1


def cmd_status(args):
    """Show monitoring status"""
    servers = load_servers()

    output = {
        'success': True,
        'config_file': str(SERVERS_FILE),
        'servers': len(servers),
        'monitored': list(servers.keys())
    }

    print(json.dumps(output, indent=2))
    return 0


def cmd_add(args):
    """Add a server to monitor"""
    servers = load_servers()

    servers[args.server] = {
        'host': args.host,
        'port': args.port or 443,
        'type': args.type or 'https',
        'description': args.server
    }

    save_servers(servers)

    output = {
        'success': True,
        'message': f'Server {args.server} added',
        'server': servers[args.server]
    }

    print(json.dumps(output, indent=2))
    return 0


def cmd_remove(args):
    """Remove a server from monitoring"""
    servers = load_servers()

    if args.server not in servers:
        print(json.dumps({'success': False, 'error': f'Server not found: {args.server}'}))
        return 1

    del servers[args.server]
    save_servers(servers)

    output = {
        'success': True,
        'message': f'Server {args.server} removed'
    }

    print(json.dumps(output, indent=2))
    return 0


def main():
    parser = argparse.ArgumentParser(description='Brain Monitoring - Server Health')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # check
    p_check = subparsers.add_parser('check', help='Check a server')
    p_check.add_argument('server', help='Server name')
    p_check.add_argument('--alert', action='store_true', help='Send alert if down')

    # check-all
    p_all = subparsers.add_parser('check-all', help='Check all servers')
    p_all.add_argument('--alert', action='store_true', help='Send alerts if down')

    # status
    subparsers.add_parser('status', help='Show monitoring status')

    # add
    p_add = subparsers.add_parser('add', help='Add server to monitor')
    p_add.add_argument('server', help='Server name')
    p_add.add_argument('--host', required=True, help='Host/IP')
    p_add.add_argument('--port', type=int, help='Port')
    p_add.add_argument('--type', choices=['ssh', 'http', 'https', 'ping'], help='Check type')

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
        'add': cmd_add,
        'remove': cmd_remove
    }

    return commands[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
