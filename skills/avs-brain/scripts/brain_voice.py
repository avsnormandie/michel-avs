#!/usr/bin/env python3
"""
Brain Voice - Audio transcription for Michel

Usage:
    brain_voice.py transcribe FILE [--language fr]
    brain_voice.py transcribe-url URL [--language fr]
    brain_voice.py summarize FILE [--language fr]

Transcribes audio messages using Google Gemini API.
Supports: mp3, wav, ogg, m4a, webm
"""

import argparse
import base64
import json
import logging
import os
import sys
import tempfile
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
        logging.FileHandler(LOG_DIR / 'brain_voice.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('brain_voice')

# Configuration
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
GEMINI_API_URL = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent'

# MIME types
MIME_TYPES = {
    '.mp3': 'audio/mp3',
    '.wav': 'audio/wav',
    '.ogg': 'audio/ogg',
    '.m4a': 'audio/mp4',
    '.webm': 'audio/webm',
    '.oga': 'audio/ogg',
}


def transcribe_with_gemini(audio_data, mime_type, language='fr', task='transcribe'):
    """Transcribe audio using Gemini API"""
    if not GEMINI_API_KEY:
        return {'success': False, 'error': 'GEMINI_API_KEY not configured'}

    # Encode audio to base64
    audio_base64 = base64.b64encode(audio_data).decode('utf-8')

    # Build prompt based on task
    if task == 'summarize':
        prompt = f"""Ecoute cet audio et fournis:
1. Une transcription complete
2. Un resume en 2-3 phrases
3. Les points cles mentionnes
4. Le ton general (urgent, informatif, question, etc.)

Langue de l'audio: {language}
Reponds en francais."""
    else:
        prompt = f"""Transcris cet audio en texte.
Langue de l'audio: {language}
Fournis uniquement la transcription, sans commentaires."""

    # Build request
    request_data = {
        'contents': [{
            'parts': [
                {'text': prompt},
                {
                    'inline_data': {
                        'mime_type': mime_type,
                        'data': audio_base64
                    }
                }
            ]
        }],
        'generationConfig': {
            'temperature': 0.1,
            'maxOutputTokens': 2048
        }
    }

    url = f"{GEMINI_API_URL}?key={GEMINI_API_KEY}"
    headers = {'Content-Type': 'application/json'}
    req_data = json.dumps(request_data).encode('utf-8')

    try:
        req = urllib.request.Request(url, data=req_data, headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))

        # Extract text from response
        candidates = result.get('candidates', [])
        if candidates:
            content = candidates[0].get('content', {})
            parts = content.get('parts', [])
            if parts:
                text = parts[0].get('text', '')
                return {'success': True, 'transcription': text.strip()}

        return {'success': False, 'error': 'No transcription in response'}

    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else ''
        logger.error(f"Gemini API error: {e.code} - {error_body}")
        return {'success': False, 'error': f'API error: {e.code}'}
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        return {'success': False, 'error': str(e)}


def download_file(url):
    """Download file from URL"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.read()
    except Exception as e:
        logger.error(f"Download error: {e}")
        return None


def get_mime_type(file_path):
    """Get MIME type from file extension"""
    ext = Path(file_path).suffix.lower()
    return MIME_TYPES.get(ext, 'audio/mpeg')


def cmd_transcribe(args):
    """Transcribe audio file"""
    file_path = Path(args.file)

    if not file_path.exists():
        print(json.dumps({'success': False, 'error': f'File not found: {file_path}'}))
        return 1

    logger.info(f"Transcribing: {file_path}")

    # Read file
    with open(file_path, 'rb') as f:
        audio_data = f.read()

    mime_type = get_mime_type(file_path)
    result = transcribe_with_gemini(audio_data, mime_type, args.language)

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get('success') else 1


def cmd_transcribe_url(args):
    """Transcribe audio from URL"""
    logger.info(f"Downloading: {args.url}")

    audio_data = download_file(args.url)
    if not audio_data:
        print(json.dumps({'success': False, 'error': 'Failed to download audio'}))
        return 1

    # Try to detect MIME type from URL
    mime_type = 'audio/ogg'  # Default for Telegram voice messages
    url_lower = args.url.lower()
    for ext, mtype in MIME_TYPES.items():
        if ext in url_lower:
            mime_type = mtype
            break

    result = transcribe_with_gemini(audio_data, mime_type, args.language)

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get('success') else 1


def cmd_summarize(args):
    """Transcribe and summarize audio"""
    file_path = Path(args.file)

    if not file_path.exists():
        print(json.dumps({'success': False, 'error': f'File not found: {file_path}'}))
        return 1

    logger.info(f"Summarizing: {file_path}")

    with open(file_path, 'rb') as f:
        audio_data = f.read()

    mime_type = get_mime_type(file_path)
    result = transcribe_with_gemini(audio_data, mime_type, args.language, task='summarize')

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get('success') else 1


def main():
    parser = argparse.ArgumentParser(description='Brain Voice - Audio Transcription')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # transcribe
    p_transcribe = subparsers.add_parser('transcribe', help='Transcribe audio file')
    p_transcribe.add_argument('file', help='Audio file path')
    p_transcribe.add_argument('--language', default='fr', help='Audio language')

    # transcribe-url
    p_url = subparsers.add_parser('transcribe-url', help='Transcribe audio from URL')
    p_url.add_argument('url', help='Audio URL')
    p_url.add_argument('--language', default='fr', help='Audio language')

    # summarize
    p_summarize = subparsers.add_parser('summarize', help='Transcribe and summarize')
    p_summarize.add_argument('file', help='Audio file path')
    p_summarize.add_argument('--language', default='fr', help='Audio language')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    commands = {
        'transcribe': cmd_transcribe,
        'transcribe-url': cmd_transcribe_url,
        'summarize': cmd_summarize
    }

    return commands[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
