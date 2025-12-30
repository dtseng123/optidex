#!/usr/bin/env python3
"""
Knowledge Base - Local Wikipedia and Wikidata storage for Jarvis

Provides fast local search of Wikipedia articles and Wikidata entities.
Uses SQLite with FTS5 for full-text search.

Features:
- Download and parse Wikipedia dumps
- Full-text search across articles
- Entity linking between Wikipedia and Wikidata
- Integration with Jarvis memory system
"""

import os
import sys
import json
import sqlite3
import re
import bz2
import time
import argparse
import urllib.request
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

# Data directory
DATA_DIR = Path(os.path.expanduser("~/optidex/data/knowledge"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "knowledge.db"

# Wikipedia dump URL (English, articles only, multistream for streaming parse)
WIKI_URL = "https://dumps.wikimedia.org/enwiki/latest/enwiki-latest-pages-articles-multistream.xml.bz2"


def get_db_connection() -> sqlite3.Connection:
    """Get a database connection"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Initialize the database schema"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Articles table with FTS5
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY,
            title TEXT UNIQUE NOT NULL,
            content TEXT,
            summary TEXT,
            categories TEXT,
            links TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # FTS5 virtual table for full-text search
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
            title, content, summary,
            content='articles',
            content_rowid='id'
        )
    """)
    
    # Entities table (Wikidata)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS entities (
            id TEXT PRIMARY KEY,
            label TEXT,
            description TEXT,
            aliases TEXT,
            wikipedia_title TEXT,
            properties TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Check if wikipedia_title column exists, add if not
    cursor.execute("PRAGMA table_info(entities)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'wikipedia_title' not in columns:
        cursor.execute("ALTER TABLE entities ADD COLUMN wikipedia_title TEXT")
    
    # Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_articles_title ON articles(title)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_entities_label ON entities(label)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_entities_wikipedia ON entities(wikipedia_title)")
    
    conn.commit()
    conn.close()


def clean_wikitext(text: str) -> str:
    """Clean Wikipedia markup to plain text"""
    if not text:
        return ""
    
    # Remove templates {{ }}
    text = re.sub(r'\{\{[^}]*\}\}', '', text)
    
    # Remove references <ref>...</ref>
    text = re.sub(r'<ref[^>]*>.*?</ref>', '', text, flags=re.DOTALL)
    text = re.sub(r'<ref[^/]*/>', '', text)
    
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    
    # Convert wiki links [[link|text]] to text, [[link]] to link
    text = re.sub(r'\[\[([^|\]]+)\|([^\]]+)\]\]', r'\2', text)
    text = re.sub(r'\[\[([^\]]+)\]\]', r'\1', text)
    
    # Remove external links [url text]
    text = re.sub(r'\[https?://[^\s\]]+\s*([^\]]*)\]', r'\1', text)
    
    # Remove bold/italic markers
    text = re.sub(r"'{2,5}", '', text)
    
    # Remove headings markers
    text = re.sub(r'={2,6}\s*([^=]+)\s*={2,6}', r'\1', text)
    
    # Remove file/image links
    text = re.sub(r'\[\[(?:File|Image):[^\]]+\]\]', '', text, flags=re.IGNORECASE)
    
    # Remove category links
    text = re.sub(r'\[\[Category:[^\]]+\]\]', '', text, flags=re.IGNORECASE)
    
    # Clean up whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'  +', ' ', text)
    
    return text.strip()


def extract_summary(text: str, max_length: int = 500) -> str:
    """Extract first paragraph as summary"""
    if not text:
        return ""
    
    # Split into paragraphs
    paragraphs = text.split('\n\n')
    
    # Find first substantial paragraph
    for para in paragraphs:
        para = para.strip()
        # Skip short lines or ones that look like metadata
        if len(para) > 50 and not para.startswith('|') and not para.startswith('{'):
            if len(para) > max_length:
                # Try to cut at sentence boundary
                cut_point = para[:max_length].rfind('.')
                if cut_point > max_length // 2:
                    return para[:cut_point + 1]
                return para[:max_length] + "..."
            return para
    
    return text[:max_length] if text else ""


def search_articles(query: str, limit: int = 10) -> List[Dict]:
    """Search articles using full-text search"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    results = []
    
    # Check which columns exist (support both old and new schema)
    cursor.execute("PRAGMA table_info(articles)")
    columns = {row[1] for row in cursor.fetchall()}
    
    # Determine column names based on schema
    content_col = 'full_text' if 'full_text' in columns else 'content'
    summary_col = 'abstract' if 'abstract' in columns else 'summary'
    
    try:
        # Try FTS5 match query first
        cursor.execute(f"""
            SELECT a.id, a.title, a.{summary_col} as summary,
                   bm25(articles_fts) as score
            FROM articles_fts
            JOIN articles a ON a.id = articles_fts.rowid
            WHERE articles_fts MATCH ?
            ORDER BY score
            LIMIT ?
        """, (query, limit))
        
        for row in cursor.fetchall():
            results.append({
                'id': row['id'],
                'title': row['title'],
                'summary': row['summary'],
                'score': row['score']
            })
    except sqlite3.OperationalError:
        # FTS table might not exist or be populated, fall back to LIKE
        cursor.execute(f"""
            SELECT id, title, {summary_col} as summary
            FROM articles
            WHERE title LIKE ? OR {summary_col} LIKE ?
            ORDER BY CASE WHEN title LIKE ? THEN 0 ELSE 1 END, title
            LIMIT ?
        """, (f'%{query}%', f'%{query}%', f'{query}%', limit))
        
        for row in cursor.fetchall():
            results.append({
                'id': row['id'],
                'title': row['title'],
                'summary': row['summary']
            })
    
    conn.close()
    return results


def get_article(title: str) -> Optional[Dict]:
    """Get a specific article by title"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check which columns exist
    cursor.execute("PRAGMA table_info(articles)")
    columns = {row[1] for row in cursor.fetchall()}
    
    content_col = 'full_text' if 'full_text' in columns else 'content'
    summary_col = 'abstract' if 'abstract' in columns else 'summary'
    
    cursor.execute(f"""
        SELECT id, title, {content_col} as content, {summary_col} as summary, categories
        FROM articles
        WHERE title = ? OR title LIKE ?
        LIMIT 1
    """, (title, f'{title}%'))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        # Parse categories (may be JSON or simple string)
        cats = row['categories']
        if cats:
            try:
                cats = json.loads(cats)
            except:
                cats = [c.strip() for c in cats.split(',') if c.strip()]
        else:
            cats = []
        
        # Use summary or first part of content
        content = row['content'] or row['summary'] or ''
        summary = row['summary'] or (content[:500] + '...' if len(content) > 500 else content)
        
        return {
            'id': row['id'],
            'title': row['title'],
            'content': content,
            'summary': summary,
            'categories': cats
        }
    return None


def search_entities(query: str, limit: int = 10) -> List[Dict]:
    """Search Wikidata entities"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, label, description, aliases, wikipedia_title
        FROM entities
        WHERE label LIKE ? OR aliases LIKE ? OR description LIKE ?
        LIMIT ?
    """, (f'%{query}%', f'%{query}%', f'%{query}%', limit))
    
    results = []
    for row in cursor.fetchall():
        results.append({
            'id': row['id'],
            'label': row['label'],
            'description': row['description'],
            'aliases': json.loads(row['aliases']) if row['aliases'] else [],
            'wikipedia_title': row['wikipedia_title']
        })
    
    conn.close()
    return results


def get_entity(entity_id: str) -> Optional[Dict]:
    """Get a specific Wikidata entity by ID"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, label, description, aliases, wikipedia_title, properties
        FROM entities
        WHERE id = ?
    """, (entity_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            'id': row['id'],
            'label': row['label'],
            'description': row['description'],
            'aliases': json.loads(row['aliases']) if row['aliases'] else [],
            'wikipedia_title': row['wikipedia_title'],
            'properties': json.loads(row['properties']) if row['properties'] else {}
        }
    return None


def get_stats() -> Dict:
    """Get knowledge base statistics"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM articles")
    article_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM entities")
    entity_count = cursor.fetchone()[0]
    
    # Get database file size
    db_size = os.path.getsize(DB_PATH) if DB_PATH.exists() else 0
    
    conn.close()
    
    return {
        'articles': article_count,
        'entities': entity_count,
        'database_size_mb': round(db_size / (1024 * 1024), 2),
        'database_path': str(DB_PATH)
    }


def download_wikipedia():
    """Download and import Wikipedia dump"""
    print("Starting Wikipedia download...")
    print(f"URL: {WIKI_URL}")
    
    local_file = DATA_DIR / "enwiki-pages-articles.xml.bz2"
    
    # Check if already downloading/downloaded
    if local_file.exists():
        size_gb = local_file.stat().st_size / (1024**3)
        print(f"Found existing file: {size_gb:.2f} GB")
        if size_gb > 20:  # Full dump is ~22GB
            print("File appears complete, skipping download")
            import_wikipedia(local_file)
            return
        else:
            print("File incomplete, resuming download...")
    
    # Download with progress
    def report_progress(block_num, block_size, total_size):
        downloaded = block_num * block_size
        percent = (downloaded / total_size) * 100 if total_size > 0 else 0
        downloaded_gb = downloaded / (1024**3)
        total_gb = total_size / (1024**3)
        print(f"\rDownloading: {downloaded_gb:.2f} / {total_gb:.2f} GB ({percent:.1f}%)", end='', flush=True)
    
    try:
        urllib.request.urlretrieve(WIKI_URL, local_file, report_progress)
        print("\nDownload complete!")
        import_wikipedia(local_file)
    except Exception as e:
        print(f"\nDownload error: {e}")
        raise


def import_wikipedia(dump_file: Path):
    """Import Wikipedia from a dump file"""
    print(f"Importing from: {dump_file}")
    
    init_database()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Parse XML with streaming
    import xml.etree.ElementTree as ET
    
    article_count = 0
    batch = []
    batch_size = 1000
    
    print("Parsing Wikipedia dump (this may take hours)...")
    
    try:
        # Stream parse the bz2 compressed XML
        with bz2.open(dump_file, 'rt', encoding='utf-8', errors='replace') as f:
            context = ET.iterparse(f, events=('end',))
            
            for event, elem in context:
                if elem.tag.endswith('}page') or elem.tag == 'page':
                    # Extract article data
                    title_elem = elem.find('.//{http://www.mediawiki.org/xml/export-0.10/}title')
                    if title_elem is None:
                        title_elem = elem.find('.//title')
                    
                    text_elem = elem.find('.//{http://www.mediawiki.org/xml/export-0.10/}text')
                    if text_elem is None:
                        text_elem = elem.find('.//text')
                    
                    ns_elem = elem.find('.//{http://www.mediawiki.org/xml/export-0.10/}ns')
                    if ns_elem is None:
                        ns_elem = elem.find('.//ns')
                    
                    # Only process main namespace (articles)
                    if ns_elem is not None and ns_elem.text == '0':
                        if title_elem is not None and text_elem is not None:
                            title = title_elem.text or ""
                            raw_text = text_elem.text or ""
                            
                            # Skip redirects
                            if raw_text.lower().startswith('#redirect'):
                                elem.clear()
                                continue
                            
                            # Clean text
                            content = clean_wikitext(raw_text)
                            summary = extract_summary(content)
                            
                            # Extract categories
                            categories = re.findall(r'\[\[Category:([^\]|]+)', raw_text)
                            
                            batch.append((title, content, summary, json.dumps(categories[:10])))
                            article_count += 1
                            
                            if len(batch) >= batch_size:
                                cursor.executemany("""
                                    INSERT OR REPLACE INTO articles (title, content, summary, categories)
                                    VALUES (?, ?, ?, ?)
                                """, batch)
                                conn.commit()
                                print(f"\rImported {article_count:,} articles...", end='', flush=True)
                                batch = []
                    
                    # Clear element to free memory
                    elem.clear()
                    
    except KeyboardInterrupt:
        print("\nImport interrupted")
    except Exception as e:
        print(f"\nImport error: {e}")
    
    # Insert remaining batch
    if batch:
        cursor.executemany("""
            INSERT OR REPLACE INTO articles (title, content, summary, categories)
            VALUES (?, ?, ?, ?)
        """, batch)
        conn.commit()
    
    print(f"\nImported {article_count:,} articles total")
    
    # Rebuild FTS index
    print("Rebuilding full-text search index...")
    try:
        cursor.execute("INSERT INTO articles_fts(articles_fts) VALUES('rebuild')")
        conn.commit()
    except:
        pass
    
    conn.close()
    print("Import complete!")


def fetch_wikidata_entities(entity_types: List[str] = None):
    """Fetch entities from Wikidata API for specific types"""
    
    # Entity type to Wikidata class mapping
    TYPE_MAPPING = {
        'people': ('Q5', 20000),        # human
        'countries': ('Q6256', 300),    # country
        'cities': ('Q515', 10000),      # city
        'companies': ('Q4830453', 5000), # business enterprise
        'films': ('Q11424', 10000),     # film
        'tv_series': ('Q5398426', 5000), # television series
        'video_games': ('Q7889', 5000), # video game
        'albums': ('Q482994', 5000),    # album
        'books': ('Q571', 10000),       # book
        'diseases': ('Q12136', 2000),   # disease
        'species': ('Q16521', 10000),   # taxon
        'mountains': ('Q8502', 2000),   # mountain
        'lakes': ('Q23397', 1000),      # lake
        'rivers': ('Q4022', 2000),      # river
        'schools': ('Q3914', 5000),     # school
        'universities': ('Q3918', 3000), # university
        'websites': ('Q35127', 2000),   # website
        'events': ('Q1656682', 5000),   # event
    }
    
    if entity_types is None:
        entity_types = list(TYPE_MAPPING.keys())
    
    init_database()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    import urllib.request
    import urllib.parse
    
    WIKIDATA_API = "https://query.wikidata.org/sparql"
    
    for entity_type in entity_types:
        if entity_type not in TYPE_MAPPING:
            print(f"Unknown entity type: {entity_type}")
            continue
        
        wikidata_class, max_items = TYPE_MAPPING[entity_type]
        
        print(f"  Fetching {entity_type} (up to {max_items})...", end=' ', flush=True)
        
        # SPARQL query to get entities
        query = f"""
        SELECT ?item ?itemLabel ?itemDescription ?article WHERE {{
          ?item wdt:P31 wd:{wikidata_class} .
          OPTIONAL {{
            ?article schema:about ?item ;
                     schema:isPartOf <https://en.wikipedia.org/> .
          }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
        }}
        LIMIT {max_items}
        """
        
        try:
            headers = {
                'Accept': 'application/json',
                'User-Agent': 'JarvisKnowledgeBase/1.0 (https://github.com/optidex)'
            }
            
            url = f"{WIKIDATA_API}?query={urllib.parse.quote(query)}"
            req = urllib.request.Request(url, headers=headers)
            
            with urllib.request.urlopen(req, timeout=120) as response:
                data = json.loads(response.read().decode('utf-8'))
            
            results = data.get('results', {}).get('bindings', [])
            added = 0
            
            for item in results:
                entity_id = item.get('item', {}).get('value', '').split('/')[-1]
                label = item.get('itemLabel', {}).get('value', '')
                description = item.get('itemDescription', {}).get('value', '')
                wikipedia_url = item.get('article', {}).get('value', '')
                
                # Extract Wikipedia title from URL
                wikipedia_title = None
                if wikipedia_url:
                    wikipedia_title = urllib.parse.unquote(wikipedia_url.split('/wiki/')[-1]).replace('_', ' ')
                
                if entity_id and label:
                    try:
                        cursor.execute("""
                            INSERT OR REPLACE INTO entities (id, label, description, wikipedia_title, instance_of)
                            VALUES (?, ?, ?, ?, ?)
                        """, (entity_id, label, description, wikipedia_title, entity_type))
                        added += 1
                    except Exception as e:
                        pass
            
            conn.commit()
            print(f"{added} added")
            
        except urllib.error.HTTPError as e:
            print(f"error: HTTP Error {e.code}: {e.reason}")
        except Exception as e:
            print(f"error: {e}")
        
        # Rate limiting
        time.sleep(2)
    
    conn.close()
    print("Done!")


def main():
    parser = argparse.ArgumentParser(description="Jarvis Knowledge Base")
    subparsers = parser.add_subparsers(dest="command", help="Command")
    
    # Download command
    subparsers.add_parser("download", help="Download Wikipedia dump")
    
    # Fetch entities command
    fetch_parser = subparsers.add_parser("fetch-entities", help="Fetch Wikidata entities")
    fetch_parser.add_argument("types", nargs="*", help="Entity types to fetch (e.g., people companies books)")
    
    # Search command
    search_parser = subparsers.add_parser("search", help="Search articles")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--limit", "-l", type=int, default=5)
    search_parser.add_argument("--json", action="store_true")
    
    # Article command
    article_parser = subparsers.add_parser("article", help="Get article by title")
    article_parser.add_argument("title", help="Article title")
    article_parser.add_argument("--json", action="store_true")
    
    # Get command (alias for article, for tool compatibility)
    get_parser = subparsers.add_parser("get", help="Get article by title (alias)")
    get_parser.add_argument("title", help="Article title")
    get_parser.add_argument("--json", action="store_true")
    
    # Entity command
    entity_parser = subparsers.add_parser("entity", help="Get Wikidata entity")
    entity_parser.add_argument("entity_id", help="Entity ID (e.g., Q42)")
    entity_parser.add_argument("--json", action="store_true")
    
    # Stats command
    subparsers.add_parser("stats", help="Show knowledge base statistics")
    
    # Init command
    subparsers.add_parser("init", help="Initialize database")
    
    args = parser.parse_args()
    
    if args.command == "download":
        download_wikipedia()
    
    elif args.command == "search":
        results = search_articles(args.query, limit=args.limit)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            for r in results:
                print(f"\n== {r['title']} ==")
                print(r.get('summary', '')[:200])
    
    elif args.command == "article":
        article = get_article(args.title)
        if article:
            if args.json:
                print(json.dumps(article, indent=2))
            else:
                print(f"= {article['title']} =\n")
                print(article.get('summary', ''))
                if article.get('categories'):
                    print(f"\nCategories: {', '.join(article['categories'][:5])}")
        else:
            print(f"Article not found: {args.title}")
    
    elif args.command == "entity":
        entity = get_entity(args.entity_id)
        if entity:
            if args.json:
                print(json.dumps(entity, indent=2))
            else:
                print(f"= {entity['label']} ({entity['id']}) =")
                print(entity.get('description', ''))
        else:
            print(f"Entity not found: {args.entity_id}")
    
    elif args.command == "stats":
        stats = get_stats()
        print(f"Articles: {stats['articles']:,}")
        print(f"Entities: {stats['entities']:,}")
        print(f"Database: {stats['database_size_mb']} MB")
        print(f"Path: {stats['database_path']}")
    
    elif args.command == "init":
        init_database()
        print("Database initialized")
    
    elif args.command == "fetch-entities":
        types = args.types if args.types else None
        if types:
            print(f"Fetching entity types: {', '.join(types)}")
        else:
            print("Fetching all entity types...")
        fetch_wikidata_entities(types)
    
    elif args.command == "get":
        # Alias for 'article' command for compatibility
        article = get_article(args.title)
        if article:
            if args.json:
                print(json.dumps(article, indent=2))
            else:
                print(f"= {article['title']} =\n")
                print(article.get('content') or article.get('summary', ''))
        else:
            if args.json:
                print(json.dumps({'error': 'Article not found'}))
            else:
                print(f"Article not found: {args.title}")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

