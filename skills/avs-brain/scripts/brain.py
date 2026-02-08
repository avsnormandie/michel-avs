#!/usr/bin/env python3
"""
AVS Brain - Cerveau local de Michel avec embeddings

Usage:
    brain.py remember --title TITLE --content CONTENT --type TYPE [--importance N] [--tags TAGS]
    brain.py search QUERY [--type TYPE] [--limit N] [--include-avs|--local-only]
    brain.py link --from FROM_ID --to TO_ID --type TYPE [--bidirectional]
    brain.py forget ID [--reason REASON]
    brain.py sync [--direction DIR]
    brain.py stats
    brain.py reindex  # Regenerate all embeddings
"""

import argparse
import sqlite3
import os
import json
import secrets
import sys
import struct
from datetime import datetime
from pathlib import Path

# Configuration
SKILL_DIR = Path(__file__).parent.parent
DATA_DIR = os.environ.get('AVS_BRAIN_DATA_DIR', SKILL_DIR / 'data')
DB_PATH = Path(DATA_DIR) / 'brain.db'
AVS_INTRANET_URL = os.environ.get('AVS_INTRANET_URL', 'https://intra.avstech.fr')
AVS_API_KEY = os.environ.get('AVS_API_KEY', '')
EMBEDDING_MODEL = 'all-MiniLM-L6-v2'

VALID_TYPES = ['product', 'company', 'person', 'concept', 'decision', 'resource', 'memory', 'conversation']
VALID_RELATIONS = ['related_to', 'depends_on', 'implements', 'part_of', 'supersedes', 'used_by', 'created_by']

# Lazy-loaded embedding model
_embedding_model = None


def get_embedding_model():
    """Lazy load the embedding model"""
    global _embedding_model
    if _embedding_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            print(f"[AVS Brain] Loading embedding model {EMBEDDING_MODEL}...", file=sys.stderr)
            _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
            print(f"[AVS Brain] Model loaded", file=sys.stderr)
        except ImportError:
            print("[AVS Brain] sentence-transformers not installed, embeddings disabled", file=sys.stderr)
            return None
    return _embedding_model


def compute_embedding(text):
    """Compute embedding for text"""
    model = get_embedding_model()
    if model is None:
        return None
    embedding = model.encode(text, convert_to_numpy=True)
    return embedding


def embedding_to_blob(embedding):
    """Convert numpy array to blob for SQLite"""
    if embedding is None:
        return None
    return struct.pack(f'{len(embedding)}f', *embedding.tolist())


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


def generate_id(prefix='mem'):
    return f"{prefix}_{secrets.token_hex(8)}"


def init_db():
    """Initialize the database with schema"""
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            importance INTEGER DEFAULT 50,
            tags TEXT,
            avs_node_id TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            synced_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type);
        CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance);

        CREATE TABLE IF NOT EXISTS embeddings (
            memory_id TEXT PRIMARY KEY REFERENCES memories(id) ON DELETE CASCADE,
            vector BLOB NOT NULL,
            model TEXT DEFAULT 'all-MiniLM-L6-v2',
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS links (
            id TEXT PRIMARY KEY,
            from_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
            to_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
            relation_type TEXT NOT NULL,
            weight REAL DEFAULT 1.0,
            avs_edge_id TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(from_id, to_id, relation_type)
        );

        CREATE INDEX IF NOT EXISTS idx_links_from_id ON links(from_id);
        CREATE INDEX IF NOT EXISTS idx_links_to_id ON links(to_id);

        CREATE TABLE IF NOT EXISTS sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            memory_id TEXT,
            action TEXT,
            status TEXT,
            avs_node_id TEXT,
            details TEXT,
            timestamp TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS brain_meta (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        );

        INSERT OR IGNORE INTO brain_meta (key, value) VALUES ('schema_version', '2.0.0');
        INSERT OR IGNORE INTO brain_meta (key, value) VALUES ('created_at', datetime('now'));
    """)

    conn.commit()
    return conn


def store_embedding(conn, memory_id, text):
    """Compute and store embedding for a memory"""
    embedding = compute_embedding(text)
    if embedding is not None:
        blob = embedding_to_blob(embedding)
        conn.execute("""
            INSERT OR REPLACE INTO embeddings (memory_id, vector, model)
            VALUES (?, ?, ?)
        """, (memory_id, blob, EMBEDDING_MODEL))
        conn.commit()
        return True
    return False


def cmd_remember(args):
    """Store a new memory"""
    conn = init_db()

    if args.type not in VALID_TYPES:
        print(json.dumps({'success': False, 'error': f"Invalid type. Valid: {', '.join(VALID_TYPES)}"}))
        return 1

    memory_id = generate_id('mem')
    tags_json = json.dumps(args.tags.split(',') if args.tags else [])

    conn.execute("""
        INSERT INTO memories (id, title, content, type, importance, tags)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (memory_id, args.title, args.content, args.type, args.importance, tags_json))
    conn.commit()

    # Store embedding
    embed_text = f"{args.title} {args.content}"
    has_embedding = store_embedding(conn, memory_id, embed_text)

    result = {
        'success': True,
        'id': memory_id,
        'title': args.title,
        'type': args.type,
        'importance': args.importance,
        'has_embedding': has_embedding,
        'will_sync': args.importance >= 70,
        'message': f'Memoire "{args.title}" enregistree'
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))

    # Auto-sync if importance >= 70
    if args.importance >= 70 and AVS_API_KEY:
        sync_to_avs(conn, memory_id)

    conn.close()
    return 0


def cmd_search(args):
    """Search memories with hybrid scoring (FTS + semantic)"""
    conn = init_db()
    query = args.query
    results = []

    # Compute query embedding for semantic search
    query_embedding = compute_embedding(query)

    # Get all memories that match text search OR have embeddings
    sql = """
        SELECT m.id, m.title, m.content, m.type, m.importance, m.tags, m.avs_node_id,
               m.created_at, m.updated_at, e.vector
        FROM memories m
        LEFT JOIN embeddings e ON m.id = e.memory_id
        WHERE m.title LIKE ? OR m.content LIKE ? OR m.tags LIKE ? OR e.vector IS NOT NULL
    """
    params = [f'%{query}%', f'%{query}%', f'%{query}%']

    if args.type:
        sql += " AND m.type = ?"
        params.append(args.type)

    rows = conn.execute(sql, params).fetchall()

    # Score and rank results
    scored_results = []
    for row in rows:
        # Text match score (simple: 1 if matches, 0 otherwise)
        text_match = 1.0 if (query.lower() in row['title'].lower() or
                           query.lower() in row['content'].lower()) else 0.0

        # Semantic similarity score
        semantic_score = 0.0
        if query_embedding is not None and row['vector']:
            mem_embedding = blob_to_embedding(row['vector'])
            semantic_score = float(cosine_similarity(list(query_embedding), mem_embedding))

        # Combined score: 40% text match + 60% semantic (semantic is more nuanced)
        combined_score = 0.4 * text_match + 0.6 * semantic_score

        # Only include if there is some relevance
        if combined_score > 0.1 or text_match > 0:
            scored_results.append({
                'id': row['id'],
                'title': row['title'],
                'content': row['content'][:200] + ('...' if len(row['content']) > 200 else ''),
                'type': row['type'],
                'importance': row['importance'],
                'tags': json.loads(row['tags'] or '[]'),
                'source': 'local',
                'avs_node_id': row['avs_node_id'],
                'score': round(combined_score, 3),
                'text_match': round(text_match, 3),
                'semantic_score': round(semantic_score, 3)
            })

    # Sort by combined score, then importance
    scored_results.sort(key=lambda x: (x['score'], x['importance']), reverse=True)
    results = scored_results[:args.limit]

    # Search AVS KB if requested
    if args.include_avs and AVS_API_KEY:
        avs_results = search_avs(query, args.limit)
        results.extend(avs_results)

    output = {
        'success': True,
        'query': query,
        'count': len(results),
        'has_embeddings': query_embedding is not None,
        'results': results
    }

    print(json.dumps(output, indent=2, ensure_ascii=False))
    conn.close()
    return 0


def search_avs(query, limit=10):
    """Search AVS Knowledge Base"""
    try:
        import urllib.request
        import urllib.error

        data = json.dumps({
            'query': query,
            'maxNodes': limit,
            'maxDepth': 1,
            'includeEntities': False
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
                'content': node.get('content', '')[:200],
                'type': node.get('type', 'concept'),
                'tags': node.get('tags', []),
                'source': 'avs_kb',
                'avs_node_id': node['id'],
                'score': 0.5  # Default score for AVS results
            } for node in result.get('nodes', [])]
    except Exception as e:
        print(f"[AVS Brain] AVS search error: {e}", file=sys.stderr)
        return []


def sync_to_avs(conn, memory_id):
    """Sync a memory to AVS KB"""
    try:
        import urllib.request

        row = conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        if not row:
            return False

        type_map = {'memory': 'concept', 'conversation': 'resource'}
        avs_type = type_map.get(row['type'], row['type'])

        tags = json.loads(row['tags'] or '[]')
        tags.append('michel-brain')

        data = json.dumps({
            'type': avs_type,
            'title': row['title'],
            'content': row['content'],
            'tags': tags,
            'visibility': 'restricted'
        }).encode('utf-8')

        if row['avs_node_id']:
            url = f"{AVS_INTRANET_URL}/api/external/knowledge/nodes/{row['avs_node_id']}"
            method = 'PUT'
        else:
            url = f"{AVS_INTRANET_URL}/api/external/knowledge/nodes"
            method = 'POST'

        req = urllib.request.Request(
            url,
            data=data,
            headers={
                'Content-Type': 'application/json',
                'X-API-Key': AVS_API_KEY
            },
            method=method
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
            avs_node_id = result.get('id', row['avs_node_id'])

            conn.execute("""
                UPDATE memories SET avs_node_id = ?, synced_at = datetime('now') WHERE id = ?
            """, (avs_node_id, memory_id))
            conn.commit()

            conn.execute("""
                INSERT INTO sync_log (memory_id, action, status, avs_node_id, details)
                VALUES (?, 'push', 'success', ?, ?)
            """, (memory_id, avs_node_id, f"Synced: {row['title']}"))
            conn.commit()
            return True

    except Exception as e:
        conn.execute("""
            INSERT INTO sync_log (memory_id, action, status, details)
            VALUES (?, 'push', 'failed', ?)
        """, (memory_id, str(e)))
        conn.commit()
        print(f"[AVS Brain] Sync error: {e}", file=sys.stderr)
        return False


def cmd_link(args):
    """Create a link between memories"""
    conn = init_db()

    if args.type not in VALID_RELATIONS:
        print(json.dumps({'success': False, 'error': f"Invalid relation type"}))
        return 1

    from_mem = conn.execute("SELECT title FROM memories WHERE id = ?", (args.from_id,)).fetchone()
    to_mem = conn.execute("SELECT title FROM memories WHERE id = ?", (args.to_id,)).fetchone()

    if not from_mem or not to_mem:
        print(json.dumps({'success': False, 'error': 'Memory not found'}))
        return 1

    link_id = generate_id('link')
    conn.execute("""
        INSERT OR REPLACE INTO links (id, from_id, to_id, relation_type)
        VALUES (?, ?, ?, ?)
    """, (link_id, args.from_id, args.to_id, args.type))

    if args.bidirectional:
        reverse_id = generate_id('link')
        conn.execute("""
            INSERT OR REPLACE INTO links (id, from_id, to_id, relation_type)
            VALUES (?, ?, ?, ?)
        """, (reverse_id, args.to_id, args.from_id, args.type))

    conn.commit()

    result = {
        'success': True,
        'link_id': link_id,
        'from': {'id': args.from_id, 'title': from_mem['title']},
        'to': {'id': args.to_id, 'title': to_mem['title']},
        'type': args.type,
        'bidirectional': args.bidirectional,
        'message': f'Lien cree'
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))
    conn.close()
    return 0


def cmd_forget(args):
    """Delete a memory"""
    conn = init_db()

    row = conn.execute("SELECT title FROM memories WHERE id = ?", (args.id,)).fetchone()
    if not row:
        print(json.dumps({'success': False, 'error': 'Memory not found'}))
        return 1

    conn.execute("DELETE FROM memories WHERE id = ?", (args.id,))
    conn.execute("""
        INSERT INTO sync_log (memory_id, action, status, details)
        VALUES (?, 'delete', 'success', ?)
    """, (args.id, args.reason or f"Deleted: {row['title']}"))
    conn.commit()

    result = {
        'success': True,
        'deleted_id': args.id,
        'title': row['title'],
        'reason': args.reason,
        'message': f'Memoire supprimee'
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))
    conn.close()
    return 0


def cmd_sync(args):
    """Sync with AVS KB"""
    conn = init_db()

    if not AVS_API_KEY:
        print(json.dumps({'success': False, 'error': 'AVS_API_KEY not configured'}))
        return 1

    pushed = 0
    failed = 0

    if args.direction in ('push', 'both'):
        rows = conn.execute("""
            SELECT id FROM memories
            WHERE importance >= 70
            AND (avs_node_id IS NULL OR updated_at > synced_at)
        """).fetchall()

        for row in rows:
            if sync_to_avs(conn, row['id']):
                pushed += 1
            else:
                failed += 1

    result = {
        'success': True,
        'direction': args.direction,
        'pushed': pushed,
        'failed': failed,
        'pulled': 0,
        'message': f'Sync complete: {pushed} pushed, {failed} failed'
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))
    conn.close()
    return 0


def cmd_reindex(args):
    """Regenerate embeddings for all memories"""
    conn = init_db()

    rows = conn.execute("SELECT id, title, content FROM memories").fetchall()
    total = len(rows)
    indexed = 0
    failed = 0

    print(f"[AVS Brain] Reindexing {total} memories...", file=sys.stderr)

    for row in rows:
        embed_text = f"{row['title']} {row['content']}"
        if store_embedding(conn, row['id'], embed_text):
            indexed += 1
        else:
            failed += 1
        if indexed % 5 == 0:
            print(f"[AVS Brain] Progress: {indexed}/{total}", file=sys.stderr)

    result = {
        'success': True,
        'total': total,
        'indexed': indexed,
        'failed': failed,
        'message': f'Reindex complete: {indexed}/{total} memories indexed'
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))
    conn.close()
    return 0


def cmd_stats(args):
    """Show brain statistics"""
    conn = init_db()

    total = conn.execute("SELECT COUNT(*) as c FROM memories").fetchone()['c']
    by_type = conn.execute("""
        SELECT type, COUNT(*) as count FROM memories GROUP BY type ORDER BY count DESC
    """).fetchall()
    synced = conn.execute("SELECT COUNT(*) as c FROM memories WHERE avs_node_id IS NOT NULL").fetchone()['c']
    pending = conn.execute("""
        SELECT COUNT(*) as c FROM memories
        WHERE importance >= 70 AND (avs_node_id IS NULL OR updated_at > synced_at)
    """).fetchone()['c']
    links = conn.execute("SELECT COUNT(*) as c FROM links").fetchone()['c']
    embeddings = conn.execute("SELECT COUNT(*) as c FROM embeddings").fetchone()['c']

    recent_sync = conn.execute("""
        SELECT action, status, details, timestamp FROM sync_log
        ORDER BY timestamp DESC LIMIT 5
    """).fetchall()

    result = {
        'success': True,
        'stats': {
            'total_memories': total,
            'by_type': [{'type': r['type'], 'count': r['count']} for r in by_type],
            'synced_to_avs': synced,
            'pending_sync': pending,
            'total_links': links,
            'embeddings_count': embeddings,
            'embeddings_coverage': f"{round(embeddings/total*100) if total > 0 else 0}%",
            'recent_sync': [dict(r) for r in recent_sync]
        },
        'message': f'Cerveau: {total} memoires, {links} liens, {embeddings} embeddings, {synced} sync AVS'
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))
    conn.close()
    return 0


def main():
    parser = argparse.ArgumentParser(description='AVS Brain - Cerveau local de Michel')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # remember
    p_remember = subparsers.add_parser('remember', help='Store a memory')
    p_remember.add_argument('--title', required=True, help='Memory title')
    p_remember.add_argument('--content', required=True, help='Memory content')
    p_remember.add_argument('--type', required=True, help=f'Type: {", ".join(VALID_TYPES)}')
    p_remember.add_argument('--importance', type=int, default=50, help='Importance 0-100')
    p_remember.add_argument('--tags', help='Comma-separated tags')

    # search
    p_search = subparsers.add_parser('search', help='Search memories')
    p_search.add_argument('query', help='Search query')
    p_search.add_argument('--type', help='Filter by type')
    p_search.add_argument('--limit', type=int, default=10, help='Max results')
    p_search.add_argument('--include-avs', action='store_true', default=True)
    p_search.add_argument('--local-only', action='store_true')

    # link
    p_link = subparsers.add_parser('link', help='Create a link')
    p_link.add_argument('--from', dest='from_id', required=True)
    p_link.add_argument('--to', dest='to_id', required=True)
    p_link.add_argument('--type', required=True)
    p_link.add_argument('--bidirectional', action='store_true')

    # forget
    p_forget = subparsers.add_parser('forget', help='Delete a memory')
    p_forget.add_argument('id', help='Memory ID')
    p_forget.add_argument('--reason', help='Reason')

    # sync
    p_sync = subparsers.add_parser('sync', help='Sync with AVS KB')
    p_sync.add_argument('--direction', choices=['push', 'pull', 'both'], default='both')

    # stats
    subparsers.add_parser('stats', help='Show statistics')

    # reindex
    subparsers.add_parser('reindex', help='Regenerate all embeddings')

    args = parser.parse_args()

    if args.command == 'remember':
        return cmd_remember(args)
    elif args.command == 'search':
        args.include_avs = not args.local_only
        return cmd_search(args)
    elif args.command == 'link':
        return cmd_link(args)
    elif args.command == 'forget':
        return cmd_forget(args)
    elif args.command == 'sync':
        return cmd_sync(args)
    elif args.command == 'stats':
        return cmd_stats(args)
    elif args.command == 'reindex':
        return cmd_reindex(args)
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
