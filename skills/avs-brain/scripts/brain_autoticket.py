#!/usr/bin/env python3
"""
Brain Auto-Ticket - Detect problems and suggest/create tickets

Usage:
    brain_autoticket.py analyze "texte a analyser"
    brain_autoticket.py create --title TITLE --description DESC [--priority PRIORITY] [--auto]
    brain_autoticket.py suggest "contexte de conversation"

Detects problems in conversations and can automatically create tickets.
"""

import argparse
import json
import logging
import os
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path

# Setup logging
LOG_DIR = Path(os.environ.get('MICHEL_LOG_DIR', os.path.expanduser('~/michel-avs/logs')))
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'brain_autoticket.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('brain_autoticket')

# Configuration
AVS_INTRANET_URL = os.environ.get('AVS_INTRANET_URL', 'https://intra.avstech.fr')
AVS_API_KEY = os.environ.get('AVS_API_KEY', '')

# Problem detection patterns
PROBLEM_PATTERNS = {
    'bug': {
        'keywords': ['bug', 'erreur', 'error', 'crash', 'plante', 'marche pas', 'fonctionne pas', 'ne marche plus', 'casse', 'broken'],
        'priority': 'high',
        'category': 'Bug'
    },
    'urgent': {
        'keywords': ['urgent', 'critique', 'critical', 'bloque', 'blocking', 'production', 'client bloque', 'impossible'],
        'priority': 'urgent',
        'category': 'Urgent'
    },
    'request': {
        'keywords': ['besoin', 'faudrait', 'il faut', 'ajouter', 'modifier', 'changer', 'ameliorer', 'demande'],
        'priority': 'medium',
        'category': 'Demande'
    },
    'question': {
        'keywords': ['comment', 'pourquoi', 'est-ce que', 'peut-on', 'sais-tu', 'tu sais'],
        'priority': 'low',
        'category': 'Question'
    },
    'maintenance': {
        'keywords': ['mise a jour', 'update', 'maintenance', 'deployer', 'installer', 'configurer'],
        'priority': 'medium',
        'category': 'Maintenance'
    }
}


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


def detect_problems(text):
    """Detect problems in text"""
    text_lower = text.lower()
    detected = []

    for problem_type, config in PROBLEM_PATTERNS.items():
        for keyword in config['keywords']:
            if keyword in text_lower:
                detected.append({
                    'type': problem_type,
                    'keyword': keyword,
                    'priority': config['priority'],
                    'category': config['category']
                })
                break  # Only match once per type

    return detected


def extract_ticket_info(text):
    """Extract potential ticket information from text"""
    # Try to extract a title (first sentence or line)
    lines = text.strip().split('\n')
    first_line = lines[0].strip()

    # Clean up title
    title = first_line[:100]  # Max 100 chars
    if title.endswith(('.', '!', '?')):
        title = title[:-1]

    # Use rest as description
    description = text if len(lines) == 1 else '\n'.join(lines[1:]).strip()

    return title, description


def cmd_analyze(args):
    """Analyze text for problems"""
    problems = detect_problems(args.text)
    title, description = extract_ticket_info(args.text)

    # Determine overall priority
    priorities = ['urgent', 'high', 'medium', 'low']
    overall_priority = 'low'
    for p in problems:
        if priorities.index(p['priority']) < priorities.index(overall_priority):
            overall_priority = p['priority']

    result = {
        'success': True,
        'problems_detected': len(problems) > 0,
        'problems': problems,
        'suggested_ticket': {
            'title': title,
            'description': description,
            'priority': overall_priority,
            'category': problems[0]['category'] if problems else 'General'
        } if problems else None
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_create(args):
    """Create a ticket"""
    data = {
        'title': args.title,
        'description': args.description,
        'priority': args.priority or 'medium',
        'status': 'open'
    }

    if args.auto:
        # Auto mode: only create if problems detected
        problems = detect_problems(f"{args.title} {args.description}")
        if not problems:
            print(json.dumps({
                'success': False,
                'message': 'Aucun probleme detecte, ticket non cree',
                'auto_mode': True
            }))
            return 0

    result = api_request('tickets', method='POST', data=data)

    if result.get('id'):
        output = {
            'success': True,
            'message': 'Ticket cree',
            'ticket': {
                'id': result.get('id'),
                'title': result.get('title'),
                'priority': result.get('priority'),
                'url': f"{AVS_INTRANET_URL}/tickets/{result.get('id')}"
            }
        }
        logger.info(f"Created ticket: {result.get('title')}")
    else:
        output = result

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if output.get('success', True) else 1


def cmd_suggest(args):
    """Suggest a ticket based on conversation context"""
    problems = detect_problems(args.context)

    if not problems:
        print(json.dumps({
            'success': True,
            'should_create_ticket': False,
            'reason': 'Aucun probleme detecte dans le contexte'
        }))
        return 0

    title, description = extract_ticket_info(args.context)

    # Get highest priority
    priorities = ['urgent', 'high', 'medium', 'low']
    priority = 'low'
    for p in problems:
        if priorities.index(p['priority']) < priorities.index(priority):
            priority = p['priority']

    suggestion = {
        'success': True,
        'should_create_ticket': True,
        'problems': problems,
        'suggestion': {
            'title': title,
            'description': description,
            'priority': priority,
            'category': problems[0]['category']
        },
        'prompt': f"Je detecte un probleme ({problems[0]['category']}). Veux-tu que je cree un ticket ?"
    }

    print(json.dumps(suggestion, indent=2, ensure_ascii=False))
    return 0


def main():
    parser = argparse.ArgumentParser(description='Brain Auto-Ticket')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # analyze
    p_analyze = subparsers.add_parser('analyze', help='Analyze text for problems')
    p_analyze.add_argument('text', help='Text to analyze')

    # create
    p_create = subparsers.add_parser('create', help='Create a ticket')
    p_create.add_argument('--title', required=True, help='Ticket title')
    p_create.add_argument('--description', required=True, help='Ticket description')
    p_create.add_argument('--priority', choices=['low', 'medium', 'high', 'urgent'], help='Priority')
    p_create.add_argument('--auto', action='store_true', help='Only create if problems detected')

    # suggest
    p_suggest = subparsers.add_parser('suggest', help='Suggest ticket from context')
    p_suggest.add_argument('context', help='Conversation context')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    commands = {
        'analyze': cmd_analyze,
        'create': cmd_create,
        'suggest': cmd_suggest
    }

    return commands[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
