#!/usr/bin/env python3
"""
Brain Invoices - Invoice and PDF analysis

Usage:
    brain_invoices.py analyze FILE
    brain_invoices.py extract FILE --type invoice|contract|quote
    brain_invoices.py compare FILE1 FILE2
    brain_invoices.py grenke FILE
    brain_invoices.py summary FILE

Analyzes invoices and documents using vision AI.
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
        logging.FileHandler(LOG_DIR / 'brain_invoices.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('brain_invoices')

# Configuration
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
GEMINI_API_URL = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent'


def analyze_with_gemini(file_data, mime_type, prompt, max_tokens=4096):
    """Analyze document using Gemini API"""
    if not GEMINI_API_KEY:
        return {'success': False, 'error': 'GEMINI_API_KEY not configured'}

    file_base64 = base64.b64encode(file_data).decode('utf-8')

    request_data = {
        'contents': [{
            'parts': [
                {'text': prompt},
                {
                    'inline_data': {
                        'mime_type': mime_type,
                        'data': file_base64
                    }
                }
            ]
        }],
        'generationConfig': {
            'temperature': 0.1,
            'maxOutputTokens': max_tokens
        }
    }

    url = f"{GEMINI_API_URL}?key={GEMINI_API_KEY}"
    headers = {'Content-Type': 'application/json'}
    req_data = json.dumps(request_data).encode('utf-8')

    try:
        req = urllib.request.Request(url, data=req_data, headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode('utf-8'))

        candidates = result.get('candidates', [])
        if candidates:
            content = candidates[0].get('content', {})
            parts = content.get('parts', [])
            if parts:
                text = parts[0].get('text', '')
                return {'success': True, 'analysis': text.strip()}

        return {'success': False, 'error': 'No analysis in response'}

    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else ''
        logger.error(f"Gemini API error: {e.code} - {error_body}")
        return {'success': False, 'error': f'API error: {e.code}'}
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        return {'success': False, 'error': str(e)}


def get_mime_type(file_path):
    """Get MIME type from file extension"""
    ext = Path(file_path).suffix.lower()
    mime_types = {
        '.pdf': 'application/pdf',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
    }
    return mime_types.get(ext, 'application/pdf')


def cmd_analyze(args):
    """Analyze any document"""
    file_path = Path(args.file)

    if not file_path.exists():
        print(json.dumps({'success': False, 'error': f'File not found: {file_path}'}))
        return 1

    logger.info(f"Analyzing: {file_path}")

    with open(file_path, 'rb') as f:
        file_data = f.read()

    mime_type = get_mime_type(file_path)

    prompt = """Analyse ce document et fournis:

1. **Type de document**: (facture, devis, contrat, courrier, etc.)
2. **Emetteur**: Nom et coordonnees
3. **Destinataire**: Nom et coordonnees
4. **Date**: Date du document
5. **Reference**: Numero de reference/facture
6. **Montants**:
   - Sous-total HT
   - TVA
   - Total TTC
7. **Lignes principales**: Liste des articles/services
8. **Informations de paiement**: Mode, echeance, RIB
9. **Notes importantes**: Conditions particulieres

Reponds en francais avec un format structure."""

    result = analyze_with_gemini(file_data, mime_type, prompt)

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get('success') else 1


def cmd_extract(args):
    """Extract structured data from document"""
    file_path = Path(args.file)

    if not file_path.exists():
        print(json.dumps({'success': False, 'error': f'File not found: {file_path}'}))
        return 1

    logger.info(f"Extracting from: {file_path} (type: {args.type})")

    with open(file_path, 'rb') as f:
        file_data = f.read()

    mime_type = get_mime_type(file_path)

    if args.type == 'invoice':
        prompt = """Extrais les donnees de cette facture au format JSON strict:

{
  "type": "invoice",
  "vendor": {
    "name": "...",
    "address": "...",
    "siret": "...",
    "vat_number": "..."
  },
  "customer": {
    "name": "...",
    "address": "..."
  },
  "invoice_number": "...",
  "invoice_date": "YYYY-MM-DD",
  "due_date": "YYYY-MM-DD",
  "items": [
    {
      "description": "...",
      "quantity": 1,
      "unit_price_ht": 0.00,
      "vat_rate": "20%",
      "total_ht": 0.00
    }
  ],
  "subtotal_ht": 0.00,
  "vat_amount": 0.00,
  "total_ttc": 0.00,
  "payment_method": "...",
  "payment_due": "..."
}

Reponds UNIQUEMENT avec le JSON, sans texte supplementaire."""

    elif args.type == 'contract':
        prompt = """Extrais les donnees de ce contrat au format JSON strict:

{
  "type": "contract",
  "contract_type": "location/vente/service/...",
  "parties": [
    {"role": "bailleur/vendeur", "name": "...", "address": "..."},
    {"role": "preneur/acheteur", "name": "...", "address": "..."}
  ],
  "reference": "...",
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "duration": "... mois",
  "object": "description du contrat",
  "monthly_amount": 0.00,
  "total_amount": 0.00,
  "payment_terms": "...",
  "special_conditions": ["..."],
  "renewal": "tacite reconduction / non"
}

Reponds UNIQUEMENT avec le JSON, sans texte supplementaire."""

    else:  # quote
        prompt = """Extrais les donnees de ce devis au format JSON strict:

{
  "type": "quote",
  "vendor": {
    "name": "...",
    "address": "..."
  },
  "customer": {
    "name": "...",
    "address": "..."
  },
  "quote_number": "...",
  "quote_date": "YYYY-MM-DD",
  "valid_until": "YYYY-MM-DD",
  "items": [
    {
      "description": "...",
      "quantity": 1,
      "unit_price_ht": 0.00,
      "total_ht": 0.00
    }
  ],
  "subtotal_ht": 0.00,
  "vat_amount": 0.00,
  "total_ttc": 0.00,
  "conditions": "..."
}

Reponds UNIQUEMENT avec le JSON, sans texte supplementaire."""

    result = analyze_with_gemini(file_data, mime_type, prompt)

    if result.get('success'):
        try:
            analysis = result['analysis']
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


def cmd_grenke(args):
    """Parse Grenke leasing contract"""
    file_path = Path(args.file)

    if not file_path.exists():
        print(json.dumps({'success': False, 'error': f'File not found: {file_path}'}))
        return 1

    logger.info(f"Parsing Grenke contract: {file_path}")

    with open(file_path, 'rb') as f:
        file_data = f.read()

    mime_type = get_mime_type(file_path)

    prompt = """Analyse ce contrat de leasing Grenke et extrais au format JSON:

{
  "contract_number": "numero du contrat",
  "lessor": "Grenke...",
  "lessee": {
    "name": "nom du client",
    "address": "adresse complete",
    "siret": "numero SIRET"
  },
  "equipment": [
    {
      "description": "description du materiel",
      "brand": "marque",
      "model": "modele",
      "serial": "numero de serie",
      "quantity": 1
    }
  ],
  "financial": {
    "equipment_value": 0.00,
    "monthly_payment_ht": 0.00,
    "monthly_payment_ttc": 0.00,
    "duration_months": 0,
    "first_payment": "YYYY-MM-DD",
    "total_amount": 0.00
  },
  "dates": {
    "signature_date": "YYYY-MM-DD",
    "start_date": "YYYY-MM-DD",
    "end_date": "YYYY-MM-DD"
  },
  "options": {
    "maintenance": true/false,
    "insurance": true/false,
    "buyout": "conditions de rachat"
  }
}

Reponds UNIQUEMENT avec le JSON."""

    result = analyze_with_gemini(file_data, mime_type, prompt)

    if result.get('success'):
        try:
            analysis = result['analysis']
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


def cmd_compare(args):
    """Compare two documents"""
    file1 = Path(args.file1)
    file2 = Path(args.file2)

    if not file1.exists() or not file2.exists():
        print(json.dumps({'success': False, 'error': 'One or both files not found'}))
        return 1

    logger.info(f"Comparing: {file1} vs {file2}")

    # For now, just analyze both and return
    with open(file1, 'rb') as f:
        data1 = f.read()
    with open(file2, 'rb') as f:
        data2 = f.read()

    # Analyze first document
    result1 = analyze_with_gemini(
        data1,
        get_mime_type(file1),
        "Resume ce document en 3 lignes avec les montants cles."
    )

    result2 = analyze_with_gemini(
        data2,
        get_mime_type(file2),
        "Resume ce document en 3 lignes avec les montants cles."
    )

    output = {
        'success': True,
        'document1': {
            'file': str(file1),
            'summary': result1.get('analysis', 'Error')
        },
        'document2': {
            'file': str(file2),
            'summary': result2.get('analysis', 'Error')
        }
    }

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


def cmd_summary(args):
    """Quick summary of document"""
    file_path = Path(args.file)

    if not file_path.exists():
        print(json.dumps({'success': False, 'error': f'File not found: {file_path}'}))
        return 1

    logger.info(f"Summarizing: {file_path}")

    with open(file_path, 'rb') as f:
        file_data = f.read()

    mime_type = get_mime_type(file_path)

    prompt = """Resume ce document en francais:

1. Type de document (1 mot)
2. Emetteur
3. Destinataire
4. Montant total
5. Date
6. Points importants (2-3 bullet points)

Format compact, pas de longs paragraphes."""

    result = analyze_with_gemini(file_data, mime_type, prompt)

    if result.get('success'):
        result['summary'] = result.pop('analysis')

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get('success') else 1


def main():
    parser = argparse.ArgumentParser(description='Brain Invoices - Document Analysis')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # analyze
    p_analyze = subparsers.add_parser('analyze', help='Analyze document')
    p_analyze.add_argument('file', help='Document file (PDF/image)')

    # extract
    p_extract = subparsers.add_parser('extract', help='Extract structured data')
    p_extract.add_argument('file', help='Document file')
    p_extract.add_argument('--type', choices=['invoice', 'contract', 'quote'], required=True)

    # compare
    p_compare = subparsers.add_parser('compare', help='Compare two documents')
    p_compare.add_argument('file1', help='First document')
    p_compare.add_argument('file2', help='Second document')

    # grenke
    p_grenke = subparsers.add_parser('grenke', help='Parse Grenke contract')
    p_grenke.add_argument('file', help='Grenke contract PDF')

    # summary
    p_summary = subparsers.add_parser('summary', help='Quick summary')
    p_summary.add_argument('file', help='Document file')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    commands = {
        'analyze': cmd_analyze,
        'extract': cmd_extract,
        'compare': cmd_compare,
        'grenke': cmd_grenke,
        'summary': cmd_summary
    }

    return commands[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
