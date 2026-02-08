#!/usr/bin/env python3
"""
Brain Maintenance - Consolidation, decay, and optimization

Usage:
    brain_maintenance.py consolidate [--threshold 0.85] [--dry-run]
    brain_maintenance.py decay [--days 30] [--rate 5] [--dry-run]
    brain_maintenance.py duplicates [--threshold 0.95] [--dry-run]
    brain_maintenance.py optimize
    brain_maintenance.py full [--dry-run]

Maintenance operations:
- consolidate: Merge similar memories into consolidated summaries
- decay: Reduce importance of memories not accessed recently
- duplicates: Find and merge duplicate memories
- optimize: Vacuum database and rebuild indexes
- full: Run all maintenance operations
"""

import argparse
import json
import logging
import os
import sqlite3
import struct
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Setup logging
LOG_DIR = Path(os.environ.get('MICHEL_LOG_DIR', os.path.expanduser('~/michel-avs/logs')))
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'brain_maintenance.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('brain_maintenance')

# Database path
DB_PATH = Path(os.environ.get('BRAIN_DB_PATH', os.path.expanduser('~/michel-avs/skills/avs-brain/brain.db')))

# Embedding model
EMBEDDING_MODEL = 'all-MiniLM-L6-v2'
_embedding_model = None


def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_embedding_model():
    """Lazy load embedding model"""
    global _embedding_model
    if _embedding_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
            logger.info(f"Loaded embedding model: {EMBEDDING_MODEL}")
        except ImportError:
            logger.warning("sentence-transformers not installed")
            return None
    return _embedding_model


def compute_embedding(text):
    """Compute embedding for text"""
    model = get_embedding_model()
    if model is None:
        return None
    return model.encode(text, convert_to_numpy=True)


def deserialize_embedding(blob):
    """Deserialize embedding from blob"""
    if blob is None:
        return None
    n_floats = len(blob) // 4
    return list(struct.unpack(f'{n_floats}f', blob))


def cosine_similarity(vec1, vec2):
    """Compute cosine similarity between two vectors"""
    if vec1 is None or vec2 is None:
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = sum(a * a for a in vec1) ** 0.5
    norm2 = sum(b * b for b in vec2) ** 0.5
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def cmd_consolidate(args):
    """Consolidate similar memories into summaries"""
    logger.info(f"Starting consolidation with threshold {args.threshold}")

    conn = get_db()
    cursor = conn.cursor()

    # Get all memories with embeddings
    cursor.execute("""
        SELECT m.id, m.title, m.content, m.type, m.importance, m.tags,
               m.created_at, m.accessed_at, e.vector
        FROM memories m
        LEFT JOIN embeddings e ON m.id = e.memory_id
        WHERE m.consolidated_into IS NULL
        ORDER BY m.importance DESC
    """)

    memories = cursor.fetchall()
    logger.info(f"Found {len(memories)} memories to analyze")

    # Find clusters of similar memories
    clusters = []
    used = set()

    for i, mem1 in enumerate(memories):
        if mem1['id'] in used:
            continue

        vec1 = deserialize_embedding(mem1['vector'])
        if vec1 is None:
            continue

        cluster = [mem1]
        used.add(mem1['id'])

        for j, mem2 in enumerate(memories[i+1:], i+1):
            if mem2['id'] in used:
                continue
            if mem2['type'] != mem1['type']:
                continue

            vec2 = deserialize_embedding(mem2['vector'])
            if vec2 is None:
                continue

            similarity = cosine_similarity(vec1, vec2)
            if similarity >= args.threshold:
                cluster.append(mem2)
                used.add(mem2['id'])

        if len(cluster) > 1:
            clusters.append(cluster)

    logger.info(f"Found {len(clusters)} clusters to consolidate")

    consolidated_count = 0
    for cluster in clusters:
        # Sort by importance (keep highest as base)
        cluster.sort(key=lambda x: x['importance'], reverse=True)
        base = cluster[0]
        others = cluster[1:]

        logger.info(f"Consolidating {len(others)} memories into '{base['title']}'")

        if args.dry_run:
            for mem in others:
                logger.info(f"  Would merge: '{mem['title']}' (importance: {mem['importance']})")
            continue

        # Combine content
        combined_content = base['content']
        for mem in others:
            if mem['content'] not in combined_content:
                combined_content += f"\n\n---\n{mem['content']}"

        # Combine tags
        all_tags = set()
        if base['tags']:
            all_tags.update(json.loads(base['tags']))
        for mem in others:
            if mem['tags']:
                all_tags.update(json.loads(mem['tags']))

        # Update base memory
        cursor.execute("""
            UPDATE memories
            SET content = ?, tags = ?, updated_at = datetime('now')
            WHERE id = ?
        """, (combined_content, json.dumps(list(all_tags)), base['id']))

        # Mark others as consolidated
        for mem in others:
            cursor.execute("""
                UPDATE memories
                SET consolidated_into = ?, updated_at = datetime('now')
                WHERE id = ?
            """, (base['id'], mem['id']))

        consolidated_count += len(others)

    if not args.dry_run:
        conn.commit()

    conn.close()

    result = {
        'success': True,
        'clusters_found': len(clusters),
        'memories_consolidated': consolidated_count,
        'dry_run': args.dry_run
    }
    print(json.dumps(result, indent=2))
    logger.info(f"Consolidation complete: {consolidated_count} memories consolidated")
    return 0


def cmd_decay(args):
    """Apply importance decay to old, unused memories"""
    logger.info(f"Starting decay: {args.rate}% for memories not accessed in {args.days} days")

    conn = get_db()
    cursor = conn.cursor()

    cutoff_date = (datetime.now() - timedelta(days=args.days)).isoformat()

    # Find memories to decay
    cursor.execute("""
        SELECT id, title, importance, accessed_at, created_at
        FROM memories
        WHERE importance > 10
        AND (accessed_at IS NULL OR accessed_at < ?)
        AND created_at < ?
        AND consolidated_into IS NULL
    """, (cutoff_date, cutoff_date))

    memories = cursor.fetchall()
    logger.info(f"Found {len(memories)} memories eligible for decay")

    decayed_count = 0
    for mem in memories:
        new_importance = max(10, mem['importance'] - args.rate)

        if new_importance == mem['importance']:
            continue

        logger.debug(f"Decaying '{mem['title']}': {mem['importance']} -> {new_importance}")

        if not args.dry_run:
            cursor.execute("""
                UPDATE memories
                SET importance = ?, updated_at = datetime('now')
                WHERE id = ?
            """, (new_importance, mem['id']))

        decayed_count += 1

    if not args.dry_run:
        conn.commit()

    conn.close()

    result = {
        'success': True,
        'memories_decayed': decayed_count,
        'decay_rate': args.rate,
        'days_threshold': args.days,
        'dry_run': args.dry_run
    }
    print(json.dumps(result, indent=2))
    logger.info(f"Decay complete: {decayed_count} memories affected")
    return 0


def cmd_duplicates(args):
    """Find and merge duplicate memories"""
    logger.info(f"Searching for duplicates with threshold {args.threshold}")

    conn = get_db()
    cursor = conn.cursor()

    # Get all memories with embeddings
    cursor.execute("""
        SELECT m.id, m.title, m.content, m.type, m.importance, e.vector
        FROM memories m
        LEFT JOIN embeddings e ON m.id = e.memory_id
        WHERE m.consolidated_into IS NULL
    """)

    memories = cursor.fetchall()

    # Find exact or near-exact duplicates
    duplicates = []
    checked = set()

    for i, mem1 in enumerate(memories):
        if mem1['id'] in checked:
            continue

        vec1 = deserialize_embedding(mem1['vector'])
        dupe_group = [mem1]

        for mem2 in memories[i+1:]:
            if mem2['id'] in checked:
                continue

            # Check title similarity first (fast)
            if mem1['title'].lower() == mem2['title'].lower():
                dupe_group.append(mem2)
                checked.add(mem2['id'])
                continue

            # Check content similarity
            if vec1 is not None:
                vec2 = deserialize_embedding(mem2['vector'])
                if vec2 is not None:
                    similarity = cosine_similarity(vec1, vec2)
                    if similarity >= args.threshold:
                        dupe_group.append(mem2)
                        checked.add(mem2['id'])

        if len(dupe_group) > 1:
            duplicates.append(dupe_group)
            checked.add(mem1['id'])

    logger.info(f"Found {len(duplicates)} duplicate groups")

    merged_count = 0
    for group in duplicates:
        # Keep the one with highest importance
        group.sort(key=lambda x: (x['importance'], x['id']), reverse=True)
        keep = group[0]
        remove = group[1:]

        logger.info(f"Keeping '{keep['title']}', merging {len(remove)} duplicates")

        if args.dry_run:
            for mem in remove:
                logger.info(f"  Would remove: '{mem['title']}'")
            continue

        for mem in remove:
            # Update any links pointing to removed memory
            cursor.execute("""
                UPDATE links SET to_id = ? WHERE to_id = ?
            """, (keep['id'], mem['id']))
            cursor.execute("""
                UPDATE links SET from_id = ? WHERE from_id = ?
            """, (keep['id'], mem['id']))

            # Mark as consolidated
            cursor.execute("""
                UPDATE memories
                SET consolidated_into = ?, updated_at = datetime('now')
                WHERE id = ?
            """, (keep['id'], mem['id']))

        merged_count += len(remove)

    if not args.dry_run:
        conn.commit()

    conn.close()

    result = {
        'success': True,
        'duplicate_groups': len(duplicates),
        'memories_merged': merged_count,
        'dry_run': args.dry_run
    }
    print(json.dumps(result, indent=2))
    return 0


def cmd_optimize(args):
    """Optimize database"""
    logger.info("Optimizing database...")

    conn = get_db()
    cursor = conn.cursor()

    # Get size before
    cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
    size_before = cursor.fetchone()[0]

    # Vacuum
    cursor.execute("VACUUM")

    # Rebuild FTS index
    cursor.execute("INSERT INTO memories_fts(memories_fts) VALUES('rebuild')")

    # Analyze
    cursor.execute("ANALYZE")

    # Get size after
    cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
    size_after = cursor.fetchone()[0]

    conn.commit()
    conn.close()

    result = {
        'success': True,
        'size_before_kb': size_before // 1024,
        'size_after_kb': size_after // 1024,
        'saved_kb': (size_before - size_after) // 1024
    }
    print(json.dumps(result, indent=2))
    logger.info(f"Optimization complete: saved {result['saved_kb']}KB")
    return 0


def cmd_full(args):
    """Run full maintenance"""
    logger.info("Running full maintenance...")

    # Run all maintenance tasks
    args.threshold = 0.85
    cmd_consolidate(args)

    args.days = 30
    args.rate = 5
    cmd_decay(args)

    args.threshold = 0.95
    cmd_duplicates(args)

    if not args.dry_run:
        cmd_optimize(args)

    logger.info("Full maintenance complete")
    return 0


def ensure_schema():
    """Ensure maintenance columns exist"""
    conn = get_db()
    cursor = conn.cursor()

    # Add consolidated_into column if not exists
    try:
        cursor.execute("ALTER TABLE memories ADD COLUMN consolidated_into TEXT")
        logger.info("Added consolidated_into column")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Add accessed_at column if not exists
    try:
        cursor.execute("ALTER TABLE memories ADD COLUMN accessed_at TEXT")
        logger.info("Added accessed_at column")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()


def main():
    parser = argparse.ArgumentParser(description='Brain Maintenance')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # consolidate
    p_consolidate = subparsers.add_parser('consolidate', help='Consolidate similar memories')
    p_consolidate.add_argument('--threshold', type=float, default=0.85, help='Similarity threshold')
    p_consolidate.add_argument('--dry-run', action='store_true', help='Preview only')

    # decay
    p_decay = subparsers.add_parser('decay', help='Apply importance decay')
    p_decay.add_argument('--days', type=int, default=30, help='Days since last access')
    p_decay.add_argument('--rate', type=int, default=5, help='Decay rate (importance points)')
    p_decay.add_argument('--dry-run', action='store_true', help='Preview only')

    # duplicates
    p_dupes = subparsers.add_parser('duplicates', help='Find and merge duplicates')
    p_dupes.add_argument('--threshold', type=float, default=0.95, help='Similarity threshold')
    p_dupes.add_argument('--dry-run', action='store_true', help='Preview only')

    # optimize
    p_optimize = subparsers.add_parser('optimize', help='Optimize database')

    # full
    p_full = subparsers.add_parser('full', help='Run full maintenance')
    p_full.add_argument('--dry-run', action='store_true', help='Preview only')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Ensure schema
    ensure_schema()

    if args.command == 'consolidate':
        return cmd_consolidate(args)
    elif args.command == 'decay':
        return cmd_decay(args)
    elif args.command == 'duplicates':
        return cmd_duplicates(args)
    elif args.command == 'optimize':
        return cmd_optimize(args)
    elif args.command == 'full':
        return cmd_full(args)


if __name__ == '__main__':
    sys.exit(main())
