#!/usr/bin/env python3
"""
AVS Knowledge Base - Direct KB node management

Usage:
    avs_kb.py create --title TITLE --content CONTENT --type TYPE [--visibility VIS] [--tags TAGS]
    avs_kb.py search QUERY [--limit N]
    avs_kb.py get ID
    avs_kb.py update ID [--title TITLE] [--content CONTENT] [--visibility VIS]
    avs_kb.py link FROM_ID TO_ID [--type TYPE]
    avs_kb.py context QUERY [--max-nodes N]

Direct interface to AVS Knowledge Base for creating and managing nodes.
"""

import argparse
import json
import logging
import os
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
        logging.FileHandler(LOG_DIR / 'avs_kb.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('avs_kb')

# Configuration
AVS_INTRANET_URL = os.environ.get('AVS_INTRANET_URL', 'https://intra.avstech.fr')
AVS_API_KEY = os.environ.get('AVS_API_KEY', '')

VALID_TYPES = ['product', 'concept', 'decision', 'resource', 'company', 'person', 'procedure']
VALID_VISIBILITIES = ['public', 'restricted', 'admin']
VALID_EDGE_TYPES = ['related_to', 'depends_on', 'implements', 'part_of', 'supersedes', 'used_by', 'created_by']


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
            error_data = json.loads(error_body)
            return {'success': False, 'error': error_data.get('error', str(e)), 'status': e.code}
        except:
            return {'success': False, 'error': str(e), 'status': e.code}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def cmd_create(args):
    """Create a new KB node"""
    if args.type not in VALID_TYPES:
        print(json.dumps({
            'success': False,
            'error': f"Invalid type. Valid: {', '.join(VALID_TYPES)}"
        }))
        return 1

    if args.visibility and args.visibility not in VALID_VISIBILITIES:
        print(json.dumps({
            'success': False,
            'error': f"Invalid visibility. Valid: {', '.join(VALID_VISIBILITIES)}"
        }))
        return 1

    data = {
        'title': args.title,
        'content': args.content,
        'type': args.type,
        'visibility': args.visibility or 'public'
    }

    if args.tags:
        data['tags'] = [t.strip() for t in args.tags.split(',')]

    result = api_request('knowledge/nodes', method='POST', data=data)

    if result.get('id'):
        output = {
            'success': True,
            'message': 'Node cree avec succes',
            'node': {
                'id': result.get('id'),
                'title': result.get('title'),
                'type': result.get('type'),
                'visibility': result.get('visibility'),
                'url': f"{AVS_INTRANET_URL}/knowledge/{result.get('id')}"
            }
        }
        logger.info(f"Created KB node: {result.get('title')}")
    else:
        output = result

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if output.get('success', True) and 'id' in result else 1


def cmd_search(args):
    """Search KB nodes"""
    result = api_request('knowledge/context', method='POST', data={
        'query': args.query,
        'maxNodes': args.limit or 10,
        'includeEntities': True
    })

    if result.get('success', True) and 'nodes' in result:
        nodes = result.get('nodes', [])
        output = {
            'success': True,
            'count': len(nodes),
            'nodes': [{
                'id': n.get('id'),
                'title': n.get('title'),
                'type': n.get('type'),
                'score': n.get('score'),
                'preview': n.get('content', '')[:100] + '...' if len(n.get('content', '')) > 100 else n.get('content', '')
            } for n in nodes]
        }
    else:
        output = result

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


def cmd_get(args):
    """Get a specific KB node"""
    result = api_request(f'knowledge/nodes/{args.id}')

    if result.get('id'):
        output = {
            'success': True,
            'node': {
                'id': result.get('id'),
                'title': result.get('title'),
                'type': result.get('type'),
                'content': result.get('content'),
                'visibility': result.get('visibility'),
                'tags': result.get('tags', []),
                'createdAt': result.get('createdAt'),
                'updatedAt': result.get('updatedAt'),
                'edges': result.get('edges', [])
            }
        }
    else:
        output = result

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if output.get('success', True) else 1


def cmd_update(args):
    """Update a KB node"""
    data = {}

    if args.title:
        data['title'] = args.title
    if args.content:
        data['content'] = args.content
    if args.visibility:
        if args.visibility not in VALID_VISIBILITIES:
            print(json.dumps({
                'success': False,
                'error': f"Invalid visibility. Valid: {', '.join(VALID_VISIBILITIES)}"
            }))
            return 1
        data['visibility'] = args.visibility

    if not data:
        print(json.dumps({
            'success': False,
            'error': 'Nothing to update'
        }))
        return 1

    result = api_request(f'knowledge/nodes/{args.id}', method='PATCH', data=data)

    if result.get('id'):
        output = {
            'success': True,
            'message': 'Node mis a jour',
            'node': {
                'id': result.get('id'),
                'title': result.get('title')
            }
        }
        logger.info(f"Updated KB node: {result.get('id')}")
    else:
        output = result

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if output.get('success', True) else 1


def cmd_link(args):
    """Create an edge between two nodes"""
    edge_type = args.type or 'related_to'

    if edge_type not in VALID_EDGE_TYPES:
        print(json.dumps({
            'success': False,
            'error': f"Invalid edge type. Valid: {', '.join(VALID_EDGE_TYPES)}"
        }))
        return 1

    data = {
        'fromId': args.from_id,
        'toId': args.to_id,
        'type': edge_type
    }

    result = api_request('knowledge/edges', method='POST', data=data)

    if result.get('id'):
        output = {
            'success': True,
            'message': 'Lien cree',
            'edge': {
                'id': result.get('id'),
                'from': args.from_id,
                'to': args.to_id,
                'type': edge_type
            }
        }
        logger.info(f"Created KB edge: {args.from_id} -> {args.to_id}")
    else:
        output = result

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if output.get('success', True) else 1


def cmd_context(args):
    """Get context for a query (for AI assistants)"""
    result = api_request('knowledge/context', method='POST', data={
        'query': args.query,
        'maxNodes': args.max_nodes or 15,
        'maxDepth': 2,
        'includeEntities': True
    })

    if result.get('markdown'):
        # Output raw markdown for AI consumption
        print(result['markdown'])
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))

    return 0


def main():
    parser = argparse.ArgumentParser(description='AVS Knowledge Base Management')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # create
    p_create = subparsers.add_parser('create', help='Create a KB node')
    p_create.add_argument('--title', required=True, help='Node title')
    p_create.add_argument('--content', required=True, help='Node content')
    p_create.add_argument('--type', required=True, choices=VALID_TYPES, help='Node type')
    p_create.add_argument('--visibility', choices=VALID_VISIBILITIES, help='Visibility level')
    p_create.add_argument('--tags', help='Comma-separated tags')

    # search
    p_search = subparsers.add_parser('search', help='Search KB nodes')
    p_search.add_argument('query', help='Search query')
    p_search.add_argument('--limit', type=int, default=10, help='Max results')

    # get
    p_get = subparsers.add_parser('get', help='Get a KB node')
    p_get.add_argument('id', help='Node ID')

    # update
    p_update = subparsers.add_parser('update', help='Update a KB node')
    p_update.add_argument('id', help='Node ID')
    p_update.add_argument('--title', help='New title')
    p_update.add_argument('--content', help='New content')
    p_update.add_argument('--visibility', choices=VALID_VISIBILITIES, help='New visibility')

    # link
    p_link = subparsers.add_parser('link', help='Link two nodes')
    p_link.add_argument('from_id', help='Source node ID')
    p_link.add_argument('to_id', help='Target node ID')
    p_link.add_argument('--type', choices=VALID_EDGE_TYPES, help='Edge type')

    # context
    p_context = subparsers.add_parser('context', help='Get context for AI')
    p_context.add_argument('query', help='Context query')
    p_context.add_argument('--max-nodes', type=int, default=15, help='Max nodes')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    commands = {
        'create': cmd_create,
        'search': cmd_search,
        'get': cmd_get,
        'update': cmd_update,
        'link': cmd_link,
        'context': cmd_context
    }

    return commands[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
