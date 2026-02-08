#!/usr/bin/env python3
"""
Brain Entity Extraction - Extract and link entities from text

Usage:
    brain_entities.py extract "texte a analyser"
    brain_entities.py analyze MEMORY_ID
    brain_entities.py link-all [--dry-run]
    brain_entities.py list [--type TYPE]

Extracts: companies, products, people, and auto-links to existing memories.
"""

import argparse
import json
import logging
import os
import re
import sqlite3
import sys
from pathlib import Path

# Setup logging
LOG_DIR = Path(os.environ.get('MICHEL_LOG_DIR', os.path.expanduser('~/michel-avs/logs')))
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'brain_entities.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('brain_entities')

# Database path
DB_PATH = Path(os.environ.get('BRAIN_DB_PATH', os.path.expanduser('~/michel-avs/skills/avs-brain/brain.db')))

# Known AVS entities (loaded from KB or hardcoded)
AVS_PRODUCTS = [
    "Logic'S", "Logic'S Cloud", "Logic'S Mobile", "Logic'S Gestion",
    "Logic'S Encaissements", "Logic'S Fidelite", "Logic Display",
    "Totem", "Borne", "TPE", "Terminal", "Monetique",
    "Paxton", "Net2", "Controle d'acces"
]

AVS_COMPANIES = [
    "AVS", "AVS Technologies", "AVS Normandie",
    "Grenke", "Sellsy", "OVH", "Cloudflare"
]

# Patterns for entity detection
PATTERNS = {
    'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    'phone': r'\b(?:0|\+33)[1-9](?:[\s.-]?\d{2}){4}\b',
    'url': r'https?://[^\s<>"{}|\\^`\[\]]+',
    'ticket_ref': r'\b(?:TICKET|TKT|#)[-_]?\d+\b',
    'sujet_ref': r'\b(?:SUJET|SUJ|PRJ)[-_]?\d+\b',
}


def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def normalize_text(text):
    """Normalize text for matching"""
    return text.lower().strip()


def extract_entities(text):
    """Extract all entities from text"""
    entities = {
        'products': [],
        'companies': [],
        'people': [],
        'emails': [],
        'phones': [],
        'urls': [],
        'references': []
    }

    text_lower = text.lower()

    # Extract known products
    for product in AVS_PRODUCTS:
        if product.lower() in text_lower:
            if product not in entities['products']:
                entities['products'].append(product)

    # Extract known companies
    for company in AVS_COMPANIES:
        if company.lower() in text_lower:
            if company not in entities['companies']:
                entities['companies'].append(company)

    # Extract emails
    for match in re.finditer(PATTERNS['email'], text, re.IGNORECASE):
        email = match.group()
        if email not in entities['emails']:
            entities['emails'].append(email)

    # Extract phones
    for match in re.finditer(PATTERNS['phone'], text):
        phone = match.group()
        if phone not in entities['phones']:
            entities['phones'].append(phone)

    # Extract URLs
    for match in re.finditer(PATTERNS['url'], text):
        url = match.group()
        if url not in entities['urls']:
            entities['urls'].append(url)

    # Extract ticket/sujet references
    for match in re.finditer(PATTERNS['ticket_ref'], text, re.IGNORECASE):
        ref = match.group().upper()
        entities['references'].append({'type': 'ticket', 'ref': ref})

    for match in re.finditer(PATTERNS['sujet_ref'], text, re.IGNORECASE):
        ref = match.group().upper()
        entities['references'].append({'type': 'sujet', 'ref': ref})

    # Extract potential person names (capitalized words that aren't products/companies)
    # Simple heuristic: two consecutive capitalized words
    name_pattern = r'\b([A-Z][a-z]+)\s+([A-Z][a-z]+)\b'
    for match in re.finditer(name_pattern, text):
        full_name = f"{match.group(1)} {match.group(2)}"
        # Exclude known products/companies
        if full_name not in AVS_PRODUCTS and full_name not in AVS_COMPANIES:
            if full_name not in entities['people']:
                entities['people'].append(full_name)

    return entities


def find_related_memories(entities):
    """Find memories related to extracted entities"""
    conn = get_db()
    cursor = conn.cursor()

    related = []

    # Search for product memories
    for product in entities.get('products', []):
        cursor.execute("""
            SELECT id, title, type FROM memories
            WHERE type = 'product' AND title LIKE ?
            LIMIT 5
        """, (f'%{product}%',))
        for row in cursor.fetchall():
            related.append({
                'memory_id': row['id'],
                'title': row['title'],
                'type': row['type'],
                'matched_entity': product,
                'entity_type': 'product'
            })

    # Search for company memories
    for company in entities.get('companies', []):
        cursor.execute("""
            SELECT id, title, type FROM memories
            WHERE type = 'company' AND title LIKE ?
            LIMIT 5
        """, (f'%{company}%',))
        for row in cursor.fetchall():
            related.append({
                'memory_id': row['id'],
                'title': row['title'],
                'type': row['type'],
                'matched_entity': company,
                'entity_type': 'company'
            })

    # Search for person memories
    for person in entities.get('people', []):
        cursor.execute("""
            SELECT id, title, type FROM memories
            WHERE type = 'person' AND title LIKE ?
            LIMIT 5
        """, (f'%{person}%',))
        for row in cursor.fetchall():
            related.append({
                'memory_id': row['id'],
                'title': row['title'],
                'type': row['type'],
                'matched_entity': person,
                'entity_type': 'person'
            })

    conn.close()
    return related


def cmd_extract(args):
    """Extract entities from text"""
    entities = extract_entities(args.text)
    related = find_related_memories(entities)

    result = {
        'success': True,
        'entities': entities,
        'related_memories': related,
        'total_entities': sum(len(v) for v in entities.values() if isinstance(v, list))
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_analyze(args):
    """Analyze a specific memory and extract entities"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, title, content, type FROM memories WHERE id = ?
    """, (args.memory_id,))

    row = cursor.fetchone()
    if not row:
        print(json.dumps({'success': False, 'error': 'Memory not found'}))
        return 1

    # Combine title and content for analysis
    text = f"{row['title']} {row['content']}"
    entities = extract_entities(text)
    related = find_related_memories(entities)

    conn.close()

    result = {
        'success': True,
        'memory_id': row['id'],
        'memory_title': row['title'],
        'entities': entities,
        'related_memories': related
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_link_all(args):
    """Auto-link all memories based on entities"""
    logger.info("Starting auto-linking of all memories")

    conn = get_db()
    cursor = conn.cursor()

    # Get all memories
    cursor.execute("""
        SELECT id, title, content, type FROM memories
        WHERE consolidated_into IS NULL
    """)

    memories = cursor.fetchall()
    links_created = 0

    for mem in memories:
        text = f"{mem['title']} {mem['content']}"
        entities = extract_entities(text)
        related = find_related_memories(entities)

        for rel in related:
            if rel['memory_id'] == mem['id']:
                continue  # Don't link to self

            # Check if link already exists
            cursor.execute("""
                SELECT 1 FROM links
                WHERE from_id = ? AND to_id = ?
            """, (mem['id'], rel['memory_id']))

            if cursor.fetchone():
                continue  # Link already exists

            if args.dry_run:
                logger.info(f"Would link '{mem['title']}' -> '{rel['title']}' (entity: {rel['matched_entity']})")
                continue

            # Create link
            import uuid
            link_id = f"link_{uuid.uuid4().hex[:12]}"

            cursor.execute("""
                INSERT INTO links (id, from_id, to_id, relation_type, created_at)
                VALUES (?, ?, ?, 'related_to', datetime('now'))
            """, (link_id, mem['id'], rel['memory_id']))

            links_created += 1
            logger.info(f"Linked '{mem['title']}' -> '{rel['title']}'")

    if not args.dry_run:
        conn.commit()

    conn.close()

    result = {
        'success': True,
        'memories_analyzed': len(memories),
        'links_created': links_created,
        'dry_run': args.dry_run
    }

    print(json.dumps(result, indent=2))
    return 0


def cmd_list(args):
    """List all known entities"""
    entities = {
        'products': AVS_PRODUCTS,
        'companies': AVS_COMPANIES
    }

    if args.type:
        if args.type in entities:
            entities = {args.type: entities[args.type]}
        else:
            print(json.dumps({'success': False, 'error': f'Unknown type: {args.type}'}))
            return 1

    # Also get entities from database
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT type, title FROM memories
        WHERE type IN ('product', 'company', 'person')
        ORDER BY type, title
    """)

    db_entities = {'product': [], 'company': [], 'person': []}
    for row in cursor.fetchall():
        db_entities[row['type']].append(row['title'])

    conn.close()

    result = {
        'success': True,
        'known_entities': entities,
        'database_entities': db_entities
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def main():
    parser = argparse.ArgumentParser(description='Brain Entity Extraction')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # extract
    p_extract = subparsers.add_parser('extract', help='Extract entities from text')
    p_extract.add_argument('text', help='Text to analyze')

    # analyze
    p_analyze = subparsers.add_parser('analyze', help='Analyze a memory')
    p_analyze.add_argument('memory_id', help='Memory ID')

    # link-all
    p_link = subparsers.add_parser('link-all', help='Auto-link all memories')
    p_link.add_argument('--dry-run', action='store_true', help='Preview only')

    # list
    p_list = subparsers.add_parser('list', help='List known entities')
    p_list.add_argument('--type', choices=['products', 'companies'], help='Filter by type')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == 'extract':
        return cmd_extract(args)
    elif args.command == 'analyze':
        return cmd_analyze(args)
    elif args.command == 'link-all':
        return cmd_link_all(args)
    elif args.command == 'list':
        return cmd_list(args)


if __name__ == '__main__':
    sys.exit(main())
