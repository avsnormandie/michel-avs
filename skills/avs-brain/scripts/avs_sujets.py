#!/usr/bin/env python3
"""
AVS Sujets - Gestion des sujets (projets long-terme) Intranet AVS

Usage:
    avs_sujets.py list [--status STATUS] [--limit N]
    avs_sujets.py create --title TITLE --description DESC [--priority PRIORITY]
    avs_sujets.py get ID
    avs_sujets.py update ID [--status STATUS] [--progress PERCENT]
    avs_sujets.py step ID --title TITLE [--description DESC]
    avs_sujets.py note ID --content CONTENT

Les sujets sont des projets long-terme avec etapes et notes.
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error

# Configuration
AVS_INTRANET_URL = os.environ.get('AVS_INTRANET_URL', 'https://intra.avstech.fr')
AVS_API_KEY = os.environ.get('AVS_API_KEY', '')

VALID_STATUSES = ['backlog', 'active', 'on_hold', 'completed', 'cancelled']
VALID_PRIORITIES = ['low', 'medium', 'high', 'critical']


def api_request(endpoint, method='GET', data=None):
    """Make API request to AVS Intranet"""
    if not AVS_API_KEY:
        return {'success': False, 'error': 'AVS_API_KEY not configured'}

    url = f"{AVS_INTRANET_URL}/api/external/{endpoint}"

    headers = {
        'Content-Type': 'application/json',
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


def cmd_list(args):
    """List sujets"""
    params = []
    if args.status:
        params.append(f"status={args.status}")
    if args.limit:
        params.append(f"limit={args.limit}")

    endpoint = "sujets"
    if params:
        endpoint += "?" + "&".join(params)

    result = api_request(endpoint)

    if not result.get('success', True) and 'error' in result:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1

    sujets = result if isinstance(result, list) else result.get('sujets', [])

    output = {
        'success': True,
        'count': len(sujets),
        'sujets': []
    }

    for sujet in sujets[:args.limit or 10]:
        output['sujets'].append({
            'id': sujet.get('id'),
            'title': sujet.get('title'),
            'status': sujet.get('status'),
            'priority': sujet.get('priority'),
            'progress': sujet.get('progress'),
            'stepsCount': len(sujet.get('steps', [])),
            'assignedTo': sujet.get('assignedTo', {}).get('name') if isinstance(sujet.get('assignedTo'), dict) else None,
            'url': f"{AVS_INTRANET_URL}/sujets/{sujet.get('id')}"
        })

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


def cmd_create(args):
    """Create a new sujet"""
    if args.priority and args.priority not in VALID_PRIORITIES:
        print(json.dumps({
            'success': False,
            'error': f"Invalid priority. Valid: {', '.join(VALID_PRIORITIES)}"
        }))
        return 1

    data = {
        'title': args.title,
        'description': args.description,
        'priority': args.priority or 'medium',
        'status': 'backlog'
    }

    result = api_request("sujets", method='POST', data=data)

    if result.get('success', True) and 'id' in result:
        output = {
            'success': True,
            'message': f"Sujet cree avec succes",
            'sujet': {
                'id': result.get('id'),
                'title': result.get('title'),
                'status': result.get('status'),
                'priority': result.get('priority'),
                'url': f"{AVS_INTRANET_URL}/sujets/{result.get('id')}"
            }
        }
    else:
        output = result

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if output.get('success', True) else 1


def cmd_get(args):
    """Get sujet details"""
    result = api_request(f"sujets/{args.id}")

    if result.get('success', True) and 'id' in result:
        sujet = result
        output = {
            'success': True,
            'sujet': {
                'id': sujet.get('id'),
                'title': sujet.get('title'),
                'description': sujet.get('description'),
                'status': sujet.get('status'),
                'priority': sujet.get('priority'),
                'progress': sujet.get('progress'),
                'assignedTo': sujet.get('assignedTo', {}).get('name') if isinstance(sujet.get('assignedTo'), dict) else None,
                'createdBy': sujet.get('createdBy', {}).get('name') if isinstance(sujet.get('createdBy'), dict) else None,
                'createdAt': sujet.get('createdAt'),
                'updatedAt': sujet.get('updatedAt'),
                'steps': [
                    {
                        'id': step.get('id'),
                        'title': step.get('title'),
                        'completed': step.get('completed'),
                        'order': step.get('order')
                    }
                    for step in sujet.get('steps', [])
                ],
                'notesCount': len(sujet.get('notes', [])),
                'url': f"{AVS_INTRANET_URL}/sujets/{sujet.get('id')}"
            }
        }
    else:
        output = result

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if output.get('success', True) else 1


def cmd_update(args):
    """Update sujet status or progress"""
    data = {}
    if args.status:
        if args.status not in VALID_STATUSES:
            print(json.dumps({
                'success': False,
                'error': f"Invalid status. Valid: {', '.join(VALID_STATUSES)}"
            }))
            return 1
        data['status'] = args.status

    if args.progress is not None:
        if args.progress < 0 or args.progress > 100:
            print(json.dumps({
                'success': False,
                'error': 'Progress must be between 0 and 100'
            }))
            return 1
        data['progress'] = args.progress

    if not data:
        print(json.dumps({
            'success': False,
            'error': 'Nothing to update. Specify --status or --progress'
        }))
        return 1

    result = api_request(f"sujets/{args.id}", method='PATCH', data=data)

    if result.get('success', True) and 'id' in result:
        output = {
            'success': True,
            'message': f"Sujet mis a jour",
            'sujet': {
                'id': result.get('id'),
                'title': result.get('title'),
                'status': result.get('status'),
                'progress': result.get('progress')
            }
        }
    else:
        output = result

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if output.get('success', True) else 1


def cmd_step(args):
    """Add step to sujet"""
    data = {
        'title': args.title
    }
    if args.description:
        data['description'] = args.description

    result = api_request(f"sujets/{args.id}/steps", method='POST', data=data)

    if result.get('success', True):
        output = {
            'success': True,
            'message': f"Etape ajoutee au sujet {args.id}",
            'step': {
                'id': result.get('id'),
                'title': args.title
            }
        }
    else:
        output = result

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if output.get('success', True) else 1


def cmd_note(args):
    """Add note to sujet"""
    data = {
        'content': args.content
    }

    result = api_request(f"sujets/{args.id}/notes", method='POST', data=data)

    if result.get('success', True):
        output = {
            'success': True,
            'message': f"Note ajoutee au sujet {args.id}",
            'note': {
                'id': result.get('id'),
                'content': args.content[:100] + ('...' if len(args.content) > 100 else '')
            }
        }
    else:
        output = result

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if output.get('success', True) else 1


def main():
    parser = argparse.ArgumentParser(description='AVS Sujets - Gestion des projets long-terme')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # list
    p_list = subparsers.add_parser('list', help='List sujets')
    p_list.add_argument('--status', choices=VALID_STATUSES, help='Filter by status')
    p_list.add_argument('--limit', type=int, default=10, help='Max results')

    # create
    p_create = subparsers.add_parser('create', help='Create a sujet')
    p_create.add_argument('--title', required=True, help='Sujet title')
    p_create.add_argument('--description', required=True, help='Sujet description')
    p_create.add_argument('--priority', choices=VALID_PRIORITIES, help='Priority level')

    # get
    p_get = subparsers.add_parser('get', help='Get sujet details')
    p_get.add_argument('id', help='Sujet ID')

    # update
    p_update = subparsers.add_parser('update', help='Update sujet')
    p_update.add_argument('id', help='Sujet ID')
    p_update.add_argument('--status', choices=VALID_STATUSES, help='New status')
    p_update.add_argument('--progress', type=int, help='Progress percentage (0-100)')

    # step
    p_step = subparsers.add_parser('step', help='Add step to sujet')
    p_step.add_argument('id', help='Sujet ID')
    p_step.add_argument('--title', required=True, help='Step title')
    p_step.add_argument('--description', help='Step description')

    # note
    p_note = subparsers.add_parser('note', help='Add note to sujet')
    p_note.add_argument('id', help='Sujet ID')
    p_note.add_argument('--content', required=True, help='Note content')

    args = parser.parse_args()

    if args.command == 'list':
        return cmd_list(args)
    elif args.command == 'create':
        return cmd_create(args)
    elif args.command == 'get':
        return cmd_get(args)
    elif args.command == 'update':
        return cmd_update(args)
    elif args.command == 'step':
        return cmd_step(args)
    elif args.command == 'note':
        return cmd_note(args)
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
