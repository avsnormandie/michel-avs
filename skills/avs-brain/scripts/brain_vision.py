#!/usr/bin/env python3
"""
Brain Vision - Image analysis for Michel

Usage:
    brain_vision.py analyze FILE [--prompt "question about image"]
    brain_vision.py analyze-url URL [--prompt "question"]
    brain_vision.py ocr FILE
    brain_vision.py describe FILE
    brain_vision.py extract-data FILE [--type invoice|receipt|document]

Analyzes images using Claude Vision API.
Supports: jpg, jpeg, png, gif, webp
"""

import argparse
import base64
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
        logging.FileHandler(LOG_DIR / 'brain_vision.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('brain_vision')

# Configuration
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
ANTHROPIC_API_URL = 'https://api.anthropic.com/v1/messages'

# MIME types
MIME_TYPES = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
}


def analyze_with_claude(image_data, mime_type, prompt, max_tokens=2048):
    """Analyze image using Claude Vision API"""
    if not ANTHROPIC_API_KEY:
        return {'success': False, 'error': 'ANTHROPIC_API_KEY not configured'}

    # Encode image to base64
    image_base64 = base64.b64encode(image_data).decode('utf-8')

    # Build request
    request_data = {
        'model': 'claude-sonnet-4-20250514',
        'max_tokens': max_tokens,
        'messages': [{
            'role': 'user',
            'content': [
                {
                    'type': 'image',
                    'source': {
                        'type': 'base64',
                        'media_type': mime_type,
                        'data': image_base64
                    }
                },
                {
                    'type': 'text',
                    'text': prompt
                }
            ]
        }]
    }

    headers = {
        'Content-Type': 'application/json',
        'x-api-key': ANTHROPIC_API_KEY,
        'anthropic-version': '2023-06-01'
    }

    req_data = json.dumps(request_data).encode('utf-8')

    try:
        req = urllib.request.Request(ANTHROPIC_API_URL, data=req_data, headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))

        # Extract text from response
        content = result.get('content', [])
        if content:
            text = content[0].get('text', '')
            return {'success': True, 'analysis': text.strip()}

        return {'success': False, 'error': 'No analysis in response'}

    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else ''
        logger.error(f"Claude API error: {e.code} - {error_body}")
        return {'success': False, 'error': f'API error: {e.code}'}
    except Exception as e:
        logger.error(f"Analysis error: {e}")
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
    return MIME_TYPES.get(ext, 'image/jpeg')


def cmd_analyze(args):
    """Analyze image with custom prompt"""
    file_path = Path(args.file)

    if not file_path.exists():
        print(json.dumps({'success': False, 'error': f'File not found: {file_path}'}))
        return 1

    logger.info(f"Analyzing: {file_path}")

    with open(file_path, 'rb') as f:
        image_data = f.read()

    mime_type = get_mime_type(file_path)
    prompt = args.prompt or "Decris cette image en detail. Que vois-tu?"

    result = analyze_with_claude(image_data, mime_type, prompt)

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get('success') else 1


def cmd_analyze_url(args):
    """Analyze image from URL"""
    logger.info(f"Downloading: {args.url}")

    image_data = download_file(args.url)
    if not image_data:
        print(json.dumps({'success': False, 'error': 'Failed to download image'}))
        return 1

    # Detect MIME type from URL
    mime_type = 'image/jpeg'
    url_lower = args.url.lower()
    for ext, mtype in MIME_TYPES.items():
        if ext in url_lower:
            mime_type = mtype
            break

    prompt = args.prompt or "Decris cette image en detail. Que vois-tu?"

    result = analyze_with_claude(image_data, mime_type, prompt)

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get('success') else 1


def cmd_ocr(args):
    """Extract text from image (OCR)"""
    file_path = Path(args.file)

    if not file_path.exists():
        print(json.dumps({'success': False, 'error': f'File not found: {file_path}'}))
        return 1

    logger.info(f"OCR: {file_path}")

    with open(file_path, 'rb') as f:
        image_data = f.read()

    mime_type = get_mime_type(file_path)
    prompt = """Extrais tout le texte visible dans cette image.
Conserve la mise en forme autant que possible (paragraphes, listes, tableaux).
Ne commente pas, fournis uniquement le texte extrait."""

    result = analyze_with_claude(image_data, mime_type, prompt)

    if result.get('success'):
        result['text'] = result.pop('analysis')

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get('success') else 1


def cmd_describe(args):
    """Generate detailed description"""
    file_path = Path(args.file)

    if not file_path.exists():
        print(json.dumps({'success': False, 'error': f'File not found: {file_path}'}))
        return 1

    logger.info(f"Describing: {file_path}")

    with open(file_path, 'rb') as f:
        image_data = f.read()

    mime_type = get_mime_type(file_path)
    prompt = """Fournis une description detaillee de cette image:

1. **Description generale**: Que represente cette image?
2. **Elements principaux**: Liste les objets/personnes/textes visibles
3. **Contexte**: Quel est le contexte probable (bureau, magasin, document...)?
4. **Details techniques**: Qualite, couleurs dominantes, mise en page
5. **Informations utiles**: Donnees importantes a retenir

Reponds en francais."""

    result = analyze_with_claude(image_data, mime_type, prompt)

    if result.get('success'):
        result['description'] = result.pop('analysis')

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get('success') else 1


def cmd_extract_data(args):
    """Extract structured data from document image"""
    file_path = Path(args.file)

    if not file_path.exists():
        print(json.dumps({'success': False, 'error': f'File not found: {file_path}'}))
        return 1

    logger.info(f"Extracting data: {file_path} (type: {args.type})")

    with open(file_path, 'rb') as f:
        image_data = f.read()

    mime_type = get_mime_type(file_path)

    if args.type == 'invoice':
        prompt = """Extrais les informations de cette facture au format JSON:
{
  "vendor": "nom du fournisseur",
  "vendor_address": "adresse complete",
  "invoice_number": "numero de facture",
  "invoice_date": "date (YYYY-MM-DD)",
  "due_date": "date d'echeance",
  "customer": "nom du client",
  "items": [{"description": "...", "quantity": 1, "unit_price": 0.00, "total": 0.00}],
  "subtotal": 0.00,
  "tax_rate": "20%",
  "tax_amount": 0.00,
  "total": 0.00,
  "payment_info": "informations de paiement"
}
Reponds UNIQUEMENT avec le JSON, sans commentaires."""

    elif args.type == 'receipt':
        prompt = """Extrais les informations de ce ticket de caisse au format JSON:
{
  "store": "nom du magasin",
  "date": "date (YYYY-MM-DD)",
  "time": "heure",
  "items": [{"name": "...", "price": 0.00}],
  "subtotal": 0.00,
  "tax": 0.00,
  "total": 0.00,
  "payment_method": "CB/especes/etc"
}
Reponds UNIQUEMENT avec le JSON, sans commentaires."""

    else:  # document
        prompt = """Extrais les informations cles de ce document au format JSON:
{
  "type": "type de document",
  "title": "titre ou objet",
  "date": "date si presente",
  "sender": "expediteur/emetteur",
  "recipient": "destinataire",
  "reference": "numero de reference",
  "key_points": ["point 1", "point 2"],
  "amounts": [{"description": "...", "amount": 0.00}],
  "action_required": "action a prendre si mentionnee"
}
Reponds UNIQUEMENT avec le JSON, sans commentaires."""

    result = analyze_with_claude(image_data, mime_type, prompt, max_tokens=4096)

    if result.get('success'):
        # Try to parse JSON from response
        try:
            analysis = result['analysis']
            # Find JSON in response
            if '{' in analysis:
                json_start = analysis.find('{')
                json_end = analysis.rfind('}') + 1
                json_str = analysis[json_start:json_end]
                result['data'] = json.loads(json_str)
                result.pop('analysis')
        except json.JSONDecodeError:
            result['raw'] = result.pop('analysis')

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get('success') else 1


def main():
    parser = argparse.ArgumentParser(description='Brain Vision - Image Analysis')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # analyze
    p_analyze = subparsers.add_parser('analyze', help='Analyze image with prompt')
    p_analyze.add_argument('file', help='Image file path')
    p_analyze.add_argument('--prompt', help='Question or prompt')

    # analyze-url
    p_url = subparsers.add_parser('analyze-url', help='Analyze image from URL')
    p_url.add_argument('url', help='Image URL')
    p_url.add_argument('--prompt', help='Question or prompt')

    # ocr
    p_ocr = subparsers.add_parser('ocr', help='Extract text (OCR)')
    p_ocr.add_argument('file', help='Image file path')

    # describe
    p_describe = subparsers.add_parser('describe', help='Detailed description')
    p_describe.add_argument('file', help='Image file path')

    # extract-data
    p_extract = subparsers.add_parser('extract-data', help='Extract structured data')
    p_extract.add_argument('file', help='Image file path')
    p_extract.add_argument('--type', choices=['invoice', 'receipt', 'document'], default='document')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    commands = {
        'analyze': cmd_analyze,
        'analyze-url': cmd_analyze_url,
        'ocr': cmd_ocr,
        'describe': cmd_describe,
        'extract-data': cmd_extract_data
    }

    return commands[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
