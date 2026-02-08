#!/usr/bin/env python3
"""
AVS Tickets - Gestion des tickets Intranet AVS

Usage:
    avs_tickets.py list [--status STATUS] [--limit N]
    avs_tickets.py create --title TITLE --description DESC [--priority PRIORITY] [--category CATEGORY]
    avs_tickets.py get ID
    avs_tickets.py update ID [--status STATUS] [--priority PRIORITY]
    avs_tickets.py comment ID --message MESSAGE
    avs_tickets.py categories

Permet a Michel de creer et gerer des tickets sur l'Intranet AVS.
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime

# Configuration
AVS_INTRANET_URL = os.environ.get('AVS_INTRANET_URL', 'https://intra.avstech.fr')
AVS_API_KEY = os.environ.get('AVS_API_KEY', '')

VALID_STATUSES = ['open', 'in_progress', 'waiting', 'resolved', 'closed']
VALID_PRIORITIES = ['low', 'medium', 'high', 'urgent']


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
    """List tickets"""
    params = []
    if args.status:
        params.append(f"status={args.status}")
    if args.limit:
        params.append(f"limit={args.limit}")

    endpoint = "tickets"
    if params:
        endpoint += "?" + "&".join(params)

    result = api_request(endpoint)

    if not result.get('success', True) and 'error' in result:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1

    tickets = result if isinstance(result, list) else result.get('tickets', [])

    output = {
        'success': True,
        'count': len(tickets),
        'tickets': []
    }

    for ticket in tickets[:args.limit or 10]:
        output['tickets'].append({
            'id': ticket.get('id'),
            'title': ticket.get('title'),
            'status': ticket.get('status'),
            'priority': ticket.get('priority'),
            'category': ticket.get('category', {}).get('name') if isinstance(ticket.get('category'), dict) else ticket.get('categoryId'),
            'createdAt': ticket.get('createdAt'),
            'assignedTo': ticket.get('assignedTo', {}).get('name') if isinstance(ticket.get('assignedTo'), dict) else None
        })

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


def cmd_create(args):
    """Create a new ticket"""
    if args.priority and args.priority not in VALID_PRIORITIES:
        print(json.dumps({
            'success': False,
            'error': f"Invalid priority. Valid: {', '.join(VALID_PRIORITIES)}"
        }))
        return 1

    data = {
        'title': args.title,
        'description': args.description,
        'priority': args.priority or 'medium'
    }

    if args.category:
        data['categoryId'] = args.category

    result = api_request("tickets", method='POST', data=data)

    if result.get('success', True) and 'id' in result:
        output = {
            'success': True,
            'message': f"Ticket cree avec succes",
            'ticket': {
                'id': result.get('id'),
                'title': result.get('title'),
                'status': result.get('status'),
                'priority': result.get('priority'),
                'url': f"{AVS_INTRANET_URL}/tickets/{result.get('id')}"
            }
        }
    else:
        output = result

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if output.get('success', True) else 1


def cmd_get(args):
    """Get ticket details"""
    result = api_request(f"tickets/{args.id}")

    if result.get('success', True) and 'id' in result:
        ticket = result
        output = {
            'success': True,
            'ticket': {
                'id': ticket.get('id'),
                'title': ticket.get('title'),
                'description': ticket.get('description'),
                'status': ticket.get('status'),
                'priority': ticket.get('priority'),
                'category': ticket.get('category', {}).get('name') if isinstance(ticket.get('category'), dict) else None,
                'assignedTo': ticket.get('assignedTo', {}).get('name') if isinstance(ticket.get('assignedTo'), dict) else None,
                'createdBy': ticket.get('createdBy', {}).get('name') if isinstance(ticket.get('createdBy'), dict) else None,
                'createdAt': ticket.get('createdAt'),
                'updatedAt': ticket.get('updatedAt'),
                'comments': len(ticket.get('comments', [])),
                'url': f"{AVS_INTRANET_URL}/tickets/{ticket.get('id')}"
            }
        }
    else:
        output = result

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if output.get('success', True) else 1


def cmd_update(args):
    """Update ticket status or priority"""
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

    result = api_request(f"tickets/{args.id}", method='PATCH', data=data)

    if result.get('success', True) and 'id' in result:
        output = {
            'success': True,
            'message': f"Ticket mis a jour",
            'ticket': {
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


def cmd_comment(args):
    """Add comment to ticket"""
    data = {
        'content': args.message
    }

    result = api_request(f"tickets/{args.id}/comments", method='POST', data=data)

    if result.get('success', True):
        output = {
            'success': True,
            'message': f"Commentaire ajoute au ticket {args.id}",
            'comment': {
                'id': result.get('id'),
                'content': args.message[:100] + ('...' if len(args.message) > 100 else '')
            }
        }
    else:
        output = result

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if output.get('success', True) else 1


def cmd_categories(args):
    """List ticket categories"""
    result = api_request("ticket-categories")

    if isinstance(result, list):
        output = {
            'success': True,
            'count': len(result),
            'categories': [
                {
                    'id': cat.get('id'),
                    'name': cat.get('name'),
                    'color': cat.get('color')
                }
                for cat in result
            ]
        }
    else:
        output = result

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


def main():
    parser = argparse.ArgumentParser(description='AVS Tickets - Gestion des tickets Intranet')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # list
    p_list = subparsers.add_parser('list', help='List tickets')
    p_list.add_argument('--status', choices=VALID_STATUSES, help='Filter by status')
    p_list.add_argument('--limit', type=int, default=10, help='Max results')

    # create
    p_create = subparsers.add_parser('create', help='Create a ticket')
    p_create.add_argument('--title', required=True, help='Ticket title')
    p_create.add_argument('--description', required=True, help='Ticket description')
    p_create.add_argument('--priority', choices=VALID_PRIORITIES, help='Priority level')
    p_create.add_argument('--category', help='Category ID')

    # get
    p_get = subparsers.add_parser('get', help='Get ticket details')
    p_get.add_argument('id', help='Ticket ID')

    # update
    p_update = subparsers.add_parser('update', help='Update ticket')
    p_update.add_argument('id', help='Ticket ID')
    p_update.add_argument('--status', choices=VALID_STATUSES, help='New status')
    p_update.add_argument('--priority', choices=VALID_PRIORITIES, help='New priority')

    # comment
    p_comment = subparsers.add_parser('comment', help='Add comment')
    p_comment.add_argument('id', help='Ticket ID')
    p_comment.add_argument('--message', required=True, help='Comment text')

    # categories
    subparsers.add_parser('categories', help='List categories')

    args = parser.parse_args()

    if args.command == 'list':
        return cmd_list(args)
    elif args.command == 'create':
        return cmd_create(args)
    elif args.command == 'get':
        return cmd_get(args)
    elif args.command == 'update':
        return cmd_update(args)
    elif args.command == 'comment':
        return cmd_comment(args)
    elif args.command == 'categories':
        return cmd_categories(args)
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
