#!/usr/bin/env python3
"""
AVS Brain Context - Charge le contexte pertinent avant de repondre

Usage:
    brain_context.py "message utilisateur"

Retourne le contexte pertinent depuis:
1. La memoire locale (SQLite + embeddings)
2. La Base de Connaissances AVS (optionnel)

Output: JSON avec les memoires pertinentes, pret a etre injecte dans le contexte.
"""

import sys
import json
import os
import sqlite3
import struct
from pathlib import Path

# Configuration
SKILL_DIR = Path(__file__).parent.parent
DATA_DIR = os.environ.get('AVS_BRAIN_DATA_DIR', SKILL_DIR / 'data')
DB_PATH = Path(DATA_DIR) / 'brain.db'
AVS_INTRANET_URL = os.environ.get('AVS_INTRANET_URL', 'https://intra.avstech.fr')
AVS_API_KEY = os.environ.get('AVS_API_KEY', '')
EMBEDDING_MODEL = 'all-MiniLM-L6-v2'

# Minimum score threshold for context inclusion
MIN_SCORE_THRESHOLD = 0.25
MAX_CONTEXT_ITEMS = 5

# Lazy-loaded embedding model
_embedding_model = None


def get_embedding_model():
    """Lazy load the embedding model"""
    global _embedding_model
    if _embedding_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
        except ImportError:
            return None
    return _embedding_model


def compute_embedding(text):
    """Compute embedding for text"""
    model = get_embedding_model()
    if model is None:
        return None
    return model.encode(text, convert_to_numpy=True)


def blob_to_embedding(blob):
    """Convert blob back to list"""
    if blob is None:
        return None
    num_floats = len(blob) // 4
    return list(struct.unpack(f'{num_floats}f', blob))


def cosine_similarity(vec1, vec2):
    """Compute cosine similarity between two vectors"""
    if vec1 is None or vec2 is None:
        return 0.0
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = sum(a * a for a in vec1) ** 0.5
    norm2 = sum(b * b for b in vec2) ** 0.5
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot_product / (norm1 * norm2)


def search_local(query, limit=10):
    """Search local brain with hybrid scoring"""
    if not DB_PATH.exists():
        return []

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Compute query embedding
    query_embedding = compute_embedding(query)
    query_embedding_list = list(query_embedding) if query_embedding is not None else None

    # Get all memories with embeddings
    rows = conn.execute("""
        SELECT m.id, m.title, m.content, m.type, m.importance, m.tags, e.vector
        FROM memories m
        LEFT JOIN embeddings e ON m.id = e.memory_id
    """).fetchall()

    results = []
    for row in rows:
        # Text match score
        text_match = 1.0 if (query.lower() in row['title'].lower() or
                           query.lower() in row['content'].lower()) else 0.0

        # Semantic similarity
        semantic_score = 0.0
        if query_embedding_list is not None and row['vector']:
            mem_embedding = blob_to_embedding(row['vector'])
            semantic_score = float(cosine_similarity(query_embedding_list, mem_embedding))

        # Combined score
        combined_score = 0.4 * text_match + 0.6 * semantic_score

        if combined_score >= MIN_SCORE_THRESHOLD or text_match > 0:
            results.append({
                'id': row['id'],
                'title': row['title'],
                'content': row['content'],
                'type': row['type'],
                'importance': row['importance'],
                'score': round(combined_score, 3),
                'source': 'local'
            })

    # Sort by score then importance
    results.sort(key=lambda x: (x['score'], x['importance']), reverse=True)
    conn.close()
    return results[:limit]


def search_avs(query, limit=5):
    """Search AVS Knowledge Base"""
    if not AVS_API_KEY:
        return []

    try:
        import urllib.request

        data = json.dumps({
            'query': query,
            'maxNodes': limit,
            'maxDepth': 1,
            'includeEntities': True
        }).encode('utf-8')

        req = urllib.request.Request(
            f'{AVS_INTRANET_URL}/api/external/knowledge/context',
            data=data,
            headers={
                'Content-Type': 'application/json',
                'X-API-Key': AVS_API_KEY
            },
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode('utf-8'))
            return [{
                'id': f"avs_{node['id']}",
                'title': node['title'],
                'content': node.get('content', ''),
                'type': node.get('type', 'concept'),
                'source': 'avs_kb'
            } for node in result.get('nodes', [])]
    except Exception:
        return []


def format_context(memories, avs_results):
    """Format context as markdown for injection"""
    if not memories and not avs_results:
        return None

    lines = ["## Contexte pertinent de ma memoire\n"]

    if memories:
        lines.append("### Memoire locale")
        for mem in memories:
            lines.append(f"**{mem['title']}** ({mem['type']}, score: {mem['score']})")
            lines.append(f"> {mem['content'][:300]}{'...' if len(mem['content']) > 300 else ''}")
            lines.append("")

    if avs_results:
        lines.append("### Base de Connaissances AVS")
        for item in avs_results:
            lines.append(f"**{item['title']}** ({item['type']})")
            if item.get('content'):
                lines.append(f"> {item['content'][:200]}{'...' if len(item.get('content', '')) > 200 else ''}")
            lines.append("")

    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            'success': False,
            'error': 'Usage: brain_context.py "message"'
        }))
        return 1

    query = sys.argv[1]

    # Search local brain
    local_results = search_local(query, MAX_CONTEXT_ITEMS)

    # Search AVS KB (only if we have results locally or explicit AVS content)
    avs_results = []
    avs_keywords = ['avs', 'logic', 'sellsy', 'intranet', 'client', 'ticket', 'sujet']
    if any(kw in query.lower() for kw in avs_keywords):
        avs_results = search_avs(query, 3)

    # Format output
    context_md = format_context(local_results, avs_results)

    output = {
        'success': True,
        'query': query,
        'local_count': len(local_results),
        'avs_count': len(avs_results),
        'has_context': context_md is not None,
        'context_markdown': context_md,
        'memories': local_results[:3],  # Top 3 for structured access
        'avs_items': avs_results[:2]    # Top 2 AVS items
    }

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
