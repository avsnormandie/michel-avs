#!/usr/bin/env python3
"""
Brain Meetings - Meeting summaries and calendar management

Usage:
    brain_meetings.py today
    brain_meetings.py upcoming [--hours N]
    brain_meetings.py past [--hours N]
    brain_meetings.py summarize EVENT_ID --notes "notes from meeting"
    brain_meetings.py remind [--minutes N]

Manages calendar events and creates meeting summaries.
"""

import argparse
import json
import logging
import os
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
        logging.FileHandler(LOG_DIR / 'brain_meetings.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('brain_meetings')

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


def format_event(event):
    """Format event for display"""
    start = event.get('start', {})
    end = event.get('end', {})

    start_time = start.get('dateTime', start.get('date', ''))
    end_time = end.get('dateTime', end.get('date', ''))

    # Parse times
    if 'T' in start_time:
        start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        start_str = start_dt.strftime('%H:%M')
    else:
        start_str = 'Journee'

    if 'T' in end_time:
        end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        end_str = end_dt.strftime('%H:%M')
    else:
        end_str = 'entiere'

    return {
        'id': event.get('id'),
        'title': event.get('summary', 'Sans titre'),
        'start': start_time,
        'end': end_time,
        'time': f"{start_str} - {end_str}",
        'location': event.get('location'),
        'attendees': [a.get('email') for a in event.get('attendees', [])],
        'description': event.get('description', '')[:200]
    }


def cmd_today(args):
    """Show today's events"""
    logger.info("Getting today's events...")

    result = api_request('calendar/events?timeMin=today&timeMax=tomorrow')

    events = result.get('events', result.get('items', []))
    if isinstance(result, list):
        events = result

    output = {
        'success': True,
        'date': datetime.now().strftime('%Y-%m-%d'),
        'count': len(events),
        'events': [format_event(e) for e in events]
    }

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


def cmd_upcoming(args):
    """Show upcoming events"""
    logger.info(f"Getting events for next {args.hours} hours...")

    result = api_request(f'calendar/events?hours={args.hours}')

    events = result.get('events', result.get('items', []))
    if isinstance(result, list):
        events = result

    output = {
        'success': True,
        'hours': args.hours,
        'count': len(events),
        'events': [format_event(e) for e in events]
    }

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


def cmd_past(args):
    """Show past events (for summarization)"""
    logger.info(f"Getting events from past {args.hours} hours...")

    # Calculate time range
    now = datetime.now()
    past = now - timedelta(hours=args.hours)

    result = api_request(f'calendar/events?timeMin={past.isoformat()}&timeMax={now.isoformat()}')

    events = result.get('events', result.get('items', []))
    if isinstance(result, list):
        events = result

    # Filter only past events
    past_events = []
    for e in events:
        end = e.get('end', {}).get('dateTime', e.get('end', {}).get('date', ''))
        if end:
            try:
                end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
                if end_dt.replace(tzinfo=None) < now:
                    past_events.append(e)
            except:
                pass

    output = {
        'success': True,
        'hours': args.hours,
        'count': len(past_events),
        'events': [format_event(e) for e in past_events],
        'need_summary': [e.get('id') for e in past_events if not e.get('description', '').startswith('[RESUME]')]
    }

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


def cmd_summarize(args):
    """Create meeting summary"""
    logger.info(f"Creating summary for event: {args.event_id}")

    # Get the event
    result = api_request(f'calendar/events/{args.event_id}')

    if not result.get('id'):
        print(json.dumps({'success': False, 'error': 'Event not found'}))
        return 1

    event = result

    # Build summary
    summary = f"""[RESUME] - {datetime.now().strftime('%Y-%m-%d %H:%M')}

**Reunion**: {event.get('summary', 'Sans titre')}
**Date**: {event.get('start', {}).get('dateTime', '')}
**Participants**: {', '.join([a.get('email', '') for a in event.get('attendees', [])])}

**Notes**:
{args.notes}

---
Resume genere par Michel
"""

    # Update event description
    update_data = {
        'description': summary
    }

    update_result = api_request(f'calendar/events/{args.event_id}', method='PATCH', data=update_data)

    # Also save to brain memory
    memory_data = {
        'title': f"Resume: {event.get('summary', 'Reunion')}",
        'content': summary,
        'type': 'memory',
        'importance': 70,
        'tags': ['reunion', 'resume', event.get('summary', '').lower()]
    }

    # Save to local brain (if available)
    try:
        import subprocess
        subprocess.run([
            'python3', 'brain.py', 'remember',
            '--title', memory_data['title'],
            '--content', memory_data['content'],
            '--type', 'memory',
            '--importance', '70',
            '--tags', 'reunion,resume'
        ], cwd=Path(__file__).parent, capture_output=True)
    except:
        pass

    output = {
        'success': True,
        'message': 'Resume cree',
        'event': format_event(event),
        'summary': summary[:200] + '...'
    }

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


def cmd_remind(args):
    """Check for events needing reminder"""
    logger.info(f"Checking for events in next {args.minutes} minutes...")

    now = datetime.now()
    soon = now + timedelta(minutes=args.minutes)

    result = api_request(f'calendar/events?hours=2')

    events = result.get('events', result.get('items', []))
    if isinstance(result, list):
        events = result

    upcoming = []
    for e in events:
        start = e.get('start', {}).get('dateTime', '')
        if start and 'T' in start:
            try:
                start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                start_dt = start_dt.replace(tzinfo=None)
                if now < start_dt < soon:
                    upcoming.append(e)
            except:
                pass

    output = {
        'success': True,
        'minutes': args.minutes,
        'count': len(upcoming),
        'reminders': [format_event(e) for e in upcoming]
    }

    if upcoming:
        output['message'] = f"{len(upcoming)} evenement(s) dans les {args.minutes} prochaines minutes!"

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


def main():
    parser = argparse.ArgumentParser(description='Brain Meetings - Calendar Management')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # today
    subparsers.add_parser('today', help="Today's events")

    # upcoming
    p_upcoming = subparsers.add_parser('upcoming', help='Upcoming events')
    p_upcoming.add_argument('--hours', type=int, default=24, help='Hours ahead')

    # past
    p_past = subparsers.add_parser('past', help='Past events')
    p_past.add_argument('--hours', type=int, default=24, help='Hours back')

    # summarize
    p_summarize = subparsers.add_parser('summarize', help='Create meeting summary')
    p_summarize.add_argument('event_id', help='Event ID')
    p_summarize.add_argument('--notes', required=True, help='Meeting notes')

    # remind
    p_remind = subparsers.add_parser('remind', help='Check for reminders')
    p_remind.add_argument('--minutes', type=int, default=30, help='Minutes ahead')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    commands = {
        'today': cmd_today,
        'upcoming': cmd_upcoming,
        'past': cmd_past,
        'summarize': cmd_summarize,
        'remind': cmd_remind
    }

    return commands[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
