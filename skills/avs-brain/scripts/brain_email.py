#!/usr/bin/env python3
"""
Brain Email - Email drafting and sending for Michel

Usage:
    brain_email.py draft --to EMAIL --subject SUBJECT --body BODY [--cc CC]
    brain_email.py send --to EMAIL --subject SUBJECT --body BODY [--cc CC]
    brain_email.py reply MESSAGE_ID --body BODY
    brain_email.py check [--unread] [--limit N]
    brain_email.py search QUERY [--limit N]
    brain_email.py read MESSAGE_ID

Manages emails via AVS Intranet Gmail API.
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
        logging.FileHandler(LOG_DIR / 'brain_email.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('brain_email')

# Load env file if environment variables not set
def load_env_file():
    env_file = Path.home() / '.config' / 'michel' / 'env'
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    if key not in os.environ or not os.environ[key]:
                        os.environ[key] = value

load_env_file()

# Configuration
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
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else ''
        try:
            return json.loads(error_body)
        except:
            return {'success': False, 'error': str(e), 'status': e.code}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def cmd_draft(args):
    """Create email draft (doesn't send)"""
    logger.info(f"Creating draft to: {args.to}")

    email_data = {
        'to': args.to,
        'subject': args.subject,
        'body': args.body,
        'draft': True
    }

    if args.cc:
        email_data['cc'] = args.cc

    result = api_request('gmail/draft', method='POST', data=email_data)

    if result.get('success', True) and result.get('id'):
        output = {
            'success': True,
            'message': 'Brouillon cree',
            'draft': {
                'id': result.get('id'),
                'to': args.to,
                'subject': args.subject
            }
        }
    else:
        output = result

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if output.get('success', True) else 1


def cmd_send(args):
    """Send email"""
    logger.info(f"Sending email to: {args.to}")

    email_data = {
        'to': args.to,
        'subject': args.subject,
        'body': args.body,
        'html': '<p>' + args.body.replace('\n', '</p><p>') + '</p>'
    }

    if args.cc:
        email_data['cc'] = args.cc

    result = api_request('gmail/send', method='POST', data=email_data)

    if result.get('success', True) and result.get('messageId'):
        output = {
            'success': True,
            'message': 'Email envoye',
            'email': {
                'id': result.get('messageId'),
                'to': args.to,
                'subject': args.subject
            }
        }
        logger.info(f"Email sent: {result.get('messageId')}")
    else:
        output = result

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if output.get('success', True) else 1


def cmd_reply(args):
    """Reply to an email"""
    logger.info(f"Replying to: {args.message_id}")

    # First get the original message
    original = api_request(f'gmail/messages/{args.message_id}')

    if not original.get('id'):
        print(json.dumps({'success': False, 'error': 'Original message not found'}))
        return 1

    # Build reply
    reply_data = {
        'to': original.get('from', {}).get('email'),
        'subject': f"Re: {original.get('subject', '')}",
        'body': args.body,
        'replyTo': args.message_id,
        'threadId': original.get('threadId')
    }

    result = api_request('gmail/send', method='POST', data=reply_data)

    if result.get('success', True) and result.get('messageId'):
        output = {
            'success': True,
            'message': 'Reponse envoyee',
            'reply': {
                'id': result.get('messageId'),
                'to': reply_data['to'],
                'subject': reply_data['subject']
            }
        }
        logger.info(f"Reply sent: {result.get('messageId')}")
    else:
        output = result

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if output.get('success', True) else 1


def cmd_check(args):
    """Check emails"""
    logger.info("Checking emails...")

    params = [f'limit={args.limit}']
    if args.unread:
        params.append('unread=true')

    endpoint = 'gmail/messages?' + '&'.join(params)
    result = api_request(endpoint)

    if isinstance(result, list) or result.get('messages'):
        messages = result if isinstance(result, list) else result.get('messages', [])

        output = {
            'success': True,
            'count': len(messages),
            'emails': [{
                'id': msg.get('id'),
                'from': msg.get('from', {}).get('email') if isinstance(msg.get('from'), dict) else msg.get('from'),
                'subject': msg.get('subject'),
                'date': msg.get('date'),
                'unread': msg.get('unread', False),
                'snippet': msg.get('snippet', '')[:100]
            } for msg in messages[:args.limit]]
        }
    else:
        output = result

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


def cmd_search(args):
    """Search emails"""
    logger.info(f"Searching emails: {args.query}")

    endpoint = f'gmail/search?q={urllib.parse.quote(args.query)}&limit={args.limit}'
    result = api_request(endpoint)

    if isinstance(result, list) or result.get('messages'):
        messages = result if isinstance(result, list) else result.get('messages', [])

        output = {
            'success': True,
            'query': args.query,
            'count': len(messages),
            'emails': [{
                'id': msg.get('id'),
                'from': msg.get('from', {}).get('email') if isinstance(msg.get('from'), dict) else msg.get('from'),
                'subject': msg.get('subject'),
                'date': msg.get('date'),
                'snippet': msg.get('snippet', '')[:100]
            } for msg in messages[:args.limit]]
        }
    else:
        output = result

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


def cmd_read(args):
    """Read a specific email"""
    logger.info(f"Reading email: {args.message_id}")

    result = api_request(f'gmail/messages/{args.message_id}')

    if result.get('id'):
        output = {
            'success': True,
            'email': {
                'id': result.get('id'),
                'from': result.get('from'),
                'to': result.get('to'),
                'cc': result.get('cc'),
                'subject': result.get('subject'),
                'date': result.get('date'),
                'body': result.get('body') or result.get('snippet'),
                'attachments': result.get('attachments', [])
            }
        }
    else:
        output = result

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if output.get('success', True) else 1


# Need to import urllib.parse for URL encoding
import urllib.parse


def main():
    parser = argparse.ArgumentParser(description='Brain Email - Email Management')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # draft
    p_draft = subparsers.add_parser('draft', help='Create email draft')
    p_draft.add_argument('--to', required=True, help='Recipient email')
    p_draft.add_argument('--subject', required=True, help='Email subject')
    p_draft.add_argument('--body', required=True, help='Email body')
    p_draft.add_argument('--cc', help='CC recipients')

    # send
    p_send = subparsers.add_parser('send', help='Send email')
    p_send.add_argument('--to', required=True, help='Recipient email')
    p_send.add_argument('--subject', required=True, help='Email subject')
    p_send.add_argument('--body', required=True, help='Email body')
    p_send.add_argument('--cc', help='CC recipients')

    # reply
    p_reply = subparsers.add_parser('reply', help='Reply to email')
    p_reply.add_argument('message_id', help='Original message ID')
    p_reply.add_argument('--body', required=True, help='Reply body')

    # check
    p_check = subparsers.add_parser('check', help='Check emails')
    p_check.add_argument('--unread', action='store_true', help='Only unread')
    p_check.add_argument('--limit', type=int, default=10, help='Max results')

    # search
    p_search = subparsers.add_parser('search', help='Search emails')
    p_search.add_argument('query', help='Search query')
    p_search.add_argument('--limit', type=int, default=10, help='Max results')

    # read
    p_read = subparsers.add_parser('read', help='Read email')
    p_read.add_argument('message_id', help='Message ID')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    commands = {
        'draft': cmd_draft,
        'send': cmd_send,
        'reply': cmd_reply,
        'check': cmd_check,
        'search': cmd_search,
        'read': cmd_read
    }

    return commands[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
