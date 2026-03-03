"""
Data Cleaning Script for Reference Matching Pipeline
Clean các trường trong refs.bib và references.json
Output: refs_cleaned.json và references_cleaned.json
"""

import os
import re
import json
from pathlib import Path
from typing import Dict, List, Optional
from unidecode import unidecode

# Config
DATA_DIR = Path(r"D:\23120257\data_modelling")


# =============================================================================
# Text Cleaning Function
# =============================================================================

def normalize_text(text: str) -> str:
    """Chuẩn hóa text để matching"""
    if not text:
        return ""
    text = text.lower()
    text = unidecode(text)                      # é → e, ü → u
    text = re.sub(r'\s+', ' ', text)            # collapse whitespace
    text = re.sub(r'[^\w\s]', ' ', text)        # punctuation → space
    text = re.sub(r'\s+', ' ', text)            # collapse again
    return text.strip()


def clean_latex(text: str) -> str:
    """Xóa LaTeX formatting"""
    if not text:
        return ""
    # Remove braces around single words: {Deep} → Deep
    text = re.sub(r'\{([^{}]*)\}', r'\1', text)
    # Remove common LaTeX commands
    text = re.sub(r'\\emph\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\textbf\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\textit\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\textrm\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\text\{([^}]*)\}', r'\1', text)
    # Remove escape characters
    text = text.replace('\\&', '&')
    text = text.replace('\\%', '%')
    text = text.replace('\\_', '_')
    text = text.replace('\\$', '$')
    # Remove remaining backslash commands
    text = re.sub(r'\\[a-zA-Z]+', '', text)
    return text.strip()


def clean_mathml(text: str) -> str:
    """Xóa MathML tags từ Semantic Scholar data"""
    if not text:
        return ""
    # Remove all MathML tags
    text = re.sub(r'<mml:[^>]*>[^<]*</mml:[^>]*>', '', text)
    text = re.sub(r'<mml:[^>]*/>', '', text)
    text = re.sub(r'<[^>]+>', '', text)  # Remove any remaining HTML tags
    # Clean HTML entities
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&quot;', '"')
    return text.strip()


def normalize_author_name(name: str) -> str:
    """Normalize author name: 'Nguyen, Van A.' → 'van a nguyen'"""
    if not name:
        return ""
    name = clean_latex(name)
    # Handle "Last, First" format
    if ',' in name:
        parts = name.split(',', 1)
        if len(parts) == 2:
            name = f"{parts[1].strip()} {parts[0].strip()}"
    return normalize_text(name)


def normalize_authors_list(authors: List[str]) -> str:
    """Flatten and normalize author list"""
    if not authors:
        return ""
    normalized = [normalize_author_name(a) for a in authors]
    return ', '.join(normalized)


def extract_year(date_str: str) -> str:
    """Extract 4-digit year from date string"""
    if not date_str:
        return ""
    match = re.search(r'(\d{4})', str(date_str))
    return match.group(1) if match else ""


# =============================================================================
# BibTeX Parsing
# =============================================================================

def parse_bib_file(bib_path: Path) -> Dict:
    """Parse .bib file thành dict of entries"""
    entries = {}
    
    try:
        with open(bib_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except:
        return entries
    
    # Find all entries: @type{key, ... }
    entry_pattern = r'@(\w+)\s*\{\s*([^,\s]+)\s*,([^@]*?)(?=\n@|\Z)'
    
    for match in re.finditer(entry_pattern, content, re.DOTALL):
        entry_type = match.group(1).lower()
        entry_key = match.group(2).strip()
        fields_str = match.group(3)
        
        # Parse fields
        fields = {}
        field_pattern = r'(\w+)\s*=\s*[{"]([^}"]*)[}"]'
        for field_match in re.finditer(field_pattern, fields_str):
            field_name = field_match.group(1).lower()
            field_value = field_match.group(2).strip()
            fields[field_name] = field_value
        
        entries[entry_key] = {
            'type': entry_type,
            'key': entry_key,
            **fields
        }
    
    return entries


def clean_bib_entry(entry: Dict) -> Dict:
    """Clean một bib entry"""
    cleaned = {
        'key': entry.get('key', ''),
        'type': entry.get('type', ''),
    }
    
    # Title
    raw_title = entry.get('title', '')
    cleaned['title_raw'] = raw_title
    cleaned['title_clean'] = normalize_text(clean_latex(raw_title))
    
    # Author
    raw_author = entry.get('author', '')
    cleaned['author_raw'] = raw_author
    # Split by ' and ' and normalize each
    if raw_author:
        authors = re.split(r'\s+and\s+', raw_author)
        cleaned['author_clean'] = ', '.join([normalize_author_name(a) for a in authors])
    else:
        cleaned['author_clean'] = ''
    
    # Year
    cleaned['year'] = extract_year(entry.get('year', ''))
    
    # Journal/Venue
    raw_venue = entry.get('journal', '') or entry.get('booktitle', '') or entry.get('venue', '')
    cleaned['venue_raw'] = raw_venue
    cleaned['venue_clean'] = normalize_text(clean_latex(raw_venue))
    
    return cleaned


# =============================================================================
# References.json Cleaning
# =============================================================================

def clean_reference_entry(arxiv_id: str, entry: Dict) -> Dict:
    """Clean một reference entry từ Semantic Scholar"""
    cleaned = {
        'arxiv_id': arxiv_id,
    }
    
    # Title
    raw_title = entry.get('title', '')
    cleaned['title_raw'] = raw_title
    cleaned['title_clean'] = normalize_text(clean_mathml(raw_title))
    
    # Authors
    raw_authors = entry.get('authors', [])
    cleaned['authors_raw'] = raw_authors
    cleaned['authors_clean'] = normalize_authors_list(raw_authors)
    
    # Year
    pub_date = entry.get('publication_date', '')
    cleaned['year'] = extract_year(pub_date)
    
    # Venue
    raw_venue = entry.get('venue', '')
    cleaned['venue_raw'] = raw_venue
    cleaned['venue_clean'] = normalize_text(raw_venue)
    
    # Keep useful metadata
    cleaned['semantic_scholar_id'] = entry.get('semantic_scholar_id', '')
    cleaned['corpus_id'] = entry.get('corpus_id', '')
    
    return cleaned


# =============================================================================
# Main Processing
# =============================================================================

def process_paper(paper_dir: Path) -> Dict:
    """Process một paper: clean refs.bib và references.json"""
    paper_id = paper_dir.name
    result = {'paper_id': paper_id, 'bib_entries': {}, 'candidates': {}}
    
    # Clean refs.bib
    bib_path = paper_dir / 'refs.bib'
    if bib_path.exists():
        raw_entries = parse_bib_file(bib_path)
        for key, entry in raw_entries.items():
            result['bib_entries'][key] = clean_bib_entry(entry)
    
    # Clean references.json
    refs_path = paper_dir / 'references.json'
    if refs_path.exists():
        try:
            with open(refs_path, 'r', encoding='utf-8') as f:
                raw_refs = json.load(f)
            for arxiv_id, entry in raw_refs.items():
                result['candidates'][arxiv_id] = clean_reference_entry(arxiv_id, entry)
        except:
            pass
    
    return result


def save_cleaned_files(paper_dir: Path, cleaned_data: Dict):
    """Lưu cleaned data thành 2 file riêng"""
    # Save refs_cleaned.json
    refs_cleaned_path = paper_dir / 'refs_cleaned.json'
    with open(refs_cleaned_path, 'w', encoding='utf-8') as f:
        json.dump(cleaned_data['bib_entries'], f, indent=2, ensure_ascii=False)
    
    # Save references_cleaned.json
    candidates_cleaned_path = paper_dir / 'references_cleaned.json'
    with open(candidates_cleaned_path, 'w', encoding='utf-8') as f:
        json.dump(cleaned_data['candidates'], f, indent=2, ensure_ascii=False)


def main():
    print(f"Data directory: {DATA_DIR}")
    print("-" * 50)
    
    paper_dirs = sorted([d for d in DATA_DIR.iterdir() if d.is_dir()])
    total = len(paper_dirs)
    
    print(f"Processing {total} papers...")
    
    stats = {'total': 0, 'bib_entries': 0, 'candidates': 0}
    
    for i, paper_dir in enumerate(paper_dirs):
        cleaned_data = process_paper(paper_dir)
        save_cleaned_files(paper_dir, cleaned_data)
        
        stats['total'] += 1
        stats['bib_entries'] += len(cleaned_data['bib_entries'])
        stats['candidates'] += len(cleaned_data['candidates'])
        
        if (i + 1) % 100 == 0:
            print(f"  Processed {i + 1}/{total}...")
    
    print(f"\nDone!")
    print(f"  Papers processed: {stats['total']}")
    print(f"  Total bib entries: {stats['bib_entries']}")
    print(f"  Total candidates: {stats['candidates']}")
    print(f"\nOutput files per paper:")
    print(f"  - refs_cleaned.json")
    print(f"  - references_cleaned.json")


if __name__ == '__main__':
    main()
