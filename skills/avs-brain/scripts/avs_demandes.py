#!/usr/bin/env python3
"""
AVS Demandes - Gestion des demandes (feature requests) Intranet AVS

Usage:
    avs_demandes.py list [--status STATUS] [--project PROJECT] [--limit N]
    avs_demandes.py create --title TITLE --description DESC --project PROJECT [--priority PRIORITY]
    avs_demandes.py get ID
    avs_demandes.py update ID [--status STATUS] [--priority PRIORITY]
    avs_demandes.py vote ID [--up|--down]

Les demandes sont des feature requests liees a des projets specifiques.
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

VALID_STATUSES = ['submitted', 'under_review', 'planned', 'in_progress', 'completed', 'rejected']
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
    """List feature requests"""
    params = []
    if args.status:
        params.append(f"status={args.status}")
    if args.project:
        params.append(f"projectId={args.project}")
    if args.limit:
        params.append(f"limit={args.limit}")

    endpoint = "feature-requests"
    if params:
        endpoint += "?" + "&".join(params)

    result = api_request(endpoint)

    if not result.get('success', True) and 'error' in result:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1

    demandes = result if isinstance(result, list) else result.get('featureRequests', result.get('requests', []))

    output = {
        'success': True,
        'count': len(demandes),
        'demandes': []
    }

    for demande in demandes[:args.limit or 10]:
        output['demandes'].append({
            'id': demande.get('id'),
            'title': demande.get('title'),
            'status': demande.get('status'),
            'priority': demande.get('priority'),
            'project': demande.get('project', {}).get('name') if isinstance(demande.get('project'), dict) else demande.get('projectId'),
            'votes': demande.get('votes', 0),
            'createdBy': demande.get('createdBy', {}).get('name') if isinstance(demande.get('createdBy'), dict) else None,
            'createdAt': demande.get('createdAt')
        })

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


def cmd_create(args):
    """Create a new feature request"""
    if args.priority and args.priority not in VALID_PRIORITIES:
        print(json.dumps({
            'success': False,
            'error': f"Invalid priority. Valid: {', '.join(VALID_PRIORITIES)}"
        }))
        return 1

    data = {
        'title': args.title,
        'description': args.description,
        'projectId': args.project,
        'priority': args.priority or 'medium',
        'status': 'submitted'
    }

    result = api_request("feature-requests", method='POST', data=data)

    if result.get('success', True) and 'id' in result:
        output = {
            'success': True,
            'message': f"Demande creee avec succes",
            'demande': {
                'id': result.get('id'),
                'title': result.get('title'),
                'status': result.get('status'),
                'priority': result.get('priority'),
                'url': f"{AVS_INTRANET_URL}/demandes/{result.get('id')}"
            }
        }
    else:
        output = result

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if output.get('success', True) else 1


def cmd_get(args):
    """Get feature request details"""
    result = api_request(f"feature-requests/{args.id}")

    if result.get('success', True) and 'id' in result:
        demande = result
        output = {
            'success': True,
            'demande': {
                'id': demande.get('id'),
                'title': demande.get('title'),
                'description': demande.get('description'),
                'status': demande.get('status'),
                'priority': demande.get('priority'),
                'project': demande.get('project', {}).get('name') if isinstance(demande.get('project'), dict) else None,
                'votes': demande.get('votes', 0),
                'createdBy': demande.get('createdBy', {}).get('name') if isinstance(demande.get('createdBy'), dict) else None,
                'createdAt': demande.get('createdAt'),
                'updatedAt': demande.get('updatedAt'),
                'url': f"{AVS_INTRANET_URL}/demandes/{demande.get('id')}"
            }
        }
    else:
        output = result

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if output.get('success', True) else 1


def cmd_update(args):
    """Update feature request"""
    data = {}
    if args.status:
        if args.status not in VALID_STATUSES:
            print(json.dumps({
                'success': False,
                'error': f"Invalid status. Valid: {', '.join(VALID_STATUSES)}"
            }))
            return 1
        data['status'] = args.status

    if args.priority:
        if args.priority not in VALID_PRIORITIES:
            print(json.dumps({
                'success': False,
                'error': f"Invalid priority. Valid: {', '.join(VALID_PRIORITIES)}"
            }))
            return 1
        data['priority'] = args.priority

    if not data:
        print(json.dumps({
            'success': False,
            'error': 'Nothing to update. Specify --status or --priority'
        }))
        return 1

    result = api_request(f"feature-requests/{args.id}", method='PATCH', data=data)

    if result.get('success', True) and 'id' in result:
        output = {
            'success': True,
            'message': f"Demande mise a jour",
            'demande': {
                'id': result.get('id'),
                'title': result.get('title'),
                'status': result.get('status'),
                'priority': result.get('priority')
            }
        }
    else:
        output = result

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if output.get('success', True) else 1


def cmd_vote(args):
    """Vote on feature request"""
    vote_value = 1 if args.up else (-1 if args.down else 1)

    result = api_request(f"feature-requests/{args.id}/vote", method='POST', data={'value': vote_value})

    if result.get('success', True):
        output = {
            'success': True,
            'message': f"Vote {'positif' if vote_value > 0 else 'negatif'} enregistre",
            'demande': {
                'id': args.id,
                'votes': result.get('votes', 'unknown')
            }
        }
    else:
        output = result

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if output.get('success', True) else 1


def main():
    parser = argparse.ArgumentParser(description='AVS Demandes - Gestion des feature requests')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # list
    p_list = subparsers.add_parser('list', help='List demandes')
    p_list.add_argument('--status', choices=VALID_STATUSES, help='Filter by status')
    p_list.add_argument('--project', help='Filter by project ID')
    p_list.add_argument('--limit', type=int, default=10, help='Max results')

    # create
    p_create = subparsers.add_parser('create', help='Create a demande')
    p_create.add_argument('--title', required=True, help='Demande title')
    p_create.add_argument('--description', required=True, help='Demande description')
    p_create.add_argument('--project', required=True, help='Project ID')
    p_create.add_argument('--priority', choices=VALID_PRIORITIES, help='Priority level')

    # get
    p_get = subparsers.add_parser('get', help='Get demande details')
    p_get.add_argument('id', help='Demande ID')

    # update
    p_update = subparsers.add_parser('update', help='Update demande')
    p_update.add_argument('id', help='Demande ID')
    p_update.add_argument('--status', choices=VALID_STATUSES, help='New status')
    p_update.add_argument('--priority', choices=VALID_PRIORITIES, help='New priority')

    # vote
    p_vote = subparsers.add_parser('vote', help='Vote on demande')
    p_vote.add_argument('id', help='Demande ID')
    vote_group = p_vote.add_mutually_exclusive_group()
    vote_group.add_argument('--up', action='store_true', help='Vote up')
    vote_group.add_argument('--down', action='store_true', help='Vote down')

    args = parser.parse_args()

    if args.command == 'list':
        return cmd_list(args)
    elif args.command == 'create':
        return cmd_create(args)
    elif args.command == 'get':
        return cmd_get(args)
    elif args.command == 'update':
        return cmd_update(args)
    elif args.command == 'vote':
        return cmd_vote(args)
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
