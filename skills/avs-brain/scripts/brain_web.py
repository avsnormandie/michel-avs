#!/usr/bin/env python3
"""
Brain Web Search - Web search capability for Michel

Usage:
    brain_web.py search "query" [--limit N] [--region fr-fr]
    brain_web.py fetch URL [--summary]
    brain_web.py news "topic" [--limit N]

Uses DuckDuckGo for search (no API key required).
"""

import argparse
import json
import logging
import os
import re
import sys
import urllib.request
import urllib.parse
import urllib.error
from html.parser import HTMLParser
from pathlib import Path

# Setup logging
LOG_DIR = Path(os.environ.get('MICHEL_LOG_DIR', os.path.expanduser('~/michel-avs/logs')))
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'brain_web.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('brain_web')

# User agent
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'


class HTMLTextExtractor(HTMLParser):
    """Extract text from HTML"""
    def __init__(self):
        super().__init__()
        self.text = []
        self.skip_tags = {'script', 'style', 'nav', 'footer', 'header', 'aside'}
        self.current_tag = None

    def handle_starttag(self, tag, attrs):
        self.current_tag = tag

    def handle_endtag(self, tag):
        self.current_tag = None

    def handle_data(self, data):
        if self.current_tag not in self.skip_tags:
            text = data.strip()
            if text:
                self.text.append(text)

    def get_text(self):
        return ' '.join(self.text)


def fetch_url(url, timeout=10):
    """Fetch content from URL"""
    headers = {
        'User-Agent': USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8'
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            content = response.read()
            charset = response.headers.get_content_charset() or 'utf-8'
            return content.decode(charset, errors='replace')
    except Exception as e:
        logger.error(f"Failed to fetch {url}: {e}")
        return None


def extract_text(html):
    """Extract clean text from HTML"""
    parser = HTMLTextExtractor()
    parser.feed(html)
    return parser.get_text()


def summarize_text(text, max_length=500):
    """Simple text summarization (first N chars at sentence boundary)"""
    if len(text) <= max_length:
        return text

    # Find sentence boundary near max_length
    truncated = text[:max_length]
    last_period = truncated.rfind('.')
    last_exclaim = truncated.rfind('!')
    last_question = truncated.rfind('?')

    boundary = max(last_period, last_exclaim, last_question)
    if boundary > max_length // 2:
        return text[:boundary + 1]

    return truncated + '...'


def search_duckduckgo(query, limit=5, region='fr-fr'):
    """Search using DuckDuckGo HTML"""
    # Use DuckDuckGo HTML version
    encoded_query = urllib.parse.quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded_query}&kl={region}"

    html = fetch_url(url)
    if not html:
        return []

    results = []

    # Parse results using regex (simple but effective for DDG HTML)
    # Find result blocks
    result_pattern = r'<a rel="nofollow" class="result__a" href="([^"]+)"[^>]*>([^<]+)</a>'
    snippet_pattern = r'<a class="result__snippet"[^>]*>([^<]+(?:<[^>]+>[^<]+)*)</a>'

    matches = re.findall(result_pattern, html)
    snippets = re.findall(snippet_pattern, html)

    for i, (link, title) in enumerate(matches[:limit]):
        # Decode DDG redirect URL
        if link.startswith('//duckduckgo.com/l/'):
            # Extract actual URL from redirect
            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)
            actual_url = parsed.get('uddg', [link])[0]
        else:
            actual_url = link

        # Clean URL
        if actual_url.startswith('//'):
            actual_url = 'https:' + actual_url

        snippet = ''
        if i < len(snippets):
            # Remove HTML tags from snippet
            snippet = re.sub(r'<[^>]+>', '', snippets[i])

        results.append({
            'title': title.strip(),
            'url': actual_url,
            'snippet': snippet.strip()
        })

    return results


def search_duckduckgo_api(query, limit=5):
    """Search using DuckDuckGo Instant Answer API"""
    encoded_query = urllib.parse.quote_plus(query)
    url = f"https://api.duckduckgo.com/?q={encoded_query}&format=json&no_html=1&skip_disambig=1"

    try:
        req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))

        results = []

        # Abstract (main answer)
        if data.get('Abstract'):
            results.append({
                'title': data.get('Heading', 'Result'),
                'url': data.get('AbstractURL', ''),
                'snippet': data.get('Abstract', ''),
                'source': data.get('AbstractSource', '')
            })

        # Related topics
        for topic in data.get('RelatedTopics', [])[:limit-1]:
            if isinstance(topic, dict) and topic.get('Text'):
                results.append({
                    'title': topic.get('Text', '')[:50],
                    'url': topic.get('FirstURL', ''),
                    'snippet': topic.get('Text', '')
                })

        return results

    except Exception as e:
        logger.error(f"DuckDuckGo API error: {e}")
        return []


def cmd_search(args):
    """Search the web"""
    logger.info(f"Searching: {args.query}")

    # Try API first (faster, structured)
    results = search_duckduckgo_api(args.query, args.limit)

    # Fall back to HTML scraping if no results
    if not results:
        results = search_duckduckgo(args.query, args.limit, args.region)

    output = {
        'success': True,
        'query': args.query,
        'count': len(results),
        'results': results
    }

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


def cmd_fetch(args):
    """Fetch and extract content from URL"""
    logger.info(f"Fetching: {args.url}")

    html = fetch_url(args.url)
    if not html:
        print(json.dumps({
            'success': False,
            'error': 'Failed to fetch URL'
        }))
        return 1

    text = extract_text(html)

    if args.summary:
        text = summarize_text(text, 1000)

    # Extract title
    title_match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
    title = title_match.group(1).strip() if title_match else 'No title'

    output = {
        'success': True,
        'url': args.url,
        'title': title,
        'content': text,
        'length': len(text)
    }

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


def cmd_news(args):
    """Search for news"""
    # Add "news" or "actualites" to query
    query = f"{args.topic} actualites 2026"

    logger.info(f"Searching news: {query}")
    results = search_duckduckgo(query, args.limit, 'fr-fr')

    output = {
        'success': True,
        'topic': args.topic,
        'count': len(results),
        'results': results
    }

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


def main():
    parser = argparse.ArgumentParser(description='Brain Web Search')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # search
    p_search = subparsers.add_parser('search', help='Search the web')
    p_search.add_argument('query', help='Search query')
    p_search.add_argument('--limit', type=int, default=5, help='Max results')
    p_search.add_argument('--region', default='fr-fr', help='Region code')

    # fetch
    p_fetch = subparsers.add_parser('fetch', help='Fetch URL content')
    p_fetch.add_argument('url', help='URL to fetch')
    p_fetch.add_argument('--summary', action='store_true', help='Summarize content')

    # news
    p_news = subparsers.add_parser('news', help='Search for news')
    p_news.add_argument('topic', help='News topic')
    p_news.add_argument('--limit', type=int, default=5, help='Max results')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    commands = {
        'search': cmd_search,
        'fetch': cmd_fetch,
        'news': cmd_news
    }

    return commands[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
