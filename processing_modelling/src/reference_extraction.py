"""
Reference Extraction Script
Trích xuất và quản lý references từ LaTeX papers
"""

import os
import re
import glob
import json
from pathlib import Path
from collections import Counter, defaultdict


# ============================================================================
# FIELD PATTERN LEARNING - 58 COMMON FIELDS
# ============================================================================

# 58 common fields discovered từ bib_field_analysis.json (coverage >= 0.1%)
COMMON_FIELDS = [
    'title', 'author', 'year', 'pages', 'url', 'address', 'publisher', 
    'booktitle', 'doi', 'journal', 'volume', 'number', 'editor', 'eprint', 
    'archiveprefix', 'keywords', 'primaryclass', 'month', 'issn', 'adsnote', 
    'language', 'abstract', 'adsurl', 'note', 'isbn', 'urldate', 'eid', 
    'file', 'organization', 'numpages', 'series', 'issue', 'reportnumber', 
    'shorttitle', 'slaccitation', 'howpublished', 'timestamp', 'fjournal', 
    'mrnumber', 'mrclass', 'collaboration', 'biburl', 'bibsource', 'location', 
    'arxivid', 'mrreviewer', 'copyright', 'langid', 'type', 'pmid', 'date', 
    'eprinttype', 'edition', 'school', 'institution', 'groups'
]

                                                                                                                                                                # Global cache cho learned patterns
_LEARNED_PATTERNS = None


# ============================================================================
# REGEX PATTERNS
# ============================================================================

# pattern cho bibitem entries
# dạng 1: \bibitem[optional]{key}content  
# dạng 2: \bibitem{key}content
BIBITEM_PATTERN = re.compile(
    r'\\bibitem\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}'  # capture key
    r'([\s\S]*?)'  # capture content (non-greedy)
    r'(?=\\bibitem\s*(?:\[[^\]]*\])?\s*\{|\\end\{|\\bibliography\{|\Z)',  # lookahead: next bibitem, \end{...}, \bibliography{...}, or EOF
    re.MULTILINE | re.DOTALL
)

# pattern cho amsrefs \bib format
AMSREFS_BIB_PATTERN = re.compile(
    r'\\bib\{([^}]+)\}\{([^}]+)\}\s*\{',  # \bib{key}{type}{
    re.MULTILINE
)

# patterns cho citation extraction
CITATION_PATTERNS = [
    # \cite, \citep, \citet với optional arguments
    re.compile(r'\\cite[apt]?\*?\s*(?:\[[^\]]*\])?\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}'),
    # \citealt, \citealp, \citeauthor, \citeyear
    re.compile(r'\\cite(?:alt|alp|author|year|alias)\*?\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}'),
    # uppercase variants
    re.compile(r'\\Cite[apt]?\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}'),
    # \nocite
    re.compile(r'\\nocite\s*\{([^}]+)\}'),
]

# pattern để tìm bibtex entries trong file .bib
BIBTEX_ENTRY_PATTERN = re.compile(
    r'@(\w+)\s*\{\s*([^,\s]+)\s*,',  # @type{key,
    re.MULTILINE
)

# ============================================================================
# ENTRY TYPE NORMALIZATION
# ============================================================================

# các entry types chuẩn của bibtex
STANDARD_ENTRY_TYPES = {
    'article', 'book', 'booklet', 'conference', 'inbook', 'incollection',
    'inproceedings', 'manual', 'mastersthesis', 'misc', 'phdthesis',
    'proceedings', 'techreport', 'unpublished',
    # extended types
    'online', 'patent', 'periodical', 'report', 'thesis', 'dataset',
    'software', 'standard', 'electronic', 'www', 'webpage'
}

# mapping entry types lỗi chính tả/không chuẩn -> entry type chuẩn
ENTRY_TYPE_NORMALIZATION = {
    # lỗi chính tả của article
    'articl': 'article', 'articƒle': 'article', 'rticle': 'article',
    'articule': 'article', 'artile': 'article', 'artivle': 'article',
    'aritcle': 'article', 'articlearxiv': 'article', 'articleinfo': 'article',
    # lỗi chính tả của inproceedings  
    'inproceedingsv': 'inproceedings', 'inproceddings': 'inproceedings',
    'ainproceedings': 'inproceedings', 'iproceedings': 'inproceedings',
    'inproceedinfs': 'inproceedings', 'inproceedigs': 'inproceedings',
    'inrproceedings': 'inproceedings', 'inroceedings': 'inproceedings',
    'inoriceedings': 'inproceedings',
    # lỗi chính tả của mastersthesis
    'masterthesis': 'mastersthesis',
    # lỗi chính tả của unpublished
    'unplublished': 'unpublished',
    # lỗi chính tả của incollection
    'incolllection': 'incollection',
    # lỗi chính tả khác
    'electronis': 'electronic', 'oneline': 'online', 'mis': 'misc',
    'manuascript': 'misc', 'manuscript': 'misc',
    # mapping các loại đặc biệt -> misc hoặc loại phù hợp
    'eprint': 'article', 'preprint': 'article', 'journal': 'article',
    'paper': 'article', 'letter': 'article',
    'book_section': 'inbook', 'collection': 'incollection',
    'presentation': 'misc', 'blog': 'misc', 'url': 'online',
    'generic': 'misc', 'unknown': 'misc', 'data': 'dataset',
    'newspaper': 'article', 'inreference': 'incollection',
    'bachelorthesis': 'mastersthesis', 'underreview': 'unpublished',
    # các loại control/metadata -> giữ nguyên hoặc bỏ qua
    'string': 'string', 'preamble': 'preamble', 'comment': 'comment',
    'control': 'control', 'ieeetranbstctl': 'control',
    # các loại đặc thù của tổ chức
    'lhcbreport': 'techreport',
    'softwareversion': 'software', 'softwaremodule': 'software',
    'codefragment': 'software', 'softmisc': 'software',
    'artifactdataset': 'dataset', 'artifactsoftware': 'software',
    'languageresource': 'dataset',
    # conference aliases
    'wmt': 'inproceedings', 'conll': 'inproceedings', 'coling': 'inproceedings',
    'dac21': 'inproceedings', 'ling': 'inproceedings',
    # các loại còn lại map về misc
    'footnote': 'misc', 'jurisdiction': 'misc', 'tt': 'misc',
    '3': 'misc', 'c': 'misc', 'apoorva': 'misc', 'mvbook': 'book',
    'booktitle': 'misc', 'tournal': 'article', 'hournal': 'article',
    'ournal': 'article',
}

def normalize_entry_type(entry_type):
    """normalize entry type về dạng chuẩn"""
    entry_type_lower = entry_type.lower()
    
    # nếu là loại chuẩn, giữ nguyên
    if entry_type_lower in STANDARD_ENTRY_TYPES:
        return entry_type_lower
    
    # nếu có trong mapping, dùng mapping
    if entry_type_lower in ENTRY_TYPE_NORMALIZATION:
        return ENTRY_TYPE_NORMALIZATION[entry_type_lower]
    
    # mặc định trả về misc
    return 'misc'

def extract_bibinfo_values(content, field_name):
    """
    Extract all values for a specific bibinfo field, handling nested braces correctly.
    
    Args:
        content: Raw LaTeX content
        field_name: Field name like 'author', 'title', 'journal'
    
    Returns:
        list: List of extracted values
    """
    values = []
    # Pattern: \bibinfo{field_name}{
    pattern = f'\\\\bibinfo\\s*\\{{{field_name}\\}}\\s*\\{{'
    
    for match in re.finditer(pattern, content, re.IGNORECASE):
        start = match.end() - 1  # Position of opening {
        
        # Count braces to find matching closing brace
        brace_count = 0
        end = start
        for i in range(start, len(content)):
            if content[i] == '{':
                brace_count += 1
            elif content[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    end = i
                    break
        
        if end > start:
            value = content[start+1:end]
            # Clean the extracted value
            value = re.sub(r'\\bibfnamefont\s*\{([^}]+)\}', r'\1', value)
            value = re.sub(r'\\bibnamefont\s*\{([^}]+)\}', r'\1', value)
            value = value.replace('~', ' ')
            value = re.sub(r'\\[a-zA-Z]+\s*', '', value)
            value = ' '.join(value.split()).strip(' ,')
            if value and len(value) > 1:
                values.append(value)
    
    return values

# ============================================================================
# PHASE 1: PATTERN LEARNING FROM EXISTING BIB FILES
# ============================================================================

def learn_field_patterns_from_bib_files(base_dir, max_files=None):
    """
    PHASE 1: Thu thập field values VÀ extraction patterns từ .bib files
    
    Args:
        base_dir: Thư mục chứa papers
        max_files: Giối hạn số file (None = all)
    
    Returns:
        dict: {
            'field_values': {field: Counter},
            'field_patterns': {field: extraction_rules},
            'statistics': metadata
        }
    """
    print("=" * 70)
    print("PHASE 1: LEARNING FROM EXISTING BIB FILES")
    print("=" * 70)
    
    base_path = Path(base_dir)
    field_values = {field: Counter() for field in COMMON_FIELDS}
    field_examples = {field: [] for field in COMMON_FIELDS}
    
    # Tìm .bib files
    print("\nScanning for .bib files...")
    bib_files = []
    for bib_file in base_path.rglob('*.bib'):
        if bib_file.name not in ['refs.bib', 'all_references.bib']:
            bib_files.append(bib_file)
    
    if max_files:
        bib_files = bib_files[:max_files]
    
    print(f"Found {len(bib_files):,} .bib files")
    
    # Parse từng file
    print("\nExtracting field values...")
    total_entries = 0
    
    for i, bib_file in enumerate(bib_files):
        if (i + 1) % 500 == 0:
            print(f"  Progress: {i+1:,}/{len(bib_files):,} files")
        
        try:
            content = bib_file.read_text(encoding='utf-8', errors='ignore')
            
            # Parse BibTeX entries
            entries = re.findall(
                r'@\w+\s*\{[^,]+,(.*?)(?=@|\Z)',
                content,
                re.MULTILINE | re.DOTALL
            )
            
            total_entries += len(entries)
            
            for entry_text in entries:
                # Extract field = {value} or field = "value"
                field_matches = re.findall(
                    r'^\s*(\w+)\s*=\s*[{"]([^}"]*)[}"]',
                    entry_text,
                    re.MULTILINE
                )
                
                for field_name, field_value in field_matches:
                    field_name = field_name.lower()
                    if field_name in COMMON_FIELDS and field_value.strip():
                        field_values[field_name][field_value.strip()] += 1
                        
                        # Save examples (max 20 per field)
                        if len(field_examples[field_name]) < 20:
                            field_examples[field_name].append(field_value.strip())
        
        except Exception as e:
            continue
    
    print(f"\n✓ Processed {total_entries:,} BibTeX entries")
    
    # Build extraction patterns
    print("\nBuilding field recognition patterns...")
    field_patterns = {}
    
    for field_name in COMMON_FIELDS:
        if not field_values[field_name]:
            continue
        
        values = field_values[field_name]
        top_values = values.most_common(100)
        
        field_patterns[field_name] = {
            'count': sum(values.values()),
            'unique': len(values),
            'coverage': sum(values.values()) / total_entries if total_entries > 0 else 0,
            'top_values': dict(top_values),
            'examples': field_examples[field_name][:10],
        }
        
        # Field-specific pattern learning
        if field_name == 'author':
            # Learn author patterns
            separators = Counter()
            for val in field_examples[field_name][:100]:
                if ' and ' in val:
                    separators['and'] += 1
                if '\\and' in val:
                    separators['\\and'] += 1
                if ', ' in val:
                    separators[','] += 1
            field_patterns[field_name]['separators'] = dict(separators.most_common(5))
        
        elif field_name in ['doi', 'url']:
            # Learn URL/DOI prefixes
            prefixes = Counter()
            for val in field_examples[field_name][:100]:
                if val.startswith('http'):
                    prefixes['http'] += 1
                if val.startswith('https'):
                    prefixes['https'] += 1
                if val.startswith('10.'):
                    prefixes['10.'] += 1
                if 'doi.org' in val:
                    prefixes['doi.org'] += 1
            field_patterns[field_name]['prefixes'] = dict(prefixes.most_common(5))
        
        elif field_name in ['eprint', 'arxivid']:
            # Learn arXiv ID formats
            formats = Counter()
            for val in field_examples[field_name][:100]:
                if re.match(r'\d{4}\.\d+', val):
                    formats['new'] += 1
                if '/' in val:
                    formats['old'] += 1
            field_patterns[field_name]['formats'] = dict(formats.most_common())
    
    print(f"✓ Built patterns for {len(field_patterns)} fields")
    
    # Print summary
    print("\n" + "=" * 70)
    print("LEARNING COMPLETE")
    print("=" * 70)
    print(f"Total entries analyzed: {total_entries:,}")
    print(f"Fields with data: {len(field_patterns)}")
    print(f"\nTop 10 fields by coverage:")
    sorted_fields = sorted(field_patterns.items(), 
                          key=lambda x: x[1]['coverage'], 
                          reverse=True)
    for field, data in sorted_fields[:10]:
        print(f"  {field:<20} {data['coverage']*100:>6.2f}%  ({data['count']:,} values)")
    
    return {
        'field_values': field_values,
        'field_patterns': field_patterns,
        'statistics': {
            'total_bib_files': len(bib_files),
            'total_entries': total_entries,
            'fields_found': len(field_patterns)
        }
    }


def get_learned_patterns(base_dir='d:/23120257/23120257', force_reload=False):
    """
    Get learned patterns (with caching)
    Load từ cache hoặc run Phase 1 nếu chưa có
    """
    global _LEARNED_PATTERNS
    
    if _LEARNED_PATTERNS is not None and not force_reload:
        return _LEARNED_PATTERNS
    
    # Try load from cache file
    cache_file = Path('field_patterns_cache.json')
    if cache_file.exists() and not force_reload:
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                _LEARNED_PATTERNS = data.get('field_patterns', {})
            print(f"✓ Loaded cached patterns for {len(_LEARNED_PATTERNS)} fields")
            return _LEARNED_PATTERNS
        except Exception as e:
            print(f"Warning: Failed to load cache: {e}")
            pass
    
    # Run Phase 1: Learn new patterns
    print("\nNo cache found. Running Phase 1 learning...")
    learning_result = learn_field_patterns_from_bib_files(base_dir, max_files=None)
    _LEARNED_PATTERNS = learning_result['field_patterns']
    
    # Save cache
    try:
        cache_data = {
            'field_patterns': _LEARNED_PATTERNS,
            'statistics': learning_result['statistics'],
            'generated_at': str(Path('.').resolve())
        }
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)
        print(f"\n✓ Saved pattern cache to {cache_file}")
    except Exception as e:
        print(f"Warning: Failed to save cache: {e}")
    
    return _LEARNED_PATTERNS


def extract_additional_fields_with_patterns(raw_content, patterns):
    """
    Extract các field bổ sung dựa trên learned patterns
    
    Args:
        raw_content: Nội dung bibitem
        patterns: Learned patterns dict
    
    Returns:
        dict: Additional fields extracted
    """
    additional = {}
    
    if not patterns:
        return additional
    
    # ISBN
    if 'isbn' in patterns:
        isbn_match = re.search(r'ISBN\s*[:-]?\s*([\d-]+)', raw_content, re.I)
        if isbn_match:
            additional['isbn'] = isbn_match.group(1).strip()
    
    # ISSN  
    if 'issn' in patterns:
        issn_match = re.search(r'ISSN\s*[:-]?\s*([\d-]+)', raw_content, re.I)
        if issn_match:
            additional['issn'] = issn_match.group(1).strip()
    
    # Month
    if 'month' in patterns:
        month_pattern = r'\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\b'
        month_match = re.search(month_pattern, raw_content, re.I)
        if month_match:
            additional['month'] = month_match.group(1).lower()
    
    # Edition
    if 'edition' in patterns:
        edition_match = re.search(r'(\d+)(?:st|nd|rd|th)?\s+(?:ed\.|edition)', raw_content, re.I)
        if edition_match:
            additional['edition'] = edition_match.group(1)
    
    # Series
    if 'series' in patterns:
        series_patterns = [
            r'(?:Lecture Notes|LNCS|LNAI)\s+(?:in\s+)?([^,\.]+)',
            r'Series:\s*([^,\.]+)',
        ]
        for pattern in series_patterns:
            series_match = re.search(pattern, raw_content, re.I)
            if series_match:
                additional['series'] = series_match.group(1).strip()
                break
    
    # EID
    if 'eid' in patterns:
        eid_match = re.search(r'\beid[:\s]+(\w+)', raw_content, re.I)
        if eid_match:
            additional['eid'] = eid_match.group(1)
    
    # Collaboration
    if 'collaboration' in patterns:
        collab_match = re.search(r'\[([A-Z][A-Za-z0-9-]+)\s+Collaboration\]', raw_content)
        if collab_match:
            additional['collaboration'] = collab_match.group(1)
    
    # Editor - disabled, causes incorrect extraction
    # if 'editor' in patterns:
    #     editor_match = re.search(r'(?:ed(?:itor)?s?\.?|Ed\.)[:\s]+([^,\.]+)', raw_content, re.I)
    #     if editor_match:
    #         additional['editor'] = editor_match.group(1).strip()
    
    # School/Institution
    if 'school' in patterns or 'institution' in patterns:
        school_match = re.search(
            r'(?:thesis|dissertation)[,\s]+([^,\.]+(?:University|Institute|College|School))',
            raw_content, re.I
        )
        if school_match:
            school_name = school_match.group(1).strip()
            if 'ph\.?d|phd|doctoral' in raw_content.lower():
                additional['school'] = school_name
            else:
                additional['school'] = school_name
    
    # Address/Location - disabled, causes incorrect extraction  
    # if 'address' in patterns or 'location' in patterns:
    #     addr_match = re.search(r',\s*([A-Z][a-z]+(?:,\s*[A-Z]{2,})?)[\.,]', raw_content)
    #     if addr_match:
    #         additional['address'] = addr_match.group(1).strip()
    
    # Organization
    if 'organization' in patterns:
        org_match = re.search(r'(?:org(?:anization)?)[:\s]+([^,\.]+)', raw_content, re.I)
        if org_match:
            additional['organization'] = org_match.group(1).strip()
    
    # Issue (alternative to number)
    if 'issue' in patterns:
        issue_match = re.search(r'issue\s+(\d+)', raw_content, re.I)
        if issue_match:
            additional['issue'] = issue_match.group(1)
    
    # Report Number
    if 'reportnumber' in patterns:
        report_match = re.search(r'(?:Report\s+No\.|Tech\.?\s+Rep\.?)[:\s]*([A-Z]+-?[\w-]+)', raw_content, re.I)
        if report_match:
            additional['reportnumber'] = report_match.group(1)
    
    # Primary Class (arXiv)
    if 'primaryclass' in patterns:
        pclass_match = re.search(r'\[([\w-]+\.[\w-]+)\]', raw_content)
        if pclass_match:
            additional['primaryclass'] = pclass_match.group(1)
    
    return additional


# ============================================================================
# HELPER FUNCTIONS  
# ============================================================================

def remove_latex_comments(content):
    """xóa comments latex (dòng bắt đầu bằng % hoặc phần sau %)"""
    lines = content.split('\n')
    cleaned = []
    for line in lines:
        # tìm % không bị escape
        idx = 0
        while idx < len(line):
            pos = line.find('%', idx)
            if pos == -1:
                break
            # kiểm tra escape
            if pos > 0 and line[pos-1] == '\\':
                idx = pos + 1
                continue
            # tìm thấy comment thật
            line = line[:pos]
            break
        cleaned.append(line)
    return '\n'.join(cleaned)


def find_all_versions(base_dir):
    """
    tìm tất cả version folders trong data
    returns: list of (paper_id, version_dir) tuples
    """
    versions = []
    base_path = Path(base_dir)
    
    # tìm trong 23120257/paper_id/tex/paper_idvN/
    for paper_dir in base_path.iterdir():
        if not paper_dir.is_dir():
            continue
        tex_dir = paper_dir / 'tex'
        if not tex_dir.exists():
            continue
        for version_dir in tex_dir.iterdir():
            if version_dir.is_dir():
                versions.append((paper_dir.name, version_dir))
    
    # Filter versions by paper ID range 14000-15000
    # No filter - process all papers
    return versions


def has_bib_file(version_dir):
    """kiểm tra đã có file .bib chưa (không tính phản hồi do script tạo)"""
    bib_files = list(Path(version_dir).glob('*.bib'))
    # lọc bỏ file output của script nếu có (tên file = tên thư mục .bib)
    output_bib_name = f"{Path(version_dir).name}.bib"
    original_bibs = [f for f in bib_files 
                     if f.name.lower() != output_bib_name.lower()]
    return len(original_bibs) > 0, original_bibs


def get_all_tex_files(version_dir):
    """lấy tất cả file .tex trong version directory"""
    return list(Path(version_dir).glob('*.tex'))


def read_file_content(file_path):
    """đọc nội dung file với nhiều encoding"""
    encodings = ['utf-8', 'latin-1', 'cp1252']
    for enc in encodings:
        try:
            with open(file_path, 'r', encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    return None


# ============================================================================
# BIBITEM EXTRACTION
# ============================================================================


# ============================================================================
# HELPER DATA
# ============================================================================

COMMON_PUBLISHERS = [
    'Springer', 'Wiley', 'IEEE', 'ACM', 'Elsevier', 'Oxford University Press',
    'Cambridge University Press', 'MIT Press', 'Pearson', 'Routledge',
    'Sage', 'Taylor & Francis', 'Wolters Kluwer', 'Nature Publishing Group',
    'AAAS', 'Prentice Hall', 'McGraw-Hill', 'Addison-Wesley', 'O\'Reilly',
    'Chapman and Hall', 'CRC Press', 'Hindaawi', 'Frontiers', 'MDPI',
    'PLOS', 'BioMed Central', 'IOP', 'AIP', 'APS', 'ACS', 'RSC',
    'Emerald', 'Inderscience', 'World Scientific', 'Bentham Science',
    'Morgan Kaufmann', 'Kluwer', 'Academic Press', 'Pergamon',
    'North-Holland', 'Butterworth-Heinemann', 'Saunders', 'Mosby',
    'Churchill Livingstone'
]

MONTHS = {
    'jan': 'jan', 'january': 'jan',
    'feb': 'feb', 'february': 'feb',
    'mar': 'mar', 'march': 'mar',
    'apr': 'apr', 'april': 'apr',
    'may': 'may',
    'jun': 'jun', 'june': 'jun',
    'jul': 'jul', 'july': 'jul',
    'aug': 'aug', 'august': 'aug',
    'sep': 'sep', 'september': 'sep',
    'oct': 'oct', 'october': 'oct',
    'nov': 'nov', 'november': 'nov',
    'dec': 'dec', 'december': 'dec'
}

# danh sách universities/schools để detect thesis
UNIVERSITIES = [
    'University', 'Institut', 'College', 'School', 'Academy',
    'MIT', 'Stanford', 'Harvard', 'Berkeley', 'CMU', 'Oxford', 'Cambridge',
    'ETH', 'EPFL', 'Caltech', 'Princeton', 'Yale', 'Columbia', 'Cornell',
    'UCLA', 'NYU', 'Georgia Tech', 'Tsinghua', 'Peking', 'NUS', 'NTU'
]

# collaborations trong physics/HEP
COLLABORATIONS = [
    'ATLAS', 'CMS', 'LHCb', 'ALICE', 'CERN', 'Fermilab', 'SLAC',
    'Belle', 'BaBar', 'DESY', 'KEK', 'LIGO', 'Virgo', 'IceCube',
    'Planck', 'WMAP', 'DES', 'SDSS', 'DUNE', 'T2K', 'NOvA'
]

# series names phổ biến
SERIES_NAMES = [
    'Lecture Notes in Computer Science', 'LNCS', 'LNAI',
    'Lecture Notes in Artificial Intelligence',
    'Communications in Computer and Information Science', 'CCIS',
    'Advances in Neural Information Processing Systems', 'NeurIPS',
    'Proceedings of Machine Learning Research', 'PMLR', 'JMLR',
    'ACL Anthology', 'EMNLP', 'NAACL', 'COLING', 'EACL',
    'Studies in Computational Intelligence', 'SCI',
    'Springer Series', 'Graduate Texts in Mathematics'
]

# languages phổ biến
LANGUAGES = [
    'english', 'german', 'french', 'spanish', 'italian', 'portuguese',
    'chinese', 'japanese', 'korean', 'russian', 'arabic', 'hindi',
    'dutch', 'polish', 'turkish', 'vietnamese', 'thai', 'indonesian'
]

# ============================================================================
# BIBITEM EXTRACTION
# ============================================================================

def extract_bibitems(tex_content):
    """
    trích xuất các bibitem entries từ nội dung tex
    Tìm trực tiếp \\bibitem thay vì yêu cầu thebibliography block
    returns: list of (key, raw_content) tuples
    """
    # xóa comments trước
    content = remove_latex_comments(tex_content)
    
    entries = []
    
    # Tìm TẤT CẢ \\bibitem trực tiếp trong file
    # Pattern: \\bibitem[optional]{key}content until next \\bibitem or \\end{...} or EOF
    for match in BIBITEM_PATTERN.finditer(content):
        key = match.group(1).strip()
        raw_content = match.group(2).strip()
        if key and raw_content:
            entries.append((key, raw_content))
    
    return entries


def clean_bibitem_content(raw_content):
    """làm sạch nội dung bibitem để tạo bibtex"""
    content = raw_content
    
    # --- RevTeX/APS specific patterns ---
    # Remove BibitemOpen, BibitemShut, NoStop etc
    content = re.sub(r'\\BibitemOpen\b', '', content)
    content = re.sub(r'\\BibitemShut\s*\{[^}]*\}', '', content)
    
    # Remove bibfield wrapper but keep content
    content = re.sub(r'\\bibfield\s*\{[^}]*\}\s*\{', '{', content)
    
    # Remove href@noop and similar
    content = re.sub(r'\\href@noop\s*\{[^}]*\}\s*\{', '{', content)
    content = re.sub(r'\\href\s*\{[^}]*\}\s*\{([^}]*)\}', r'\1', content)
    
    # Extract content from bibinfo - keep the actual value
    content = re.sub(r'\\bibinfo\s*\{[^}]*\}\s*\{([^}]*)\}', r'\1', content)
    
    # Remove bibfnamefont, bibnamefont, citenamefont - keep content
    content = re.sub(r'\\bibfnamefont\s*\{([^}]*)\}', r'\1', content)
    content = re.sub(r'\\bibnamefont\s*\{([^}]*)\}', r'\1', content)
    content = re.sub(r'\\citenamefont\s*\{([^}]*)\}', r'\1', content)
    
    # Remove natexlab
    content = re.sub(r'\\natexlab\s*\{[^}]*\}', '', content)
    
    # --- Standard LaTeX patterns ---
    # xóa các newblock, em, sc, etc
    content = re.sub(r'\\newblock\s*', ' ', content)
    content = re.sub(r'\{\\sc\s+', '', content)
    content = re.sub(r'\{\\em\s+', '', content)
    content = re.sub(r'\\emph\{([^}]*)\}', r'\1', content)
    content = re.sub(r'\\textit\{([^}]*)\}', r'\1', content)
    content = re.sub(r'\\textbf\{([^}]*)\}', r'\1', content)
    content = re.sub(r'\\texttt\{([^}]*)\}', r'\1', content)
    
    # Remove remaining single-arg LaTeX commands but keep content
    content = re.sub(r'\\[a-zA-Z@]+\s*\{([^}]*)\}', r'\1', content)
    
    # Clean up tildes and backslash-space
    content = content.replace('~', ' ')
    content = re.sub(r'\\ ', ' ', content)
    
    # Remove empty braces and clean up
    content = re.sub(r'\{\s*\}', '', content)
    content = re.sub(r'\{([^{}]*)\}', r'\1', content)  # Remove remaining single braces
    
    # normalize whitespace
    content = ' '.join(content.split())
    return content.strip()


def clean_latex_formatting(text):
    """Xóa formatting latex nhưng giữ lại nội dung text"""
    # Xóa các command kẹp text: \emph{...}, \textbf{...}, \textit{...}, \textsc{...}
    # Loop để xử lý lồng nhau đơn giản
    prev_text = ""
    while text != prev_text:
        prev_text = text
        text = re.sub(r'\\[a-zA-Z]+\{([^{}]+)\}', r'\1', text)
    
    # Xóa command đơn lẻ: \newblock, \relax
    text = re.sub(r'\\[a-zA-Z]+', ' ', text)
    
    # Xóa ngoặc dư thừa
    text = text.replace('{', '').replace('}', '')
    
    # Xóa gạch nối dư và backslash-space
    text = text.replace('~', ' ')
    text = re.sub(r'\\ ', ' ', text)  # backslash-space
    text = re.sub(r'\\\s+', ' ', text)  # backslash followed by whitespace
    
    # Normalize space
    text = ' '.join(text.split())
    return text


def strip_formatting_for_parsing(content):
    """
    Loại bỏ hoàn toàn các formatting LaTeX để parsing dễ hơn.
    Dùng trước khi tách author/title/journal.
    """
    # 1. Xóa các link/href pattern nhưng giữ text hiển thị
    content = re.sub(r'\\href\{[^}]*\}\{([^}]*)\}', r'\1', content)
    content = re.sub(r'\\url\{[^}]*\}', '', content)
    
    # 2. Xóa các formatting commands: \textbf{}, \textit{}, \emph{}, {\it }, {\em }, {\bf }
    # Loop để xử lý nested
    prev = ""
    while prev != content:
        prev = content
        # \textbf{content} -> content
        content = re.sub(r'\\textbf\{([^{}]*)\}', r'\1', content)
        content = re.sub(r'\\textit\{([^{}]*)\}', r'\1', content)
        content = re.sub(r'\\emph\{([^{}]*)\}', r'\1', content)
        content = re.sub(r'\\textsc\{([^{}]*)\}', r'\1', content)
        content = re.sub(r'\\texttt\{([^{}]*)\}', r'\1', content)
        # {\it content} -> content
        content = re.sub(r'\{\\it\s+([^{}]*)\}', r'\1', content)
        content = re.sub(r'\{\\em\s+([^{}]*)\}', r'\1', content)
        content = re.sub(r'\{\\bf\s+([^{}]*)\}', r'\1', content)
        content = re.sub(r'\{\\sc\s+([^{}]*)\}', r'\1', content)
        content = re.sub(r'\{\\tt\s+([^{}]*)\}', r'\1', content)
        # $\bf{content}$ or $content$ -> content
        content = re.sub(r'\$\\?bf\{?([^${}]*)\}?\$', r'\1', content)
        content = re.sub(r'\$([^$]*)\$', r'\1', content)
    
    # 3. Xóa các command còn lại: \command{content} -> content
    content = re.sub(r'\\[a-zA-Z]+\{([^{}]*)\}', r'\1', content)
    
    # 4. Xóa dấu ngoặc nhọn thừa
    content = re.sub(r'\{([^{}]*)\}', r'\1', content)
    
    # 5. Xóa ~ và \\ space
    content = content.replace('~', ' ')
    content = re.sub(r'\\\s', ' ', content)
    
    # 6. Xóa các escape characters
    content = re.sub(r'\\&', '&', content)
    content = re.sub(r'\\%', '%', content)
    content = re.sub(r'\\#', '#', content)
    content = re.sub(r'\\_', '_', content)
    
    # 7. Normalize whitespace
    content = re.sub(r'\s+', ' ', content)
    
    return content.strip()


def is_valid_author_text(text):
    """Kiểm tra text có phải là author hợp lệ không (không chứa số, link, ...)"""
    if not text or len(text) < 2:
        return False
    # Author không nên chứa: URL, DOI, số volume/pages, năm đứng một mình
    if re.search(r'https?://', text):
        return False
    if re.search(r'\b10\.\d{4,}/', text):  # DOI pattern
        return False
    if re.search(r'\b\d{3,}\b', text):  # Số 3+ chữ số (volume, pages, year)
        return False
    # Author thường có chữ cái và có thể có dấu chấm (initials), dấu phẩy, "and"
    if not re.search(r'[A-Za-z]', text):
        return False
    return True


def is_valid_title_or_journal(text):
    """Kiểm tra text có phải là title/journal hợp lệ không"""
    if not text or len(text) < 2:
        return False
    # Title/Journal không nên chứa: URL, DOI
    if re.search(r'https?://', text):
        return False
    if re.search(r'\b10\.\d{4,}/', text):  # DOI pattern
        return False
    # Không nên có số volume/pages patterns
    if re.search(r'\b\d{3,}\b', text):  # 3+ digits
        return False
    return True


def multipass_parse_bibitem(content):
    """
    Simple fallback parsing for bibitems.
    Only extracts basic metadata - author/title/journal parsed by main strategies.
    """
    result = {
        'author': None,
        'title': None,
        'journal': None,
        'year': None,
        'volume': None,
        'pages': None,
        'doi': None,
        'url': None,
        'number': None,
        'eprint': None,
        'note': None,
    }
    
    # Extract DOI
    doi_match = re.search(r'(?:doi[:\s]*)?(10\.\d{4,9}/[-._;()/:a-zA-Z0-9]+)', content, re.I)
    if doi_match:
        result['doi'] = doi_match.group(1).rstrip('.')
    
    # Extract URL
    url_match = re.search(r'\\url\{([^}]+)\}', content)
    if url_match:
        result['url'] = url_match.group(1)
    
    # Extract arXiv
    arxiv_match = re.search(r'arXiv[:\s]*(\d{4}\.\d{4,5}|[a-z-]+/\d+)', content, re.I)
    if arxiv_match:
        result['eprint'] = arxiv_match.group(1)
    
    # Extract year from (YYYY)
    year_match = re.search(r'\((\d{4})\)', content)
    if year_match:
        result['year'] = year_match.group(1)
    
    # Extract volume from \textbf{}
    vol_match = re.search(r'\\textbf\{(\d+)\}', content)
    if vol_match:
        result['volume'] = vol_match.group(1)
    
    # Extract pages
    pages_match = re.search(r'(\d+)\s*[-–—]+\s*(\d+)', content)
    if pages_match:
        result['pages'] = f"{pages_match.group(1)}--{pages_match.group(2)}"
    
    return result


def clean_field_value(text, keep_period=False):
    """
    Remove LaTeX formatting and surrounding delimiters from field values.
    Ex: \\textit{Journal} -> Journal
        {Title} -> Title
    """
    if not text:
        return text
        
    # 0. specific replacements
    text = re.sub(r'\\etal\b', 'et al.', text, flags=re.I)
    text = re.sub(r'\\&', '&', text)
    text = re.sub(r'\\textendash', '-', text)
    text = re.sub(r'\\textemdash', '--', text)

    # 1. Remove LaTeX formatting commands: \textit{...}, \textbf{...}, etc.
    # Keep the content inside the braces
    # Repeat to handle nested commands if simple
    for _ in range(3):
        # cmd{content} -> content
        text = re.sub(r'\\(?:textit|textbf|emph|mathbf|mathrm|text|bibnamefont|bibfnamefont|textsc|citenamefont|bibnamefont|bibinfo\s*\{[^}]+\})\s*\{([^}]+)\}', r'\1', text)
        
        # {\cmd content} -> content  (e.g., {\it Journal})
        text = re.sub(r'\{\\(?:it|bf|sc|sl|rm|sf|tt|em|textsc|bibnamefont)(?:\s+)([^}]+)\}', r'\1', text)
        
        # Loose font commands if any match: \it Text -> Text
        text = re.sub(r'\\(?:it|bf|sc|sl|rm|sf|tt|em|textsc)\b\s*', '', text)
    
    # 2. Remove surrounding delimiters if they enclose the whole string
    text = text.strip()
    
    # Check for {}, (), [], "", '', ``''
    # Loop to handle multiple layers like {{Title}}
    changed = True
    while changed:
        changed = False
        if len(text) >= 2 and (
           (text.startswith('{') and text.endswith('}')) or \
           (text.startswith('(') and text.endswith(')')) or \
           (text.startswith('[') and text.endswith(']')) or \
           (text.startswith('"') and text.endswith('"')) or \
           (text.startswith("'") and text.endswith("'"))
        ):
             text = text[1:-1].strip()
             changed = True
        
        # Handle LaTeX specific quotes ``...''
        if len(text) >= 4 and text.startswith("``") and text.endswith("''"):
            text = text[2:-2].strip()
            changed = True

    # 2.3 Strip unpaired quote chars at start/end
    text = text.strip('"\'')
    text = text.lstrip('`').rstrip("'")
            
            
    # 2.5 Strict Punctuation Strip (User Request)
    # "dấu phẩy, dấu chấm thì xóa hết" -> Strip . and , from start/end
    # EXCEPT for journals where period might be an abbreviation
    if keep_period:
        text = text.strip(" ,")
    else:
        text = text.strip(" .,")
    
    # Reverted aggressive quote cleanup because user requires "balanced" (có đóng có mở).
    # Strategy 0j should handle the extraction so that quotes are not part of the field content.
             
    # 3. Final whitespace clean
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def parse_bibitem_to_bibtex(key, raw_content):
    """
    chuyển đổi một bibitem thành bibtex entry
    Xử lý nhiều định dạng khác nhau dựa trên dấu ngăn cách:
    - Semicolon format: Author. {Title}. Journal Year;Vol:Pages
    - Braces format: Author, {Title}, Journal
    - Quoted format: Author, "Title", Journal
    - Period format: Author. Title. Journal
    - Comma format: Author, Title, Journal
    """
    fields = {}
    
    # === 0. PREPROCESSING ===
    # Save original content for format detection (before ~ removal)
    raw_content_orig = raw_content
    
    # Pre-split lines before normalization to preserve structural info
    lines_orig = [l.strip() for l in raw_content.splitlines() if l.strip()]
    
    # 0a. Remove organization names in parentheses after "et al."
    raw_content = re.sub(r'(et\s+al\.?)\s*\([^)]*Collaboration[^)]*\)', r'\1', raw_content, flags=re.I)
    raw_content = re.sub(r'(et\s+al\.?)\s*\([^)]*Consortium[^)]*\)', r'\1', raw_content, flags=re.I)
    raw_content = re.sub(r'(et\s+al\.?)\s*\([^)]*Group[^)]*\)', r'\1', raw_content, flags=re.I)
    
    # 0b. Normalize tildes and special spaces
    raw_content = raw_content.replace('~', ' ')
    raw_content = raw_content.replace(r'\thinspace', ' ')
    
    # 0c. Clean multiple spaces
    raw_content = re.sub(r'\s+', ' ', raw_content).strip()
    
    # === 0e. DETECT FORMAT CHECK ===

    # === 0a5-NEW. STRATEGY: Elsevier/IEEE Plain Text (HIGHEST PRIORITY) ===
    # Format: K.~Lee, R.~Mishra, Title text, Journal Vol (Year) Pages.
    # Key identifier: Has ~ in original content for author initials
    # Must run FIRST before any other strategy can catch these entries
    if '~' in raw_content_orig and r'\path{' in raw_content:
        content = raw_content  # Already normalized
        
        # 1. Extract DOI from \path{doi:...} or \path{...}
        path_m = re.search(r'\\path\s*\{(?:doi:)?([^}]+)\}', content)
        if path_m:
            fields['doi'] = path_m.group(1).strip()
        
        # 2. Extract URL from \href{URL}{...}
        href_m = re.search(r'\\href\s*\{([^}]+)\}', content)
        if href_m:
            fields['url'] = href_m.group(1).strip()
        
        # 3. Get main text (before \newblock or \href)
        main_text = content
        for marker in [r'\newblock', r'\href']:
            pos = main_text.find(marker)
            if pos > 0:
                main_text = main_text[:pos]
        main_text = main_text.strip(' .')
        
        # 4. Split by comma and classify
        parts = [p.strip() for p in main_text.split(',') if p.strip()]
        author_parts = []
        title_part = None
        journal_part = None
        
        for i, p in enumerate(parts):
            # Check if this looks like an author: starts with Initial. (e.g., "K. Lee", "J. R. Smith")
            # Pattern: Starts with capital letter followed by period within first 3 chars
            is_author = bool(re.match(r'^[A-Z]\.', p)) or bool(re.match(r'^[A-Z]\.\s*[A-Z]\.', p))
            
            if is_author and title_part is None:
                # Still in authors section
                author_parts.append(p)
            elif title_part is None:
                # First non-author segment is the title
                title_part = p
            elif journal_part is None:
                # Next segment is journal (may have Vol/Year/Pages attached)
                journal_part = p
        
        if author_parts:
            fields['author'] = ' and '.join(author_parts)
        if title_part:
            fields['title'] = title_part.strip(' .')
        if journal_part:
            # Clean journal - remove Vol (Year) Pages pattern
            j = re.sub(r'\s*\d+\s*\(\d+\)\s*\(\d{4}\).*$', '', journal_part)  # Vol(Num)(Year)...
            j = re.sub(r'\s*\d+\s*\(\d{4}\).*$', '', j)  # Vol(Year)...
            j = re.sub(r'\s*\d+\s*$', '', j)  # Trailing numbers
            fields['journal'] = j.strip(' .')
        
        # 5. Extract Year, Volume, Number, Pages from full content
        year_m = re.search(r'\((\d{4})\)', content)
        if year_m:
            fields['year'] = year_m.group(1)
        
        # Vol~(Num) (Year) Pages or Vol (Year) Pages
        vp_m = re.search(r'(\d+)\s*\((\d+)\)\s*\((\d{4})\)\s*(\d+(?:--?\d+)?)', content)
        if vp_m:
            fields['volume'] = vp_m.group(1)
            fields['number'] = vp_m.group(2)
            fields['year'] = vp_m.group(3)
            fields['pages'] = vp_m.group(4).replace('–', '--').replace('-', '--')
        else:
            vp_m2 = re.search(r'(\d+)\s*\((\d{4})\)\s*(\d+(?:--?\d+)?)', content)
            if vp_m2:
                fields['volume'] = vp_m2.group(1)
                fields['year'] = vp_m2.group(2)
                fields['pages'] = vp_m2.group(3).replace('–', '--').replace('-', '--')
        
        # 6. Return if we have valid fields
        if fields.get('author') and fields.get('title'):
            cl_fields = {k: clean_field_value(v, keep_period=(k == 'journal')) for k, v in fields.items()}
            ent_type = 'article' if cl_fields.get('journal') else 'misc'
            res_lines = [f"@{ent_type}{{" + key + ","]
            for f in ['author', 'title', 'journal', 'year', 'volume', 'number', 'pages', 'doi', 'url']:
                if cl_fields.get(f):
                    res_lines.append(f"  {f} = {{{cl_fields[f]}}},")
                res_lines.append("}")
            return '\n'.join(res_lines)

    # === 0a7. STRATEGY: Plain Text Author (Year). Title. Journal/arXiv Format ===
    # Patterns: 
    #   Author, A. (Year). Title. arXiv preprint arXiv:ID.
    #   Author, A. (Year). Title. Journal, Vol, Pages.
    #   Org (Year), Title, URL
    # Key identifier: (YYYY). or (YYYY), pattern
    year_paren_m = re.search(r'\((\d{4})\)[.,]', raw_content)
    has_quoted_title = '"' in raw_content or "``" in raw_content
    if year_paren_m and not has_quoted_title and not r'\textit' in raw_content and not r'{\it' in raw_content:
        content = ' '.join(l.strip() for l in raw_content.splitlines() if l.strip())
        
        fields['year'] = year_paren_m.group(1)
        
        # Extract arXiv ID if present
        arxiv_m = re.search(r'arXiv[:\s]*(\d+\.\d+)', content, re.I)
        if arxiv_m:
            fields['eprint'] = arxiv_m.group(1)
            fields['archivePrefix'] = 'arXiv'
        
        # Extract DOI if present
        doi_m = re.search(r'https?://doi\.org/([^\s,]+)|doi:\s*([^\s,]+)', content, re.I)
        if doi_m:
            fields['doi'] = (doi_m.group(1) or doi_m.group(2)).rstrip('.')
        
        # Extract URL if present
        url_m = re.search(r'(https?://[^\s,]+)', content)
        if url_m and not fields.get('doi'):
            fields['url'] = url_m.group(1).rstrip('.,')
        
        # Author is before (Year)
        before_year = content[:year_paren_m.start()].strip(' ,')
        fields['author'] = before_year
        
        # Everything after (Year).
        after_year = content[year_paren_m.end():].strip()
        
        # Remove arXiv/DOI/URL from after_year for cleaner title/journal parsing
        clean_after = after_year
        for pattern in [r'arXiv\s+preprint\s+arXiv[:\s]*\d+\.\d+\.?', r'https?://[^\s,]+', r'doi:[^\s,]+']:
            clean_after = re.sub(pattern, '', clean_after, flags=re.I).strip(' .')
        
        # Title is first segment, journal is rest
        if clean_after:
            period_split = re.split(r'\.\s+(?=[A-Z])', clean_after, maxsplit=1)
            if len(period_split) >= 2:
                fields['title'] = period_split[0].strip(' .')
                journal_info = period_split[1].strip(' .')
            else:
                fields['title'] = clean_after.strip(' .')
                journal_info = ''
            
            # Parse journal info
            if journal_info:
                # pp.XXX-YYY pattern
                pp_m = re.search(r'pp\.?\s*(\d+[-–]\d+)', journal_info)
                if pp_m:
                    fields['pages'] = pp_m.group(1).replace('–', '--')
                    journal_info = journal_info[:pp_m.start()].strip(' ,.')
                
                # Vol(Num) pattern
                vol_m = re.search(r',?\s*(\d+)\((\d+)\)', journal_info)
                if vol_m:
                    fields['volume'] = vol_m.group(1)
                    fields['number'] = vol_m.group(2)
                    journal_info = journal_info[:vol_m.start()].strip(' ,.')
                
                if journal_info:
                    fields['journal'] = journal_info.strip(' ,.')
        
        if fields.get('author') and fields.get('title'):
            cl_fields = {k: clean_field_value(v, keep_period=(k == 'journal')) for k, v in fields.items()}
            ent_type = 'article' if cl_fields.get('journal') else 'misc'
            res_lines = [f"@{ent_type}{{" + key + ","]
            for f in ['author', 'title', 'journal', 'year', 'volume', 'number', 'pages', 'eprint', 'archivePrefix', 'doi', 'url']:
                if cl_fields.get(f):
                    res_lines.append(f"  {f} = {{{cl_fields[f]}}},")
            res_lines.append("}")
            return '\n'.join(res_lines)

    
    # === 0j. STRATEGY: Explicit Quoted Title Format (HIGH PRIORITY) ===
    # Handles: "Title," Journal \textbf{Vol}, Pages (Year). or ${Vol}$ format
    
    quote_match = None
    # Style 1: ``...'' (Latex)
    match_latex_quote = re.search(r"``(.*?)''", raw_content, re.DOTALL)
    if match_latex_quote:
        quote_match = match_latex_quote
        
    # Style 2: "..." (Simple) - Only if latex quotes not found
    if not quote_match:
        match_quote = re.search(r'"([^"]+)"', raw_content)
        if match_quote:
            quote_match = match_quote
            
    if quote_match:
        title_raw = quote_match.group(1).strip()
        
        start_idx = quote_match.start()
        end_idx = quote_match.end()
        
        before_title = raw_content[:start_idx].strip()
        after_title = raw_content[end_idx:].strip(' ,')
        
        # Author is before title
        fields['author'] = before_title.strip(' ,')
        fields['title'] = title_raw.strip(' ,')
        
        # Extract Year at end: (YYYY). or (YYYY)
        year_end_m = re.search(r'\((\d{4})\)\.?\s*$', after_title)
        if year_end_m:
            fields['year'] = year_end_m.group(1)
            after_title = after_title[:year_end_m.start()].strip(' ,')
        
        # Extract Volume from \textbf{Vol} or ${Vol}$ or $\bf{Vol}$
        vol_match = re.search(r'(?:\\textbf\{(\d+)\}|\$\{?\\bf\{?(\d+)\}?\$|\$(\d+)\$)', after_title)
        if vol_match:
            fields['volume'] = (vol_match.group(1) or vol_match.group(2) or vol_match.group(3))
            after_title = after_title[:vol_match.start()] + after_title[vol_match.end():]
        
        # Extract Number in (Num) after volume
        num_match = re.search(r'\((\d+)\)', after_title)
        if num_match:
            fields['number'] = num_match.group(1)
            after_title = after_title[:num_match.start()] + after_title[num_match.end():]
        
        # Extract Pages (digits with dash)
        pages_match = re.search(r',?\s*(\d+[-–—]\d+)\s*\.?$', after_title)
        if pages_match:
            fields['pages'] = pages_match.group(1).replace('–', '--').replace('—', '--')
            after_title = after_title[:pages_match.start()].strip(' ,')
        else:
            # Single page number
            single_page_m = re.search(r',?\s*(\d{4,})\s*\.?$', after_title)
            if single_page_m:
                fields['pages'] = single_page_m.group(1)
                after_title = after_title[:single_page_m.start()].strip(' ,')
        
        # Journal is whatever is left (cleaned up)
        journal_guess = after_title.strip(' ,.')
        if journal_guess:
            journal_guess = clean_latex_formatting(journal_guess).strip(' ,;.')
            journal_guess = re.sub(r'\s+', ' ', journal_guess)
            fields['journal'] = journal_guess

        # CLEANUP FIELDS
        cleaned_fields = {k: clean_field_value(v, keep_period=(k == 'journal')) for k, v in fields.items()}
        
        if cleaned_fields.get('author') and cleaned_fields.get('title'):
            entry_type = 'article' if cleaned_fields.get('journal') else 'misc'
            lines = [f"@{entry_type}{{" + key + ","]
            for field in ['author', 'title', 'journal', 'year', 'volume', 'number', 'pages']:
                if cleaned_fields.get(field):
                    lines.append(f"  {field} = {{{cleaned_fields[field]}}},")
            lines.append("}")
            return '\n'.join(lines)

    # === 0u. STRATEGY: Small-Braced Author (Economics/Finance - e.g. 2411-13557 variant) ===
    # Pattern: \small{Author (Year)} [Colon/Comma] Title, Journal ...
    cmd_m = re.match(r'[\s{]*\\(?:small|footnotesize|tiny|large)\{?([^}]+)\}?', raw_content)
    if not fields.get('title') and cmd_m:
        author_section = cmd_m.group(1).strip()
        y_m = re.search(r'\((\d{4})\)', author_section)
        if y_m:
            fields['year'] = y_m.group(1)
            fields['author'] = author_section[:y_m.start()].strip(' .,')
            
            # Content after the braced/small section
            rest = raw_content[cmd_m.end():].strip(' .,')
            # Look for separator
            sep_m = re.match(r'[:;,]\s*', rest)
            if sep_m: rest = rest[sep_m.end():].strip()
            
            # Now rest typically starts with Title. 
            # If Title has commas, it might be Title, Journal, Vol, Pages.
            if ',' in rest:
                parts = [p.strip() for p in rest.split(',')]
                fields['title'] = parts[0].strip(' .,')
                if len(parts) > 1:
                    fields['journal'] = parts[1].strip(' .,')
                    rem = ', '.join(parts[2:])
                    # Extract Vol, Num, Pages
                    vn_m = re.search(r'\b(\d+)\b', rem)
                    if vn_m:
                        fields['volume'] = vn_m.group(1)
                        rem_after = rem[vn_m.end():].strip()
                        num_m = re.search(r'\((\d+)\)', rem_after)
                        if num_m:
                            fields['number'] = num_m.group(1)
                            rem_after = rem_after[num_m.end():].strip()
                        pg_m = re.search(r'\b(\d+(?:--?\d+)?)\b', rem_after)
                        if pg_m: fields['pages'] = pg_m.group(1).replace('-', '--')
            elif '. ' in rest: # Title. Journal info
                t_parts = rest.split('. ', 1)
                fields['title'] = t_parts[0].strip(' .,')
                fields['journal'] = t_parts[1].strip(' .,')
            else:
                 fields['title'] = rest.strip(' .,')

            # Build result
            ent_type = 'article' if fields.get('journal') else 'misc'
            cl_fields = {k: clean_field_value(v, keep_period=(k == 'journal')) for k, v in fields.items()}
            res_lines = [f"@{ent_type}{{" + key + ","]
            for f in ['author', 'title', 'journal', 'year', 'volume', 'number', 'pages']:
                if cl_fields.get(f):
                    res_lines.append(f"  {f} = {{{cl_fields[f]}}},")
            res_lines.append("}")
            return '\n'.join(res_lines)

    # === 0a1. STRATEGY: Modern AI/CS Newblock (CVPR/ICML/ArXiv) ===
    # Patterns: \newblock In {\em ...} or \newblock {\em arXiv preprint ...}
    if not fields.get('title') and r'\newblock' in raw_content and ('arXiv' in raw_content or 'In \\em' in raw_content or 'IEEE/CVF' in raw_content or 'Hugging Face' in raw_content or 'github.com' in raw_content):
        # We split by \newblock.
        parts = [p.strip() for p in raw_content.split(r'\newblock')]
        
        if len(parts) >= 2:
            # Authors are in parts[0]
            fields['author'] = parts[0].strip(' .,')
            fields['title'] = parts[1].strip(' .,')
            
            if len(parts) >= 3:
                jinfo_raw = parts[2].strip()
                jinfo = clean_latex_formatting(jinfo_raw)
                
                # Extract year: prioritize end of string or after comma
                y_m = re.search(r'(\d{4})\s*\.?$', jinfo)
                if y_m:
                    fields['year'] = y_m.group(1)
                
                # Extract Volume(Number):Pages
                # Example: 2(3):8 or 35:36479--36494 or 1(2):3
                vn_m = re.search(r'\b(\d+)(?:\((\d+)\))?:\s*([0-9\-–—]+)', jinfo)
                if vn_m:
                    fields['volume'] = vn_m.group(1)
                    if vn_m.group(2): fields['number'] = vn_m.group(2)
                    fields['pages'] = vn_m.group(3).replace('–', '--').replace('—', '--')
                
                # Detect Booktitle / Journal
                # Case 1: In {\em ...}
                conf_m = re.search(r'In\s+(?:\{\\em\s+([^}]+)\}|\\textit\{([^}]+)\}|\\emph\{([^}]+)\})', jinfo_raw)
                if conf_m:
                    fields['booktitle'] = (conf_m.group(1) or conf_m.group(2) or conf_m.group(3)).strip(' ,')
                
                # Case 2: arXiv preprint
                ax_m = re.search(r'(?:arXiv\s+preprint\s+)?arXiv:\s*([0-9.]+)', jinfo, re.I)
                if ax_m:
                    fields['journal'] = 'arXiv preprint arXiv:' + ax_m.group(1)
                    fields['eprint'] = ax_m.group(1)
                    fields['archivePrefix'] = 'arXiv'
                
                # Case 3: {\em Journal Name}
                if not fields.get('booktitle') and not fields.get('journal'):
                    em_m = re.search(r'(?:\{\\em\s+([^}]+)\}|\\textit\{([^}]+)\}|\\emph\{([^}]+)\})', jinfo_raw)
                    if em_m:
                        fields['journal'] = (em_m.group(1) or em_m.group(2) or em_m.group(3)).strip(' ,')
                
                # URL
                url_m = re.search(r'\\url\{([^}]+)\}', jinfo_raw)
                if url_m: fields['url'] = url_m.group(1)
            
            # Special case for "github.com" or "huggingface.co" at end of parts[0] or parts[1]
            if 'github.com' in raw_content or 'huggingface.co' in raw_content:
                if not fields.get('journal'):
                    if 'github.com' in raw_content: fields['journal'] = 'github.com'
                    elif 'huggingface.co' in raw_content: fields['journal'] = 'huggingface.co'

            entry_type = 'inproceedings' if fields.get('booktitle') else 'article' if fields.get('journal') else 'misc'
            cl_fields = {k: clean_field_value(v, keep_period=(k == 'journal' or k == 'booktitle')) for k, v in fields.items()}
            res_lines = [f"@{entry_type}{{" + key + ","]
            for f in ['author', 'title', 'journal', 'booktitle', 'year', 'volume', 'number', 'pages', 'eprint', 'archivePrefix', 'url']:
                if cl_fields.get(f):
                    res_lines.append(f"  {f} = {{{cl_fields[f]}}},")
            res_lines.append("}")
            return '\n'.join(res_lines)

    # === 0a2. STRATEGY: Structured Tagged Format (\bibinfo) ===
    # Patterns: \bibinfo{author}, \bibinfo{title}, \bibinfo{journal}, etc.
    if not fields.get('title') and (r'\bibinfo{author}' in raw_content or r'\bibinfo{title}' in raw_content):
        # Extract authors: could be multiple \bibinfo{author} blocks
        # We handle one level of nested braces (like \bibinfo{author}{\bibfnamefont{...}})
        author_blocks = re.findall(r'\\bibinfo\s*\{author\}\s*\{((?:[^{}]|\{[^{}]*\})*)\}', raw_content)
        if author_blocks:
            fields['author'] = ' and '.join(author_blocks)
        
        # Extract other fields using \bibinfo
        # Map of bibtex field to \bibinfo type
        tag_map = {
            'title': 'title',
            'journal': 'journal',
            'booktitle': 'booktitle',
            'volume': 'volume',
            'pages': 'pages',
            'year': 'year',
            'publisher': 'publisher'
        }
        
        for bib_f, tag_f in tag_map.items():
            if not fields.get(bib_f):
                m = re.search(r'\\bibinfo\{' + tag_f + r'\}\{([^}]+)\}', raw_content)
                if m:
                    val = m.group(1).strip()
                    if bib_f == 'pages': val = val.replace('–', '--').replace('—', '--')
                    fields[bib_f] = val
        
        if fields.get('author') or fields.get('title'):
            # Detect entry type
            entry_type = 'book' if fields.get('publisher') and not fields.get('journal') else \
                         'inproceedings' if fields.get('booktitle') else \
                         'article' if fields.get('journal') else 'misc'
            
            cl_fields = {k: clean_field_value(v, keep_period=(k == 'journal' or k == 'booktitle')) for k, v in fields.items()}
            res_lines = [f"@{entry_type}{{" + key + ","]
            for f in ['author', 'title', 'journal', 'booktitle', 'year', 'volume', 'number', 'pages', 'publisher', 'eprint', 'archivePrefix', 'doi', 'url']:
                if cl_fields.get(f):
                    res_lines.append(f"  {f} = {{{cl_fields[f]}}},")
            res_lines.append("}")
            return '\n'.join(res_lines)

    # === 0a6. STRATEGY: Author Year {\it Journal} \textbf{Volume} Pages ===
    # Handles BOTH: {\it Journal} and \textit{Journal}
    # Handles BOTH: {\bf Volume} and \textbf{Volume}
    # Logic: Find italic block (= Journal), then find Year (4 digits) BEFORE it.
    # Author = before Year, Title = between Year and Journal (if any), Volume/Pages = after Journal.
    has_italic = r'\textit' in raw_content or r'{\it' in raw_content
    has_bold = r'\textbf' in raw_content or r'{\bf' in raw_content
    
    if has_italic and has_bold:
        content = ' '.join(l.strip() for l in raw_content.splitlines() if l.strip())
        content = content.rstrip(' .')
        
        # Find ALL italic blocks: \textit{...} or {\it ...}
        italic_matches = list(re.finditer(r'(?:\\textit\s*\{([^{}]*)\}|\{\\it\s+([^{}]*)\})', content))
        
        if len(italic_matches) >= 1:
            # Take the LAST italic as Journal
            journal_match = italic_matches[-1]
            journal_start = journal_match.start()
            fields['journal'] = (journal_match.group(1) or journal_match.group(2)).strip()
            
            # Look for 4-digit Year BEFORE the journal
            before_journal = content[:journal_start]
            year_m = re.search(r'\s(\d{4})\s', before_journal)
            
            if year_m:
                fields['author'] = before_journal[:year_m.start()].strip(' ,')
                fields['year'] = year_m.group(1)
                # Title is between year and journal (may be empty for physics format)
                title_candidate = before_journal[year_m.end():].strip(' ,')
                if title_candidate:
                    fields['title'] = title_candidate
                else:
                    # For physics format, journal IS the title essentially
                    fields['title'] = fields['journal']
                
                # Volume from \textbf{...} or {\bf ...} and Pages (after journal)
                after_journal = content[journal_match.end():].strip()
                v_m = re.search(r'(?:\\textbf\s*\{([^{}]*)\}|\{\\bf\s+([^{}]*)\})', after_journal)
                if v_m:
                    fields['volume'] = (v_m.group(1) or v_m.group(2)).strip()
                    fields['pages'] = after_journal[v_m.end():].strip(' ,').replace('–', '--').replace('-', '--')
                
                if fields.get('author') and fields.get('journal'):
                    cl_fields = {k: clean_field_value(v, keep_period=(k == 'journal')) for k, v in fields.items()}
                    res_lines = ["@article{" + key + ","]
                    for f in ['author', 'title', 'journal', 'year', 'volume', 'pages']:
                        if cl_fields.get(f):
                            res_lines.append(f"  {f} = {{{cl_fields[f]}}},")
                    res_lines.append("}")
                    return '\n'.join(res_lines)

    # === 0a3. STRATEGY: Math Vol-Year Format (\textbf{Vol}(Year)) ===
    # Patterns: \emph{Journal,} \textbf{14}(1973) 349-381. 
    # Example: 1973AR, 1983BN, 2021Bieganowski
    if not fields.get('title') and (r'\textbf' in raw_content or r'{\bf' in raw_content) and '(' in raw_content:
        # Match Vol(Year) or Vol (Year)
        vy_m = re.search(r'(?:\\textbf\{(\d+)\}|\{\\bf\s+(\d+)\})\s*\((\d{4})\)', raw_content)
        if vy_m:
            fields['volume'] = vy_m.group(1) or vy_m.group(2)
            fields['year'] = vy_m.group(3)
            
            # Pages: After vy_m
            after_vy = raw_content[vy_m.end():].strip(' .,')
            # Handle "34 pp." case (e.g. 2016Bartsch-Dohnal-Plum-Reichel)
            pp_m = re.search(r'(\d+)\s+pp\.?', after_vy)
            if pp_m:
                fields['pages'] = pp_m.group(1)
            else:
                pg_m = re.search(r'\b([0-9\-–—]+)\b', after_vy)
                if pg_m: fields['pages'] = pg_m.group(1).replace('–', '--').replace('—', '--')
            
            # Everything before vy_m
            before_vy = raw_content[:vy_m.start()].strip(' ,')
            
            # Journal/Booktitle is often in \emph or {\em} or {\it} right before Volume
            # Let's look for the last italic block before Volume
            it_m = list(re.finditer(r'(?:\\emph\{([^}]+)\}|\\textit\{([^}]+)\}|{\\it\s+([^}]+)\}|{\\em\s+([^}]+)\})', before_vy))
            if it_m:
                last_it = it_m[-1]
                fields['journal'] = (last_it.group(1) or last_it.group(2) or last_it.group(3) or last_it.group(4)).strip(' ,')
                
                # Content before the italic block is Author, Title
                before_it = before_vy[:last_it.start()].strip(' ,')
                
                # REFINED AUTHOR/TITLE SPLITTING: Split by comma
                parts = [p.strip() for p in before_it.split(',')]
                author_parts = []
                title_parts = []
                found_title = False
                for p in parts:
                    if not found_title:
                        # Heuristic for author: contains a dot (initial) or matches name pattern
                        if re.search(r'[A-Z]\.', p) or (len(p.split()) <= 3 and not re.search(r'\b(the|a|on|of|and|for)\b', p, re.I)):
                            author_parts.append(p)
                        else:
                            found_title = True
                            title_parts.append(p)
                    else:
                        title_parts.append(p)
                
                if author_parts: fields['author'] = ', '.join(author_parts)
                if title_parts: fields['title'] = ', '.join(title_parts).strip(' .')
                elif not fields.get('title'): fields['title'] = before_it.strip(' .')
            else:
                # Fallback: try to split by some logic
                fields['journal'] = before_vy
        
        # Book Case Fallback within 0a3: \emph{Publisher, City,} Year.
        # Example: 2006Benci-Fortunato (Progr. Nonlinear Differential Equations Appl., 66, Birkhäuser, Basel, 2006)
        elif not fields.get('year'):
             book_y_m = re.search(r',?\s*(\d{4})\s*\.?$', raw_content)
             if book_y_m:
                 fields['year'] = book_y_m.group(1)
                 # Look for \emph{...} before it
                 before_y = raw_content[:book_y_m.start()].strip(' ,')
                 it_m = list(re.finditer(r'(?:\\emph\{([^}]+)\}|\\textit\{([^}]+)\}|{\\it\s+([^}]+)\}|{\\em\s+([^}]+)\})', before_y))
                 if it_m:
                     last_it = it_m[-1]
                     fields['publisher'] = (last_it.group(1) or last_it.group(2) or last_it.group(3) or last_it.group(4)).strip(' ,')
                     before_it = before_y[:last_it.start()].strip(' ,')
                     
                     # REFINED AUTHOR/TITLE SPLITTING
                     parts = [p.strip() for p in before_it.split(',')]
                     author_parts = []
                     title_parts = []
                     found_title = False
                     for p in parts:
                         if not found_title:
                             if re.search(r'[A-Z]\.', p) or (len(p.split()) <= 3 and not re.search(r'\b(the|a|on|of|and|for)\b', p, re.I)):
                                 author_parts.append(p)
                             else:
                                 found_title = True
                                 title_parts.append(p)
                         else:
                             title_parts.append(p)
                     
                     if author_parts: fields['author'] = ', '.join(author_parts)
                     if title_parts: fields['title'] = ', '.join(title_parts).strip(' .')
                     elif not fields.get('title'): fields['title'] = before_it.strip(' .')

        if fields.get('author') or fields.get('title'):
            entry_type = 'book' if fields.get('publisher') and not fields.get('journal') else 'article'
            cl_fields = {k: clean_field_value(v, keep_period=(k == 'journal')) for k, v in fields.items()}
            res_lines = [f"@{entry_type}{{" + key + ","]
            for f in ['author', 'title', 'journal', 'year', 'volume', 'pages', 'publisher']:
                if cl_fields.get(f):
                    res_lines.append(f"  {f} = {{{cl_fields[f]}}},")
            res_lines.append("}")
            return '\n'.join(res_lines)

    # === 0v. STRATEGY: Newblock-Split (Math/SIAM/AMS format - e.g. Bieterman/Demlow) ===
    if not fields.get('title') and r'\newblock' in raw_content:
        # We split by \newblock. Part 0: Author, Part 1: Title, Part 2+: Journal/Info
        parts = [p.strip() for p in raw_content.split(r'\newblock')]
        if len(parts) >= 2:
            fields['author'] = parts[0].strip(' .,')
            # Title often has {\em ...} or similar
            fields['title'] = parts[1].strip(' .,')
            
            if len(parts) >= 3:
                journal_info = parts[2].strip()
                
                # Extract year: prioritize 4 digits at the end or in parentheses
                year_match = re.search(r'\((\d{4})\)', journal_info)
                if not year_match:
                    year_match = re.search(r',?\s*(\d{4})\s*\.?$', journal_info)
                if not year_match:
                    # Look for any 4-digit number in 1900-2099 range as a fallback
                    years_found = re.findall(r'\b(19\d{2}|20\d{2})\b', journal_info)
                    if years_found: fields['year'] = years_found[-1] # Take the last one
                else:
                    fields['year'] = year_match.group(1)
                
                # Volume/Number/Pages: 40(3):339--371
                vn_m = re.search(r'\b(\d+)\((\d+)\):(\d+(?:--?\d+)?)\b', journal_info)
                if vn_m:
                    fields['volume'] = vn_m.group(1)
                    fields['number'] = vn_m.group(2)
                    fields['pages'] = vn_m.group(3).replace('--', '-').replace('-', '--')
                    # Trim journal: everything before volume. Preserve trailing period.
                    fields['journal'] = journal_info[:vn_m.start()].strip(' ,')
                else:
                    # Alternative: 43(5), 2562--2584 or 43, 2562-2584
                    vp_m = re.search(r'\b(\d+)(?:\((\d+)\))?,\s*(\d+(?:--?\d+)?)\b', journal_info)
                    if vp_m:
                        fields['volume'] = vp_m.group(1)
                        if vp_m.group(2): fields['number'] = vp_m.group(2)
                        fields['pages'] = vp_m.group(3).replace('--', '-').replace('-', '--')
                        # Trim journal. Preserve trailing period.
                        fields['journal'] = journal_info[:vp_m.start()].strip(' ,')
                    else:
                        fields['journal'] = journal_info.strip(' ,')
                
                # Clean up journal from year if it was picked up
                if fields.get('journal') and fields.get('year'):
                    fields['journal'] = fields['journal'].replace(fields['year'], '').strip(' ,')

            # Build result
            cl_fields = {k: clean_field_value(v, keep_period=(k == 'journal')) for k, v in fields.items()}
            # Specific titles in math can have extra braces or \em
            if cl_fields.get('title'):
                cl_fields['title'] = re.sub(r'\\(?:em|it|textit|emph|textit)\{?([^}]+)\}?', r'\1', cl_fields['title']).strip(' {}')
            
            ent_type = 'article' if cl_fields.get('journal') else 'misc'
            res_lines = [f"@{ent_type}{{" + key + ","]
            for f in ['author', 'title', 'journal', 'year', 'volume', 'number', 'pages']:
                if cl_fields.get(f):
                    res_lines.append(f"  {f} = {{{cl_fields[f]}}},")
            res_lines.append("}")
            return '\n'.join(res_lines)

    # === 0w. STRATEGY: Italic Title (Math/Dynamics - e.g. Avila/Benedicks) ===
    # Pattern: Author. {\it Title}. Journal... or \emph{Title}
    if not fields.get('title'):
        # Match {\it Title} or \textit{Title} or \emph{Title} or {\emph Title}
        title_m = re.search(r'(?:\{\\(?:it|it|em|emph|textit)\s+([^{}]+)\}|\\(?:textit|emph)\{([^{}]+)\})', raw_content)
        if title_m:
            fields['title'] = (title_m.group(1) or title_m.group(2)).strip(' .,')
            author_raw = raw_content[:title_m.start()].strip(' .,')
            fields['author'] = author_raw
            
            rest = raw_content[title_m.end():].strip(' .,')
            if rest:
                # Extract year
                y_m = re.search(r'\((\d{4})\)', rest)
                if not y_m: y_m = re.search(r',?\s*(\d{4})\s*\.?$', rest)
                if y_m:
                    fields['year'] = y_m.group(1)
                    rest = rest.replace(y_m.group(0), '').strip(' ,')
                
                # ArXiv
                arxiv_m = re.search(r'arXiv:(\d+\.\d+)', rest)
                if arxiv_m:
                    fields['note'] = 'arXiv:' + arxiv_m.group(1)
                    rest = rest.replace(arxiv_m.group(0), '').strip(' ,')
                
                # Split rest for journal / volume / pages
                # Common: Journal Vol:Pages or Journal Vol (Year) Pages
                # Let's try to extract Vol:Pages
                pg_m = re.search(r'(\d+)[:,\s]\s*(\d+(?:[-–—]\d+)?)\b', rest)
                if pg_m:
                    fields['volume'] = pg_m.group(1)
                    fields['pages'] = pg_m.group(2).replace('--', '-').replace('-', '--')
                    fields['journal'] = rest[:pg_m.start()].strip(' ,')
                else:
                    fields['journal'] = rest.strip(' ,')

            # Build result
            ent_type = 'article' if fields.get('journal') else 'misc'
            cl_fields = {k: clean_field_value(v, keep_period=(k == 'journal')) for k, v in fields.items()}
            res_lines = [f"@{ent_type}{{" + key + ","]
            for f in ['author', 'title', 'journal', 'year', 'volume', 'number', 'pages', 'note']:
                if cl_fields.get(f):
                    res_lines.append(f"  {f} = {{{cl_fields[f]}}},")
            res_lines.append("}")
            return '\n'.join(res_lines)

    # === 0x. STRATEGY: Highly Structured APS/RevTeX (bibfield/bibinfo) ===
    if r'\bibfield' in raw_content or r'\bibinfo' in raw_content:
        # 1. Author extraction: find all \bibinfo{author}{...} blocks
        # Use a function to handle nested braces properly
        def extract_balanced_brace(s, start):
            """Extract content within balanced braces starting at position start."""
            if start >= len(s) or s[start] != '{':
                return None, start
            depth = 0
            content_start = start + 1
            i = start
            while i < len(s):
                if s[i] == '{':
                    depth += 1
                elif s[i] == '}':
                    depth -= 1
                    if depth == 0:
                        return s[content_start:i], i + 1
                i += 1
            return None, start
        
        # Find all \bibinfo{author}{...} occurrences
        author_pattern = re.compile(r'\\bibinfo\s*\{author\}\s*\{')
        authors = []
        for m in author_pattern.finditer(raw_content):
            # Find the matching closing brace
            content, _ = extract_balanced_brace(raw_content, m.end() - 1)
            if content:
                # Now extract \bibfnamefont{...} and \bibnamefont{...} from content
                fn_m = re.search(r'\\bibfnamefont\s*\{([^}]+)\}', content)
                ln_m = re.search(r'\\bibnamefont\s*\{([^}]+)\}', content)
                
                if fn_m and ln_m:
                    given = fn_m.group(1).strip()
                    surname = ln_m.group(1).strip()
                    authors.append(f"{surname}, {given}")
                elif ln_m:
                    authors.append(ln_m.group(1).strip())
                elif fn_m:
                    authors.append(fn_m.group(1).strip())
                else:
                    # Fallback: clean the whole content
                    clean_c = clean_field_value(content).strip(' ,&\n\t~\\')
                    if clean_c and len(clean_c) > 1:
                        authors.append(clean_c)
        
        # Handle et al.
        if re.search(r'\\emph\s*\{et~al\.\}|et\s+al\.', raw_content):
            if authors and 'others' not in ' '.join(authors):
                authors.append('others')
        
        if authors:
            unique_authors = []
            seen = set()
            for a in authors:
                if a not in seen and a:
                    unique_authors.append(a)
                    seen.add(a)
            fields['author'] = ' and '.join(unique_authors)

        # 2. Other fields: search globally for \bibinfo{tag}
        tag_map = {'title': 'title', 'journal': 'journal', 'volume': 'volume', 'pages': 'pages', 'year': 'year', 'publisher': 'publisher'}
        for bib_f, tag_f in tag_map.items():
            if not fields.get(bib_f):
                m = re.search(r'\\bibinfo\s*\{' + tag_f + r'\}\s*\{([^}]+)\}', raw_content)
                if m:
                    val = m.group(1).strip()
                    if bib_f == 'pages': val = val.replace('–', '--').replace('—', '--')
                    fields[bib_f] = val

        # 3. DOI / eprint
        if not fields.get('doi'):
            doi_m = re.search(r'https://doi\.org/([^} \n\t]+)', raw_content)
            if doi_m: fields['doi'] = doi_m.group(1).rstrip('., ')
        
        if not fields.get('eprint'):
            ax_m = re.search(r'arXiv:([0-9.]+)', raw_content)
            if ax_m:
                fields['eprint'] = ax_m.group(1)
                fields['archivePrefix'] = 'arXiv'

        if fields.get('author') or fields.get('journal') or fields.get('title'):
            entry_type = 'article' if fields.get('journal') else 'misc'
            cl_fields = {k: clean_field_value(v, keep_period=(k == 'journal')) for k, v in fields.items()}
            res_lines = [f"@{entry_type}{{" + key + ","]
            for f in ['author', 'title', 'journal', 'year', 'volume', 'number', 'pages', 'doi', 'eprint', 'archivePrefix']:
                if cl_fields.get(f):
                    res_lines.append(f"  {f} = {{{cl_fields[f]}}},")
            res_lines.append("}")
            return '\n'.join(res_lines)

    # === 0y. STRATEGY: Semi-Structured Physics (Year; Vol:Pages / Books) ===
    # Patterns: Ag1-Ag5, UFN, Has1-Has2, Pain_3-Pain_5, polzai2012, pol2025
    if not fields.get('title'):
        # 1. Detect Journal Pattern: Year; Vol(Num): Pages or Year; Vol: Pages
        # Example: 1987; 23(5): 510--524 or 2024; 56: 129900
        journ_p = re.search(r'(\d{4});\s*(\d+)(?:\(([^)]+)\))?:\s*([0-9\-–—]+)', raw_content)
        
        # 2. Detect Alternative Journal Pattern: Vol (Num) (Year) Pages
        # Example: 24 (3) (1982) 522--526
        alt_journ_p = re.search(r'(\d+)\s*\((\d+)\)\s*\((\d{4})\)\s*([0-9\-–—]+)', raw_content)
        
        # 3. Detect Book Pattern: City: Publisher, Year
        # Example: New York: Academic Press, 2007
        book_p = re.search(r'([^:.,\s][^:.]+):\s*([^,]+),\s*(\d{4})\.?$', raw_content)
        
        if journ_p:
            fields['year'] = journ_p.group(1)
            fields['volume'] = journ_p.group(2)
            if journ_p.group(3): fields['number'] = journ_p.group(3)
            fields['pages'] = journ_p.group(4).replace('–', '--').replace('—', '--')
            
            # Text before journ_p check Authors/Title
            before = raw_content[:journ_p.start()].strip(' ,')
            # Look for boundary: last period before journal name
            # Boundary is often Author. Title. Journal
            parts = [p.strip() for p in before.split('. ') if p.strip()]
            if len(parts) >= 3:
                fields['author'] = parts[0]
                fields['title'] = parts[1]
                fields['journal'] = '. '.join(parts[2:])
            elif len(parts) == 2:
                # Ambiguous: Author. Journal or Author. Title
                if re.search(r'[,;]', parts[0]) or len(parts[0].split()) <= 3:
                    fields['author'] = parts[0]
                    fields['journal'] = parts[1]
                else:
                    fields['title'] = parts[0]
                    fields['journal'] = parts[1]
            else:
                fields['journal'] = before
            
            entry_type = 'article'
            cl_fields = {k: clean_field_value(v, keep_period=(k == 'journal')) for k, v in fields.items()}
            res_lines = [f"@{entry_type}{{" + key + ","]
            for f in ['author', 'title', 'journal', 'year', 'volume', 'number', 'pages']:
                if cl_fields.get(f):
                    res_lines.append(f"  {f} = {{{cl_fields[f]}}},")
            res_lines.append("}")
            return '\n'.join(res_lines)

        elif alt_journ_p:
            fields['volume'] = alt_journ_p.group(1)
            fields['number'] = alt_journ_p.group(2)
            fields['year'] = alt_journ_p.group(3)
            fields['pages'] = alt_journ_p.group(4).replace('–', '--').replace('—', '--')
            
            before = raw_content[:alt_journ_p.start()].strip(' ,')
            parts = [p.strip() for p in before.split('. ') if p.strip()]
            if len(parts) >= 3:
                fields['author'] = parts[0]
                fields['title'] = parts[1]
                fields['journal'] = '. '.join(parts[2:])
            elif len(parts) == 2:
                fields['author'] = parts[0]
                fields['journal'] = parts[1]
            else:
                fields['journal'] = before
            
            entry_type = 'article'
            cl_fields = {k: clean_field_value(v, keep_period=(k == 'journal')) for k, v in fields.items()}
            res_lines = [f"@{entry_type}{{" + key + ","]
            for f in ['author', 'title', 'journal', 'year', 'volume', 'number', 'pages']:
                if cl_fields.get(f):
                    res_lines.append(f"  {f} = {{{cl_fields[f]}}},")
            res_lines.append("}")
            return '\n'.join(res_lines)
            
        elif book_p:
            fields['publisher'] = book_p.group(2)
            fields['year'] = book_p.group(3)
            
            # Text before City: is Authors/Title
            # City is often at the end of Title/Info
            # Example: Agrawal G.P. Nonlinear Fiber Optics, 4th ed. New York: Academic Press, 2007.
            before = raw_content[:book_p.start()].strip(' ,')
            
            # Author pattern: often at start before first significant space or period
            # Let's try to split by first period that looks like Author. Title
            auth_split = re.split(r'\.\s+', before, 1)
            if len(auth_split) > 1:
                fields['author'] = auth_split[0]
                fields['title'] = auth_split[1]
            else:
                fields['title'] = before
                
            entry_type = 'book'
            cl_fields = {k: clean_field_value(v, keep_period=(k == 'journal')) for k, v in fields.items()}
            res_lines = [f"@{entry_type}{{" + key + ","]
            for f in ['author', 'title', 'publisher', 'year']:
                if cl_fields.get(f):
                    res_lines.append(f"  {f} = {{{cl_fields[f]}}},")
            res_lines.append("}")
            return '\n'.join(res_lines)

    # === 0z. STRATEGY: Multiline Physics/Report (JLab format) ===
    # Patterns: LOI, reports, talks, or journals with multiline/blank line separators
    if not fields.get('title') and ('\n\n' in raw_content or 'et al.' in raw_content or 'doi:' in raw_content or 'arXiv:' in raw_content or 'JINST' in raw_content):
        # Normalize lines
        lines = [l.strip() for l in lines_orig if l.strip()]
        
        if len(lines) >= 2:
            # Authors are usually the first line(s) before a gap or formatting
            fields['author'] = lines[0].strip(' .,')
            
            # Remaining content joined
            rest_raw = ' '.join(lines[1:])
            rest = clean_latex_formatting(rest_raw)
            
            # Extract Identifiers (DOI, arXiv, URL)
            doi_m = re.search(r'doi:\s*([^\s,;\]]+)', rest_raw)
            if doi_m: fields['doi'] = doi_m.group(1).rstrip('.')
            
            ax_m = re.search(r'arXiv[:\s]*([0-9.]+)', rest_raw, re.I)
            if ax_m:
                fields['eprint'] = ax_m.group(1)
                fields['archivePrefix'] = 'arXiv'
            
            url_m = re.search(r'\\href\{([^}]+)\}', rest_raw)
            if url_m: fields['url'] = url_m.group(1)
            
            # Journal/Title logic
            # Case 1: Journal info like "Nucl. Instrum. Meth. A \textbf{959} (2020), 163419" or "JINST \textbf{10} (2015)"
            # Note: handle no. too
            journ_m = re.search(r'([A-Za-z.\s]+?)\s*(?:\\textbf\{(\d+)\}|\{\\bf\s+(\d+)\})\s*\((\d{4})\)(?:\s*no\.(\d+))?(?:,\s*([A-Z0-9]+))?', rest_raw)
            if journ_m:
                fields['journal'] = journ_m.group(1).strip(' ,')
                fields['volume'] = journ_m.group(2) or journ_m.group(3)
                fields['year'] = journ_m.group(4)
                if journ_m.group(5): fields['number'] = journ_m.group(5)
                if journ_m.group(6): fields['pages'] = journ_m.group(6)
                
                # Title often in \textit
                title_m = re.search(r'\\textit\{([^}]+)\}', rest_raw)
                if title_m: fields['title'] = title_m.group(1)
            else:
                # Case 2: Report/Talk/Manual
                keywords = ["Letter of Intent", "talk", "manual", "Report", "Task Force"]
                if any(kw.lower() in rest.lower() for kw in keywords):
                    # Extract title components from lines
                    title_parts = []
                    for line in lines[1:]:
                        if any(x in line.lower() for x in ["doi:", "\\href", "http", "arXiv:"]):
                            break
                        title_parts.append(line)
                    if title_parts:
                        fields['title'] = ' '.join(title_parts).strip(' ,.')
                        if not fields.get('year'):
                            y_m = re.search(r'\b(20\d{2}|19\d{2})\b', fields['title'])
                            if y_m: fields['year'] = y_m.group(1)
                else:
                    # Fallback: line 1 after author
                    fields['title'] = lines[1].strip(' .,')
                    if not fields.get('year'):
                         y_m = re.search(r'\b(20\d{2}|19\d{2})\b', rest)
                         if y_m: fields['year'] = y_m.group(1)

            entry_type = 'article' if fields.get('journal') else 'misc'
            cl_fields = {k: clean_field_value(v, keep_period=(k == 'journal')) for k, v in fields.items()}
            res_lines = [f"@{entry_type}{{" + key + ","]
            for f in ['author', 'title', 'journal', 'year', 'volume', 'number', 'pages', 'doi', 'eprint', 'archivePrefix', 'url']:
                if cl_fields.get(f):
                    res_lines.append(f"  {f} = {{{cl_fields[f]}}},")
            res_lines.append("}")
            return '\n'.join(res_lines)

    # === 0n. STRATEGY: \textsc{Author} \textit{Title} (e.g. 2411-14820) ===
    if not fields.get('title') and r'\textsc{' in raw_content and r'\textit{' in raw_content:
        author_m = re.search(r'\\textsc\{([^}]+)\}', raw_content)
        title_m = re.search(r'\\textit\{([^}]+)\}', raw_content)
        if author_m and title_m:
            fields['author'] = author_m.group(1).strip(' .,')
            fields['title'] = title_m.group(1).strip(' .,')
            after_title_raw = raw_content[title_m.end():].strip()
            after_title = clean_latex_formatting(after_title_raw)
            vol_m = re.search(r'\\textbf\{(\d+)\}', after_title_raw)
            if not vol_m: vol_m = re.search(r'\\textbf\s+(\d+)', after_title_raw)
            year_m = re.search(r'\((\d{4})\)', after_title)
            num_m = re.search(r'(?:no\.|No\.|no\.~)\s*(\d+)', after_title)
            journal_end_pos = None
            if vol_m: journal_end_pos = after_title_raw.find(vol_m.group(0))
            elif num_m: journal_end_pos = after_title.find(num_m.group(0))
            elif year_m: journal_end_pos = after_title.find(year_match.group(0)) if 'year_match' in locals() else after_title.find(year_m.group(0)) if year_m else None
            if journal_end_pos is not None:
                journal_cand = after_title_raw[:journal_end_pos].strip(' ,')
                if journal_cand: fields['journal'] = clean_field_value(journal_cand, keep_period=True)
            if vol_m: fields['volume'] = vol_m.group(1)
            if year_m: fields['year'] = year_m.group(1)
            if num_m: fields['number'] = num_m.group(1)
            pages_m = re.search(r'(?:pp\.|p\.|pp\.~|p\.~)\s*([0-9\-–—]+)', after_title)
            if pages_m: fields['pages'] = pages_m.group(1).replace('–', '--').replace('—', '--')
            entry_type = 'article' if fields.get('journal') else 'misc'
            cleaned_fields = {k: clean_field_value(v, keep_period=(k == 'journal')) for k, v in fields.items()}
            lines = [f"@{entry_type}{{" + key + ","]
            for field in ['author', 'title', 'journal', 'year', 'volume', 'number', 'pages']:
                if cleaned_fields.get(field):
                    lines.append(f"  {field} = {{{cleaned_fields[field]}}},")
            lines.append("}")
            return '\n'.join(lines)

    # === 0k. STRATEGY: Structured \b... Tags (e.g. 2411-14226) ===
    if not fields.get('title') and (r'\bauthor' in raw_content or r'\bbtitle' in raw_content or r'\bjtitle' in raw_content):
        author_mats = re.findall(r'\\bauthor\s*\{\s*\\bsnm\{([^}]+)\}\s*,\s*\\binits\{([^}]+)\}\s*\}', raw_content)
        if author_mats:
            authors = [f"{m[0]}, {m[1].strip('.')}" for m in author_mats]
            fields['author'] = ' and '.join(authors)
        title_m = re.search(r'\\(?:bbtitle|batitle)\s*\{([^}]+)\}', raw_content)
        if title_m: fields['title'] = title_m.group(1)
        jtitle_m = re.search(r'\\bjtitle\s*\{([^}]+)\}', raw_content)
        if jtitle_m: fields['journal'] = jtitle_m.group(1)
        vol_m = re.search(r'\\bvolume\s*\{([^}]+)\}', raw_content)
        if vol_m: fields['volume'] = vol_m.group(1)
        year_m = re.search(r'\\byear\s*\{(\d{4})\}', raw_content)
        if year_m: fields['year'] = year_m.group(1)
        pages_m = re.search(r'\\(?:bfpage|blpage)\s*\{([^}]+)\}', raw_content)
        if pages_m:
             end_p = re.search(r'\\blpage\s*\{([^}]+)\}', raw_content)
             start_p = pages_m.group(1)
             if end_p: fields['pages'] = f"{start_p}--{end_p.group(1)}"
             else: fields['pages'] = start_p
        entry_type = 'article' if fields.get('journal') else 'misc'
        cleaned_fields = {k: clean_field_value(v, keep_period=(k == 'journal')) for k, v in fields.items()}
        lines = [f"@{entry_type}{{" + key + ","]
        for field in ['author', 'title', 'journal', 'year', 'volume', 'number', 'pages']:
            if cleaned_fields.get(field):
                lines.append(f"  {field} = {{{cleaned_fields[field]}}},")
        lines.append("}")
        return '\n'.join(lines)

    # === 0l. STRATEGY: Curly Quotes + In: (e.g. 2411-14239) ===
    if not fields.get('title') and ('“' in raw_content or '”' in raw_content) and 'In:' in raw_content:
        q_start = raw_content.find('“')
        q_end = raw_content.find('”')
        if q_start != -1 and q_end != -1:
            fields['title'] = raw_content[q_start+1:q_end].strip(' .,')
            fields['author'] = raw_content[:q_start].strip(' .,')
            in_part = raw_content[q_end:].split('In:', 1)
            if len(in_part) > 1:
                after_in = in_part[1].strip()
                j_match = re.search(r'\\emph\{([^}]+)\}', after_in)
                if j_match:
                    fields['journal'] = j_match.group(1)
                    rem = after_in[j_match.end():]
                else:
                    j_part = re.split(r'\d', after_in, 1)[0]
                    fields['journal'] = j_part.strip(' .,')
                    rem = after_in[len(j_part):]
                y_match = re.search(r'\((\d{4})\)', rem)
                if y_match: fields['year'] = y_match.group(1)
                vn_m = re.search(r'(\d+)\.(\d+)', rem)
                if vn_m:
                    fields['volume'] = vn_m.group(1)
                    fields['number'] = vn_m.group(2)
                else:
                    v_match = re.search(r'(\d+)', rem)
                    if v_match and (not fields.get('year') or v_match.group(1) != fields.get('year')):
                        fields['volume'] = v_match.group(1)
                p_match = re.search(r'(?:pp\.|p\.|,)\s*([\d\u2013\-]+)', rem)
                if p_match: fields['pages'] = p_match.group(1)
                entry_type = 'article'
                cleaned_fields = {k: clean_field_value(v, keep_period=(k == 'journal')) for k, v in fields.items()}
                lines = [f"@{entry_type}{{" + key + ","]
                for field in ['author', 'title', 'journal', 'year', 'volume', 'number', 'pages']:
                    if cleaned_fields.get(field):
                        lines.append(f"  {field} = {{{cleaned_fields[field]}}},")
                lines.append("}")
                return '\n'.join(lines)

    # === 0o. STRATEGY: Author \textit{Title} Journal (Physics/Astro) ===
    if not fields.get('title') and r'\textit{' in raw_content:
        title_m = re.search(r'\\textit\{([^}]+)\}', raw_content)
        if title_m:
            author_part = raw_content[:title_m.start()].strip(' .,')
            # Title must be preceded by something that looks like authors
            if len(author_part) > 3:
                fields['author'] = author_part
                fields['title'] = title_m.group(1).strip(' .,')
                
                after_title_raw = raw_content[title_m.end():].strip()
                after_title = clean_latex_formatting(after_title_raw)
                
                # Markers for journal info
                vol_m = re.search(r'\\textbf\{(\d+)\}', after_title_raw)
                if not vol_m: vol_m = re.search(r'\\textbf\s+(\d+)', after_title_raw)
                year_m = re.search(r'\((\d{4})\)', after_title)
                
                journal_end = None
                if vol_m: journal_end = after_title_raw.find(vol_m.group(0))
                elif year_m: journal_end = after_title.find(year_m.group(0))
                
                if journal_end is not None:
                    journal_cand = after_title_raw[:journal_end].strip(' ,')
                    if journal_cand:
                        fields['journal'] = clean_field_value(journal_cand, keep_period=True)
                
                if vol_m: fields['volume'] = vol_m.group(1)
                if year_m: fields['year'] = year_m.group(1)
                
                # Pages/ID
                pages_m = re.search(r'\b(\d{4,}(?:--?\d+)?)\b', after_title)
                if pages_m:
                    cand = pages_m.group(1)
                    if cand != fields.get('year') and cand != fields.get('volume'):
                        fields['pages'] = cand.replace('-', '--')
                
                entry_type = 'article' if fields.get('journal') else 'misc'
                cleaned_fields = {k: clean_field_value(v, keep_period=(k == 'journal')) for k, v in fields.items()}
                lines = [f"@{entry_type}{{" + key + ","]
                for field in ['author', 'title', 'journal', 'year', 'volume', 'number', 'pages']:
                    if cleaned_fields.get(field):
                        lines.append(f"  {field} = {{{cleaned_fields[field]}}},")
                lines.append("}")
                return '\n'.join(lines)

    # === 0p. STRATEGY: Multiline Plain Text (Math Journals - 2411-14645) ===
    # Pattern: Line 1: Author, Line 2: Title, Line 3: Journal Vol(Year) Pages
    if not fields.get('title') and len(lines_orig) >= 2:
        # Check if the last line looks like a journal citation: Journal.Vol(Year)
        last_line = clean_latex_formatting(lines_orig[-1])
        journal_m = re.search(r'([A-Za-z.\s]+?)(\d+)\s*\((\d{4})\)', last_line)
        
        # Or Line 2 looks like Title and Line 3 looks like ArXiv (GGP24 case)
        arxiv_m = re.search(r'arxiv\.org/abs/([0-9.]+)', last_line, re.I)
        
        if journal_m or arxiv_m:
            author_cand = lines_orig[0]
            title_cand = lines_orig[1]
            
            # Smart Swap: if Line 1 looks like Title and Line 2 looks like Authors
            # Authors usually have commas, semicolons, or multiple short capitalized words
            # Title usually has more lowercase words or math keywords
            is_l1_title = len(author_cand.split()) > 4 and not re.search(r'[,;]', author_cand)
            is_l2_author = re.search(r'[,;]', title_cand) or len(title_cand.split()) <= 4
            
            if is_l1_title and is_l2_author:
                author_cand, title_cand = title_cand, author_cand
            
            fields['author'] = author_cand.strip(' .,')
            fields['title'] = title_cand.strip(' .,')
            
            if journal_m:
                fields['journal'] = journal_m.group(1).strip(' .,')
                fields['volume'] = journal_m.group(2)
                fields['year'] = journal_m.group(3)
                
                # Pages follow: , 123-456
                rem = last_line[journal_m.end():].strip(' .,')
                pages_m = re.search(r'(\d+(?:[-–—]\d+)?)', rem)
                if pages_m:
                    fields['pages'] = pages_m.group(1).replace('–', '--').replace('—', '--')
                
                # Number: no. 3
                num_m = re.search(r'(?:no\.|No\.)\s*(\d+)', last_line)
                if num_m: fields['number'] = num_m.group(1)
            
            elif arxiv_m:
                fields['eprint'] = arxiv_m.group(1)
                fields['archivePrefix'] = 'arXiv'
                # Try to find year in author/title/key if possible, or leave empty
                year_m = re.search(r'\b(20\d{2})\b', raw_content)
                if year_m: fields['year'] = year_m.group(1)

            # Return
            entry_type = 'article' if fields.get('journal') or fields.get('eprint') else 'misc'
            cleaned_fields = {k: clean_field_value(v, keep_period=(k == 'journal')) for k, v in fields.items()}
            lines = [f"@{entry_type}{{" + key + ","]
            for field in ['author', 'title', 'journal', 'year', 'volume', 'number', 'pages', 'eprint', 'archivePrefix']:
                if cleaned_fields.get(field):
                    lines.append(f"  {field} = {{{cleaned_fields[field]}}},")
            lines.append("}")
            return '\n'.join(lines)



    # === 0s. STRATEGY: Author-Year-Emph (Physics/Astro - e.g., 2411-14328) ===
    # Pattern: Author [Comma] Year \emph{Journal/Title} \textbf{Vol} Pages
    if not fields.get('title') and r'\emph{' in raw_content:
        y_m = re.search(r'\b(19\d{2}|20\d{2})\b', raw_content)
        emph_m = re.search(r'\\emph\{([^}]+)\}', raw_content)
        
        if y_m and emph_m and y_m.start() < emph_m.start():
            author_p = raw_content[:y_m.start()].strip(' .,')
            gap = raw_content[y_m.end():emph_m.start()].strip()
            
            if len(author_p) > 2 and len(gap) < 5:
                fields['author'] = author_p
                fields['year'] = y_m.group(1)
                
                title_journal = emph_m.group(1).strip(' .,')
                after_emph = raw_content[emph_m.end():].strip(' .,')
                
                vol_m = re.search(r'\\(?:textbf|bf)\{(\d+)\}', after_emph)
                if not vol_m: vol_m = re.search(r'\{\\bf\s*(\d+)\}', after_emph)
                if not vol_m: vol_m = re.search(r'\\textbf\s+(\d+)', after_emph)
                
                if vol_m:
                    fields['journal'] = title_journal
                    fields['volume'] = vol_m.group(1)
                    rem = after_emph[vol_m.end():].strip()
                    num_m = re.search(r'^\((\d+)\)', rem)
                    if num_m:
                        fields['number'] = num_m.group(1)
                        rem = rem[num_m.end():].strip()
                    
                    pg_m = re.search(r'\b(\d+(?:[-–—]\d+)?)\b', rem)
                    if pg_m:
                        fields['pages'] = pg_m.group(1).replace('–', '--').replace('—', '--')
                else:
                    fields['title'] = title_journal
                    pub_m = re.search(r'\(([^)]+)\)', after_emph)
                    if pub_m:
                        pub_text = pub_m.group(1)
                        if ':' in pub_text: fields['publisher'] = pub_text.split(':')[-1].strip()
                        else: fields['publisher'] = pub_text.strip()
                    
                    pg_m = re.search(r'(?:pp\.?|p\.?)\s*([0-9\-–—]+)', after_emph)
                    if pg_m: fields['pages'] = pg_m.group(1).replace('–', '--').replace('—', '--')

                entry_type = 'article' if fields.get('journal') else 'book' if fields.get('publisher') else 'misc'
                cl_fields = {k: clean_field_value(v, keep_period=(k == 'journal')) for k, v in fields.items()}
                res_lines = [f"@{entry_type}{{" + key + ","]
                for f in ['author', 'title', 'journal', 'publisher', 'year', 'volume', 'number', 'pages']:
                    if cl_fields.get(f):
                        res_lines.append(f"  {f} = {{{cl_fields[f]}}},")
                res_lines.append("}")
                return '\n'.join(res_lines)

    # === 0t. STRATEGY: Colon-Split (Authors: Title. Journal - 2411-13557) ===
    if not fields.get('title') and ': ' in raw_content:
        c_parts = raw_content.split(':', 1)
        author_cand = c_parts[0].strip(' .,')
        if len(author_cand) > 3 and (',' in author_cand or re.search(r'\b[A-Z]\.', author_cand)):
            fields['author'] = author_cand
            rest = c_parts[1].strip()
            if '. ' in rest:
                t_parts = rest.split('. ', 1)
                fields['title'] = t_parts[0].strip(' .,')
                rem = t_parts[1].strip()
                
                y_m = re.search(r'\((\d{4})[^)]*\)', rem)
                if y_m: fields['year'] = y_m.group(1)
                
                vn_m = re.search(r'(\d+)\s*\(([\d\-]+)\)', rem)
                if vn_m:
                    fields['volume'] = vn_m.group(1)
                    fields['number'] = vn_m.group(2)
                else:
                    v_m = re.search(r'\b(\d+)\b', rem)
                    if v_m and v_m.group(1) != fields.get('year'):
                         fields['volume'] = v_m.group(1)
                
                pg_m = re.search(r'(\d+)\s*[-–—]\s*(\d+)', rem)
                if pg_m:
                    fields['pages'] = f"{pg_m.group(1)}--{pg_m.group(2)}"
                
                j_end = None
                if vn_m: j_end = rem.find(vn_m.group(0))
                elif fields.get('volume'): j_end = rem.find(fields['volume'])
                elif y_m: j_end = rem.find(y_m.group(0))
                
                j_cand = rem[:j_end].strip(' .,') if j_end is not None else rem.strip(' .,')
                if j_cand:
                    if j_cand.lower().startswith('in:'):
                        fields['booktitle'] = j_cand[3:].strip()
                    else:
                        fields['journal'] = j_cand

                ent_type = 'article' if fields.get('journal') or fields.get('booktitle') else 'misc'
                if fields.get('booktitle'): ent_type = 'inproceedings'
                cl_fields = {k: clean_field_value(v, keep_period=(k == 'journal')) for k, v in fields.items()}
                res_lines = [f"@{ent_type}{{" + key + ","]
                for f in ['author', 'title', 'journal', 'booktitle', 'year', 'volume', 'number', 'pages']:
                    if cl_fields.get(f):
                        res_lines.append(f"  {f} = {{{cl_fields[f]}}},")
                res_lines.append("}")
                return '\n'.join(res_lines)

    # === 0q. STRATEGY: Comma-Initial Format (e.g., 2411-14399 / DiscoTEX) ===
    # Pattern: Author, Title, Journal Vol (Year) Pages
    if not fields.get('title') and ',' in raw_content:
        # Split by comma but be careful with LaTeX braces if any (though usually plain text here)
        tmp_parts = [p.strip() for p in raw_content.split(',')]
        
        # Identify boundary between authors and title
        # Authors section: parts from start that contain initials A. B. or single words
        l_idx = -1
        for i, p in enumerate(tmp_parts):
            # Author signals: A. B. , A. B. Name, et al, Name A.
            if re.search(r'\b[A-Z]\.\s*[A-Z]?|et\s+al', p, re.I) or (len(p.split()) <= 2 and i == 0):
                l_idx = i
            else:
                if l_idx != -1: break # Stopped looking after authors
        
        if l_idx != -1 and len(tmp_parts) > l_idx + 1:
            fields['author'] = ', '.join(tmp_parts[:l_idx+1]).strip(' .,')
            
            # Title is typically the next part
            title_part = tmp_parts[l_idx+1].strip(' .,')
            # If title is very short and next part exists, maybe combine? 
            # But usually it's just one part in this format.
            if len(title_part) < 10 and len(tmp_parts) > l_idx + 2:
                 title_part += ", " + tmp_parts[l_idx+2].strip(' .,')
                 after_idx = l_idx + 3
            else:
                 after_idx = l_idx + 2
            
            fields['title'] = title_part
            
            # Info Section (Journal, Vol, Year)
            if len(tmp_parts) >= after_idx:
                info_parts = tmp_parts[after_idx-1:] # include title part if it contained journal info? No.
                info_raw = ', '.join(tmp_parts[after_idx:]).strip()
                
                # Extract arXiv
                ax_m = re.search(r'arXiv[:\s]*([0-9.]+)', info_raw, re.I)
                if ax_m:
                    fields['eprint'] = ax_m.group(1)
                    fields['archivePrefix'] = 'arXiv'
                
                # Extract Year (Year)
                y_m = re.search(r'\((\d{4})\)', info_raw)
                if y_m: fields['year'] = y_m.group(1)
                
                # Vol/Num: 26 (16) or 26(16)
                vn_m = re.search(r'(\d+)\s*\((\d+)\)', info_raw)
                if vn_m:
                    fields['volume'] = vn_m.group(1)
                    fields['number'] = vn_m.group(2)
                    j_cand = info_raw[:vn_m.start()].strip(' .,')
                else:
                    v_m = re.search(r'\b(\d+)\b', info_raw)
                    if v_m and (not fields.get('year') or v_m.group(1) != fields.get('year')):
                        fields['volume'] = v_m.group(1)
                        j_cand = info_raw[:v_m.start()].strip(' .,')
                    else:
                        j_cand = info_raw.split('(')[0].strip(' .,')
                
                if j_cand and len(j_cand) > 2:
                    fields['journal'] = j_cand
                
                # Pages/ID at end
                p_m = re.search(r'\b(\d+(?:--?\d+)?)\b\.?$', info_raw)
                if p_m:
                    cand = p_m.group(1)
                    if cand not in [fields.get('year'), fields.get('volume'), fields.get('number')]:
                        fields['pages'] = cand.replace('-', '--')

            # Build result
            ent_type = 'article' if fields.get('journal') or fields.get('eprint') else 'misc'
            cl_fields = {k: clean_field_value(v, keep_period=(k == 'journal')) for k, v in fields.items()}
            res_lines = [f"@{ent_type}{{" + key + ","]
            for f in ['author', 'title', 'journal', 'year', 'volume', 'number', 'pages', 'eprint', 'archivePrefix']:
                if cl_fields.get(f):
                    res_lines.append(f"  {f} = {{{cl_fields[f]}}},")
            res_lines.append("}")
            return '\n'.join(res_lines)

    # === 0r. STRATEGY: Emphasized Title (Math/Control - e.g., 2411-14382) ===
    # Pattern: Author, \emph{Title}, Journal, Vol(Num):Pages, Year.
    if not fields.get('title') and r'\emph{' in raw_content:
        emph_m = re.search(r'\\emph\{([^}]+)\}', raw_content)
        if emph_m:
            author_cand = raw_content[:emph_m.start()].strip(' .,')
            # Check if before_emph looks like authors
            if len(author_cand) > 3:
                fields['author'] = author_cand
                fields['title'] = emph_m.group(1).strip(' .,')
                
                after_emph_raw = raw_content[emph_m.end():].strip(' .,')
                
                # Check for Journal Vol(Num):Pages, Year pattern
                det_m = re.search(r'(\d+)\s*\((\d+)\)\s*:\s*([0-9\-–—]+)', after_emph_raw)
                if det_m:
                    fields['volume'] = det_m.group(1)
                    fields['number'] = det_m.group(2)
                    fields['pages'] = det_m.group(3).replace('–', '--').replace('—', '--').replace(' ', '')
                    
                    journal_cand = after_emph_raw[:det_m.start()].strip(' .,')
                    if journal_cand: fields['journal'] = journal_cand
                
                # Extract Year
                year_m = re.search(r'\b(\d{4})\b', after_emph_raw)
                if year_m: fields['year'] = year_m.group(1)
                
                # If no Journal Vol(Num):Pages pattern, try Book format
                if not fields.get('journal'):
                     if year_m:
                         pub_cand = after_emph_raw[:year_m.start()].strip(' .,')
                         if pub_cand: fields['publisher'] = pub_cand
                
                # Final Clean and Return
                entry_type = 'article' if fields.get('journal') else 'book' if fields.get('publisher') else 'misc'
                cl_fields = {k: clean_field_value(v, keep_period=(k == 'journal')) for k, v in fields.items()}
                res_lines = [f"@{entry_type}{{" + key + ","]
                for f in ['author', 'title', 'journal', 'publisher', 'year', 'volume', 'number', 'pages']:
                    if cl_fields.get(f):
                        res_lines.append(f"  {f} = {{{cl_fields[f]}}},")
                res_lines.append("}")
                return '\n'.join(res_lines)



    # === 0e. DETECT FORMAT BASED ON SEPARATORS ===
    # Check which separator pattern is used
    
    has_semicolon_format = bool(re.search(r'\d{4};\{?\d+\}?:', raw_content))
    has_braced_title = bool(re.search(r'\.\s*\{[^}]{10,}\}', raw_content))  # . {Long title}
    has_quoted_title = bool(re.search(r'[,\s]"[^"]{10,}"', raw_content))   # , "Title"
    has_paren_title = bool(re.search(r'[,\s]\([^)]{20,}\)', raw_content))  # , (Long title) - at least 20 chars
    has_newblock = r'\newblock' in raw_content
    
    # Count separators to detect primary format
    period_count = raw_content.count('.')
    comma_count = raw_content.count(',')
    
    
    # === 0d. STRATEGY: Semicolon Format (Math/Bibliography) ===
    # Pattern: Author. {Title}. Journal Year;{Volume}:Pages-Pages
    # Note: Volume and sometimes pages may have braces
    semicolon_match = re.search(r'(\d{4});\{?(\d+)\}?:(\d+)(?:[-–](\d+))?', raw_content)
    if semicolon_match:
        fields['year'] = semicolon_match.group(1)
        fields['volume'] = semicolon_match.group(2)
        if semicolon_match.group(4):
            fields['pages'] = f"{semicolon_match.group(3)}--{semicolon_match.group(4)}"
        else:
            fields['pages'] = semicolon_match.group(3)
        
        # Get content before Year;Vol:Pages pattern
        before_pattern = raw_content[:semicolon_match.start()].strip()
        
        # Check if title is in braces: Author. {Title}. Journal
        brace_title_match = re.search(r'\{([^}]+)\}', before_pattern)
        if brace_title_match:
            # Title is the content inside braces
            fields['title'] = brace_title_match.group(1).strip()
            
            # Author is before the brace
            author_part = before_pattern[:brace_title_match.start()].strip(' .')
            fields['author'] = author_part
            
            # Journal is after the brace
            journal_part = before_pattern[brace_title_match.end():].strip(' .')
            if journal_part:
                fields['journal'] = journal_part
        else:
            # No braced title - split by periods
            parts = [p.strip() for p in before_pattern.split('.') if p.strip()]
            
            if len(parts) >= 3:
                fields['journal'] = parts[-1]
                fields['author'] = parts[0]
                fields['title'] = '. '.join(parts[1:-1])
            elif len(parts) == 2:
                fields['author'] = parts[0]
                fields['journal'] = parts[1]
            elif len(parts) == 1:
                fields['author'] = parts[0]
        
        # Return BibTeX entry for semicolon format
        entry_type = 'article' if fields.get('journal') else 'misc'
        
        # CLEANUP FIELDS
        cleaned_fields = {k: clean_field_value(v, keep_period=(k == 'journal')) for k, v in fields.items()}
        
        lines = [f"@{entry_type}{{" + key + ","]
        for field in ['author', 'title', 'journal', 'year', 'volume', 'pages']:
            if cleaned_fields.get(field):
                lines.append(f"  {field} = {{{cleaned_fields[field]}}},")
        lines.append("}")
        return '\n'.join(lines)
    
    # === 0f. STRATEGY: Physics Format ===
    # Pattern: Author, Journal \textbf{Vol}, Pages (Year)
    # Or: Author, Journal {\bf Vol}, Pages (Year)
    # Key indicator: \textbf{number} or {\bf number} for volume
    
    # Try both \textbf{} and {\bf } patterns
    textbf_vol_match = re.search(r'\\textbf\{(\d+)\}', raw_content)
    if not textbf_vol_match:
        textbf_vol_match = re.search(r'\{\\bf\s*(\d+[A-Z]?\d*)\}', raw_content)
    
    if textbf_vol_match:
        fields['volume'] = textbf_vol_match.group(1)
        
        # Extract year from (YYYY)
        year_match = re.search(r'\((\d{4})\)', raw_content)
        if year_match:
            fields['year'] = year_match.group(1)
        
        # Extract pages - number after volume marker and comma
        # Pattern: {\bf 23}, 246 (1935) or \textbf{119}, 161101 (2017)
        pages_match = re.search(r'(?:\\textbf\{\d+\}|\{\\bf\s*\d+[A-Z]?\d*\})\s*,\s*([A-Z]?\d+)', raw_content)
        if pages_match:
            fields['pages'] = pages_match.group(1)
        
        # Get content before volume marker = Author + Title + Journal
        before_vol = raw_content[:textbf_vol_match.start()].strip(' ,.')
        
        # Split by comma
        parts = [p.strip() for p in before_vol.split(',') if p.strip()]
        
        if len(parts) >= 3:
            # Format: Author, Title, Journal OR Author, Author, Journal (no title)
            # Check if the second-to-last part looks like an author or title
            potential_title = parts[-2]
            
            # Helper to check if text looks like an author
            # 1. Contains "et al"
            # 2. Contains initials like "A. B." or "A. Name"
            # 3. Very short (< 25 chars) and doesn't start with quote
            is_likely_author = (
                re.search(r'et\s+al', potential_title, re.I) or
                re.search(r'\b[A-Z]\.\s*[A-Z]?', potential_title) or
                (len(potential_title) < 25 and not potential_title.strip().startswith('"'))
            )
            
            if is_likely_author:
                # It's actually the last author
                fields['journal'] = parts[-1]
                fields['author'] = ', '.join(parts[:-1])
                # No title
            else:
                # It's likely a title
                fields['journal'] = parts[-1]
                fields['title'] = parts[-2]
                fields['author'] = ', '.join(parts[:-2])
                
        elif len(parts) == 2:
            # Format: Author, Journal (no title, common in physics)
            # Heuristic: if second part is very long, it might be title
            if len(parts[1]) > 50 and not re.search(r'\b(?:Phys|Rev|Lett|J\.|Nucl|Eur)\b', parts[1]):
                # Second part is likely title
                fields['author'] = parts[0]
                fields['title'] = parts[1]
            else:
                fields['author'] = parts[0]
                fields['journal'] = parts[1]
        elif len(parts) == 1:
            # Single part - likely author only
            fields['author'] = parts[0]
        
        # Clean up journal - remove trailing volume number if present
        if fields.get('journal'):
            fields['journal'] = re.sub(r'\s+\d+\s*$', '', fields['journal']).strip()
        
        # Return BibTeX entry for physics format
        entry_type = 'article' if fields.get('journal') else 'misc'
        
        # CLEANUP FIELDS
        cleaned_fields = {k: clean_field_value(v, keep_period=(k == 'journal')) for k, v in fields.items()}
        
        lines = [f"@{entry_type}{{" + key + ","]
        for field in ['author', 'title', 'journal', 'year', 'volume', 'pages']:
            if cleaned_fields.get(field):
                lines.append(f"  {field} = {{{cleaned_fields[field]}}},")
        lines.append("}")
        return '\n'.join(lines)
    
    # === 0g. STRATEGY: JHEP/arXiv Format (No bold volume) ===
    # Pattern: Author, Title, Journal Vol (Year) Pages; arXiv: XXXX
    # Key: Known journal name followed by volume (year) pages
    
    KNOWN_JOURNALS = [
        'JHEP', 'Phys. Rev.', 'Phys. Lett.', 'Nucl. Phys.', 'Commun. Math. Phys.',
        'Class. Quantum Grav.', 'Gen. Rel. Grav.', 'J. Math. Phys.', 'J. Phys.',
        'Fortschr. Phys.', 'Ann. Phys.', 'Annals of Physics', 'Annals. Phys. NY', 'Rev. Mod. Phys.',
        'Eur. Phys. J.', 'Int. J. Mod. Phys.', 'Mod. Phys. Lett.', 'Adv. Theor. Math. Phys.',
        'PoS',
        'Nature', 'Science', 'Prog. Theor. Phys.', 'Living Rev. Rel.',
    ]
    
    # Find known journal in content
    journal_pos = None
    journal_name = None
    for j in KNOWN_JOURNALS:
        pos = raw_content.find(j)
        if pos != -1:
            journal_pos = pos
            journal_name = j
            break
    
    if journal_pos is not None:
        # Extract volume (Year) pages after journal name
        # Pattern: Vol (Year) Pages OR Vol (Year) [no pages]
        after_journal = raw_content[journal_pos + len(journal_name):]
        # Regex allows optional pages: (\d+)\s*\((\d{4})\)(?:\s*(\d+))?
        vol_year_pages = re.search(r'\s*(\d+)\s*\((\d{4})\)(?:\s*(\d+))?', after_journal)
        
        if vol_year_pages:
            fields['journal'] = journal_name
            fields['volume'] = vol_year_pages.group(1)
            fields['year'] = vol_year_pages.group(2)
            if vol_year_pages.group(3):
                fields['pages'] = vol_year_pages.group(3)
            
            # Everything before journal is Author, Title
            before_journal = raw_content[:journal_pos].strip(' ,')
            
            # Split by comma to get Author | Title
            parts = [p.strip() for p in before_journal.split(',') if p.strip()]
            
            if len(parts) >= 2:
                author_parts = []
                title_parts = []
                found_title = False
                
                for i, part in enumerate(parts):
                    if not found_title:
                        # Heuristic for Author vs Title
                        
                        # 0. Always assume first part is Author (e.g. "Weinberg", "J. Polchinski")
                        if i == 0:
                            author_parts.append(part)
                            continue
                            
                        # 1. Check if this part looks like an author
                        # Author signals: 
                        # - "et al"
                        # - Initials "A. B." or "A.Name" (regex: one letter followed by dot)
                        # - "and" followed by name (handled by splitting, so "and" might be its own part or start of part)
                        
                        # 1. Check strict author signals
                        has_initials = bool(re.search(r'\b[A-Z]\.', part))
                        is_et_al = bool(re.search(r'et\s+al', part, re.I))
                        
                        # Check "and" prefix
                        starts_with_and = part.strip().lower().startswith('and ') or part.strip().lower() == 'and'
                        
                        # LOGIC COMBINATION:
                        is_strict_author = has_initials or is_et_al or (starts_with_and and (part.strip().lower() == 'and' or has_initials))
                        is_long_title = len(part) > 45 and not is_strict_author
                        
                        if is_strict_author:
                            author_parts.append(part)
                        elif is_long_title:
                            found_title = True
                            title_parts.append(part)
                        else:
                            # Ambiguous
                            title_keywords = ['theory', 'study', 'analysis', 'model', 'invariant', 'symmetry', 'algebra', 'quantum', 'gravity']
                            has_title_keyword = any(kw in part.lower() for kw in title_keywords)
                            
                            if has_title_keyword:
                                found_title = True
                                title_parts.append(part)
                            else:
                                # Fallback: Short & Capitalized -> Author
                                n_words = len(part.strip().split())
                                if n_words <= 2 and not re.search(r'\d', part):
                                    author_parts.append(part)
                                else:
                                    found_title = True
                                    title_parts.append(part)
                    else:
                        title_parts.append(part)
                
                if author_parts:
                    fields['author'] = ', '.join(author_parts)
                if title_parts:
                    fields['title'] = ', '.join(title_parts)
                    
            elif len(parts) == 1:
                fields['author'] = parts[0]
            
            # Extract arXiv if present
            arxiv_match = re.search(r'arXiv[:\s]*([0-9.]+|[a-z-]+/\d+)', raw_content, re.I)
            if arxiv_match:
                fields['eprint'] = arxiv_match.group(1)
                fields['archivePrefix'] = 'arXiv'
            
            # Return BibTeX entry
            entry_type = 'article'
            
            # CLEANUP FIELDS
            cleaned_fields = {k: clean_field_value(v, keep_period=(k == 'journal')) for k, v in fields.items()}
            
            lines = [f"@{entry_type}{{" + key + ","]
            for field in ['author', 'title', 'journal', 'year', 'volume', 'pages', 'eprint', 'archivePrefix']:
                if cleaned_fields.get(field):
                    lines.append(f"  {field} = {{{cleaned_fields[field]}}},")
            lines.append("}")
            return '\n'.join(lines)
    
    
    # === 0h. STRATEGY: Book/General Format (Author, Title (Publisher, Year)) ===
    # Pattern: Author, Title (Publisher, Year) OR Author, Title (Year)
    # Detects: Content ending with (Year) or (Publisher, Year)
    
    # Regex to capture content inside last parentheses at end of string
    # Matches: (Cambridge University Press, 1998) or (1998)
    pub_year_match = re.search(r'\((?:.*?,)?\s*(\d{4})\)$', raw_content)
    
    if pub_year_match:
        fields['year'] = pub_year_match.group(1)
        
        # Extract publisher if present (text before comma inside parens)
        # Get the full content inside parens
        paren_content = raw_content[pub_year_match.start()+1 : pub_year_match.end()-1]
        if ',' in paren_content:
            fields['publisher'] = paren_content[:paren_content.rfind(',')].strip()
        
        # Content before the parentheses is Author, Title
        before_parens = raw_content[:pub_year_match.start()].strip(' ,')
        
        # Split by comma to detect Author vs Title
        # Using similar heuristic as Strategy 0g
        parts = [p.strip() for p in before_parens.split(',') if p.strip()]
        
        if len(parts) >= 2:
            author_parts = []
            title_parts = []
            found_title = False
            
            for i, part in enumerate(parts):
                if not found_title:
                    # Heuristic for Author vs Title
                    
                    # 0. Always assume first part is Author
                    if i == 0:
                        author_parts.append(part)
                        continue
                        
                    # 1. Check strict author signals
                    has_initials = bool(re.search(r'\b[A-Z]\.', part))
                    is_et_al = bool(re.search(r'et\s+al', part, re.I))
                    
                    # Check "and" prefix
                    starts_with_and = part.strip().lower().startswith('and ') or part.strip().lower() == 'and'
                    
                    # LOGIC COMBINATION:
                    is_strict_author = has_initials or is_et_al or (starts_with_and and (part.strip().lower() == 'and' or has_initials))
                    is_long_title = len(part) > 45 and not is_strict_author
                    
                    if is_strict_author:
                        author_parts.append(part)
                    elif is_long_title:
                        found_title = True
                        title_parts.append(part)
                    else:
                        # Ambiguous
                        title_keywords = ['theory', 'study', 'analysis', 'model', 'invariant', 'symmetry', 'algebra', 'quantum', 'gravity']
                        has_title_keyword = any(kw in part.lower() for kw in title_keywords)
                        
                        if has_title_keyword:
                            found_title = True
                            title_parts.append(part)
                        else:
                            # Fallback: Short & Capitalized -> Author
                            n_words = len(part.strip().split())
                            if n_words <= 2 and not re.search(r'\d', part):
                                author_parts.append(part)
                            else:
                                found_title = True
                                title_parts.append(part)
                else:
                    # Once title is found, everything else is title
                    title_parts.append(part)
            
            if author_parts:
                fields['author'] = ', '.join(author_parts)
            if title_parts:
                fields['title'] = ', '.join(title_parts)
        elif len(parts) == 1:
            fields['author'] = parts[0]
            
        # Return BibTeX entry
        entry_type = 'book' if fields.get('publisher') else 'misc'
        
        # CLEANUP FIELDS
        cleaned_fields = {k: clean_field_value(v, keep_period=(k == 'journal')) for k, v in fields.items()}
        
        lines = [f"@{entry_type}{{" + key + ","]
        for field in ['author', 'title', 'publisher', 'year', 'volume', 'pages', 'eprint', 'archivePrefix']:
            if cleaned_fields.get(field):
                lines.append(f"  {field} = {{{cleaned_fields[field]}}},")
        lines.append("}")
        return '\n'.join(lines)


    # === 0i. STRATEGY: Style Format (Author Year {\it Journal} \textbf{Vol} Pages) ===
    # Example: Bethe H A 1990 {\it Rev. Mod. Phys.} \textbf{62} 801-866
    
    # 1. Volume: \textbf{62} or {\bf 62}
    # 2. Journal: {\it Journal} or \textit{Journal} before Volume
    # 3. Year: 1990 before Journal
    
    # Find Volume first (bold number)
    style_vol_match = re.search(r'(?:\\textbf\{(\d+)\}|\{\\bf\s*(\d+)\})', raw_content)
    
    # Needs italics journal earlier in the string
    style_journal_match = re.search(r'(?:\\textit\{([^}]+)\}|\{\\it\s+([^}]+)\})', raw_content)
    
    # Year match (4 digits)
    style_year_match = re.search(r'(\d{4})', raw_content)
    
    # Check if they exist and are in likely order: Year < Journal < Volume
    is_style_format = False
    if style_vol_match and style_journal_match and style_year_match:
        if style_year_match.end() < style_journal_match.start() and style_journal_match.end() < style_vol_match.start():
            is_style_format = True
            
    if is_style_format:
        fields['volume'] = style_vol_match.group(1) or style_vol_match.group(2)
        fields['journal'] = style_journal_match.group(1) or style_journal_match.group(2)
        fields['year'] = style_year_match.group(1)
        
        # Pages: After volume
        after_vol = raw_content[style_vol_match.end():]
        pages_match = re.search(r'^\s*([0-9-–—]+)', after_vol.strip())
        if pages_match:
            fields['pages'] = pages_match.group(1)
            
        # Author: Everything before Year
        fields['author'] = raw_content[:style_year_match.start()].strip()
        
        # CLEANUP FIELDS
        cleaned_fields = {k: clean_field_value(v, keep_period=(k == 'journal')) for k, v in fields.items()}
        
        entry_type = 'article'
        lines = [f"@{entry_type}{{" + key + ","]
        for field in ['author', 'title', 'journal', 'year', 'volume', 'pages', 'eprint', 'archivePrefix']:
            if cleaned_fields.get(field):
                lines.append(f"  {field} = {{{cleaned_fields[field]}}},")
        lines.append("}")
        return '\n'.join(lines)








    # === 1. EXTRACT IDENTIFIERS (URL, DOI, arXiv) ===
    
    # URL từ \url{} hoặc plain https://
    url_match = re.search(r'\\url\{([^}]+)\}', raw_content)
    if url_match:
        fields['url'] = url_match.group(1)
    else:
        url_match = re.search(r'\\href\{([^}]+)\}', raw_content)
        if url_match:
            fields['url'] = url_match.group(1)
        else:
            url_match = re.search(r'(https?://[^\s,;}\]]+)', raw_content)
            if url_match:
                fields['url'] = url_match.group(1).rstrip('.')
    
    # DOI
    doi_match = re.search(r'(?:doi[:\s]*)?(10\.\d{4,9}/[-._;()/:a-zA-Z0-9]+)', raw_content, re.I)
    if doi_match:
        fields['doi'] = doi_match.group(1).rstrip('.')
        
    # arXiv - nhiều format
    arxiv_patterns = [
        r'arXiv[:\s]*(\d{4}\.\d{4,5})',  # arXiv:2404.12345
        r'arXiv[:\s]*([a-z-]+/\d+)',      # arXiv:hep-th/9901001
        r'arXiv[:\s](\d{4}\.\d{4,5})',    # arXiv 2404.12345
    ]
    for pattern in arxiv_patterns:
        arxiv_match = re.search(pattern, raw_content, re.I)
        if arxiv_match:
            fields['eprint'] = arxiv_match.group(1)
            fields['archivePrefix'] = 'arXiv'
            break
    
    # MR number
    mr_match = re.search(r'\\MR\{(\d+)\}', raw_content)
    if mr_match:
        fields['mrnumber'] = mr_match.group(1)
    
    # === 2. EXTRACT NUMERIC FIELDS (Year, Volume, Number, Pages) ===
    
    # Year - ưu tiên trong ngoặc đơn (2024), sau đó standalone
    year_match = re.search(r'\((\d{4})\)', raw_content)
    if not year_match:
        year_match = re.search(r',\s*(\d{4})\.?$', raw_content)
    if not year_match:
        year_match = re.search(r'\b(19\d{2}|20\d{2})\b', raw_content)
    if year_match:
        fields['year'] = year_match.group(1)
    
    # Volume - từ \textbf{} hoặc vol.~ hoặc Volume X
    vol_match = re.search(r'\\textbf\{(\d+)\}', raw_content)
    if not vol_match:
        vol_match = re.search(r'vol\.?\s*~?(\d+)', raw_content, re.I)
    if not vol_match:
        vol_match = re.search(r'Volume\s+(\d+)', raw_content, re.I)
    if vol_match:
        fields['volume'] = vol_match.group(1)
    
    # Number - từ no.~ hoặc No. X hoặc (X) sau volume
    no_match = re.search(r'no\.?\s*~?(\d+)', raw_content, re.I)
    if not no_match:
        no_match = re.search(r'No\.?\s+(\d+)', raw_content, re.I)
    if not no_match and 'volume' in fields:
        no_match = re.search(r'\((\d{1,2})\)', raw_content)
    if no_match:
        fields['number'] = no_match.group(1)
    
    # Pages - pp.~ hoặc pp. X--Y hoặc X--Y
    pages_match = re.search(r'pp\.?\s*~?(\d+)\s*[-–—]+\s*~?(\d+)', raw_content, re.I)
    if not pages_match:
        pages_match = re.search(r'(\d+)\s*[-–—]+\s*(\d+)', raw_content)
    if pages_match:
        fields['pages'] = f"{pages_match.group(1)}--{pages_match.group(2)}"
    
    # === 3. EXTRACT AUTHOR AND TITLE (CORE LOGIC) ===
    
    author = None
    title = None
    journal_or_note = None
    
    # --- Strategy A0: REVTeX/APS format (bibinfo/bibfield) ---
    # Format: \bibfield{author}{\bibinfo{author}{\bibfnamefont{H.}~\bibnamefont{Name}}}
    # Use proper nested brace parser
    is_revtex = False
    if '\\bibinfo' in raw_content:
        # Extract authors using proper nested brace parser
        author_values = extract_bibinfo_values(raw_content, 'author')
        if author_values and not author:
            author = ' and '.join(author_values)
        
        # Extract title - try bibinfo first, then emph
        title_values = extract_bibinfo_values(raw_content, 'title')
        if title_values and not title:
            title = title_values[0]  # Take first title
        
        # If no title found via bibinfo, try extracting from \emph{} or \emph {\\bibinfo{title}...}
        if not title:
            # Pattern 1: \emph {\bibinfo {title} {Actual Title}}
            emph_title_match = re.search(r'\\emph\s*\{\\bibinfo\s*\{title\}\s*\{([^}]+)\}', raw_content)
            if emph_title_match:
                title = emph_title_match.group(1).strip()
            else:
                # Pattern 2: \href{url}{\emph{Title}} or \href@noop{}{\emph{Title}}
                href_emph_match = re.search(r'\\href(?:@noop)?\s*\{[^}]*\}\s*\{\\emph\s*\{([^}]+)\}', raw_content)
                if href_emph_match:
                    title = href_emph_match.group(1).strip()
        
        # Extract journal
        journal_values = extract_bibinfo_values(raw_content, 'journal')
        if journal_values and not journal_or_note:
            journal_or_note = journal_values[0]
        
        # Extract year (simple pattern is fine)
        year_match = re.search(r'\\bibinfo\s*\{year\}\s*\{(\d{4}[a-z]?)\}', raw_content)
        if year_match and 'year' not in fields:
            fields['year'] = year_match.group(1)
        
        # Extract volume
        vol_values = extract_bibinfo_values(raw_content, 'volume')
        if vol_values and 'volume' not in fields:
            fields['volume'] = vol_values[0]
        
        # Extract pages
        pages_values = extract_bibinfo_values(raw_content, 'pages')
        if pages_values and 'pages' not in fields:
            fields['pages'] = pages_values[0]
        
        # Extract booktitle
        book_values = extract_bibinfo_values(raw_content, 'booktitle')
        if book_values and 'booktitle' not in fields:
            fields['booktitle'] = book_values[0]
        
        # Extract publisher
        pub_values = extract_bibinfo_values(raw_content, 'publisher')
        if pub_values and 'publisher' not in fields:
            fields['publisher'] = pub_values[0]
        
        # Extract address
        addr_values = extract_bibinfo_values(raw_content, 'address')
        if addr_values and 'address' not in fields:
            fields['address'] = addr_values[0]
        
        # Extract series
        series_values = extract_bibinfo_values(raw_content, 'series')
        if series_values and 'series' not in fields:
            fields['series'] = series_values[0]
        
        # Extract edition
        ed_values = extract_bibinfo_values(raw_content, 'edition')
        if ed_values and 'edition' not in fields:
            fields['edition'] = ed_values[0]
        
        # Mark as REVTeX if we successfully extracted author or journal
        if author or journal_or_note:
            is_revtex = True
    
    # --- Strategy A0.HEP_Classic: Classic HEP format (HIGH PRIORITY) ---
    # Format: "Author, {\it Title}, {\em Journal} {\bf Vol} (Year) Pages, [\href{URL}{arXiv}]"
    # Key: {\it ...} or {\it{...}} for title, {\em ...} for journal, {\bf ...} for volume
    # This is the most common format in high-energy physics papers
    if not title and not author and not is_revtex:
        # Check for {\it ...} pattern for title (with optional nested braces)
        title_it_match = re.search(r'\{\\it\s*\{?([^}]+)\}?\}', raw_content)
        
        # Check for {\em ...} pattern for journal  
        journal_em_match = re.search(r'\{\\em\s+([^}]+)\}', raw_content)
        
        # Check for {\bf ...} pattern for volume
        volume_bf_match = re.search(r'\{\\bf\s+([^}]+)\}', raw_content)
        
        # If we found title in {\it}, this is HEP format
        if title_it_match:
            # Extract title - clean up nested braces
            title_raw = title_it_match.group(1).strip()
            title_raw = re.sub(r'^\{', '', title_raw)  # Remove leading {
            title_raw = re.sub(r'\}$', '', title_raw)  # Remove trailing }
            title = clean_latex_formatting(title_raw).strip(' ,.')
            
            # Author is everything before {\it
            author_part = raw_content[:title_it_match.start()]
            author_text = clean_latex_formatting(author_part)
            author_text = re.sub(r'~', ' ', author_text)
            author_text = re.sub(r'\s+', ' ', author_text)
            author = author_text.strip(' ,.')
            
            # Extract journal from {\em ...}
            if journal_em_match:
                journal_or_note = clean_latex_formatting(journal_em_match.group(1)).strip(' ,.')
            
            # Extract volume from {\bf ...}
            if volume_bf_match and 'volume' not in fields:
                vol_text = volume_bf_match.group(1).strip()
                # Volume might include letter prefix like "B379"
                vol_match = re.match(r'([A-Z]?\d+)', vol_text)
                if vol_match:
                    fields['volume'] = vol_match.group(1)
            
            # Extract year from parentheses
            year_match = re.search(r'\((\d{4})\)', raw_content)
            if year_match and 'year' not in fields:
                fields['year'] = year_match.group(1)
            
            # Extract pages
            if 'pages' not in fields:
                # Look for pages after volume/year
                content_after_vol = raw_content
                if volume_bf_match:
                    content_after_vol = raw_content[volume_bf_match.end():]
                pages_match = re.search(r'(\d+)[-–]+(\d+)', content_after_vol)
                if pages_match:
                    fields['pages'] = f"{pages_match.group(1)}--{pages_match.group(2)}"
            
            # Extract arXiv from [\href{URL}{arXiv}] pattern
            href_match = re.search(r'\\href\{([^}]+)\}\{[^}]*(?:arXiv[:\s]*)?([^}]+)\}', raw_content)
            if href_match:
                url = href_match.group(1)
                arxiv_text = href_match.group(2).strip()
                
                if 'url' not in fields:
                    fields['url'] = url
                
                # Extract eprint ID
                arxiv_id_match = re.search(r'(\d{4}\.\d+|(?:hep|astro|math|cond-mat|gr-qc|quant|nucl|nlin)[/-][a-z]+/\d+)', arxiv_text, re.I)
                if not arxiv_id_match:
                    arxiv_id_match = re.search(r'(\d{4}\.\d+|(?:hep|astro|math|cond-mat|gr-qc|quant|nucl|nlin)[/-][a-z]+/\d+)', url, re.I)
                
                if arxiv_id_match and 'eprint' not in fields:
                    fields['eprint'] = arxiv_id_match.group(1)
                    if 'archivePrefix' not in fields:
                        fields['archivePrefix'] = 'arXiv'
    
    # --- Strategy A0.IOP: IOP/British style format (HIGH PRIORITY) ---
    # Format: "Author Year {\it Journal} \textbf{Vol} Pages"
    # Example: "Bethe H A 1990 {\it Rev. Mod. Phys.} \textbf{62} 801-866"
    # Key: NO TITLE, Year at end of author, Journal in {\it ...}, Volume in \textbf{...}
    # This is common in British physics journals (IOP, etc.)
    if not title and not author and not is_revtex:
        # Check for {\it Journal} pattern followed by \textbf{Vol}
        journal_it_match = re.search(r'\{\\it\s+([^}]+)\}', raw_content)
        volume_textbf_match = re.search(r'\\textbf\{(\d+)\}', raw_content)
        
        # Also check for ${\bf Vol}$ pattern
        if not volume_textbf_match:
            volume_textbf_match = re.search(r'\$\{?\\bf\s*(\d+)\}?\$', raw_content)
        
        if journal_it_match and volume_textbf_match:
            # This is IOP format - check if there's a year before {\it
            before_it = raw_content[:journal_it_match.start()]
            
            # Look for year at end of before_it (format: "Author Name 1990")
            year_at_end = re.search(r'(\d{4})\s*$', before_it.strip())
            
            if year_at_end:
                # This confirms IOP format
                # Extract year
                if 'year' not in fields:
                    fields['year'] = year_at_end.group(1)
                
                # Author is everything before the year
                author_text = before_it[:year_at_end.start()]
                author_text = clean_latex_formatting(author_text)
                author_text = re.sub(r'~', ' ', author_text)
                author_text = re.sub(r'\s+', ' ', author_text)
                author = author_text.strip(' ,.')
                
                # Journal from {\it ...}
                journal_text = journal_it_match.group(1).strip()
                journal_or_note = clean_latex_formatting(journal_text).strip(' ,.')
                
                # Volume from \textbf{...}
                if 'volume' not in fields:
                    fields['volume'] = volume_textbf_match.group(1)
                
                # Pages: look for pattern after volume
                after_vol = raw_content[volume_textbf_match.end():]
                pages_match = re.search(r'(\d+)[-–](\d+)', after_vol)
                if pages_match and 'pages' not in fields:
                    fields['pages'] = f"{pages_match.group(1)}--{pages_match.group(2)}"
                elif 'pages' not in fields:
                    # Single page/article number
                    single_page = re.search(r'^\s*(\d+)', after_vol)
                    if single_page:
                        fields['pages'] = single_page.group(1)
                
                # NO TITLE for this format
                title = ''
    
    # --- Strategy A0.Physics_General: Common physics format (HIGH PRIORITY) ---
    # Format: "Author, Journal \textbf{Vol}, Pages (Year)." - NO TITLE
    # Example: "B. P. Abbott et al., Phys. Rev. Lett. \textbf{119}, 161101 (2017)."
    # Key: \textbf{Vol} for volume, year in parentheses at end, no explicit title
    if not title and not author and not is_revtex:
        # Check for \textbf{Vol} pattern
        vol_textbf = re.search(r'\\textbf\{(\d+)\}', raw_content)
        
        # Check for year in parentheses at end: (YYYY)
        year_paren = re.search(r'\((\d{4})\)\s*\.?\s*$', raw_content)
        
        if vol_textbf and year_paren:
            # This is common physics format
            # Extract year
            if 'year' not in fields:
                fields['year'] = year_paren.group(1)
            
            # Extract volume
            if 'volume' not in fields:
                fields['volume'] = vol_textbf.group(1)
            
            # Journal patterns - text before \textbf{Vol}
            before_vol = raw_content[:vol_textbf.start()]
            
            # Common physics journal patterns 
            phys_journals = [
                r'Phys\.\s*Rev\.\s*(?:Lett\.|[A-D])?',
                r'Astrophys\.\s*J\.(?:\s*Lett\.|\s*Suppl\.)?',
                r'Nature\s*(?:Phys\.|Astron\.|Commun\.)?',
                r'Nucl\.\s*Phys\.\s*[A-B]?',
                r'Phys\.\s*Lett\.\s*[A-B]?',
                r'Eur\.\s*Phys\.\s*J\.\s*(?:Plus|[A-C])?',
                r'J\.\s*Phys\.\s*(?:Soc\.\s*Jpn\.|[A-G]:?(?:\s*Nucl\.\s*Part\.\s*Phys\.)?)?',
                r'Prog\.\s*(?:Theor\.\s*)?(?:Exp\.\s*)?Phys\.?',
                r'Mon\.\s*Not\.\s*Roy\.\s*Astron\.\s*Soc\.?',
                r'Ann\.\s*Phys\.?',
                r'Rev\.\s*Mod\.\s*Phys\.?',
                r'JHEP',
                r'JCAP',
                r'Living\s*Rev\.\s*Rel\.?',
                r'Int\.\s*J\.\s*Mod\.\s*Phys\.\s*[A-E]?',
                r'Chin\.\s*Phys\.\s*[A-C]?',
                r'Front\.\s*(?:Phys\.|Astron\.\s*Space\s*Sci\.)?',
                r'New\s*Astronomy',
                r'Chinese\s*Phys\.\s*[A-C]?',
            ]
            
            # Find journal in text before volume
            journal_text = None
            for jp in phys_journals:
                jm = re.search(jp, before_vol, re.I)
                if jm:
                    journal_text = jm.group(0).strip(' ,.')
                    # Author is everything before journal
                    author_part = before_vol[:jm.start()]
                    break
            
            if journal_text:
                journal_or_note = journal_text
                
                # Clean author 
                author_text = strip_formatting_for_parsing(author_part)
                author_text = re.sub(r'\s+', ' ', author_text)
                author = author_text.strip(' ,.')
                
                # Extract pages from between volume and year
                after_vol = raw_content[vol_textbf.end():year_paren.start()]
                
                # Pages pattern: comma/space followed by number(s)
                pages_match = re.search(r',?\s*(\d+(?:[-–]\d+)?)', after_vol)
                if pages_match and 'pages' not in fields:
                    pages_val = pages_match.group(1).replace('–', '--')
                    # Make sure this isn't the year
                    if not re.match(r'^\d{4}$', pages_val):
                        fields['pages'] = pages_val
                
                # NO TITLE for this format
                title = ''
    
    # --- Strategy A0.AASTeX: AASTeX/Astronomy format (HIGH PRIORITY) ---
    # Format: "{LastName}, F.~C. 2011, \apj, 730, 27, \dodoi{10.xxx}"
    # Key: Journal macros like \apj, \aap, \mnras, \aj + \dodoi{} for DOI
    # NO explicit title - these are article references
    if not title and not author and not is_revtex:
        # AASTeX journal macros - commonly used in astronomy
        aastex_journals = {
            r'\\apj\b': 'ApJ',
            r'\\apjl\b': 'ApJL', 
            r'\\apjs\b': 'ApJS',
            r'\\aj\b': 'AJ',
            r'\\aap\b': 'A&A',
            r'\\mnras\b': 'MNRAS',
            r'\\nat\b': 'Nature',
            r'\\natast\b': 'Nature Astronomy',
            r'\\pasp\b': 'PASP',
            r'\\pasj\b': 'PASJ',
            r'\\icarus\b': 'Icarus',
            r'\\solphys\b': 'Solar Physics',
            r'\\ssr\b': 'Space Science Reviews',
            r'\\prd\b': 'Phys. Rev. D',
            r'\\prl\b': 'Phys. Rev. Lett.',
            r'\\jgr\b': 'J. Geophys. Res.',
            r'\\grl\b': 'Geophys. Res. Lett.',
            r'\\araa\b': 'ARA&A',
        }
        
        # Check for journal macro pattern
        journal_macro_found = None
        journal_expanded = None
        for pattern, expanded in aastex_journals.items():
            jm = re.search(pattern, raw_content, re.I)
            if jm:
                journal_macro_found = jm
                journal_expanded = expanded
                break
        
        # Also check for \dodoi{} pattern - strong indicator of AASTeX
        dodoi_match = re.search(r'\\dodoi\{([^}]+)\}', raw_content)
        doarXiv_match = re.search(r'\\doarXiv\{([^}]+)\}', raw_content)
        
        if journal_macro_found or dodoi_match:
            # This is AASTeX format
            content = raw_content
            
            # Extract DOI from \dodoi{}
            if dodoi_match and 'doi' not in fields:
                fields['doi'] = dodoi_match.group(1).strip()
            
            # Extract arXiv from \doarXiv{}
            if doarXiv_match:
                arxiv_id = doarXiv_match.group(1).strip()
                if 'eprint' not in fields:
                    fields['eprint'] = arxiv_id
                if 'archivePrefix' not in fields:
                    fields['archivePrefix'] = 'arXiv'
            
            # Remove \dodoi{} and \doarXiv{} from content for parsing
            content = re.sub(r',?\s*\\dodoi\{[^}]+\}', '', content)
            content = re.sub(r',?\s*\\doarXiv\{[^}]+\}', '', content)
            
            # Find journal position if macro found
            if journal_macro_found:
                journal_or_note = journal_expanded
                journal_pos = journal_macro_found.start()
                before_journal = content[:journal_pos]
                after_journal = content[journal_macro_found.end():]
                
                # Parse author and year from before_journal
                # Format: "{LastName}, F.~C. 2011," or "{LastName}, F.~C., {Name2}, G. 2011,"
                # Also: "{LastName} {et~al.}(2011)" or similar
                
                # First, clean the braces around names (AASTeX style)
                before_clean = before_journal.strip(' ,')
                
                # Try to find year pattern near the end of before_journal
                year_match = re.search(r'[\s,\(]*((?:19|20)\d{2})[a-z]?\s*[,\.\)]?\s*$', before_clean)
                if year_match:
                    if 'year' not in fields:
                        fields['year'] = year_match.group(1)
                    # Author is everything before year
                    author_text = before_clean[:year_match.start()].strip(' ,')
                else:
                    author_text = before_clean
                
                # Clean author text
                # Remove braces around names: {LastName} -> LastName
                author_text = re.sub(r'\{([^}]+)\}', r'\1', author_text)
                # Clean tildes and special spacing
                author_text = re.sub(r'~', ' ', author_text)
                author_text = re.sub(r'\\&', '&', author_text)
                author_text = re.sub(r'\s+', ' ', author_text)
                # Handle "et al." patterns
                author_text = re.sub(r'\{et\s*al\.\}', 'et al.', author_text)
                author_text = re.sub(r'et\s*~?\s*al\.?', 'et al.', author_text)
                author_text = clean_latex_formatting(author_text)
                author = author_text.strip(' ,.')
                
                # Parse volume and pages from after_journal
                # Format: ", 730, 27," or ", 730, L27," or ", 688, A43,"
                after_clean = after_journal.strip(' ,')
                
                # Extract volume (first number after journal)
                vol_match = re.search(r'^,?\s*(\d+)', after_clean)
                if vol_match and 'volume' not in fields:
                    fields['volume'] = vol_match.group(1)
                    after_vol = after_clean[vol_match.end():]
                    
                    # Extract pages (next number/letter-number combo)
                    pages_match = re.search(r'^,?\s*([A-Z]?\d+)', after_vol)
                    if pages_match and 'pages' not in fields:
                        fields['pages'] = pages_match.group(1)
                
                # No title for this format
                title = ''
            
            else:
                # No journal macro but has \dodoi - try comma-separated parsing
                # Format: "Author 2024, arXiv e-prints, arXiv:XXXX"
                parts = content.split(',')
                if len(parts) >= 2:
                    # First part might be author + year
                    first_part = parts[0].strip()
                    year_match = re.search(r'((?:19|20)\d{2})[a-z]?\s*$', first_part)
                    if year_match:
                        if 'year' not in fields:
                            fields['year'] = year_match.group(1)
                        author_text = first_part[:year_match.start()].strip()
                        author_text = re.sub(r'\{([^}]+)\}', r'\1', author_text)
                        author_text = re.sub(r'~', ' ', author_text)
                        author_text = clean_latex_formatting(author_text)
                        author = author_text.strip(' ,.')
                    
                    # Look for arXiv pattern
                    for part in parts[1:]:
                        arxiv_match = re.search(r'arXiv[:\s]*(\d{4}\.\d+)', part)
                        if arxiv_match and 'eprint' not in fields:
                            fields['eprint'] = arxiv_match.group(1)
                            if 'archivePrefix' not in fields:
                                fields['archivePrefix'] = 'arXiv'
                    
                    title = ''
    
    # --- Strategy A0.Physics: Physics format WITHOUT title (HIGH PRIORITY) ---
    # Format: "Author et al. (Collaboration), Journal \textbf{Vol}, Pages (Year)"
    # Key: NO TITLE, volume in \\textbf{...}, Year in parentheses at end
    # This format is very common in physics papers and must be handled early
    if not title and not author and not is_revtex:
        # Check for \\textbf{} volume pattern
        bf_match = re.search(r'\\textbf\{(\d+)\}', raw_content)
        
        if bf_match:
            # Physics journal patterns - comprehensive list
            physics_journals = [
                # Physical Review family
                r'Phys\.?\s*Rev\.?\s*(?:Lett\.?|[A-DX]|Accel\.?\s*Beams)?',
                # Nature family
                r'Nature(?:\s+(?:Phys\.?|Commun\.?|Astron\.?))?',
                r'Science(?:\s+(?:Bull\.?|Adv\.?))?',
                # Nuclear Physics
                r'Nucl\.?\s*Phys\.?\s*[A-B]?',
                # Physics Letters
                r'Phys\.?\s*Lett\.?\s*[A-B]?',
                r'Phys\.?\s*Rep(?:t|ort)?\.?',
                # High Energy Physics
                r'JHEP',
                r'JCAP',
                r'PTEP',
                # Journal of Physics
                r'J\.?\s*Phys\.?\s*(?:Soc\.?\s*Jpn\.?|[A-G]|Conf\.?\s*Ser\.?)?',
                # Astronomy journals
                r'Mon\.?\s*Not\.?\s*R(?:oy)?\.?\s*Astron\.?\s*Soc\.?',
                r'Astrophys\.?\s*J\.?(?:\s*Lett\.?)?(?:\s*Suppl\.?)?',
                r'Astron\.?\s*Astrophys\.?',
                r'Astron\.?\s*J\.?',
                # European Physical Journal
                r'Eur\.?\s*Phys\.?\s*J\.?\s*(?:[A-C]|ST|Plus|Web\s*Conf\.?)?',
                # Other physics journals
                r'Ann(?:als)?\.?\s*Phys\.?',
                r'Rev\.?\s*Mod\.?\s*Phys\.?',
                r'Prog\.?\s*(?:Part\.?\s*Nucl\.?\s*)?(?:Theor\.?\s*)?(?:Exp\.?\s*)?Phys\.?(?:\s*Suppl\.?)?',
                r'Living\s+Rev\.?\s*Rel\.?',
                r'Int\.?\s*J\.?\s*Mod\.?\s*Phys\.?\s*[A-E]?',
                r'New\s+J\.?\s*Phys\.?',
                r'Class\.?\s*Quant\.?\s*Grav\.?',
                r'Gen\.?\s*Rel\.?\s*Grav\.?',
                r'Commun\.?\s*Math\.?\s*Phys\.?',
                r'Phys\.?\s*Dark\s*Univ\.?',
                r'Fortschr?\.?\s*Phys\.?',
                r'Chinese\s+Phys\.?\s*[A-C]?',
                r'Front\.?\s*(?:Astron\.?\s*Space\s*Sci\.?|Phys\.?)',
                r'Res\.?\s*Astron\.?\s*Astrophys\.?',
                r'SciPost\s+Phys\.?',
                r'Comput\.?\s*Phys\.?\s*Commun\.?',
                r'J\.?\s*Exp\.?\s*Theor\.?\s*Phys\.?',
                r'Z\.?\s*Phys\.?\s*[A-C]?',
                r'Adv\.?\s*Theor\.?\s*Math\.?\s*Phys\.?',
                r'Mod\.?\s*Phys\.?\s*Lett\.?\s*[A-B]?',
                r'Universe',
                r'Particles',
                r'Symmetry',
                r'Entropy',
                r'Atoms',
                r'Ann\.?\s*Rev\.?\s*Nucl\.?\s*Part\.?\s*Sci\.?',
            ]
            
            # Find journal name in content - search before \textbf
            journal_found = None
            journal_start = -1
            journal_end = -1
            content_before_bf = raw_content[:bf_match.start()]
            
            for jp in physics_journals:
                j_match = re.search(jp, content_before_bf, re.I)
                if j_match:
                    # Take the match that's closest to \textbf (rightmost position)
                    if j_match.end() > journal_end:
                        journal_end = j_match.end()
                        journal_start = j_match.start()
                        journal_found = j_match.group(0).strip()
            
            if journal_found and journal_start > 0:
                # Author is everything before journal name
                author_part = raw_content[:journal_start]
                # Clean up author - handle \\thinspace, tildes, collaboration names
                author_text = re.sub(r'\\thinspace', ' ', author_part)
                author_text = re.sub(r'~', ' ', author_text)
                author_text = clean_latex_formatting(author_text)
                author_text = re.sub(r'\s+', ' ', author_text)
                author_text = re.sub(r'et\s*al\.?', 'et al.', author_text)
                author = author_text.strip(' ,.')
                
                # Journal name: from journal_start to before \textbf
                # May include letter suffix like "D" or "B"
                journal_text = raw_content[journal_start:bf_match.start()]
                journal_text = clean_latex_formatting(journal_text)
                journal_or_note = journal_text.strip(' ,.')
                
                # Volume from \\textbf{}
                if 'volume' not in fields:
                    fields['volume'] = bf_match.group(1)
                
                # Year in parentheses at end - NOT volume/number
                year_match = re.search(r'\((\d{4})\)\s*\.?\s*$', raw_content)
                if year_match and 'year' not in fields:
                    fields['year'] = year_match.group(1)
                
                # Pages: between \\textbf{Vol} and (Year)
                after_vol = raw_content[bf_match.end():]
                # Remove year at end first
                after_vol_clean = re.sub(r'\(?\d{4}\)?\s*\.?\s*$', '', after_vol)
                # Also remove number patterns like no.X or (X)
                after_vol_clean = re.sub(r'\s*(?:no\.?\s*\d+\s*,?\s*|\(\d+\)\s*,?\s*)', '', after_vol_clean)
                # Find pages - may be comma-separated
                pages_match = re.search(r',?\s*([A-Z]?\d+[-–]\d+|\d{5,}|[A-Z]\d+|L\d+|\d+)', after_vol_clean)
                if pages_match and 'pages' not in fields:
                    pages_val = pages_match.group(1).replace('–', '--')
                    fields['pages'] = pages_val
                
                # Handle issue number: e.g., no.5 or (5)
                number_match = re.search(r'(?:no\.?\s*(\d+)|\((\d+)\))', after_vol)
                if number_match and 'number' not in fields:
                    num_val = number_match.group(1) or number_match.group(2)
                    fields['number'] = num_val
                
                # No title for this format - set to empty string
                title = ''
    
    # --- Strategy A0.HEP_arXiv: HEP format with arXiv URL at end (HIGH PRIORITY) ---
    # Format: "Author, Title, Journal Vol (Year) Pages, [http://arxiv.org/abs/XXXX arXiv:XXXX]"
    # Key: arXiv URL in brackets at end, comma-separated, Journal Vol (Year) pattern
    # No \textbf{} or \textit{} - plain text format common in HEP papers
    if not title and not author and not is_revtex:
        # Check for arXiv URL pattern at end: [http://arxiv.org/abs/...]
        arxiv_bracket = re.search(r',?\s*\[?\s*https?://arxiv\.org/abs/([^\s\]\[]+)\s*(?:arXiv:)?([^\s\]\[]+)?\s*\]?\s*$', raw_content, re.I)
        
        if arxiv_bracket:
            # Extract eprint
            eprint = arxiv_bracket.group(1)
            if eprint:
                eprint = re.sub(r'[\s,\]\}]+$', '', eprint)
                if 'eprint' not in fields:
                    fields['eprint'] = eprint.strip()
                if 'archivePrefix' not in fields:
                    fields['archivePrefix'] = 'arXiv'
            
            # Extract URL
            url_match = re.search(r'https?://arxiv\.org/abs/[^\s\]\}]+', raw_content)
            if url_match and 'url' not in fields:
                fields['url'] = url_match.group(0).rstrip(',]')
            
            # Content before arXiv bracket: "Author, Title, Journal Vol (Year) Pages"
            content_clean = raw_content[:arxiv_bracket.start()].strip(' ,[]')
            
            # Find journal pattern near end: "Journal Vol (Year) Pages" or "Journal Vol, Pages (Year)"
            # Look for pattern: Journal Name + Volume + (Year) + optional Pages
            # Common journals: Phys. Lett., Phys. Rev., JHEP, Nucl. Phys., Commun. Math. Phys., etc.
            journal_pattern = re.search(
                r'((?:Phys\.\s*(?:Lett\.\s*[AB]?|Rev\.\s*(?:Lett\.|[A-DX])?)|'
                r'JHEP|JCAP|'
                r'Nucl\.\s*Phys\.\s*[AB]?|'
                r'Commun\.\s*Math\.\s*Phys\.|'
                r'Adv\.\s*Theor\.\s*Math\.\s*Phys\.|'
                r'Class\.\s*Quant\.\s*Grav\.|'
                r'SciPost\s+Phys\.|'
                r'arXiv\s+[A-Za-z]+\s+e-prints|'
                r'J\.\s*High\s+Energy\s+Phys\.|'
                r'(?:Ann(?:als)?|Int\.\s*J\.|Rev\.|Eur\.\s*Phys\.\s*J\.)\s*[A-Za-z\s\.]+)'
                r')\s*'
                r'(?:[A-Z])?(\d+)\s*'  # Volume (with optional letter prefix like B379)
                r'(?:\s*\((\d{4})\))?\s*'  # Year in parens
                r'(?:,?\s*(?:no\.\s*\d+\s*,?\s*)?)?'  # Optional issue number
                r'(\d+[-–]\d+|\d{5,}|\d+)?\s*'  # Pages
                r'(?:\((\d{4})\))?\s*$',  # Year at end
                content_clean, re.I)
            
            if journal_pattern:
                journal_or_note = journal_pattern.group(1).strip(' .')
                
                if journal_pattern.group(2) and 'volume' not in fields:
                    fields['volume'] = journal_pattern.group(2)
                
                year_val = journal_pattern.group(3) or journal_pattern.group(5)
                if year_val and 'year' not in fields:
                    fields['year'] = year_val
                
                if journal_pattern.group(4) and 'pages' not in fields:
                    fields['pages'] = journal_pattern.group(4).replace('–', '--')
                
                # Content before journal: "Author, Title"
                before_journal = content_clean[:journal_pattern.start()].strip(' ,')
                
                # Split author and title
                # Look for "and" pattern to identify end of authors
                # Authors: "A. Name, B. Name, and C. Name"
                # Title: everything after last author
                
                # Try to find "and LastAuthor," pattern
                and_author_match = re.search(r'(.*\band\s+[A-Z]\.?\s*(?:[A-Z]\.?\s*)?[A-Za-z\'-]+)\s*,\s*(.+)$', before_journal)
                
                if and_author_match:
                    author = and_author_match.group(1).strip(' ,')
                    title = and_author_match.group(2).strip(' ,.')
                else:
                    # No "and" - try comma separation
                    # Find last comma that separates author from title
                    # Title typically is longer and has content words
                    parts = before_journal.split(',')
                    if len(parts) >= 2:
                        # Accumulate author parts (short, have initials)
                        # Title is the remaining part (longer, academic words)
                        author_parts = []
                        title_parts = []
                        found_title = False
                        
                        for i, part in enumerate(parts):
                            part = part.strip()
                            if not part:
                                continue
                            
                            # Check if part looks like author name
                            has_initials = bool(re.search(r'\b[A-Z]\.\s*[A-Z]?\.?\s*[A-Za-z\'-]+', part))
                            is_short = len(part) < 50
                            
                            if not found_title and has_initials and is_short:
                                author_parts.append(part)
                            else:
                                found_title = True
                                title_parts.append(part)
                        
                        if author_parts:
                            author = ', '.join(author_parts)
                        if title_parts:
                            title = ', '.join(title_parts)
    
    # --- Strategy IEEE/OSA: Format with double-quoted title (HIGH PRIORITY) ---
    # Format: 'Author, "Title," Journal Vol, Pages (Year).'
    # Also handles: Author, "Title," Journal \textbf{Vol}(Issue), Pages (Year).
    # Key: Title is in double quotes "..."
    if not title and not author and '"' in raw_content:
        # Find quoted title - handle both "Title," and "Title"
        quoted_match = re.search(r'"([^"]+)"', raw_content)
        
        if quoted_match:
            title = quoted_match.group(1).strip(' ,.')
            before_title = raw_content[:quoted_match.start()]
            after_title = raw_content[quoted_match.end():]
            
            # Author is everything before the quoted title
            author_text = clean_latex_formatting(before_title).strip(' ,')
            # Clean up "and" separators and normalize
            author_text = re.sub(r'\s+and\s+', ' and ', author_text)
            # Handle ampersand separators
            author_text = re.sub(r'\s*&\s*', ' and ', author_text)
            author_text = re.sub(r'\\&', 'and', author_text)
            author = author_text.strip()
            
            # --- Parse journal, volume, pages, year from after_title ---
            # First, clean up LaTeX formatting commands to make parsing easier
            after_clean = after_title
            
            # Extract volume from various formats FIRST
            vol_num = None
            after_vol_pos = 0
            
            # Pattern 1: \textbf{Vol}
            vol_match = re.search(r'\\textbf\{(\d+)\}', after_clean)
            if vol_match:
                vol_num = vol_match.group(1)
                after_vol_pos = vol_match.end()
            
            # Pattern 2: $\bf{Vol}$ or $Vol$
            if not vol_num:
                vol_match = re.search(r'\$\\?bf\{?(\d+)\}?\$|\$(\d+)\$', after_clean)
                if vol_match:
                    vol_num = vol_match.group(1) or vol_match.group(2)
                    after_vol_pos = vol_match.end()
            
            # Pattern 3: vol. X or vol X
            if not vol_num:
                vol_match = re.search(r'vol\.?\s*(\d+)', after_clean, re.I)
                if vol_match:
                    vol_num = vol_match.group(1)
                    after_vol_pos = vol_match.end()
            
            # Pattern 4: Plain number after journal (like "J. Opt. Soc. Am. A 13")
            # We'll handle this after extracting journal name
            
            if vol_num and 'volume' not in fields:
                fields['volume'] = vol_num
            
            # Now clean the content for journal extraction
            # Remove LaTeX volume markers: \textbf{...}, $\bf{...}$, $...$
            journal_content = re.sub(r'\\textbf\{[^}]*\}', ' ', after_clean)
            journal_content = re.sub(r'\$\\?bf\{?[^}$]*\}?\$', ' ', journal_content)
            journal_content = re.sub(r'\$[^$]*\$', ' ', journal_content)
            journal_content = re.sub(r'\s+', ' ', journal_content)
            
            # Check for "in \textit{...}" pattern (booktitle for book chapters)
            in_book_match = re.search(r'\bin\s+\\textit\{([^}]+)\}|\bin\s+\\emph\{([^}]+)\}', after_title, re.I)
            
            if in_book_match:
                # This is a book chapter/conference paper
                booktitle = (in_book_match.group(1) or in_book_match.group(2)).strip(' ,.')
                if 'booktitle' not in fields:
                    fields['booktitle'] = booktitle
                after_journal = after_title[in_book_match.end():]
            else:
                # Regular journal article - find journal name
                # Journal is text before volume number
                # Pattern: ", Journal Name Vol, Pages (Year)"
                
                # Try to extract journal from \textit{} first
                textit_match = re.search(r'\\textit\{([^}]+)\}|\\emph\{([^}]+)\}', after_title)
                if textit_match:
                    journal_or_note = (textit_match.group(1) or textit_match.group(2)).strip(' ,.')
                    after_journal = after_title[textit_match.end():]
                else:
                    # Journal is plain text - extract text before first number/volume
                    # Pattern: ", J. Opt. Soc. Am. A 13, 470-473 (1996)"
                    #           ^-- journal name --^ ^-- number/vol
                    
                    # Clean comma/space at start
                    journal_content = journal_content.strip(' ,')
                    
                    # Find where the numbers start (this is likely volume or pages)
                    # Journal name = words before first standalone number
                    num_start = re.search(r'\b(\d{1,4})\b', journal_content)
                    if num_start:
                        potential_journal = journal_content[:num_start.start()].strip(' ,.')
                        if len(potential_journal) >= 3:
                            journal_or_note = potential_journal
                        
                        # If we didn't find volume yet, this first number might be it
                        if not vol_num and 'volume' not in fields:
                            fields['volume'] = num_start.group(1)
                    else:
                        # No number found, journal might be the whole thing
                        potential_journal = journal_content.strip(' ,.')
                        if len(potential_journal) >= 3:
                            journal_or_note = potential_journal
                    
                    after_journal = after_title
            
            # Extract issue/number: (7) or no.7 after volume
            if vol_num:
                after_vol_text = after_clean[after_vol_pos:] if after_vol_pos > 0 else after_clean
                num_match = re.search(r'^\s*\((\d+)\)|^\s*no\.?\s*(\d+)', after_vol_text)
                if num_match and 'number' not in fields:
                    fields['number'] = num_match.group(1) or num_match.group(2)
            
            # Extract pages
            if 'pages' not in fields:
                # Pages pattern: 470-473 or 470--473 or single number like 125609
                pages_match = re.search(r'(\d+[-–]\d+|\d{5,})', after_clean)
                if pages_match:
                    fields['pages'] = pages_match.group(1).replace('–', '--')
            
            # Extract year from parentheses at end
            if 'year' not in fields:
                year_match = re.search(r'\((\d{4})\)\s*\.?\s*$', after_clean)
                if year_match:
                    fields['year'] = year_match.group(1)
                else:
                    # Fallback: any 4-digit year
                    year_match = re.search(r'\b(19\d{2}|20\d{2})\b', after_clean)
                    if year_match:
                        fields['year'] = year_match.group(1)
            
            # Check for publisher (contains "Press")
            press_match = re.search(r'([A-Za-z\s]+Press)\b', after_journal if 'after_journal' in dir() else after_title, re.I)
            if press_match and 'publisher' not in fields:
                fields['publisher'] = press_match.group(1).strip()
            
            # Extract DOI if present
            doi_match = re.search(r'https?://doi\.org/[^\s,]+|10\.\d{4,}/[^\s,]+', after_title, re.I)
            if doi_match and 'doi' not in fields:
                fields['doi'] = doi_match.group(0).strip(' .')

    
    # --- Strategy A0.Book: Book format (Publisher, Year) ---
    # Format: "Author, Book Title (Publisher, Year)."
    # Key: Publisher and year in parentheses at end, no quotes around title
    if not title and not author:
        # Check for (Publisher, Year) pattern at end  
        book_match = re.search(r'^(.+?),\s*(.+?)\s*\(([^,\)]+),\s*(\d{4})\)\s*\.?\s*$', raw_content)
        if book_match:
            author = clean_latex_formatting(book_match.group(1)).strip(' ,.')
            title = clean_latex_formatting(book_match.group(2)).strip(' ,.')
            if 'publisher' not in fields:
                fields['publisher'] = book_match.group(3).strip()
            if 'year' not in fields:
                fields['year'] = book_match.group(4)
    
    # --- Strategy AMS: Meteorology/AMS journal format ---
    # Format: "Author, Year: Title. J. Atmos. Oceanic Technol., Vol, Pages, DOI"
    # Key: Year followed by colon after author
    if not title and not author:
        content = clean_latex_formatting(raw_content)
        
        # Pattern: Author, Year: Title. Journal...
        ams_match = re.search(r'^(.+?),\s*(19\d{2}|20\d{2}):\s*(.+?)\.(.+)$', content, re.DOTALL)
        
        if ams_match:
            author = ams_match.group(1).strip()
            if 'year' not in fields:
                fields['year'] = ams_match.group(2)
            title = ams_match.group(3).strip()
            remaining = ams_match.group(4).strip()
            
            # Extract journal (first part before volume/pages)
            journal_match = re.match(r'^([A-Za-z][^,\d]*?)(?:,\s*\d|$)', remaining)
            if journal_match:
                journal_or_note = journal_match.group(1).strip(' .,')
            
            # Extract DOI
            doi_match = re.search(r'https?://doi\.org/[^\s,]+', remaining)
            if doi_match and 'doi' not in fields:
                fields['doi'] = doi_match.group(0).strip()
            
            # Extract volume and pages
            vol_pages_match = re.search(r',\s*(\d+),\s*(\d+[-–]\d+)', remaining)
            if vol_pages_match:
                if 'volume' not in fields:
                    fields['volume'] = vol_pages_match.group(1)
                if 'pages' not in fields:
                    fields['pages'] = vol_pages_match.group(2).replace('–', '--')
    
    # --- Strategy A0.5: Multiline format ---
    # Skip if already processed as REVTeX
    # Format:  
    # Line 1: Authors,
    # Line 2: Title. Journal vol (year), pages.  OR just  Title.
    # Line 3 (if exists): Journal vol (year), pages.
    if not title and not is_revtex and '\n' in raw_content:
        lines = [l.strip() for l in raw_content.split('\n') if l.strip()]
        
        if len(lines) >= 2:
            # Check if first line looks like authors (short, has initials, ends with comma)
            first_line = lines[0]
            
            # Author indicators: short line (< 100 chars), has name patterns, ends with comma
            looks_like_author = (
                len(first_line) < 100 and
                first_line.endswith(',') and
                bool(re.search(r'[A-Z]\.\s*[A-Z]|[A-Z][a-z]+,', first_line)) and
                # Should NOT have volume/year patterns typical of journals
                not bool(re.search(r'\d+\(\d{4}\)', first_line))
            )
            
            if looks_like_author:
                # Clean author: remove trailing comma
                author = first_line.rstrip(',').strip()
                
                # Line 2 may contain: Title. Journal vol(year), pages.
                # OR just: Title.
                # We need to split at the first period followed by a capital letter or journal keyword
                
                second_line = lines[1] if len(lines) > 1 else ""
                
                # Try to find where title ends
                # Common pattern: "Title. Journal" or "Title. Vol"
                # Look for period followed by capital letter or journal indicator
                title_end = -1
                
                # Find all periods in second line
                for match in re.finditer(r'\.\s+', second_line):
                    pos = match.end()
                    remaining = second_line[pos:]
                    
                    # Check if remaining looks like journal/publication info
                    # Indicators: starts with capital, has journal keywords, or vol/year pattern
                    if remaining and (
                        bool(re.search(r'^[A-Z]', remaining)) and
                        (bool(re.search(r'\d+\s*\(\d{4}\)', remaining[:50])) or  # vol(year)
                         any(kw in remaining[:30].lower() for kw in 
                             ['j.', 'proc.', 'ann.', 'trans.', 'phys.', 'math.', 
                              'nature', 'science', 'acta', 'funktsional']))
                    ):
                        title_end = match.start()
                        break
                
                if title_end > 0:
                    # Found title/journal boundary
                    title = second_line[:title_end].strip()
                    journal_part = second_line[title_end+1:].strip()
                    
                    # Clean journal name from vol/year/pages
                    journal_clean = re.sub(r'\s+\d+\s*\(\d{4}\).*', '', journal_part)
                    journal_clean = re.sub(r',?\s*no\.\s*\d+.*', '', journal_clean)
                    journal_clean = journal_clean.rstrip('.,').strip()
                    if journal_clean and 'journal' not in fields:
                        journal_or_note = journal_clean
                else:
                    # No clear journal found in line 2, maybe line 3?
                    if second_line.endswith('.'):
                        title = second_line.rstrip('.').strip()
                        
                        # Check line 3 for journal
                        if len(lines) > 2:
                            journal_line = ' '.join(lines[2:])
                            journal_clean = re.sub(r'\s+\d+\s*\(\d{4}\).*', '', journal_line)
                            journal_clean = re.sub(r',?\s*no\.\s*\d+.*', '', journal_clean)
                            journal_clean = journal_clean.rstrip('.,').strip()
                            if journal_clean and 'journal' not in fields:
                                journal_or_note = journal_clean
                        # Line 2 doesn't end with period, treat whole as title
                        title = second_line.strip()
    
    # --- Strategy A0.6: Period-terminated multiline format ---
    # Format: "Author.\n Title.\n {\em Journal}, vol:pages, year"
    # Key difference from A0.5: Author line ends with PERIOD (.) not comma
    # Common in physics papers with tilde-connected names like U.~an~der Heiden
    if not title and not is_revtex and '\n' in raw_content:
        lines = [l.strip() for l in raw_content.split('\n') if l.strip()]
        
        if len(lines) >= 2:
            first_line = lines[0]
            
            # Author line: ends with period, has name patterns (Initial.~Name or Name~Name)
            # And NOT already containing title/journal info (no {\em, no volume patterns)
            looks_like_author_period = (
                len(first_line) < 100 and
                first_line.endswith('.') and
                # Has name patterns (initials or names with tildes)
                bool(re.search(r'[A-Z]\.~|[A-Z][a-z]+~|[A-Z]\.\s*[A-Z]', first_line)) and
                # No journal indicators
                not bool(re.search(r'\\em\b|\\textit\b|\\emph\b', first_line)) and
                not bool(re.search(r'\d+:\d+', first_line))  # No vol:pages
            )
            
            if looks_like_author_period:
                # Clean author: remove trailing period, clean tildes
                author = first_line.rstrip('.').strip()
                author = re.sub(r'~', ' ', author)  # Replace tildes with spaces
                
                # Second line is title (may end with period)
                second_line = lines[1] if len(lines) > 1 else ""
                second_line_clean = clean_latex_formatting(second_line).strip()
                
                # Check if second line looks like title (plain text or {\em Title})
                em_in_second = re.search(r'\{\\em\s+([^}]+)\}', second_line)
                
                if em_in_second:
                    # Title is in {\em} - this is actually the journal/book title
                    # Title must be on this line before {\em}
                    before_em = second_line[:em_in_second.start()].strip()
                    if before_em and len(before_em) > 5:
                        title = clean_latex_formatting(before_em).strip(' .')
                        journal_or_note = em_in_second.group(1).strip(' .,')
                    else:
                        # {\em} is book title, check line 3 for publisher
                        title = em_in_second.group(1).strip()
                        if len(lines) > 2:
                            third_line = ' '.join(lines[2:])
                            third_clean = clean_latex_formatting(third_line).strip(' .,')
                            if third_clean:
                                fields['publisher'] = third_clean
                else:
                    # Plain text title (ends with period)
                    if second_line_clean.endswith('.'):
                        title = second_line_clean.rstrip('.').strip()
                    else:
                        title = second_line_clean.strip()
                    
                    # Check line 3+ for journal (usually in {\em})
                    if len(lines) > 2:
                        remaining_lines = ' '.join(lines[2:])
                        em_match = re.search(r'\{\\em\s+([^}]+)\}', remaining_lines)
                        if em_match:
                            journal_or_note = em_match.group(1).strip(' .,')
                        else:
                            # Fallback: clean remaining as journal
                            remaining_clean = clean_latex_formatting(remaining_lines).strip()
                            # Extract journal name before volume:pages
                            journal_match = re.match(r'^([A-Za-z][^,\d]*?)(?:,?\s*\d|$)', remaining_clean)
                            if journal_match:
                                journal_or_note = journal_match.group(1).strip(' .,')

    # --- Strategy A-2: Semicolon-separated authors format ---
    # Format: LastName1, FirstName1; LastName2, FirstName2, Title. Journal...
    # Key: ';' separates complete authors (each has "LastName, FirstName")
    # After the last author, a ',' followed by the title
    if not title and ';' in raw_content:
        content = clean_latex_formatting(raw_content)
        
        academic_words = ['gradient', 'estimate', 'theorem', 'equation', 'analysis', 
                          'optimal', 'stability', 'convergence', 'solution', 'method',
                          'manifold', 'harmonic', 'nonlinear', 'elliptic', 'parabolic',
                          'flow', 'curvature', 'existence', 'uniqueness', 'bound',
                          'differential', 'local', 'global', 'positive', 'complete',
                          'weighted', 'rigidity', 'liouville', 'harnack', 'inequality',
                          'porous', 'diffusion', 'ricci', 'laplacian', 'riemannian']
        
        # Split by ';' to get individual authors
        author_segments = content.split(';')
        
        if len(author_segments) >= 2:
            # All but last are definitely complete authors
            complete_authors = [seg.strip() for seg in author_segments[:-1]]
            
            # Last segment: "LastName, FirstName, Title. Journal..."
            last_segment = author_segments[-1].strip()
            
            # Pattern: LastName, FirstName(s), Title...
            # FirstName is usually short (< 25 chars), title is longer and has academic words
            parts = last_segment.split(', ')
            
            # Find where title starts (first part with academic words and length > 20)
            title_start_idx = -1
            for i in range(1, len(parts)):  # Start from index 1 (after LastName)
                part = parts[i]
                remaining = ', '.join(parts[i:])
                
                # Check if this part starts a title (has academic word or very long)
                is_likely_title = (
                    len(remaining) > 30 and
                    any(word in remaining.lower() for word in academic_words)
                )
                
                # Check if previous part looks like a firstname (short, no academic words)
                prev_part = parts[i-1] if i > 0 else ''
                prev_looks_firstname = len(prev_part) < 25 and not any(w in prev_part.lower() for w in academic_words)
                
                if is_likely_title and prev_looks_firstname:
                    title_start_idx = i
                    break
            
            if title_start_idx > 0:
                # Last author = parts before title
                last_author = ', '.join(parts[:title_start_idx]).strip()
                complete_authors.append(last_author)
                
                # Author string
                author = '; '.join(complete_authors)
                
                # Extract title
                title_and_rest = ', '.join(parts[title_start_idx:])
                
                # Title ends at first period followed by journal
                period_match = re.search(r'^([^.]+)\.\s*(.+)$', title_and_rest)
                if period_match:
                    title = period_match.group(1).strip()
                    journal_part = period_match.group(2).strip()
                    
                    # Clean journal (remove vol/year/pages)
                    if journal_part and not journal_or_note:
                        journal_clean = re.sub(r'\d+\s*\(\d{4}\).*', '', journal_part).strip(' .,')
                        journal_clean = re.sub(r',?\s*no\.\s*\d+.*', '', journal_clean, flags=re.I)
                        if journal_clean:
                            journal_or_note = journal_clean
                else:
                    title = title_and_rest.strip()
    
    # --- Strategy A1.9: IEEE format with quoted title ---
    # Format: "Author1, Author2, ..., \"Title\", \textit{Journal}, vol. X, no. Y, pp. Z, Month Year"
    # Key: Title in double quotes "", journal in \textit{} or \emph{}
    if not title and ('"' in raw_content or "''" in raw_content):
        content = raw_content
        
        # Find quoted title - pattern: "Title" or ``Title''
        quote_match = re.search(r'"([^"]+)"', content)
        if not quote_match:
            quote_match = re.search(r"``([^']+)''", content)
        if not quote_match:
            quote_match = re.search(r'"([^"]+)"', content)  # Unicode quotes
        
        if quote_match:
            title = quote_match.group(1).strip(' .,')
            
            # Author = before the quoted title
            before_quote = content[:quote_match.start()].strip()
            author = clean_latex_formatting(before_quote).strip(' .,')
            
            # After quote = journal info
            after_quote = content[quote_match.end():].strip()
            
            # Look for journal in \textit{} or \emph{}
            journal_match = re.search(r'\\(?:textit|emph)\{([^}]+)\}', after_quote)
            if journal_match:
                journal_or_note = journal_match.group(1).strip(' .,')
                
                # Extract volume, number, pages from remaining text
                remaining = after_quote[journal_match.end():]
                
                # Pattern: vol. X
                vol_match = re.search(r'vol\.?\s*(\d+)', remaining, re.I)
                if vol_match and 'volume' not in fields:
                    fields['volume'] = vol_match.group(1)
                
                # Pattern: no. Y
                no_match = re.search(r'no\.?\s*(\d+)', remaining, re.I)
                if no_match and 'number' not in fields:
                    fields['number'] = no_match.group(1)
                
                # Pattern: pp. Z-Z or p. Z
                pages_match = re.search(r'pp?\.?\s*(\d+[-–]\d+|\d+)', remaining, re.I)
                if pages_match and 'pages' not in fields:
                    fields['pages'] = pages_match.group(1).replace('–', '--')
    
    # --- Strategy A-1: Economics/Finance format ---
    # Format: Author (Year): Title. \emph{Journal}, volume(number), pages.
    # Example: Allen, F. (1993): Title here. \emph{Journal of Finance}, 61(2), 206-229.
    if not title and '\emph{' in raw_content:
        # Pattern: Text (YYYY): Title. \emph{Journal}, ...
        econ_pattern = re.search(
            r'^(.+?)\s*\((\d{4})\)\s*:\s*([^.]+)\.\s*\\emph\{([^}]+)\}',
            raw_content,
            re.MULTILINE
        )
        
        if econ_pattern:
            # Extract parts
            author = clean_latex_formatting(econ_pattern.group(1)).strip()
            year_from_pattern = econ_pattern.group(2)
            title = econ_pattern.group(3).strip()
            journal_or_note = econ_pattern.group(4).strip()
            
            # Set year if not already set
            if 'year' not in fields:
                fields['year'] = year_from_pattern
            
            # Extract volume and number if present after journal
            after_journal = raw_content[econ_pattern.end():]
            # Pattern: , volume(number), pages
            vol_num_pattern = re.search(r',\s*(\d+)\((\d+)\)', after_journal)
            if vol_num_pattern:
                if 'volume' not in fields:
                    fields['volume'] = vol_num_pattern.group(1)
                if 'number' not in fields:
                    fields['number'] = vol_num_pattern.group(2)
    
    # --- Strategy A1: \newblock format ---
    # Format: Author. \newblock Title. \newblock Journal...
    if '\\newblock' in raw_content:
        blocks = re.split(r'\\newblock\s*', raw_content)
        if len(blocks) >= 2:
            # Block 0 = Author (clean LaTeX)
            author_raw = blocks[0].strip()
            author = clean_latex_formatting(author_raw).strip(' .')
            
            # Block 1 = Title (có thể trong {\em ...})
            title_raw = blocks[1].strip()
            em_match = re.search(r'\{\\em\s+([^}]+)\}', title_raw)
            if em_match:
                title = em_match.group(1).strip(' .')
            else:
                title = clean_latex_formatting(title_raw).strip(' .')
            
            # Block 2+ = Journal/Note
            if len(blocks) >= 3:
                journal_raw = blocks[2].strip()
                em_match = re.search(r'\{\\em\s+([^}]+)\}', journal_raw)
                if em_match:
                    journal_or_note = em_match.group(1).strip(' .,')
                else:
                    journal_or_note = clean_latex_formatting(journal_raw).strip(' .,')
    
    # --- Strategy A1.8: APA/Harvard format ---
    # Format: "Author, A., \& Author2, B. (Year). Title. Journal, Vol(Num), Pages."
    # Key: Authors separated by ", \&" or just "\&", year in parentheses like (2002)
    # Title comes after year, journal after title
    if not title and not author:
        content = clean_latex_formatting(raw_content)
        
        # Pattern: (Year) followed by period and title
        year_match = re.search(r'\((\d{4})\)\.\s*', content)
        
        if year_match:
            year = year_match.group(1)
            before_year = content[:year_match.start()].strip()
            after_year = content[year_match.end():].strip()
            
            # Before year = authors (may contain \& or "and")
            # Clean up author - replace \& with "and"
            author_text = re.sub(r'\\?&', 'and', before_year)
            author_text = re.sub(r'\s+and\s+', ' and ', author_text)
            author = author_text.strip(' .,')
            
            if 'year' not in fields:
                fields['year'] = year
            
            # After year = "Title. Journal, Vol(Num), Pages."
            # Title ends at first period followed by capital letter or journal pattern
            if after_year:
                # Find title boundary - look for period followed by journal name pattern
                title_end = -1
                
                # Common patterns that indicate journal start
                journal_patterns = [
                    r'\.\s+[A-Z][a-z]*\s+(?:of|in|on)\s',  # "Journal of ..."
                    r'\.\s+(?:Review|Journal|Annals|Proceedings|Transactions|Nature|Science|Physical|American|European)\b',
                    r'\.\s+[A-Z][a-z]+\s*,\s*\d+',  # "Journal, Vol" pattern
                ]
                
                for pattern in journal_patterns:
                    match = re.search(pattern, after_year)
                    if match:
                        title_end = match.start() + 1  # Include the period
                        break
                
                if title_end == -1:
                    # Fallback: find first period followed by capital letter
                    period_match = re.search(r'\.\s+([A-Z])', after_year)
                    if period_match:
                        title_end = period_match.start() + 1
                
                if title_end > 0:
                    title = after_year[:title_end].strip(' .')
                    journal_part = after_year[title_end:].strip(' .,')
                    
                    # Extract journal name (before volume number)
                    if journal_part:
                        # Remove volume/number/pages pattern
                        journal_clean = re.sub(r',?\s*\d+\s*\(\d+\).*$', '', journal_part)
                        journal_clean = re.sub(r',?\s*\d+\s*$', '', journal_clean)
                        if journal_clean.strip():
                            journal_or_note = journal_clean.strip(' .,')
                else:
                    # No journal found, everything is title
                    title = after_year.strip(' .')

    # --- Strategy A1.10: Elsevier/elsarticle format ---
    # Format: "Author1, Author2, Title, Journal Vol~(Issue) (Year) Pages"
    # No quotes or \textit{} for title. Year at end in parentheses like (2012)
    # Authors often have tilde (~) for non-breaking spaces
    if not title and not author and '~' in raw_content:
        content = clean_latex_formatting(raw_content)
        content = re.sub(r'~', ' ', content)  # Replace tildes with spaces
        
        # Pattern: Year at end in parentheses, followed by optional pages
        year_at_end = re.search(r'\((\d{4})\)\s*(\d+[-–]?\d*)?\.?$', content)
        if not year_at_end:
            year_at_end = re.search(r',\s*(\d{4})\s*,\s*pp?\.\s*(\d+[-–]?\d*)\.?$', content)
        
        if year_at_end:
            year = year_at_end.group(1)
            if 'year' not in fields:
                fields['year'] = year
            
            # Content before year
            before_year = content[:year_at_end.start()].strip(' ,.')
            
            # Split by ", " to get segments
            segments = [s.strip() for s in before_year.split(',') if s.strip()]
            
            if len(segments) >= 3:
                # Heuristic: Authors are first few segments with name patterns
                # Title usually starts with capital and is longer
                author_segments = []
                title_start_idx = 0
                
                for i, seg in enumerate(segments):
                    # Check if segment looks like author (short, has initials pattern)
                    is_author_seg = (
                        len(seg) < 50 and
                        (re.search(r'^[A-Z]\.\s*[A-Z]?\.\s*[A-Z]', seg) or  # "J. M. Smith"
                         re.search(r'^[A-Z][a-z]+\s+[A-Z]\.', seg) or  # "Smith J."
                         re.search(r'^[A-Z]\.-?[A-Z]?\.\s*[A-Z]', seg) or  # "J.-M. Smith"
                         re.search(r'et\s+al\.?$', seg, re.I))  # "et al."
                    )
                    
                    if is_author_seg:
                        author_segments.append(seg)
                        title_start_idx = i + 1
                    else:
                        # Check if this looks like start of title (longer text, starts with capital)
                        if len(seg) > 20 and seg[0].isupper():
                            break
                        # Could still be author name like "G. Pfurtscheller"
                        elif re.match(r'^[A-Z]\.\s*[A-Z][a-z]+', seg):
                            author_segments.append(seg)
                            title_start_idx = i + 1
                        else:
                            break
                
                if author_segments and title_start_idx < len(segments):
                    author = ', '.join(author_segments)
                    
                    # Remaining segments = title + journal
                    remaining = segments[title_start_idx:]
                    
                    # Find journal - look for volume pattern like "Sensors 12"
                    journal_idx = len(remaining)
                    for i, seg in enumerate(remaining):
                        # Check for journal+volume pattern
                        if re.search(r'\d+\s*\(?\d+\)?$', seg) or re.search(r'^\d+\s*\(?\d+\)?', seg):
                            journal_idx = i
                            break
                        # Check for publisher keywords
                        if re.search(r'\b(?:Springer|Elsevier|IEEE|Press|Publisher)\b', seg, re.I):
                            journal_idx = i
                            break
                    
                    if journal_idx > 0:
                        title = ', '.join(remaining[:journal_idx])
                        if journal_idx < len(remaining):
                            journal_text = ', '.join(remaining[journal_idx:])
                            # Clean volume/pages from journal
                            journal_clean = re.sub(r'\s*\d+\s*\(?\d*\)?.*$', '', journal_text)
                            if journal_clean.strip():
                                journal_or_note = journal_clean.strip(' .,')
                    else:
                        # All remaining is title
                        title = ', '.join(remaining)

    # --- Strategy A1.11: AASTeX/natbib format ---
    # Format: "LastName, I. Year, Title, Journal, Vol, Pages"
    # Year appears AFTER author initials WITHOUT parentheses
    # Common in astronomy journals (ApJ, MNRAS, A&A)
    if not title and not author:
        content = clean_latex_formatting(raw_content)
        
        # Pattern: "Name, I. Year," or "Name, I. I. Year," or "Name, I., Name2, I. Year,"
        # Year is 4 digits followed by comma
        aas_match = re.search(r'^(.+?)\s+(\d{4}),\s*(.+)$', content)
        
        if aas_match:
            author_part = aas_match.group(1).strip()
            year = aas_match.group(2)
            rest = aas_match.group(3).strip()
            
            # Verify author_part looks like author names (ends with initials or et al.)
            if (re.search(r'\b[A-Z]\.\s*$', author_part) or  # Ends with "A."
                re.search(r'et\s+al\.?\s*$', author_part, re.I) or  # Ends with "et al."
                re.search(r'\b[A-Z]\.\s+[A-Z]\.\s*$', author_part)):  # Ends with "A. B."
                
                author = author_part.strip(' ,.')
                if 'year' not in fields:
                    fields['year'] = year
                
                # Rest = "Title, Journal, Vol, Pages" or just "Journal, Vol, Pages" (no title)
                # Some astronomy refs don't include titles!
                parts = [p.strip() for p in rest.split(',') if p.strip()]
                
                if parts:
                    # First check if the FIRST part is a journal name (no title case)
                    # Common astronomy journal patterns
                    astronomy_journals = [
                        r'\b(?:The\s+)?Astrophysical\s+Journal',
                        r'\b(?:The\s+)?Astronomical\s+Journal',
                        r'\bMonthly\s+Notices',
                        r'\bAstronomy\s*[&\w]*\s*Astrophysics',
                        r'\bPhysical\s+Review',
                        r'\bNature\b',
                        r'\bScience\b',
                        r'\bAnnual\s+Review',
                        r'\bApJ\b',
                        r'\bMNRAS\b',
                        r'\bA&A\b',
                        r'\bAJ\b',
                        r'\barXiv\b',
                        r'\bZenodo\b',
                        r'\bTransient\s+Name\s+Server',
                    ]
                    
                    first_is_journal = False
                    for jp in astronomy_journals:
                        if re.search(jp, parts[0], re.I):
                            first_is_journal = True
                            break
                    
                    if first_is_journal:
                        # No title - first part is journal
                        journal_or_note = parts[0].strip(' .,')
                        # Don't set title
                    else:
                        # Has title - find where journal starts
                        journal_idx = len(parts)
                        
                        for i, part in enumerate(parts):
                            # Check for journal name patterns
                            for jp in astronomy_journals:
                                if re.search(jp, part, re.I):
                                    journal_idx = i
                                    break
                            if journal_idx < len(parts):
                                break
                            # Check for volume pattern (number only)
                            if re.match(r'^\d+$', part.strip()):
                                # Previous part is likely journal
                                if i > 0:
                                    journal_idx = i - 1
                                break
                        
                        if journal_idx > 0:
                            title = ', '.join(parts[:journal_idx]).strip(' .,')
                            if journal_idx < len(parts):
                                journal_or_note = parts[journal_idx].strip(' .,')
                        else:
                            # All is title (no journal found)
                            title = rest.strip(' .,')

    # --- Strategy A1.3: LLNCS/Springer format (colon separator) ---
    # Format: Author1, I., Author2, I.: Title. Journal Vol(Num), Pages (Year)
    # Colon separates authors from title, period separates title from journal
    if not title and not author and ':' in raw_content:
        content = clean_latex_formatting(raw_content)
        
        # Split by first colon
        colon_pos = content.find(':')
        if colon_pos > 0:
            before_colon = content[:colon_pos].strip()
            after_colon = content[colon_pos + 1:].strip()
            
            # Check if before_colon looks like author names (multiple "LastName, I." patterns)
            author_pattern = re.findall(r'[A-Z][a-z]+,?\s+[A-Z]\.?', before_colon)
            
            if len(author_pattern) >= 1 and len(before_colon) < 200:
                # This looks like LLNCS format
                author = before_colon.rstrip(' ,')
                
                # After colon: Title. Journal Vol(Num), Pages (Year)
                # Find first period that's followed by a space and capital letter (journal start)
                period_match = re.search(r'\.\s+([A-Z][a-zA-Z\s]+(?:\d|\())', after_colon)
                if period_match:
                    title = after_colon[:period_match.start()].strip(' .')
                    journal_part = after_colon[period_match.start() + 1:].strip()
                    
                    # Extract journal name (before volume number)
                    journal_match = re.match(r'^([A-Za-z][^0-9\(]*?)(?:\s*\d|\s*\(|$)', journal_part)
                    if journal_match:
                        journal_or_note = journal_match.group(1).strip(' ,.')
                else:
                    # No clear journal, treat all after colon as title
                    title = after_colon.strip(' .')
    
    # Format: LastName, I., LastName2, I., {et al.} Year, Journal, Vol, Pages
    # This format has NO title - just authors, year, journal, volume, pages
    if not title and not author:
        content = clean_latex_formatting(raw_content)
        
        # Pattern: Authors (ending with Year,), Journal, Vol, Pages
        # Year is followed by comma and journal name
        year_comma_match = re.search(r'\b(19\d{2}|20\d{2}),\s*', content)
        
        if year_comma_match:
            before_year = content[:year_comma_match.start()].strip()
            after_year = content[year_comma_match.end():].strip()
            
            # Check if before_year looks like author list (has "LastName, I." patterns)
            author_pattern = re.findall(r'[A-Z][a-z]+,?\s+[A-Z]\.?', before_year)
            
            if len(author_pattern) >= 1:
                # This looks like natbib format - no title, just journal
                author = before_year.rstrip(' ,')
                # Clean up author - remove "et al" variations and format properly
                author = re.sub(r'\{?et\s*~?al\.?\}?', 'et al.', author)
                author = re.sub(r'\s*,\s*,', ',', author)  # Remove double commas
                
                # After year is Journal, Vol, Pages
                # Journal name typically ends before first number
                journal_match = re.match(r'^([A-Za-z][^0-9]*?)(?:,?\s*\d|$)', after_year)
                if journal_match:
                    journal_or_note = journal_match.group(1).strip(' ,.')
                else:
                    # Fallback - take first part before comma
                    parts = after_year.split(',')
                    if parts:
                        journal_or_note = parts[0].strip(' ,.')
                
                # Mark that this format has no title (it's a journal article citation)
                # We'll set a placeholder that will be handled later
                title = None  # Explicitly no title for this format
    
    # --- Strategy A1.5: \textsc{Author} format ---
    # Format: \textsc{Author1}, \textsc{Author2} and \textsc{Author3}, Title, \emph{Journal} Vol (Year) Pages
    # Authors are in \textsc{}, title is plain text, journal is in \emph{}
    if not title and '\\textsc' in raw_content:
        # Extract all authors from \textsc{} blocks
        textsc_matches = re.findall(r'\\textsc\{([^}]+)\}', raw_content)
        if textsc_matches:
            # Join authors
            author_list = []
            for a in textsc_matches:
                a_clean = a.replace('\\,', ' ').strip()
                author_list.append(a_clean)
            author = ' and '.join(author_list)
            
            # Find the position after last \textsc{} block
            last_textsc = None
            for m in re.finditer(r'\\textsc\{[^}]+\}', raw_content):
                last_textsc = m
            
            if last_textsc:
                after_authors = raw_content[last_textsc.end():]
                # Remove "and" at start if present
                after_authors = re.sub(r'^\s*(?:and\s+)?', '', after_authors)
                
                # Find \emph{Journal} to split title from journal
                emph_match = re.search(r'\\emph\{([^}]+)\}', after_authors)
                if emph_match:
                    # Title is between authors and journal
                    title_part = after_authors[:emph_match.start()].strip(' ,.')
                    # Clean the title
                    title = clean_latex_formatting(title_part).strip(' ,.')
                    
                    # Journal is in \emph{}
                    journal_or_note = emph_match.group(1).strip(' .,')
                else:
                    # No \emph{}, title is all remaining text
                    title = clean_latex_formatting(after_authors).strip(' ,.')
    
    # --- Strategy A1.13: IEEE format with quoted title ---
    # Format: 'Author1, Author2, and Author3, "Title Here," \textit{Journal}, vol. X, no. Y, pp. Z-Z, Month Year'
    # Key: Title is in double quotes "...",", journal is in \textit{} or \emph{}
    # Also handles: "in \textit{Book Title}" as booktitle, "...Press" as publisher
    # Authors listed with commas and "and" before last author
    if not title and not author:
        # Check for quoted title pattern
        quoted_title_match = re.search(r'"([^"]+)"', raw_content)
        
        if quoted_title_match:
            title = quoted_title_match.group(1).strip(' ,.')
            before_title = raw_content[:quoted_title_match.start()]
            after_title = raw_content[quoted_title_match.end():]
            
            # Author is everything before the quoted title
            author_text = clean_latex_formatting(before_title).strip(' ,')
            # Clean up "and" separators
            author_text = re.sub(r'\s+and\s+', ' and ', author_text)
            author = author_text.strip()
            
            # Check for "in \textit{...}" pattern (booktitle for book chapters)
            in_book_match = re.search(r'\bin\s+\\textit\{([^}]+)\}|\bin\s+\\emph\{([^}]+)\}', after_title, re.I)
            
            if in_book_match:
                # This is a book chapter/conference paper
                booktitle = (in_book_match.group(1) or in_book_match.group(2)).strip(' ,.')
                if 'booktitle' not in fields:
                    fields['booktitle'] = booktitle
                after_journal = after_title[in_book_match.end():]
                entry_type = 'incollection'
            else:
                # Regular journal article - find journal in \textit{} or \emph{}
                journal_match = re.search(r'\\textit\{([^}]+)\}|\\emph\{([^}]+)\}', after_title)
                if journal_match:
                    journal_or_note = (journal_match.group(1) or journal_match.group(2)).strip(' ,.')
                    after_journal = after_title[journal_match.end():]
                else:
                    after_journal = after_title
            
            # Check for publisher (contains "Press")
            press_match = re.search(r'([A-Za-z\s]+Press)\b', after_journal, re.I)
            if press_match and 'publisher' not in fields:
                fields['publisher'] = press_match.group(1).strip()
            
            # Extract vol, no, pp, year from remaining content
            # Pattern: vol. X, no. Y, pp. Z-Z, Month Year
            vol_match = re.search(r'vol\.?\s*(\d+)', after_journal, re.I)
            if vol_match and 'volume' not in fields:
                fields['volume'] = vol_match.group(1)
            
            no_match = re.search(r'no\.?\s*(\d+)', after_journal, re.I)
            if no_match and 'number' not in fields:
                fields['number'] = no_match.group(1)
            
            pp_match = re.search(r'pp?\.?\s*(\d+[-–]\d+|\d+)', after_journal, re.I)
            if pp_match and 'pages' not in fields:
                fields['pages'] = pp_match.group(1).replace('–', '--')
            
            # Year: 4 digits, may be preceded by month
            year_match = re.search(r'(\d{4})\s*\.?\s*$', after_journal.strip())
            if not year_match:
                year_match = re.search(r',\s*(\d{4})', after_journal)
            if year_match and 'year' not in fields:
                fields['year'] = year_match.group(1)
            
            # Extract DOI if present
            doi_match = re.search(r'(?:https?://)?(?:dx\.)?doi\.org/([^\s,]+)|10\.\d{4,}/[^\s,]+', after_journal, re.I)
            if doi_match and 'doi' not in fields:
                fields['doi'] = doi_match.group(0).strip(' .')
    
    # --- Strategy A1.14: Ampersand-separated authors with quoted title ---
    # Format: "LastName, FirstName & LastName2, FirstName2. (Year). Title. DOI"
    # Or: "LastName, FirstName & LastName2, FirstName2, Title, vol. X, Year"
    # Key: Authors separated by & (ampersand)
    if not title and not author and '&' in raw_content:
        # Check if has quoted title
        quoted_match = re.search(r'"([^"]+)"', raw_content)
        
        if quoted_match:
            title = quoted_match.group(1).strip(' ,.')
            before_title = raw_content[:quoted_match.start()]
            after_title = raw_content[quoted_match.end():]
            
            # Authors are before the quoted title, separated by &
            author_text = clean_latex_formatting(before_title).strip(' ,.')
            # Replace & with "and" for standard format
            author_text = re.sub(r'\s*&\s*', ' and ', author_text)
            author = author_text.strip()
        else:
            # No quotes - try to find title boundary
            # Pattern: LastName, FirstName & ... (Year). Title...
            content = clean_latex_formatting(raw_content)
            
            # Pattern with year in parentheses: ... (2023). Title...
            year_paren_match = re.search(r'\)\.\s*(.+?)(?:\.\s*\d|$)', content)
            if year_paren_match:
                title = year_paren_match.group(1).strip(' .')
                before_year = content[:year_paren_match.start() + 1]
                
                # Extract year from parentheses
                year_match = re.search(r'\((\d{4})\)', before_year)
                if year_match and 'year' not in fields:
                    fields['year'] = year_match.group(1)
                
                # Authors are before (Year)
                author_part = content[:content.find('(' + (year_match.group(1) if year_match else ''))].strip(' .')
                author_part = re.sub(r'\s*&\s*', ' and ', author_part)
                author = author_part.strip()
        
        # Extract DOI if present
        doi_match = re.search(r'(?:https?://)?(?:dx\.)?doi\.org/([^\s,]+)|10\.\d{4,}/[^\s,]+', raw_content, re.I)
        if doi_match and 'doi' not in fields:
            fields['doi'] = doi_match.group(0).strip(' .')
        
        # Extract vol./year if present
        vol_match = re.search(r'vol\.?\s*(\d+)', raw_content, re.I)
        if vol_match and 'volume' not in fields:
            fields['volume'] = vol_match.group(1)
        
        # Extract year at end
        if 'year' not in fields:
            year_end = re.search(r',\s*(\d{4})\s*\.?\s*$', raw_content.strip())
            if year_end:
                fields['year'] = year_end.group(1)

    # --- Strategy A1.15: Meteorology/AMS journal format ---
    # Format: "Author, I., Year: Title. J. Atmos. Oceanic Technol., Vol, Pages, DOI"
    # Key: Year followed by colon after author, journal abbreviated
    if not title and not author:
        content = clean_latex_formatting(raw_content)
        
        # Pattern: Author, Year: Title. Journal...
        ams_match = re.search(r'^(.+?),\s*(\d{4}):\s*(.+?)\.([A-Z].+)$', content, re.DOTALL)
        
        if ams_match:
            author = ams_match.group(1).strip()
            year = ams_match.group(2)
            title = ams_match.group(3).strip()
            remaining = ams_match.group(4).strip()
            
            if 'year' not in fields:
                fields['year'] = year
            
            # Extract journal (first part before volume/pages)
            journal_match = re.match(r'^([A-Za-z][^,\d]*?)(?:,\s*\d|$)', remaining)
            if journal_match:
                journal_or_note = journal_match.group(1).strip(' .,')
            
            # Extract DOI
            doi_match = re.search(r'https?://doi\.org/[^\s,]+', remaining)
            if doi_match and 'doi' not in fields:
                fields['doi'] = doi_match.group(0).strip()
            
            # Extract volume and pages
            vol_match = re.search(r',\s*(\d+),\s*(\d+[-–]\d+)', remaining)
            if vol_match:
                if 'volume' not in fields:
                    fields['volume'] = vol_match.group(1)
                if 'pages' not in fields:
                    fields['pages'] = vol_match.group(2).replace('–', '--')

    # --- Strategy A1.16: HEP/INSPIRE format ---
    # Format: "A.~Strominger and C.~Vafa, {\it Title here}, {\em Phys. Lett.} {\bf B379} (1996) 99--104, [\href{url}{\tt hep-th/9601029}]"
    # Key: Authors with tildes, title in {\it ...}, journal in {\em ...}, volume in {\bf ...}
    # arXiv/eprint in [\href{...}{\tt arXiv:XXXX}] or [{\tt arXiv:XXXX}]
    if not title and not author:
        # Check for {\it ...} title pattern
        it_match = re.search(r'\{\\it\s+([^}]+)\}', raw_content)
        
        if it_match:
            title = it_match.group(1).strip(' ,.')
            before_title = raw_content[:it_match.start()]
            after_title = raw_content[it_match.end():]
            
            # Author is everything before {\it
            author_text = before_title.strip(' ,')
            # Clean tildes and LaTeX formatting
            author_text = re.sub(r'~', ' ', author_text)
            author_text = clean_latex_formatting(author_text)
            # Normalize "and" separator
            author_text = re.sub(r'\s+and\s+', ' and ', author_text)
            author = author_text.strip(' ,.')
            
            # Find journal in {\em ...}
            em_match = re.search(r'\{\\em\s+([^}]+)\}', after_title)
            if em_match:
                journal_or_note = em_match.group(1).strip(' .,')
                after_journal = after_title[em_match.end():]
            else:
                after_journal = after_title
            
            # Find volume in {\bf ...} - may include letter like B379, D77
            bf_match = re.search(r'\{\\bf\s+([^}]+)\}', after_journal)
            if bf_match and 'volume' not in fields:
                vol_text = bf_match.group(1).strip()
                # Extract number part, remove letter prefix if present
                vol_num = re.search(r'([A-Z]?)(\d+)', vol_text)
                if vol_num:
                    fields['volume'] = vol_num.group(2)
            
            # Find year in parentheses after volume
            year_match = re.search(r'\((\d{4})\)', after_journal)
            if year_match and 'year' not in fields:
                fields['year'] = year_match.group(1)
            
            # Find pages: pattern like "99--104" or "231--252"
            pages_match = re.search(r'\)\s*(\d+[-–]+\d+|\d+)', after_journal)
            if pages_match and 'pages' not in fields:
                fields['pages'] = pages_match.group(1).replace('–', '--')
            
            # Also check for "no. X" pattern: (2013), no.~10 106005
            no_match = re.search(r'no\.?~?\s*(\d+)', after_journal)
            if no_match and 'number' not in fields:
                fields['number'] = no_match.group(1)
            
            # Extract arXiv/eprint from [\href{url}{\tt arXiv:...}] or [\href{url}{\tt hep-th/...}]
            arxiv_match = re.search(r'\\href\{[^}]*\}\{\\tt\s+(arXiv:)?(\d+\.\d+|hep-[a-z]+/\d+|math/\d+|[a-z-]+/\d+)\}', after_journal)
            if arxiv_match:
                eprint = arxiv_match.group(2)
                if 'eprint' not in fields:
                    fields['eprint'] = eprint
                if 'archivePrefix' not in fields:
                    fields['archivePrefix'] = 'arXiv'
            
            # Also try to extract URL from \href{url}
            url_match = re.search(r'\\href\{([^}]+)\}', after_journal)
            if url_match and 'url' not in fields:
                fields['url'] = url_match.group(1).strip()

    # --- Strategy A1.17: Physics format without title ---
    # Format: "Author et al., Journal Name \textbf{Vol}(Num), Pages (Year)"
    # Key: NO TITLE - common in physics papers
    # Volume is in \textbf{...}, may have (Num) after, Year in parentheses at end
    # Common journals: Phys. Rev., Nature, Science, JHEP, PTEP, etc.
    if not title and not author:
        # Check for \textbf{} volume pattern (physics format indicator)
        # Pattern: \textbf{Vol} or \textbf{Vol}(Num)
        bf_match = re.search(r'\\textbf\{(\d+)\}(?:\((\d+)\))?', raw_content)
        
        if bf_match:
            # Common physics journal patterns - expanded list
            physics_journals = [
                r'Phys\.\s*Rev\.\s*(?:Lett\.|[A-D]|X)?',
                r'Astrophys\.\s*J\.(?:\s*Lett\.)?(?:\s*Suppl\.)?',
                r'Nature(?:\s+(?:Phys\.|Commun\.))?',
                r'Science(?:\s+Bull\.)?',
                r'Nucl\.\s*Phys\.\s*[A-B]?',
                r'Phys\.\s*Lett\.\s*[A-B]?',
                r'Phys\.\s*Rep(?:t|ort)?\.?',
                r'JHEP',
                r'PTEP',
                r'J\.\s*Phys\.\s*Soc\.\s*Jpn\.',
                r'Mon\.\s*Not\.\s*Roy\.\s*Astron\.\s*Soc\.',
                r'Eur\.\s*Phys\.\s*J\.\s*(?:[A-C]|ST)?(?:\s*Plus)?',
                r'Ann(?:als)?\.?\s*Phys\.',
                r'Rev\.\s*Mod\.\s*Phys\.',
                r'Prog\.\s*(?:Part\.\s*Nucl\.\s*)?(?:Theor\.\s*)?Phys\.?(?:\s*Suppl\.)?',
                r'Rept\.\s*Prog\.\s*Phys\.',
                r'Living\s+Rev\.\s*Rel\.',
                r'Int\.\s*J\.\s*Mod\.\s*Phys\.\s*[A-D]?',
                r'Astron\.\s*Astrophys\.',
                r'New\s+Astronomy',
                r'Chinese\s+Phys\.\s*[A-C]?',
                r'Front\.\s*(?:Astron\.\s*Space\s*Sci\.|Phys\.)',
                r'Res\.\s*Astron\.\s*Astrophys',
                r'Nuovo\s+Cim\.',
                r'Fortsch\.\s*Phys\.',
                r'Commun\.\s*Math\.\s*Phys\.',
                r'J\.\s*Math\.\s*Phys\.',
                r'Symmetry',
                r'Few\s+Body\s+Syst\.',
                r'Physica\s*[A-D]?',
                r'Z\.\s*Phys\.',
                r'Am\.\s*J\.\s*Phys\.',
                r'Czech\.\s*J\.\s*Phys\.',
                r'Chin\.\s*Phys\.\s*[A-C]?',
                r'PoS',
                r'EPJ\s+Web\s+Conf\.',
            ]
            
            # Find journal name in content
            journal_found = None
            journal_start = -1
            journal_end = -1
            for jp in physics_journals:
                j_match = re.search(jp, raw_content, re.I)
                if j_match:
                    if journal_start == -1 or j_match.start() < journal_start:
                        journal_start = j_match.start()
                        journal_end = j_match.end()
                        journal_found = j_match.group(0).strip()
            
            if journal_found and journal_start > 0:
                # Author is everything before journal name
                author_part = raw_content[:journal_start]
                # Clean up author
                author_text = clean_latex_formatting(author_part)
                author_text = re.sub(r'\\thinspace', ' ', author_text)
                author_text = re.sub(r'~', ' ', author_text)
                author_text = re.sub(r'\s+', ' ', author_text)
                author_text = re.sub(r'et\s*al\.?', 'et al.', author_text)
                author = author_text.strip(' ,.')
                
                # Journal name
                journal_or_note = journal_found.strip()
                
                # Volume from \textbf{} - group 1
                if 'volume' not in fields:
                    fields['volume'] = bf_match.group(1)
                
                # Number from (Num) after volume - group 2
                if bf_match.group(2) and 'number' not in fields:
                    fields['number'] = bf_match.group(2)
                
                # Year in parentheses at end - NOT volume/number
                year_match = re.search(r'\((\d{4})\)\s*\.?\s*$', raw_content)
                if year_match and 'year' not in fields:
                    fields['year'] = year_match.group(1)
                
                # Pages: between volume and year
                # Pattern: \textbf{Vol}(Num), Pages (Year) or \textbf{Vol}, Pages (Year)
                after_vol = raw_content[bf_match.end():]
                # Remove year at end first
                after_vol_clean = re.sub(r'\(?\d{4}\)?\s*\.?\s*$', '', after_vol)
                # Find pages - may be comma-separated
                pages_match = re.search(r',?\s*([A-Z]?\d+[-–]\d+|\d+|L\d+|[A-Z]\d+)', after_vol_clean)
                if pages_match and 'pages' not in fields:
                    pages_val = pages_match.group(1).replace('–', '--')
                    fields['pages'] = pages_val
                
                # No title for this format - set to empty string to prevent fallback
                title = ''

    # --- Strategy A1.18: Book format with (Publisher, Year) ---
    # Format: "Author, Book Title (Publisher, Year)"
    # Or: "Author, Book Title, Subtitle (Publisher, Year)"
    # Key: Ends with (Publisher, Year) pattern
    if not title and not author:
        # Check for (Publisher, Year) at end
        pub_year_match = re.search(r'\(([^()]+(?:Press|Publisher|Springer|Cambridge|Oxford|Wiley|Academic|Elsevier|World Scientific|Freeman)[^()]*),?\s*(\d{4})\)\s*$', raw_content, re.I)
        
        if pub_year_match:
            publisher = pub_year_match.group(1).strip()
            year = pub_year_match.group(2)
            
            if 'publisher' not in fields:
                fields['publisher'] = publisher
            if 'year' not in fields:
                fields['year'] = year
            
            # Content before (Publisher, Year)
            before_pub = raw_content[:pub_year_match.start()].strip()
            
            # Clean LaTeX
            before_clean = clean_latex_formatting(before_pub)
            before_clean = re.sub(r'~', ' ', before_clean).strip(' ,')
            
            # Split by comma to separate author(s) and title
            # Pattern: "Author1, Author2 and Author3, Book Title"
            # Find where authors end and title begins
            
            # Look for patterns: ends with initials like "J." or "Jr." or name
            parts = before_clean.split(',')
            
            if len(parts) >= 2:
                # Heuristic: Authors have initials, title is longer text
                author_parts = []
                title_start = 0
                
                for i, part in enumerate(parts):
                    part = part.strip()
                    # Check if looks like author (has initials or short)
                    has_initial = bool(re.search(r'\b[A-Z]\.', part))
                    has_and = ' and ' in part.lower()
                    is_short = len(part) < 40
                    
                    if (has_initial or has_and) and is_short:
                        author_parts.append(part)
                        title_start = i + 1
                    else:
                        break
                
                if author_parts and title_start < len(parts):
                    author = ', '.join(author_parts)
                    title = ', '.join(parts[title_start:]).strip()
                elif len(parts) == 2:
                    # Simple case: Author, Title
                    author = parts[0].strip()
                    title = parts[1].strip()
            
            entry_type = 'book'

    # --- Strategy A1.19: Article format with semicolon-separated arXiv ---
    # Format: "Author, Title, Journal Vol (Year) Pages; arXiv: XXXX.XXXXX"
    # Key: Semicolon separates main reference from arXiv
    # arXiv format: "arXiv: XXXX.XXXXX" (with space after colon)
    if not title and not author and '; arXiv' in raw_content:
        # Split by "; arXiv"
        parts = raw_content.split('; arXiv')
        main_ref = parts[0].strip()
        arxiv_part = parts[1].strip() if len(parts) > 1 else ''
        
        # Extract arXiv ID
        arxiv_match = re.search(r':?\s*([a-z-]+/\d+|\d+\.\d+)', arxiv_part)
        if arxiv_match:
            eprint = arxiv_match.group(1)
            if 'eprint' not in fields:
                fields['eprint'] = eprint
            if 'archivePrefix' not in fields:
                fields['archivePrefix'] = 'arXiv'
        
        # Parse main reference
        # Pattern: "Author, Title, Journal Vol (Year) Pages"
        # Look for Journal Vol (Year) pattern
        journal_vol_year = re.search(r',\s*([A-Z][^,]+?)\s+(\d+)\s*\((\d{4})\)\s*([\d-]+)?', main_ref)
        
        if journal_vol_year:
            journal_or_note = journal_vol_year.group(1).strip()
            if 'volume' not in fields:
                fields['volume'] = journal_vol_year.group(2)
            if 'year' not in fields:
                fields['year'] = journal_vol_year.group(3)
            if journal_vol_year.group(4) and 'pages' not in fields:
                fields['pages'] = journal_vol_year.group(4).replace('–', '--')
            
            # Before journal = Author, Title
            before_journal = main_ref[:journal_vol_year.start()].strip(' ,')
            
            # Split by comma - find where author ends and title begins
            comma_parts = [p.strip() for p in before_journal.split(',') if p.strip()]
            
            if len(comma_parts) >= 2:
                # Find title start - title is usually longer and starts with capital
                author_segs = []
                title_idx = 0
                
                for i, seg in enumerate(comma_parts):
                    # Author segment: has initials like "J." or short name
                    has_init = bool(re.search(r'\b[A-Z]\.', seg))
                    is_short = len(seg) < 35
                    
                    if has_init and is_short:
                        author_segs.append(seg)
                        title_idx = i + 1
                    else:
                        break
                
                if author_segs and title_idx < len(comma_parts):
                    author = ', '.join(author_segs)
                    title = ', '.join(comma_parts[title_idx:]).strip()
        else:
            # No journal pattern - might be just arXiv preprint
            # Pattern: "Author, Title, arXiv: XXXX"
            comma_parts = [p.strip() for p in main_ref.split(',') if p.strip()]
            if len(comma_parts) >= 2:
                author = comma_parts[0]
                title = ', '.join(comma_parts[1:]).strip()

    # --- Strategy A1.22: Astronomy format with journal macros ---
    # Format: "Author Year, \apj, Vol, Pages" or "Author, Year, \mnras, Vol, Pages"
    # Key: Journal is LaTeX macro like \apj, \mnras, \aj, \aap, \nat, \sci, etc.
    # NO TITLE in this format - common in astronomy papers
    if not title and not author:
        # Astronomy journal macros mapping
        astro_journal_macros = {
            r'\\apj\b': 'ApJ',
            r'\\apjl\b': 'ApJL',
            r'\\apjs\b': 'ApJS',
            r'\\mnras\b': 'MNRAS',
            r'\\aj\b': 'AJ',
            r'\\aap\b': 'A&A',
            r'\\nat\b': 'Nature',
            r'\\sci\b': 'Science',
            r'\\pasp\b': 'PASP',
            r'\\pasj\b': 'PASJ',
            r'\\araa\b': 'ARA&A',
            r'\\aapr\b': 'A&ARv',
        }
        
        # Check for any astronomy journal macro
        journal_found = None
        journal_match_obj = None
        for macro_pattern, journal_name in astro_journal_macros.items():
            match = re.search(macro_pattern, raw_content, re.I)
            if match:
                journal_found = journal_name
                journal_match_obj = match
                break
        
        if journal_found and journal_match_obj:
            journal_or_note = journal_found
            before_journal = raw_content[:journal_match_obj.start()]
            after_journal = raw_content[journal_match_obj.end():]
            
            # Before journal: Author(s) Year,
            # Pattern: "Author1, Author2 Year," or "{Author} et al. Year,"
            # Extract year first - it's the 4-digit number before journal
            year_match = re.search(r'(\d{4})\s*,?\s*$', before_journal.strip())
            if year_match:
                if 'year' not in fields:
                    fields['year'] = year_match.group(1)
                author_part = before_journal[:year_match.start()].strip()
            else:
                author_part = before_journal.strip()
            
            # Clean author
            author_text = clean_latex_formatting(author_part)
            author_text = re.sub(r'\\emph\{et~al\.\}', 'et al.', author_text)
            author_text = re.sub(r'et~al\.', 'et al.', author_text)
            author_text = re.sub(r'\{|\}', '', author_text)  # Remove braces
            author_text = re.sub(r'\s+', ' ', author_text)
            author = author_text.strip(' ,.')
            
            # After journal: ", Vol, Pages" or ", Vol, PageID"
            after_clean = after_journal.strip(' ,')
            parts = [p.strip() for p in after_clean.split(',') if p.strip()]
            
            if len(parts) >= 1:
                # First part is volume (may have letter like 766L)
                vol_match = re.match(r'(\d+[A-Z]?)', parts[0])
                if vol_match and 'volume' not in fields:
                    fields['volume'] = vol_match.group(1)
                
                if len(parts) >= 2:
                    # Second part is pages or page ID
                    pages_part = parts[1].strip()
                    # Clean pages - may be like "L51" or "1033" or "323"
                    pages_clean = re.sub(r'[^0-9L\-–]', '', pages_part)
                    if pages_clean and 'pages' not in fields:
                        fields['pages'] = pages_clean.replace('–', '--')
            
            # No title for this format
            title = None

    # --- Strategy A1.21: Colon-separated Author: Title format ---
    # Format: "Author: Title. \textit{Journal} \textbf{Vol} (Year), Pages"
    # Or: "Author: \textit{Book Title}. Publisher, City, Year"
    # Key: Colon separates author from title
    if not title and not author and ':' in raw_content:
        # Find first colon that looks like author/title separator
        # (not part of URL or time)
        colon_match = re.search(r'([A-Za-z][^:]*?):\s+', raw_content)
        
        if colon_match:
            potential_author = colon_match.group(1).strip()
            after_colon = raw_content[colon_match.end():].strip()
            
            # Check if potential_author looks like author names
            # Pattern: "LastName, I." or "LastName, I.I." or multiple separated by ; or "and"
            has_author_pattern = bool(re.search(r'[A-Z][a-z]+,\s*[A-Z]\.', potential_author))
            is_short = len(potential_author) < 150
            
            if has_author_pattern and is_short:
                # Clean author
                author_text = potential_author
                author_text = re.sub(r'\s*;\s*', ', ', author_text)  # Replace ; with ,
                author = author_text.strip(' ,.')
                
                # After colon: could be Title. Journal... or \textit{Book}...
                # Check for \textit{} at start (book title)
                book_match = re.match(r'\\textit\{([^}]+)\}\.?\s*(.*)$', after_colon, re.DOTALL)
                
                if book_match:
                    title = book_match.group(1).strip()
                    remaining = book_match.group(2).strip()
                    
                    # Check if remaining has publisher pattern
                    if re.search(r'(Wiley|Springer|North-Holland|Academic|Press|World\s+Scientific)', remaining, re.I):
                        # This is a book
                        entry_type = 'book'
                        # Extract publisher
                        pub_match = re.search(r'([A-Za-z][^,]*(?:Press|Wiley|Springer|Holland|Scientific)[^,]*)', remaining, re.I)
                        if pub_match and 'publisher' not in fields:
                            fields['publisher'] = pub_match.group(1).strip()
                        # Extract year
                        year_match = re.search(r'(\d{4})', remaining)
                        if year_match and 'year' not in fields:
                            fields['year'] = year_match.group(1)
                    else:
                        # This is an article with italic journal
                        journal_or_note = title
                        title = None  # No separate title
                else:
                    # Plain text title followed by journal
                    # Pattern: "Title. \textit{Journal} \textbf{Vol}..."
                    title_journal = re.match(r'([^.]+)\.\s*\\textit\{([^}]+)\}', after_colon)
                    
                    if title_journal:
                        title = title_journal.group(1).strip()
                        journal_or_note = title_journal.group(2).strip()
                        remaining = after_colon[title_journal.end():]
                        
                        # Extract volume from \textbf{}
                        vol_match = re.search(r'\\textbf\{(\d+)\}', remaining)
                        if vol_match and 'volume' not in fields:
                            fields['volume'] = vol_match.group(1)
                        
                        # Extract year from parentheses
                        year_match = re.search(r'\((\d{4})\)', remaining)
                        if year_match and 'year' not in fields:
                            fields['year'] = year_match.group(1)
                        
                        # Extract pages
                        pages_match = re.search(r'(\d+[-–]\d+)', remaining)
                        if pages_match and 'pages' not in fields:
                            fields['pages'] = pages_match.group(1).replace('–', '--')
                    else:
                        # Simple title without italic journal
                        # Look for period as title end
                        period_match = re.search(r'^([^.]+)\.', after_colon)
                        if period_match:
                            title = period_match.group(1).strip()
                            remaining = after_colon[period_match.end():].strip()
                            
                            # Check for year
                            year_match = re.search(r'(\d{4})', remaining)
                            if year_match and 'year' not in fields:
                                fields['year'] = year_match.group(1)

    # --- Strategy A1.20: Math format with {\sl Title} or {\it Title} ---
    # Format: "Author, {\sl Title here}, Journal Vol (Year), no. X, Pages"
    # Key: Title in {\sl ...} or {\it ...} (slanted/italic text)
    # Journal follows title, with volume/year pattern
    if not title and not author:
        # Check for {\sl ...} or {\it ...} title pattern
        sl_match = re.search(r'\{\\sl\s+([^}]+)\}|\{\\it\s+([^}]+)\}', raw_content)
        
        if sl_match:
            title = (sl_match.group(1) or sl_match.group(2)).strip(' ,.')
            before_title = raw_content[:sl_match.start()]
            after_title = raw_content[sl_match.end():]
            
            # Author is everything before {\sl or {\it
            author_text = before_title.strip()
            # Handle semicolon-separated authors
            author_text = re.sub(r'\s*;\s*', ', ', author_text)
            # Clean LaTeX
            author_text = clean_latex_formatting(author_text)
            author_text = re.sub(r'~', ' ', author_text)
            author = author_text.strip(' ,.')
            
            # After title: ", Journal Vol (Year), no. X, Pages"
            after_clean = after_title.strip(' ,')
            
            # Look for Journal Vol (Year) pattern
            journal_vol_match = re.search(r'^,?\s*([A-Za-z][^0-9(]*?)\s*(\d+)\s*\((\d{4})\)', after_clean)
            
            if journal_vol_match:
                journal_or_note = journal_vol_match.group(1).strip(' .,')
                if 'volume' not in fields:
                    fields['volume'] = journal_vol_match.group(2)
                if 'year' not in fields:
                    fields['year'] = journal_vol_match.group(3)
                
                remaining = after_clean[journal_vol_match.end():]
                
                # Extract "no. X"
                no_match = re.search(r'no\.?\s*(\d+)', remaining, re.I)
                if no_match and 'number' not in fields:
                    fields['number'] = no_match.group(1)
                
                # Extract pages
                pages_match = re.search(r'(\d+[-–]\d+)', remaining)
                if pages_match and 'pages' not in fields:
                    fields['pages'] = pages_match.group(1).replace('–', '--')
            else:
                # No Volume (Year) pattern - might be arXiv preprint
                if arxiv_match:
                    if 'eprint' not in fields:
                        fields['eprint'] = arxiv_match.group(1)
                    if 'archivePrefix' not in fields:
                        fields['archivePrefix'] = 'arXiv'

    # --- Strategy A1.26: Natbib format with \textit{Title} and \textbf{Vol} ---
    # Format: "Author, \textit{Title}, Journal \textbf{Vol} (Year), Pages"
    # Key: Title in \textit{} (not {\sl} or {\it}), Volume in \textbf{}
    if not title and not author:
        # Find \textit{ and extract content handling nested braces
        textit_start = raw_content.find('\\textit{')
        textbf_match = re.search(r'\\textbf\{(\d+)\}', raw_content)
        
        if textit_start >= 0 and textbf_match:
            # Extract \textit{} content with balanced braces
            brace_start = textit_start + len('\\textit{')
            brace_count = 1
            pos = brace_start
            while pos < len(raw_content) and brace_count > 0:
                if raw_content[pos] == '{':
                    brace_count += 1
                elif raw_content[pos] == '}':
                    brace_count -= 1
                pos += 1
            textit_end = pos  # position after closing brace
            title_content = raw_content[brace_start:pos-1] if brace_count == 0 else ''
            
            if title_content and textit_end < textbf_match.start():
                # This is natbib format: Author, \textit{Title}, Journal \textbf{Vol} (Year)
                title = title_content.strip(' ,.')
                before_title = raw_content[:textit_start]
                after_title = raw_content[textit_end:textbf_match.start()]
                after_vol = raw_content[textbf_match.end():]
                
                # Author is before \textit{title}
                author_text = before_title.strip()
                author_text = clean_latex_formatting(author_text)
                author_text = re.sub(r'~', ' ', author_text)
                author = author_text.strip(' ,.')
                
                # Journal is between title and volume
                journal_text = after_title.strip(' ,')
                journal_text = clean_latex_formatting(journal_text)
                if journal_text:
                    journal_or_note = journal_text.strip(' ,.')
                
                # Volume from \textbf{}
                if 'volume' not in fields:
                    fields['volume'] = textbf_match.group(1)
                
                # Year from (YYYY) after volume
                year_match = re.search(r'\((\d{4})[^)]*\)', after_vol)
                if year_match and 'year' not in fields:
                    fields['year'] = year_match.group(1)
                
                # Pages after year
                pages_match = re.search(r'(\d+[-–]\d+)', after_vol)
                if pages_match and 'pages' not in fields:
                    fields['pages'] = pages_match.group(1).replace('–', '--')
                
                # Check for arXiv
                arxiv_match = re.search(r'\{?arXiv\}?:(\d+\.\d+)', raw_content, re.I)
                if arxiv_match:
                    if 'eprint' not in fields:
                        fields['eprint'] = arxiv_match.group(1)
                    if 'archivePrefix' not in fields:
                        fields['archivePrefix'] = 'arXiv'

    # --- Strategy A1.23: Math format with semicolon-separated authors ---
    # Format: "A. Do; J. Flynn; N. Lam, Title here. Journal Vol(Num) (Year), Pages"
    # Or: "Author; Author, Title, arXivXXXX.XXXXX (Year)"
    # Key: Authors separated by semicolons, plain text title
    if not title and not author and ';' in raw_content:
        # Split by semicolons to get potential authors
        content = raw_content
        
        # Find the last semicolon-separated segment that looks like an author
        # Then the remaining is title + journal
        parts = content.split(';')
        
        if len(parts) >= 2:
            # Check each part - authors have patterns like "A. Name" or "FirstName LastName"
            author_parts = []
            remaining_idx = 0
            
            for i, part in enumerate(parts):
                part_clean = clean_latex_formatting(part).strip()
                # Check if looks like author (short, has initial pattern)
                has_initial = bool(re.search(r'\b[A-Z]\.', part_clean))
                is_short = len(part_clean) < 50
                
                if has_initial and is_short:
                    author_parts.append(part_clean)
                    remaining_idx = i + 1
                else:
                    # This might be title or last author + title
                    # Check for comma in last segment
                    if ',' in part:
                        # Split at first comma - before is author, after is title
                        comma_idx = part.find(',')
                        last_author = part[:comma_idx].strip()
                        if bool(re.search(r'\b[A-Z]\.', last_author)) and len(last_author) < 50:
                            author_parts.append(clean_latex_formatting(last_author))
                            remaining_content = part[comma_idx+1:].strip()
                        else:
                            remaining_content = part.strip()
                    else:
                        remaining_content = part.strip()
                    break
            
            if author_parts:
                author = ', '.join(author_parts)
                
                # remaining_content has title and possibly journal
                # Look for arXiv pattern first
                arxiv_match = re.search(r'arXiv:?(\d+\.\d+)', remaining_content, re.I)
                if arxiv_match:
                    if 'eprint' not in fields:
                        fields['eprint'] = arxiv_match.group(1)
                    if 'archivePrefix' not in fields:
                        fields['archivePrefix'] = 'arXiv'
                    # Title is before arXiv
                    title = remaining_content[:arxiv_match.start()].strip(' ,.')
                    # Year at end
                    year_match = re.search(r'\((\d{4})\)', remaining_content)
                    if year_match and 'year' not in fields:
                        fields['year'] = year_match.group(1)
                else:
                    # Look for journal pattern - common math journals have patterns like:
                    # "J. Geom. Anal. 32(4) (2022)", "Adv. Math. 419 (2023)", "Math. Ann. 349(1) (2011)"
                    # Key indicators: abbreviated journal name followed by volume and year
                    
                    # First, try to find known journal abbreviation patterns
                    journal_abbrev_patterns = [
                        r'(J\.\s*[A-Z][a-z]+\.?\s*[A-Za-z\.]+\.?)',  # J. Xxx. Yyy.
                        r'(J\.\s*Differential\s*Equations)',
                        r'(Adv\.\s*Math\.?)',
                        r'(Math\.\s*Ann\.?)',
                        r'(Commun\.\s*Math\.\s*Res\.?)',
                        r'(Ann\.\s*[A-Za-z]+\.?)',
                        r'(Proc\.\s*[A-Za-z\.]+)',
                        r'(Trans\.\s*[A-Za-z\.]+)',
                        r'([A-Z][a-z]+\.\s*[A-Z][a-z]+\.)',  # Xxx. Yyy.
                    ]
                    
                    journal_found = None
                    journal_start = -1
                    for jp in journal_abbrev_patterns:
                        j_match = re.search(jp, remaining_content)
                        if j_match:
                            if journal_start == -1 or j_match.start() < journal_start:
                                journal_start = j_match.start()
                                journal_found = j_match.group(1)
                    
                    if journal_found and journal_start > 0:
                        # Title is everything before journal
                        title_text = remaining_content[:journal_start].strip()
                        # Remove trailing period
                        title = title_text.rstrip(' .')
                        
                        # Extract journal and volume/year info
                        after_journal_name = remaining_content[journal_start + len(journal_found):]
                        # Pattern: Vol(Num) (Year)
                        vol_year_match = re.search(r'(\d+)(?:\((\d+)\))?\s*\((\d{4})\)', after_journal_name)
                        if vol_year_match:
                            journal_or_note = journal_found.strip()
                            if 'volume' not in fields:
                                fields['volume'] = vol_year_match.group(1)
                            if vol_year_match.group(2) and 'number' not in fields:
                                fields['number'] = vol_year_match.group(2)
                            if 'year' not in fields:
                                fields['year'] = vol_year_match.group(3)
                            
                            # Pages after year
                            pages_match = re.search(r',?\s*(?:paper\s+no\.\s*)?(\d+[-–]\d+|\d+)', after_journal_name[vol_year_match.end():])
                            if pages_match and 'pages' not in fields:
                                fields['pages'] = pages_match.group(1).replace('–', '--')
                    else:
                        # Fallback: Look for general journal pattern: "text Vol(Num) (Year)"
                        journal_pattern = re.search(r'([A-Z][A-Za-z\.\s]+?)\s+(\d+)(?:\((\d+)\))?\s*\((\d{4})\)', remaining_content)
                        
                        if journal_pattern:
                            # Title is before journal - find last period
                            title_end = remaining_content[:journal_pattern.start()].strip()
                            last_period = title_end.rfind('.')
                            if last_period > 0:
                                title = title_end[:last_period].strip()
                            else:
                                title = title_end.strip(' ,')
                            
                            journal_or_note = journal_pattern.group(1).strip()
                            if 'volume' not in fields:
                                fields['volume'] = journal_pattern.group(2)
                            if journal_pattern.group(3) and 'number' not in fields:
                                fields['number'] = journal_pattern.group(3)
                            if 'year' not in fields:
                                fields['year'] = journal_pattern.group(4)
                            
                            # Pages after journal pattern
                            after_journal = remaining_content[journal_pattern.end():]
                            pages_match = re.search(r',?\s*(?:paper\s+no\.\s*)?(\d+[-–]\d+|\d+)', after_journal)
                            if pages_match and 'pages' not in fields:
                                fields['pages'] = pages_match.group(1).replace('–', '--')
                        else:
                            # No journal pattern - just title
                            title = remaining_content.strip(' .,')
                            # Check for year at end
                            year_match = re.search(r'\((\d{4})\)', remaining_content)
                            if year_match and 'year' not in fields:
                                fields['year'] = year_match.group(1)

    # --- Strategy A1.27: IEEE format with quoted "Title" ---
    # Format: 'Author, "Title," \textit{Journal}, vol. X, no. Y, pp. XXX-YYY, Year'
    # Or: 'Author, ``Title," \textit{Journal}, ...'
    # Key: Title in double quotes or ``...''
    if not title and not author:
        # Check for quoted title patterns: "Title" or ``Title'' or ``Title,"
        quoted_match = re.search(r'["\u201c]([^"\u201d]+?)["\u201d,]|``([^\']+)[\'\u2019,]', raw_content)
        
        if quoted_match:
            # Extract title from quotes
            title = (quoted_match.group(1) or quoted_match.group(2)).strip(' ,.')
            before_quote = raw_content[:quoted_match.start()].strip()
            after_quote = raw_content[quoted_match.end():].strip()
            
            # Author is before the quoted title
            author_text = before_quote.strip()
            author_text = clean_latex_formatting(author_text)
            author_text = re.sub(r'~', ' ', author_text)
            author = author_text.strip(' ,.')
            
            # After title: \textit{Journal}, vol. X, no. Y, pp. XXX-YYY, Year
            # Look for \textit{Journal} or plain text journal
            journal_match = re.search(r'\\textit\{([^}]+)\}', after_quote)
            if journal_match:
                journal_or_note = journal_match.group(1).strip(' .')
                after_journal = after_quote[journal_match.end():]
            else:
                # Plain text journal at start of after_quote
                after_journal = after_quote
                # Try to find journal name (ends with comma before vol.)
                journal_end = re.search(r'^,?\s*([^,]+),\s*vol\.', after_quote, re.I)
                if journal_end:
                    journal_or_note = journal_end.group(1).strip()
                    after_journal = after_quote[journal_end.end() - 4:]  # keep "vol."
            
            # Extract vol., no., pp., year from after_journal
            vol_match = re.search(r'vol\.?\s*(\d+)', after_journal, re.I)
            if vol_match and 'volume' not in fields:
                fields['volume'] = vol_match.group(1)
            
            no_match = re.search(r'no\.?\s*(\d+)', after_journal, re.I)
            if no_match and 'number' not in fields:
                fields['number'] = no_match.group(1)
            
            pages_match = re.search(r'pp?\.?\s*(\d+[-–]\d+)', after_journal, re.I)
            if pages_match and 'pages' not in fields:
                fields['pages'] = pages_match.group(1).replace('–', '--')
            
            year_match = re.search(r'\b(19\d{2}|20\d{2})\b', after_journal)
            if year_match and 'year' not in fields:
                fields['year'] = year_match.group(1)

    # --- Strategy A1.25: Cambridge/JFM format with custom macros ---
    # Format: "\au{Author} \yr{Year} \at{Title}. \jt{Journal} \bvol{Vol}~(Num), \pg{Pages}"
    # Key: Uses \au{}, \yr{}, \at{}, \jt{}, \bvol{}, \pg{} macros
    if not title and not author:
        # Check for JFM macros
        has_au = bool(re.search(r'\\au\{', raw_content))
        has_jt = bool(re.search(r'\\jt\{', raw_content))
        has_yr = bool(re.search(r'\\yr\{', raw_content))
        
        if has_au or (has_jt and has_yr):
            # Extract authors from \au{...}
            au_matches = re.findall(r'\\au\{([^}]+)\}', raw_content)
            if au_matches:
                # Clean and join authors
                authors_clean = [a.strip() for a in au_matches]
                author = ', '.join(authors_clean)
            
            # Extract year from \yr{...}
            yr_match = re.search(r'\\yr\{(\d{4})[^}]*\}', raw_content)
            if yr_match and 'year' not in fields:
                fields['year'] = yr_match.group(1)
            
            # Extract title from \at{...}
            at_match = re.search(r'\\at\{([^}]+)\}', raw_content)
            if at_match:
                title = at_match.group(1).strip(' ,.')
            
            # Extract journal from \jt{...}
            jt_match = re.search(r'\\jt\{([^}]+)\}', raw_content)
            if jt_match:
                journal_or_note = jt_match.group(1).strip()
            
            # Extract volume from \bvol{...}
            bvol_match = re.search(r'\\bvol\{(\d+)\}', raw_content)
            if bvol_match and 'volume' not in fields:
                fields['volume'] = bvol_match.group(1)
            
            # Extract number from ~(Num) after volume
            num_match = re.search(r'~\((\d+)\)', raw_content)
            if num_match and 'number' not in fields:
                fields['number'] = num_match.group(1)
            
            # Extract pages from \pg{...}
            pg_match = re.search(r'\\pg\{([^}]+)\}', raw_content)
            if pg_match and 'pages' not in fields:
                pages_text = pg_match.group(1).strip()
                # Clean "pp. XX--YY" format
                pages_clean = re.sub(r'^pp?\.\s*', '', pages_text)
                pages_clean = pages_clean.replace('–', '--').strip(' .')
                fields['pages'] = pages_clean
            
            # If no title found via \at{}, try plain text between year and journal
            if not title and has_jt and has_yr:
                yr_end = yr_match.end() if yr_match else 0
                jt_start = jt_match.start() if jt_match else len(raw_content)
                if yr_end > 0 and jt_start > yr_end:
                    title_text = raw_content[yr_end:jt_start]
                    title_text = clean_latex_formatting(title_text)
                    title = title_text.strip(' ,.')

    # --- Strategy A1.28: HEP physics comma-separated format ---
    # Format: "Author, Title, Journal Vol (Year) Pages, [http://arxiv.org/abs/XXXX arXiv:XXXX]"
    # Key: arXiv URL in brackets at end, comma-separated fields, NO \textit{}
    if not title and not author:
        # Check for arXiv URL pattern: [http://arxiv.org/abs/...] or http://arxiv.org/abs/...
        arxiv_url_match = re.search(r'\[?https?://arxiv\.org/abs/([^\s\]]+)\s*(?:arXiv:)?([^\]\s]+)?\]?', raw_content, re.I)
        # Also check for simple [arXiv:XXXX] pattern
        arxiv_bracket = re.search(r'\[\s*(?:\\href\{[^}]+\}\{)?(?:\\ttfamily\s*)?arXiv[:\s]*([a-z-]+/\d+|\d+\.\d+)[^\]]*\]', raw_content, re.I)
        
        has_arxiv = arxiv_url_match or arxiv_bracket
        has_no_textit = not re.search(r'\\textit\{', raw_content)
        has_journal_pattern = re.search(r'(?:Phys\.|JHEP|Commun\.|Nucl\.|Adv\.|Math\.|Rev\.|Lett\.|J\.)\s+[A-Z]?[a-z\.]*\s*\d+', raw_content)
        
        if has_arxiv and has_no_textit and has_journal_pattern:
            # Extract arXiv ID
            if arxiv_url_match:
                eprint = arxiv_url_match.group(1) or arxiv_url_match.group(2)
                if eprint and 'eprint' not in fields:
                    # Clean eprint of trailing characters
                    eprint = re.sub(r'[,\]\}\s]+$', '', eprint)
                    fields['eprint'] = eprint.strip()
            elif arxiv_bracket:
                if 'eprint' not in fields:
                    fields['eprint'] = arxiv_bracket.group(1).strip()
            
            if 'eprint' in fields and 'archivePrefix' not in fields:
                fields['archivePrefix'] = 'arXiv'
            
            # Remove arXiv part from content for parsing
            content_clean = raw_content
            if arxiv_url_match:
                # Remove from arXiv URL to end
                content_clean = raw_content[:arxiv_url_match.start()].strip(' ,[]')
            elif arxiv_bracket:
                content_clean = raw_content[:arxiv_bracket.start()].strip(' ,[]')
            
            # Content now: "Author, Title, Journal Vol (Year) Pages"
            # Find journal pattern: "Journal Vol (Year)" or "Journal Vol, Pages (Year)"
            journal_vol_year = re.search(
                r'((?:Phys\.|JHEP|Commun\.|Nucl\.|Adv\.|Math\.|Rev\.|Lett\.|J\.\s*)[A-Za-z\.\s]+)\s+'
                r'(?:(?:B|D|A)?(\d+))\s*'  # Volume (with optional letter prefix)
                r'(?:\((\d{4})\))?'  # Year in parens (optional here)
                r'(?:\s*,?\s*(?:no\.\s*\d+\s*,?\s*)?)?'  # Optional number
                r'(\d+[-–]\d+|\d+)?'  # Pages
                r'(?:\s*\((\d{4})\))?',  # Year (alternative position)
                content_clean, re.I)
            
            if journal_vol_year:
                journal_or_note = journal_vol_year.group(1).strip(' .')
                if journal_vol_year.group(2) and 'volume' not in fields:
                    fields['volume'] = journal_vol_year.group(2)
                year_val = journal_vol_year.group(3) or journal_vol_year.group(5)
                if year_val and 'year' not in fields:
                    fields['year'] = year_val
                if journal_vol_year.group(4) and 'pages' not in fields:
                    fields['pages'] = journal_vol_year.group(4).replace('–', '--')
                
                # Content before journal pattern: "Author, Title"
                before_journal = content_clean[:journal_vol_year.start()].strip(' ,')
                
                # Split by comma to find author/title
                # Authors typically at beginning, title before journal
                # Find patterns like "A. Name, B. Name, and C. Name, Title here"
                # Look for last author (before "and" or before title-like text)
                
                # First try to find title after last author
                # Authors have patterns like "X. Y. Name" or "Name, X." 
                and_pattern = re.search(r'\band\s+([A-Z]\.?\s*)+[A-Za-z-]+,', before_journal)
                if and_pattern:
                    # Content after "and Author," is title
                    author = before_journal[:and_pattern.end()].strip(' ,')
                    title = before_journal[and_pattern.end():].strip(' ,')
                else:
                    # Try splitting by comma - last significant comma before title
                    parts = before_journal.split(',')
                    if len(parts) >= 2:
                        # Check each part - if it looks like author, accumulate
                        # If it looks like title (longer, no initials pattern), stop
                        author_parts = []
                        title_parts = []
                        in_title = False
                        
                        for i, part in enumerate(parts):
                            part = part.strip()
                            has_author_pattern = bool(re.search(r'\b[A-Z]\.\s*([A-Z]\.?\s*)?[A-Za-z-]+|[A-Za-z-]+,\s*[A-Z]\.', part))
                            is_short = len(part) < 80
                            starts_with_upper = part and part[0].isupper()
                            
                            if not in_title and has_author_pattern and is_short:
                                author_parts.append(part)
                            else:
                                # Likely title
                                in_title = True
                                title_parts.append(part)
                        
                        if author_parts:
                            author = ', '.join(author_parts)
                        if title_parts:
                            title = ', '.join(title_parts)
            
            # Extract URL if present
            url_match = re.search(r'https?://arxiv\.org/abs/[^\s\]\}]+', raw_content)
            if url_match and 'url' not in fields:
                fields['url'] = url_match.group(0).rstrip(',]')

    # --- Strategy A1.24: INSPIRE/JHEP format with \href{}{} links ---
    # Format: "Author, \textit{Title}, \href{DOI_URL}{Journal Vol, Pages (Year)}, [\href{ARXIV_URL}{\ttfamily arXiv:XXXX}]"
    # Key: Uses \href{url}{text} for DOI and arXiv links
    if not title and not author:
        # Check for \href{} pattern which indicates INSPIRE format
        has_href = bool(re.search(r'\\href\{', raw_content))
        has_textit = bool(re.search(r'\\textit\{', raw_content))
        
        if has_href and has_textit:
            # Extract DOI from href
            doi_match = re.search(r'\\href\{https?://(?:dx\.)?doi\.org/([^}]+)\}', raw_content)
            if doi_match and 'doi' not in fields:
                fields['doi'] = doi_match.group(1).strip()
                if 'url' not in fields:
                    fields['url'] = f"http://dx.doi.org/{doi_match.group(1).strip()}"
            
            # Extract arXiv from [\href{...}{\ttfamily arXiv:XXXX}] or similar
            arxiv_href = re.search(r'\\href\{[^}]*arxiv\.org/abs/([^}]+)\}\{[^}]*arXiv:([^}]+)\}', raw_content, re.I)
            if arxiv_href:
                eprint = arxiv_href.group(2).strip().lstrip(':')
                if 'eprint' not in fields:
                    fields['eprint'] = eprint
                if 'archivePrefix' not in fields:
                    fields['archivePrefix'] = 'arXiv'
            else:
                # Try simpler arXiv pattern
                arxiv_simple = re.search(r'arXiv:([a-z-]+/\d+|\d+\.\d+)', raw_content, re.I)
                if arxiv_simple:
                    if 'eprint' not in fields:
                        fields['eprint'] = arxiv_simple.group(1)
                    if 'archivePrefix' not in fields:
                        fields['archivePrefix'] = 'arXiv'
            
            # Extract title from \textit{}
            textit_match = re.search(r'\\textit\{([^}]+)\}', raw_content)
            if textit_match:
                title = textit_match.group(1).strip(' ,.')
                before_title = raw_content[:textit_match.start()]
                
                # Author is before \textit{title}
                author_text = before_title.strip()
                author_text = clean_latex_formatting(author_text)
                author_text = re.sub(r'~', ' ', author_text)
                author = author_text.strip(' ,.')
                
                # Extract journal info from \href{DOI}{Journal \bfseries Vol, Pages (Year)}
                journal_href = re.search(r'\\href\{[^}]+\}\{([^}]+)\}', raw_content[textit_match.end():])
                if journal_href:
                    journal_text = journal_href.group(1)
                    # Clean \bfseries and extract components
                    journal_text_clean = re.sub(r'\\bfseries\s*', '', journal_text)
                    
                    # Pattern: "Journal Vol, Pages (Year)" or "Journal Vol (Year)"
                    vol_match = re.search(r'(\d+)', journal_text_clean)
                    year_match = re.search(r'\((\d{4})\)', journal_text_clean)
                    pages_match = re.search(r'(\d+[-–]\d+|\d{5,})', journal_text_clean)
                    
                    if vol_match and 'volume' not in fields:
                        fields['volume'] = vol_match.group(1)
                    if year_match and 'year' not in fields:
                        fields['year'] = year_match.group(1)
                    if pages_match and 'pages' not in fields:
                        fields['pages'] = pages_match.group(1).replace('–', '--')
                    
                    # Journal name is before volume
                    journal_name_match = re.match(r'([A-Za-z\.\s]+)', journal_text_clean)
                    if journal_name_match:
                        journal_or_note = journal_name_match.group(1).strip()

    # --- Strategy A1.12: Math/Physics format with \textit{Journal} ---
    # Format: "Author1, Author2, Title here, \textit{Journal Name} \textbf{Vol} (Year), Pages"
    # Key: Authors have tilde-connected initials like D.~V.~Alekseevski
    # \textit{} or \emph{} contains JOURNAL (not title!)
    # Title is plain text between author list and \textit{}
    if not title and not author:
        # Check if has \textit{} or \emph{} for journal
        journal_match = re.search(r'\\textit\{([^}]+)\}|\\emph\{([^}]+)\}', raw_content)
        
        if journal_match:
            journal_name = (journal_match.group(1) or journal_match.group(2)).strip()
            before_journal = raw_content[:journal_match.start()]
            
            # Check if this looks like math/physics format (has tilde-connected names)
            # Pattern: initials with tildes or periods like D.~V. or D. V. or A.~B.~Smith
            has_tilde_names = bool(re.search(r'[A-Z]\.~[A-Z]|[A-Z]\.\s+[A-Z]\.~', before_journal))
            has_initial_pattern = bool(re.search(r'[A-Z]\.\s*[A-Z]\.', before_journal))
            
            if has_tilde_names or has_initial_pattern:
                # Clean content before journal
                before_clean = clean_latex_formatting(before_journal)
                before_clean = re.sub(r'~', ' ', before_clean)  # Replace tildes with spaces
                before_clean = before_clean.strip(' ,')
                
                # Split by commas to find author/title boundary
                segments = [s.strip() for s in before_clean.split(',') if s.strip()]
                
                if len(segments) >= 2:
                    # Heuristic: Authors are segments with name patterns
                    # Title starts when we see a long segment without name pattern
                    author_segments = []
                    title_start_idx = 0
                    
                    for i, seg in enumerate(segments):
                        seg_stripped = seg.strip()
                        
                        # Check if segment looks like author name
                        # Patterns: "D. V. Alekseevski", "J.-B. Butruille", "A. Gray", etc.
                        is_author = (
                            # Has initial pattern at start: "D. V." or "J.-B."
                            bool(re.match(r'^[A-Z]\.[\s-]*[A-Z]?\.?\s*[A-Z][a-z]', seg_stripped)) or
                            # Or is short name with initials: "A. Gray"
                            (len(seg_stripped) < 30 and bool(re.match(r'^[A-Z]\.\s*[A-Z][a-z]+', seg_stripped))) or
                            # Or ends with et al.
                            bool(re.search(r'et\s+al\.?$', seg_stripped, re.I))
                        )
                        
                        if is_author:
                            author_segments.append(seg_stripped)
                            title_start_idx = i + 1
                        else:
                            # Check if this is a long segment (likely title start)
                            if len(seg_stripped) > 30:
                                break
                            # Could still be a name like "Y. G. Nikonorov"
                            elif bool(re.match(r'^[A-Z]\.?\s+[A-Z]\.?\s*[A-Z][a-z]+', seg_stripped)):
                                author_segments.append(seg_stripped)
                                title_start_idx = i + 1
                            else:
                                break
                    
                    if author_segments:
                        author = ', '.join(author_segments)
                        
                        # Remaining segments are title
                        if title_start_idx < len(segments):
                            title = ', '.join(segments[title_start_idx:]).strip(' .,')
                        
                        # Journal from \textit{} or \emph{}
                        journal_or_note = journal_name.strip(' .,')
    
    # --- Strategy B: \emph{Title} hoặc \textit{Title} format ---
    if not title:
        # Tìm \emph{...} hoặc \textit{...}
        emph_match = re.search(r'\\emph\{([^}]+)\}', raw_content)
        if not emph_match:
            emph_match = re.search(r'\\textit\{([^}]+)\}', raw_content)
        
        if emph_match:
            title = emph_match.group(1).strip()
            
            # Author = phần trước \emph (clean LaTeX)
            author_part = raw_content[:emph_match.start()]
            author = clean_latex_formatting(author_part).strip(' .,')
            
            # Journal = phần sau \emph
            after_part = raw_content[emph_match.end():]
            # Xóa year, vol, pages đã extract
            after_clean = clean_latex_formatting(after_part).strip(' .,')
            # Lấy segment đầu tiên làm journal
            journal_match = re.match(r'^([A-Za-z][^,\d]*)', after_clean)
            if journal_match:
                journal_or_note = journal_match.group(1).strip(' .,')
    
    # --- Strategy C: {\em Title} or {\it Title} format (books/articles) ---
    if not title:
        # Try {\em ...} first, then {\it ...}
        em_match = re.search(r'\{\\em\s+([^}]+)\}', raw_content)
        if not em_match:
            em_match = re.search(r'\{\\it\s+([^}]+)\}', raw_content)
        
        if em_match:
            title = em_match.group(1).strip(' .')
            
            # Author = before {\em or {\it
            author_part = raw_content[:em_match.start()]
            author = clean_latex_formatting(author_part).strip(' .,')
            
            # After part may be Journal (for articles) or Publisher, Place (for books)
            after_part = raw_content[em_match.end():]
            after_clean = clean_latex_formatting(after_part).strip(' .,')
            
            # Check if it looks like a book format: "Publisher, Place, Year" or just "Publisher, Year"
            # Book publishers often have patterns like "Springer", "Cambridge University Press", etc.
            publisher_patterns = [
                r'\b(?:Press|Publishing|Verlag|Books?|Inc\.?|Ltd\.?)\b',
                r'\b(?:Springer|Elsevier|Wiley|Cambridge|Oxford|MIT|Academic|North-Holland|Hermann|Benjamin|Gordon|Pergamon)\b',
            ]
            is_book = any(re.search(p, after_clean, re.I) for p in publisher_patterns)
            
            if is_book and len(after_clean) > 3:
                # This is a book - extract publisher and address
                # Format: Publisher, Place, Year OR just Publisher, Year
                parts = [p.strip() for p in after_clean.split(',')]
                if len(parts) >= 2:
                    # First part is usually publisher
                    fields['publisher'] = parts[0]
                    # Check if second part looks like a place (city name)
                    if len(parts) >= 3 and not re.match(r'^\d{4}$', parts[1]):
                        fields['address'] = parts[1]
            elif len(after_clean) > 3:
                # This is an article - after part is journal
                journal_or_note = after_clean
    
    # --- Strategy C.5: {\\it\\color{darkblue}Title} format ---
    if not title:
        color_match = re.search(r'\{\\it\\color\{[^}]+\}([^}]+)\}', raw_content)
        if not color_match:
            color_match = re.search(r'\{\\it\s*\\color\{[^}]+\}\s*([^}]+)\}', raw_content)
        if color_match:
            title = color_match.group(1).strip(' .')
            
            # Author = before the color block
            author_part = raw_content[:color_match.start()]
            author = clean_latex_formatting(author_part).strip(' .,')
            
            # After part may contain journal/publisher
            after_part = raw_content[color_match.end():]
            after_clean = clean_latex_formatting(after_part).strip(' .,')
            if len(after_clean) > 3:
                journal_or_note = after_clean

    # --- Strategy D.2: Period-separated book format ---
    # Format: "AuthorName. Book Title, Publisher, Year" or "Author1, Author2. Title, Publisher Year"
    # Period separates author from title - common in book citations
    if not title and not author:
        content = clean_latex_formatting(raw_content)
        
        # Find the first period that looks like author-title separator
        # Pattern: Name followed by period, then capital letter starting title
        period_match = re.search(r'^([A-Z][^.]+(?:\.\s+[A-Z])?[^.]*)\.\s+([A-Z])', content)
        
        if period_match:
            author_part = period_match.group(1).strip()
            after_period = content[period_match.end()-1:].strip()  # Include the capital letter
            
            # Check if author_part looks like author names (not too long, has name patterns)
            # Author typically: FirstName LastName or First M. Last or multiple authors with comma/and
            if len(author_part) < 100 and re.search(r'[A-Z][a-z]+\s+[A-Z]', author_part):
                author = author_part
                
                # After period: Title, Publisher, Year
                # Split by comma to separate title from publisher
                after_parts = [p.strip() for p in after_period.split(',')]
                
                if len(after_parts) >= 1:
                    # First part(s) are title until we hit publisher keywords
                    title_parts = []
                    publisher_idx = len(after_parts)
                    
                    publisher_keywords = [
                        r'\b(?:Press|Publishing|Publisher|Verlag|Books?|Inc\.?|Ltd\.?|Co\.?)\b',
                        r'\b(?:Springer|Elsevier|Wiley|Cambridge|Oxford|MIT|Academic|Manning|Apress|Packt)\b',
                        r'\b(?:IEEE|ACM|SIAM|AMS)\b',
                        r'\b\d{4}\b',  # Year
                    ]
                    
                    for i, part in enumerate(after_parts):
                        is_publisher = False
                        for pattern in publisher_keywords:
                            if re.search(pattern, part, re.I):
                                is_publisher = True
                                break
                        
                        if is_publisher:
                            publisher_idx = i
                            break
                        else:
                            title_parts.append(part)
                    
                    if title_parts:
                        title = ', '.join(title_parts).strip(' .,')
                        
                        # Publisher from remaining parts
                        if publisher_idx < len(after_parts):
                            pub_parts = after_parts[publisher_idx:]
                            # Remove year from publisher
                            pub_text = ', '.join(pub_parts)
                            pub_clean = re.sub(r',?\s*\d{4}.*$', '', pub_text)
                            if pub_clean.strip():
                                fields['publisher'] = pub_clean.strip(' .,')

    # --- Strategy D.3: Comma-separated plain text format ---
    # Format: "Author, Title, Journal, Vol (Year), Pages" or "Author, Title, Journal Vol (Year), Pages"
    # Common in math/physics papers where all fields separated by commas
    if not title and not author:
        content = clean_latex_formatting(raw_content)
        
        # Check if this looks like comma-separated format
        # Pattern: Name Initial., Title text, Journal abbrev., Vol (Year), Pages
        # or: Name Initial., Title text, Journal abbrev. Vol (Year), Pages
        
        # Split by commas
        parts = [p.strip() for p in content.split(',')]
        
        if len(parts) >= 3:
            # Try to identify author - first part(s) that look like names
            # Name patterns: "R. E. Caflisch", "H. Grad", "T.-P. Liu, S.-H. Yu"
            author_parts = []
            title_start_idx = 0
            
            for i, part in enumerate(parts):
                # Check if this part looks like an author name
                # Author name patterns: starts with initials or has "Last, First" pattern
                is_author = False
                
                # Check for "R. E. Caflisch" pattern (Initial + MidInitial + LastName)
                if re.match(r'^[A-Z]\.\s*[A-Z]?\.\s*[A-Z][a-z\'-]+$', part.strip()):
                    is_author = True
                # Check for initial patterns like "R. E." or "T.-P."
                elif re.match(r'^[A-Z]\.\s*[A-Z]\.', part.strip()):
                    is_author = True
                # Check for LastName FirstInitial pattern  
                elif re.match(r'^[A-Z][a-z\'-]+\s+[A-Z]\.', part.strip()):
                    is_author = True
                # Check for "First Last" where first starts with capital
                elif re.match(r'^[A-Z][a-z]+\s+[A-Z][a-z\'-]+$', part.strip()):
                    is_author = True
                # Check for initials only pattern "S.-H. Yu"
                elif re.match(r'^[A-Z]\.-?[A-Z]?\.\s*[A-Z][a-z]+', part.strip()):
                    is_author = True
                # Check for "H. Grad" pattern (Single Initial + LastName)
                elif re.match(r'^[A-Z]\.\s*[A-Z][a-z\'-]+$', part.strip()):
                    is_author = True
                    
                if is_author and i < 3:  # Authors typically in first 2-3 parts
                    author_parts.append(part.strip())
                    title_start_idx = i + 1
                else:
                    break
            
            # If we found author parts, extract title
            if author_parts and title_start_idx < len(parts):
                author = ', '.join(author_parts)
                
                # Find title - typically the longest segment that looks like a title
                # Title usually comes before journal abbreviation (short text with period or volume number)
                remaining_parts = parts[title_start_idx:]
                
                # Look for journal abbreviation patterns (short text, often ending with period, before volume)
                journal_patterns = [
                    r'\b(?:J\.|Phys\.|Math\.|Comm\.|Ann\.|Proc\.|Trans\.|Bull\.|Rev\.|Acad\.|Sci\.)',
                    r'\b(?:Commun\.|Indiana|Illinois|Pacific|Mosc\.|Funct\.|Anal\.|Appl\.)',
                    r'\b(?:Lecture Notes|Springer|Academic Press|Oxford|Cambridge)',
                ]
                
                title_parts = []
                journal_start_idx = len(remaining_parts)
                
                for i, part in enumerate(remaining_parts):
                    # Check if this part looks like a journal name
                    is_journal = False
                    for pattern in journal_patterns:
                        if re.search(pattern, part, re.I):
                            is_journal = True
                            break
                    
                    # Also check if part contains volume number pattern
                    if re.search(r'\b\d{1,3}\s*\(\d{4}\)', part) or re.search(r'\b\d{1,3}\s*$', part):
                        is_journal = True
                    
                    if is_journal:
                        journal_start_idx = i
                        break
                    else:
                        title_parts.append(part)
                
                if title_parts:
                    title = ', '.join(title_parts).strip(' .,')
                    
                    # Extract journal from remaining parts
                    if journal_start_idx < len(remaining_parts):
                        journal_parts = remaining_parts[journal_start_idx:]
                        # First journal part - extract name before volume
                        if journal_parts:
                            journal_text = journal_parts[0]
                            # Remove volume number from journal name
                            journal_clean = re.sub(r'\s*\d{1,3}\s*(\(\d{4}\))?.*$', '', journal_text)
                            if journal_clean.strip():
                                journal_or_note = journal_clean.strip(' .,')

    # --- Strategy D: ``Title'' quoted format ---
    if not title:
        quote_match = re.search(r"``([^']+)''", raw_content)
        if not quote_match:
            quote_match = re.search(r'"([^"]+)"', raw_content)
        
        if quote_match:
            title = quote_match.group(1).strip()
            
            # Author = trước quote
            author_part = raw_content[:quote_match.start()]
            author = clean_latex_formatting(author_part).strip(' .,')
            
            # Journal = sau quote, thường trong {\em ...}
            after_part = raw_content[quote_match.end():]
            em_match = re.search(r'\{\\em\s+([^}]+)\}', after_part)
            if em_match:
                journal_or_note = em_match.group(1).strip(' .,')
    
    # --- Strategy D.5: Inline plain text format ---
    # Format: "AuthorLastName FirstInit and Author2 Year Title Journal Vol Pages"
    # Common in physics plain bibitems
    if not title and not author:
        content = clean_latex_formatting(raw_content)
        
        # Pattern: Authors Year Title Journal...
        # Year is 4 digits, usually appears after author names
        year_match = re.search(r'\b(19\d{2}|20\d{2})\b', content)
        
        if year_match:
            before_year = content[:year_match.start()].strip()
            after_year = content[year_match.end():].strip()
            
            # Before year should be author(s) - check if looks like names
            # Pattern: Name1 Initial and Name2 Initial
            if re.search(r'[A-Z][a-z]+\s+[A-Z]', before_year):
                author = before_year.rstrip(' ,')
                
                # After year contains Title + Journal + Vol + Pages
                # Try to find journal patterns to split title from journal
                journal_patterns = [
                    r'\b(?:Ann\.\s*(?:of\s*)?Phys\.)', r'\bPhys\.\s*Rev\.', r'\bPhys\.\s*Lett\.',
                    r'\bJ\.\s*Phys\.', r'\bJ\.\s*Math\.\s*Phys\.', r'\bNonlinearity\b',
                    r'\bAm\.\s*J\.\s*Phys\.', r'\bSIGMA\b', r'\bProg\.\s*Math\.',
                    r'\bMSJ\s*Memoirs\b', r'\bPhys\.\s*Scr\.',
                ]
                
                journal_pos = -1
                journal_name = None
                for pattern in journal_patterns:
                    jmatch = re.search(pattern, after_year, re.I)
                    if jmatch:
                        journal_pos = jmatch.start()
                        # Extract journal name up to volume number
                        rest = after_year[jmatch.start():]
                        vol_match = re.search(r'\s+\d+\s*(?:\(|\,|pp\.)', rest)
                        if vol_match:
                            journal_name = rest[:vol_match.start()].strip()
                        else:
                            journal_name = re.sub(r'\s+\d+.*$', '', rest).strip()
                        break
                
                if journal_pos > 0:
                    title = after_year[:journal_pos].strip(' ,')
                    if journal_name:
                        journal_or_note = journal_name
                elif after_year:
                    # No journal found, treat all as title
                    title = after_year.strip(' ,')
    
    # --- Strategy E: Plain text fallback ---
    # Format: "Author1, Author2, Title, Journal Vol (Year) Pages"
    if not author or not title:
        content = clean_latex_formatting(raw_content)
        
        # Common journal name patterns
        journal_patterns = [
            r'\bNature\b', r'\bScience\b', r'\bPhys\.?\s*Rev\.?', r'\bPhys\.?\s*Lett\.?',
            r'\bJ\.?\s*Phys\.?', r'\bJ\.?\s*Chem\.?', r'\bJ\.?\s*Math\.?',
            r'\bActa\b', r'\bTrans\.?\s*', r'\bProc\.?\s*', r'\bAnn\.?\s*',
            r'\bAppl\.?\s*Phys\.?', r'\bChem\.?\s*Phys\.?', r'\bMat\.?\s*Res\.?',
            r'\bMater\.?\s*', r'\bSolid\s*State', r'\bSupercond\.?',
            r'\bRev\.?\s*Mod\.?', r'\bNucl\.?\s*', r'\bAIChE\b', r'\bAIME\b',
            r'\bIEEE\b', r'\bACM\b', r'\bSIAM\b', r'\bCommun\.?\s*',
        ]
        
        # Try to find journal position
        journal_pos = -1
        for pattern in journal_patterns:
            match = re.search(pattern, content, re.I)
            if match:
                # Journal thường đứng sau title, tìm dấu phẩy trước journal
                pos = match.start()
                # Tìm dấu phẩy cuối cùng trước journal position
                comma_before = content.rfind(',', 0, pos)
                if comma_before > 0:
                    journal_pos = comma_before
                    break
        
        if journal_pos > 0:
            # Phần trước journal_pos chứa Author + Title
            before_journal = content[:journal_pos].strip()
            after_journal = content[journal_pos+1:].strip()
            
            # Tách Author và Title từ before_journal
            # Pattern recognition for author names
            parts = before_journal.split(', ')
            
            author_parts = []
            title_start_idx = -1
            
            for i, part in enumerate(parts):
                part_stripped = part.strip()
                
                # Author name patterns:
                # 1. "F. LastName" or "F. M. LastName" - initial(s) + name
                # 2. "LastName" alone (short, capitalized)
                # 3. Contains "and" connecting names
                # Must be relatively short (< 50 chars)
                
                # Check if this looks like an author name
                is_author_pattern = (
                    # Initial + Name pattern: "A. Name", "A. B. Name", "A.B. Name"
                    bool(re.match(r'^[A-Z]\.(\s*[A-Z]\.)*\s*~?[A-Z][a-zäöüéèà\'\-]+', part_stripped)) or
                    # Name + Initial pattern: "Name A.", "Name A. B."  
                    bool(re.match(r'^[A-Z][a-zäöüéèà\'\-]+\s+[A-Z]\.$', part_stripped)) or
                    # Full Name pattern: "FirstName LastName" (Two capitalized words)
                    bool(re.match(r'^[A-Z][a-zäöüéèà\'\-]+\s+[A-Z][a-zäöüéèà\'\-]+$', part_stripped)) or
                    # Just a short capitalized name (likely last name alone)
                    bool(re.match(r'^[A-Z][a-zäöüéèà\'\-]+$', part_stripped)) or
                    # Contains "and" between names
                    bool(re.search(r'^[A-Z][a-z\.]+\s+and\s+[A-Z]', part_stripped)) or
                    # et al pattern
                    'et al' in part_stripped.lower()
                )
                
                # Additional check: part should be short (names are short)
                is_short = len(part_stripped) < 50
                
                # Title indicator: long text, or contains academic/descriptive words
                title_words = ['measurement', 'physical', 'properties', 'observation', 
                              'enhanced', 'electric', 'dipole', 'nuclear', 'structure',
                              'energy', 'spin', 'states', 'levels', 'band', 'transition',
                              'possible', 'deformed', 'octupole', 'shape', 'crystal']
                looks_like_title = (
                    len(part_stripped) > 50 or
                    any(w in part_stripped.lower() for w in title_words)
                )
                
                if is_author_pattern and is_short and not looks_like_title:
                    author_parts.append(part_stripped)
                else:
                    # This is where title starts
                    title_start_idx = i
                    break
            
            if author_parts and title_start_idx > 0:
                author = ', '.join(author_parts).strip()
                title = ', '.join(parts[title_start_idx:]).strip()
            elif author_parts:
                author = ', '.join(author_parts).strip()
                title = before_journal
            else:
                title = before_journal
            
            # Set journal
            if after_journal and 'journal' not in fields:
                # Clean journal - remove vol/year/pages
                journal_clean = re.sub(r'\d+\s*\(\d{4}\).*', '', after_journal).strip(' ,')
                if journal_clean:
                    journal_or_note = journal_clean
        
        else:
            # No journal detected - use simple split
            if not author:
                # Tìm "and" hoặc "&" để xác định end of author list
                # GREEDY match để lấy tất cả tác giả, bao gồm cả "and LastAuthor"
                # Pattern: Authors list ending with "and LastName" (with initials), then comma + Title
                # LastAuthor format: "and A. B. LastName" hoặc "and A. LastName"
                and_match = re.search(
                    r'^(.+\s+and\s+[A-Z](?:\.\s*[A-Z])*\.?\s*~?[A-Za-zäöüéèà\'\-]+(?:\s+[A-Z][a-zäöüéèà\'\-]+)?)\s*[,\.]\s*([A-Z])',
                    content
                )
                if and_match:
                    author = and_match.group(1).strip()
                    remaining = content[and_match.start(2):]
                else:
                    # Fallback: đến dấu phẩy thứ 2 (sau 2 tác giả)
                    parts = content.split(', ')
                    if len(parts) >= 3:
                        author = ', '.join(parts[:2]).strip()
                        remaining = ', '.join(parts[2:])
                    elif len(parts) >= 2:
                        author = parts[0].strip()
                        remaining = ', '.join(parts[1:])
                    else:
                        remaining = content
            else:
                remaining = content
            
            if title is None and remaining:
                # Title = segment đầu của remaining (đến journal hoặc year)
                year_match = re.search(r',\s*\d{4}\b', remaining)
                if year_match:
                    title = remaining[:year_match.start()].strip(' ,')
                else:
                    comma_pos = remaining.find(',')
                    if comma_pos > 0:
                        title = remaining[:comma_pos].strip()
                    else:
                        title = remaining.strip()
    
    # --- Strategy FINAL: Use multi-pass general parsing as fallback ---
    # If no author or journal was extracted, use the general multipass approach
    if not author or not journal_or_note:
        parsed = multipass_parse_bibitem(raw_content)
        
        # Use parsed fields if not already extracted
        if not author and parsed['author']:
            author = parsed['author']
        if not journal_or_note and parsed['journal']:
            journal_or_note = parsed['journal']
        if not title and parsed.get('title'):
            title = parsed['title']
        
        # Also use metadata fields if not already in fields dict
        if parsed['year'] and 'year' not in fields:
            fields['year'] = parsed['year']
        if parsed['volume'] and 'volume' not in fields:
            fields['volume'] = parsed['volume']
        if parsed['pages'] and 'pages' not in fields:
            fields['pages'] = parsed['pages']
        if parsed['doi'] and 'doi' not in fields:
            fields['doi'] = parsed['doi']
        if parsed['url'] and 'url' not in fields:
            fields['url'] = parsed['url']
        if parsed['eprint'] and 'eprint' not in fields:
            fields['eprint'] = parsed['eprint']
            if 'archivePrefix' not in fields:
                fields['archivePrefix'] = 'arXiv'
        
        # For physics format without title (Author, Journal Vol, Pages (Year))
        # If we have journal but no title, set title to empty
        if journal_or_note and not title:
            title = ''
    
    # === 4. SET FIELDS (with validation) ===
    
    # --- 4a. Validate and fix author ---
    if author:
        # Author should not contain numbers (except single digits in initials like "John D. 3rd")
        # or URLs or DOIs
        author_clean = author
        # Remove any year that might have leaked into author
        author_clean = re.sub(r'\s+\d{4}\s*$', '', author_clean).strip(' ,.')
        # If author still contains suspicious patterns, strip them
        if re.search(r'https?://', author_clean) or re.search(r'\b10\.\d{4,}/', author_clean):
            author_clean = re.sub(r'https?://[^\s,]+', '', author_clean)
            author_clean = re.sub(r'\b10\.\d{4,}/[^\s,]+', '', author_clean)
            author_clean = author_clean.strip(' ,.')
        if author_clean and len(author_clean) > 2:
            fields['author'] = author_clean
    
    # --- 4b. Validate title and check if it's actually a journal ---
    # Common error: if no title was extracted but we have journal-like text in title field
    journal_patterns = [
        r'\bJ\.\s*Phys\.', r'\bPhys\.\s*Rev\.', r'\bPhys\.\s*Lett\.', 
        r'\bNucl\.\s*Phys\.', r'\bAppl\.\s*Phys\.', r'\bEur\.\s*Phys\.', 
        r'\bJ\.\s*Chem\.', r'\bJ\.\s*Math\.', r'\bAnn\.\s*Phys\.', 
        r'\bMod\.\s*Phys\.', r'\bRev\.\s*Mod\.', r'\bAstrophys\.\s*J\.',
        r'\bMNRAS\b', r'\bJHEP\b', r'\bPRD\b', r'\bPRL\b', r'\bNature\b', r'\bScience\b',
        r'\bJ\.\s*Opt\.', r'\bOpt\.\s*Express\b', r'\bOpt\.\s*Lett\.', r'\bOpt\.\s*Eng\.',
        r'\bSci\.\s*Rep\.', r'\bCommun\.\s*Math\.', r'\bAdv\.\s*Theor\.', r'\bClass\.\s*Quant\.',
        r'\bAt\.\s*Data\b', r'\bData\s*Tables\b', r'\bChin\.\s*Phys\.'
    ]
    
    if title is not None:
        title_clean = title.strip()
        
        # Check if title looks like a journal name
        is_journal_like = any(re.search(p, title_clean, re.I) for p in journal_patterns)
        
        if is_journal_like and not journal_or_note:
            # This "title" is actually a journal - no title in this bibitem format
            journal_or_note = title_clean
            title = ''  # Empty title, not None
        elif title_clean:
            # Validate title doesn't contain numbers/URLs that indicate parsing error
            if not re.search(r'https?://', title_clean) and not re.search(r'\b10\.\d{4,}/', title_clean):
                fields['title'] = title_clean
            else:
                # Title has URLs - something went wrong, try to clean
                title_clean = re.sub(r'https?://[^\s,]+', '', title_clean)
                title_clean = re.sub(r'\b10\.\d{4,}/[^\s,]+', '', title_clean)
                title_clean = title_clean.strip(' ,.')
                if title_clean:
                    fields['title'] = title_clean
        else:
            # Empty title is valid for some formats
            fields['title'] = ''
    
    # --- 4c. Set journal/note ---
    if journal_or_note and len(journal_or_note) > 3 and 'journal' not in fields:
        # Xác định là journal hay note - expanded keywords
        journal_keywords = [
            'journal', 'trans.', 'lett.', 'rev.', 'phys.', 'math.', 'proc.',
            'nature', 'science', 'chem.', 'acta', 'soc.', 'j.', 'entropy',
            'mater.', 'metall.', 'metals', 'appl.', 'theor.', 'anal.',
            'computational', 'physical', 'chemical', 'biological',
            'annals', 'bulletin', 'financ', 'econ', 'stochast'  # finance/econ journals
        ]
        if any(x in journal_or_note.lower() for x in journal_keywords):
            fields['journal'] = journal_or_note
        else:
            fields['note'] = journal_or_note
    
    # === 5. DETERMINE ENTRY TYPE ===
    entry_type = 'misc'
    content_lower = raw_content.lower()
    
    # Ph.D./Master's thesis
    if 'thesis' in content_lower or 'dissertation' in content_lower:
        if 'ph.d' in content_lower or 'phd' in content_lower or 'doctoral' in content_lower:
            entry_type = 'phdthesis'
        else:
            entry_type = 'mastersthesis'
    # Book
    elif 'publisher' in fields or any(x in content_lower for x in ['springer', 'wiley', 'elsevier', 'cambridge university press', 'oxford university press']):
        entry_type = 'book'
    # InProceedings
    elif any(x in content_lower for x in ['proceedings', 'conference', 'symposium', 'workshop', 'proc.', 'in {\\em']):
        entry_type = 'inproceedings'
        if journal_or_note and 'booktitle' not in fields:
            fields['booktitle'] = fields.pop('journal', journal_or_note)
    # Article
    elif 'journal' in fields or 'volume' in fields or any(x in content_lower for x in ['journal', 'trans.', 'lett.', 'rev.']):
        entry_type = 'article'
    # Preprint
    elif 'eprint' in fields or 'arxiv' in content_lower or 'preprint' in content_lower:
        entry_type = 'article'
        if 'journal' not in fields:
            # Create journal with arXiv ID if available
            if 'eprint' in fields:
                arxiv_id = fields['eprint']
                fields['journal'] = f'arXiv preprint arXiv:{arxiv_id}'
            else:
                fields['journal'] = 'arXiv preprint'
    
    # === 6. CLEAN AND FORMAT ===
    final_fields = {}
    for k, v in fields.items():
        if v:
            v = str(v).strip(' .,;')
            
            # === Clean REVTeX artifacts ===
            # Remove field type words that accidentally got included (e.g., "authorM. Name" -> "M. Name")
            v = re.sub(r'\bauthor\s*', '', v, flags=re.I)
            v = re.sub(r'\bjournal\s*', '', v, flags=re.I)
            v = re.sub(r'\btitle\s*', '', v, flags=re.I)
            v = re.sub(r'\bvolume\s*', '', v, flags=re.I)
            v = re.sub(r'\bpages\s*', '', v, flags=re.I)
            v = re.sub(r'\byear\s*', '', v, flags=re.I)
            v = re.sub(r'\bbooktitle\s*', '', v, flags=re.I)
            v = re.sub(r'\bpublisher\s*', '', v, flags=re.I)
            v = re.sub(r'\baddress\s*', '', v, flags=re.I)
            v = re.sub(r'\beditor\s*', '', v, flags=re.I)
            # Clean leftover patterns like "(year", "NoStop", etc.
            v = re.sub(r'\(\s*\)', '', v)  # empty parens
            v = re.sub(r'\bNoStop\b', '', v, flags=re.I)
            v = re.sub(r'\\bibnamefont\s*', '', v)
            v = re.sub(r'\\bibfnamefont\s*', '', v)
            v = re.sub(r'\\bibinfo\s*', '', v)
            v = re.sub(r'\\bibfield\s*', '', v)
            v = re.sub(r'\\textbf\s*', '', v)
            # Remove LaTeX text formatting commands
            v = re.sub(r'\\em\b\s*', '', v)
            v = re.sub(r'\\it\b\s*', '', v)
            v = re.sub(r'\\bf\b\s*', '', v)
            v = re.sub(r'\\tt\b\s*', '', v)
            v = re.sub(r'\\emph\s*', '', v)
            v = re.sub(r'\\textit\s*', '', v)
            v = re.sub(r'\\textrm\s*', '', v)
            v = re.sub(r'\\textsf\s*', '', v)
            v = re.sub(r'\\textsc\s*', '', v)
            v = re.sub(r'\\texttt\s*', '', v)
            
            # === SPECIAL CLEANING FOR AUTHOR AND TITLE FIELDS ===
            # These fields should NEVER contain URLs, DOIs, href content, or long numbers
            if k in ['author', 'title']:
                # Remove http/https URLs
                v = re.sub(r'https?://[^\s,\]]+', '', v)
                # Remove \href{...}{...} - keep only the text part
                v = re.sub(r'\\href\{[^}]+\}\{([^}]+)\}', r'\1', v)
                # Remove DOI patterns (10.xxxx/...)
                v = re.sub(r'10\.\d+/[^\s,\]]+', '', v)
                # Remove arXiv links and IDs from title (they belong in eprint field)
                v = re.sub(r'\[?https?://arxiv\.org/abs/[^\s\]]+\]?', '', v)
                v = re.sub(r'\[?\\ttfamily\s*arXiv:[^\]]+\]?', '', v)
                v = re.sub(r'arXiv:[a-z-]+/\d+', '', v, flags=re.I)
                v = re.sub(r'arXiv:\d+\.\d+', '', v, flags=re.I)
                # Remove long number sequences (like DOI parts: 0550-3213, 1742-5468, etc.)
                v = re.sub(r'\b\d{4}-\d{4}\b', '', v)
                v = re.sub(r'\b\d{6,}\b', '', v)  # Remove 6+ digit numbers
                # Remove leftover brackets
                v = re.sub(r'\[\s*\]', '', v)
                # Remove journal-related info that sometimes leaks into title
                # Patterns like "Rev. Mod. Phys. 80, 517 (2008)"
                v = re.sub(r'(?:Rev\.|Phys\.|Lett\.|Mod\.|J\.)\s*[A-Za-z\.]+\s*\d+,?\s*\d*\s*\(\d{4}\)', '', v)
                # Remove volume/year patterns at end: "80, 517 (2008)"
                v = re.sub(r'\d+,\s*\d+[-–]?\d*\s*\(\d{4}\)\s*$', '', v)
                # Remove trailing commas/periods after cleanup
                v = v.strip(' ,.;:[]')

            
            # Loại bỏ các số volume/year/pages khỏi journal/note nếu đã extract riêng
            if k in ['journal', 'note', 'booktitle']:
                # Remove URLs from journal field
                v = re.sub(r'https?://[^\s]+', '', v)
                # Remove @noop and href@noop
                v = re.sub(r'@noop\s*', '', v, flags=re.I)
                v = re.sub(r'href@noop\s*', '', v, flags=re.I)
                # Remove DOI-like numbers (10.xxxx/...)
                v = re.sub(r'10\./[^\s]*', '', v)
                v = re.sub(r'\d{4}', '', v)  # remove years
                v = re.sub(r'vol\.?\s*~?\d+', '', v, flags=re.I)  # remove volume
                v = re.sub(r'no\.?\s*~?\d+', '', v, flags=re.I)  # remove number  
                v = re.sub(r'pp?\.?\s*~?\d+[-–—]\d+', '', v, flags=re.I)  # remove pages
                # Remove trailing volume/page numbers like "5, 106"
                v = re.sub(r',\s*\d+\s*$', '', v)
                v = v.strip(' .,;:()')
            
            # Clean backslash-space and remaining LaTeX artifacts
            v = re.sub(r'\\ ', ' ', v)  # backslash-space
            v = re.sub(r'\\\s+', ' ', v)  # backslash followed by whitespace
            v = re.sub(r'\\and\\', ' and ', v)  # \and\
            v = re.sub(r'\\and\b', ' and ', v)  # \and
            
            # Final cleanup
            v = ' '.join(v.split()).strip(' .,;:(){}')
            if v and len(v) > 0:
                final_fields[k] = v
    
    # Check if title is duplicate of author (common REVTeX parsing error)
    if 'title' in final_fields and 'author' in final_fields:
        title_clean = re.sub(r'[^a-zA-Z]', '', final_fields['title'].lower())
        author_clean = re.sub(r'[^a-zA-Z]', '', final_fields['author'].lower())
        # If title looks like author names (same or subset), remove title
        if title_clean and author_clean:
            # Check if title is similar to author (contains same names)
            title_words = set(title_clean.split())
            author_words = set(author_clean.split())
            overlap = len(title_words & author_words) / max(len(title_words), 1)
            if overlap > 0.6 or title_clean == author_clean:
                del final_fields['title']
            # Also check if title is just first author name
            elif len(final_fields['title']) < 40 and re.match(r'^[A-Z][a-z]+\s+[A-Z]', final_fields['title']):
                first_author = final_fields['author'].split(' and ')[0].split(',')[0].strip()
                if first_author.lower().replace(' ', '') in title_clean:
                    del final_fields['title']
    
    # Check if title contains "et al" - this should be in author
    if 'title' in final_fields and re.search(r'\bet\s*al\.?', final_fields['title'], re.I):
        # If title looks like author list with et al., remove it
        if len(final_fields['title']) < 100:
            title = final_fields['title']
            # Check if it's mostly author names
            name_pattern = re.findall(r'[A-Z]\.\s*[A-Z][a-z]+|[A-Z][a-z]+', title)
            if len(name_pattern) >= 2:
                del final_fields['title']
    
    # Đảm bảo có title - nhưng không dùng author làm title
    if 'title' not in final_fields:
        # For REVTeX entries or physics format (has journal but no title), skip Unknown Title
        if not is_revtex and 'journal' not in final_fields:
            final_fields['title'] = 'Unknown Title'
    
    # === 6.5. EXTRACT ADDITIONAL FIELDS WITH LEARNED PATTERNS ===
    try:
        patterns = get_learned_patterns()
        if patterns:
            additional_fields = extract_additional_fields_with_patterns(raw_content, patterns)
            # Thêm các field mới (không overwrite fields đã có)
            for field_name, field_value in additional_fields.items():
                if field_name not in final_fields and field_value:
                    final_fields[field_name] = field_value
    except Exception as e:
        # Nếu có lỗi trong pattern learning, tiếp tục với fields đã extract
        pass
    
    # === 7. FORMAT BIBTEX ===
    
    # CLEANUP FIELDS
    final_fields = {k: clean_field_value(v) for k, v in final_fields.items()}
    
    lines = [f'@{entry_type}{{{key},']
    
    priority = ['author', 'title', 'journal', 'booktitle', 'volume', 'number', 'pages', 'year', 'publisher', 'doi', 'url', 'eprint', 'archivePrefix', 'note']
    
    for f in priority:
        if f in final_fields:
            lines.append(f'  {f} = {{{final_fields[f]}}},')
    
    for f, v in final_fields.items():
        if f not in priority:
            lines.append(f'  {f} = {{{v}}},')
    
    lines.append('}')
    return '\n'.join(lines)




def create_refs_bib(version_dir, entries):
    """tạo file refs.bib từ các bibitem entries"""
    if not entries:
        return None
    
    bib_content = []
    bib_content.append('% Auto-generated from bibitem entries')
    bib_content.append(f'% Total entries: {len(entries)}')
    bib_content.append('')
    
    for key, raw_content in entries:
        bibtex_entry = parse_bibitem_to_bibtex(key, raw_content)
        bib_content.append(bibtex_entry)
        bib_content.append('')
    
    refs_path = Path(version_dir) / 'refs.bib'
    with open(refs_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(bib_content))
    
    return refs_path


# ============================================================================
# CITATION EXTRACTION
# ============================================================================

def find_citations_in_tex(tex_content):
    """
    tìm tất cả citation keys được sử dụng trong file tex
    returns: set of citation keys
    """
    content = remove_latex_comments(tex_content)
    citations = set()
    
    for pattern in CITATION_PATTERNS:
        for match in pattern.finditer(content):
            keys_str = match.group(1)
            # split nếu có nhiều keys: \cite{key1, key2, key3}
            keys = [k.strip() for k in keys_str.split(',')]
            citations.update(keys)
    
    # kiểm tra nocite{*} - cite tất cả
    if '*' in citations:
        return None  # signal để không filter
    
    return citations


def get_all_citations(version_dir):
    """lấy tất cả citations từ các file tex trong version"""
    all_citations = set()
    
    tex_files = get_all_tex_files(version_dir)
    for tex_file in tex_files:
        content = read_file_content(tex_file)
        if content:
            citations = find_citations_in_tex(content)
            if citations is None:
                # nocite{*} found
                return None
            all_citations.update(citations)
    
    return all_citations


# ============================================================================
# BIB FILE PROCESSING
# ============================================================================

def normalize_bib_entry(entry_text):
    """
    normalize một bib entry: thay thế entry type bằng loại chuẩn
    returns: normalized entry text
    """
    match = BIBTEX_ENTRY_PATTERN.match(entry_text)
    if not match:
        return entry_text
    
    original_type = match.group(1)
    normalized_type = normalize_entry_type(original_type)
    
    # skip các loại control/metadata
    if normalized_type in ('string', 'preamble', 'comment', 'control'):
        return entry_text
    
    # thay thế entry type
    if original_type.lower() != normalized_type:
        entry_text = f'@{normalized_type}' + entry_text[len(f'@{original_type}'):]
    
    return entry_text


def parse_bib_file(bib_content, normalize=True):
    """
    parse file .bib để lấy các entries
    returns: dict {key: (start_pos, end_pos, full_entry_text)}
    nếu normalize=True, entry types sẽ được chuẩn hóa
    """
    entries = {}
    
    # tìm tất cả entries
    for match in BIBTEX_ENTRY_PATTERN.finditer(bib_content):
        entry_type = match.group(1)
        key = match.group(2).strip()
        start_pos = match.start()
        
        # tìm closing brace - dùng approach tối ưu hơn
        # bắt đầu từ sau @type{key,
        search_start = match.end()
        brace_count = 1  # đã có 1 opening brace từ @type{
        end_pos = search_start
        
        # tìm từng } và { thay vì lặp từng char
        pos = search_start
        while pos < len(bib_content):
            next_open = bib_content.find('{', pos)
            next_close = bib_content.find('}', pos)
            
            if next_close == -1:
                # không tìm thấy closing brace
                end_pos = len(bib_content)
                break
            
            if next_open != -1 and next_open < next_close:
                # tìm thấy { trước }
                brace_count += 1
                pos = next_open + 1
            else:
                # tìm thấy } trước hoặc không có {
                brace_count -= 1
                if brace_count == 0:
                    end_pos = next_close + 1
                    break
                pos = next_close + 1
        
        entry_text = bib_content[start_pos:end_pos]
        
        # normalize entry type nếu cần
        if normalize:
            entry_text = normalize_bib_entry(entry_text)
        
        entries[key] = (start_pos, end_pos, entry_text)
    
    return entries


def filter_bib_file(bib_path, used_keys):
    """
    lọc file .bib chỉ giữ các entries được cite
    returns: (entries_before, entries_after)
    """
    content = read_file_content(bib_path)
    if not content:
        return 0, 0
    
    entries = parse_bib_file(content)
    entries_before = len(entries)
    
    if used_keys is None:
        # nocite{*} - giữ tất cả
        return entries_before, entries_before
    
    # tìm entries cần giữ
    kept_entries = []
    for key, (start, end, text) in entries.items():
        if key in used_keys:
            kept_entries.append(text)
    
    entries_after = len(kept_entries)
    
    # ghi lại file
    if entries_after != entries_before:
        new_content = '\n\n'.join(kept_entries)
        with open(bib_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
    
    return entries_before, entries_after


# ============================================================================
# MAIN PROCESSING
# ============================================================================

def get_all_bib_files(version_dir):
    """lấy tất cả file .bib trong version directory (không bao gồm refs.bib)"""
    bib_files = list(Path(version_dir).glob('*.bib'))
    # lọc bỏ file output nếu trùng tên
    output_bib_name = f"{Path(version_dir).name}.bib"
    return [f for f in bib_files 
            if f.name.lower() != output_bib_name.lower()]


def merge_bib_files(bib_files):
    """đọc và nối nội dung các file .bib"""
    merged_content = []
    for bib_file in bib_files:
        content = read_file_content(bib_file)
        if content:
            merged_content.append(f"% === From {bib_file.name} ===")
            merged_content.append(content.strip())
            merged_content.append("")
    return '\n'.join(merged_content)


def process_version(paper_id, version_dir):
    """xử lý một version của bài báo"""
    print(f"  Processing {version_dir.name}...")
    
    # bước 1: tìm tất cả file .bib hiện có
    bib_files = get_all_bib_files(version_dir)
    
    # bước 2: trích xuất bibitem từ tất cả file .tex
    all_bibitem_entries = []
    tex_files = get_all_tex_files(version_dir)
    
    for tex_file in tex_files:
        content = read_file_content(tex_file)
        if content:
            entries = extract_bibitems(content)
            all_bibitem_entries.extend(entries)
    
    # bước 3: kiểm tra có gì để tạo file bib không
    has_bib = len(bib_files) > 0
    has_bibitem = len(all_bibitem_entries) > 0
    
    if not has_bib and not has_bibitem:
        print(f"    No .bib files and no bibitem entries found, skipping...")
        return {'paper_id': paper_id, 'version': version_dir.name, 
                'status': 'no_references', 'entries': 0}
    
    # bước 4: tạo file bib = merge .bib files + convert bibitems
    output_bib_name = f"{version_dir.name}.bib"
    refs_content = []
    refs_content.append(f"% Auto-generated {output_bib_name}")
    refs_content.append(f"% Paper: {paper_id}, Version: {version_dir.name}")
    refs_content.append("")
    
    # thêm nội dung từ các file .bib
    if has_bib:
        print(f"    Found {len(bib_files)} .bib file(s): {[f.name for f in bib_files]}")
        merged_bib = merge_bib_files(bib_files)
        refs_content.append(merged_bib)
    
    # thêm nội dung từ bibitems
    if has_bibitem:
        print(f"    Found {len(all_bibitem_entries)} bibitem entries")
        refs_content.append("")
        refs_content.append("% === Converted from bibitem entries ===")
        for key, raw_content in all_bibitem_entries:
            bibtex_entry = parse_bibitem_to_bibtex(key, raw_content)
            refs_content.append(bibtex_entry)
            refs_content.append("")
    
    # ghi file bib
    refs_path = Path(version_dir) / output_bib_name
    with open(refs_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(refs_content))
    
    print(f"    Created {output_bib_name}")    
    
    # bước 5: tìm citations trong tex files
    used_citations = get_all_citations(version_dir)
    
    if used_citations is None:
        print(f"    Found \\nocite{{*}}, keeping all entries")
        return {'paper_id': paper_id, 'version': version_dir.name,
                'status': 'nocite_all', 'bib_file': str(refs_path)}
    
    print(f"    Found {len(used_citations)} unique citations")
    
    # bước 6: filter refs.bib - giữ lại entries được cite
    before, after = filter_bib_file(refs_path, used_citations)
    removed = before - after
    if removed > 0:
        print(f"    Filtered: {before} -> {after} entries ({removed} removed)")
    else:
        print(f"    No entries removed ({after} entries)")
    
    return {'paper_id': paper_id, 'version': version_dir.name,
            'status': 'success', 'entries_before': before, 
            'entries_after': after, 'removed': removed,
            'bib_files_merged': len(bib_files),
            'bibitems_converted': len(all_bibitem_entries),
            'bib_file': str(refs_path)}


def main():
    """entry point"""
    # base directory chứa papers
    script_dir = Path(__file__).parent
    base_dir = script_dir.parent / '23120257'
    
    if not base_dir.exists():
        print(f"Error: Directory {base_dir} not found")
        return
    
    print(f"Scanning {base_dir}...")
    versions = find_all_versions(base_dir)
    print(f"Found {len(versions)} paper versions")
    print()
    
    results = []
    
    for paper_id, version_dir in sorted(versions):
        print(f"Paper: {paper_id}")
        result = process_version(paper_id, version_dir)
        results.append(result)
        print()
    
    # summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    total_versions = len(results)
    success = sum(1 for r in results if r['status'] == 'success')
    no_refs = sum(1 for r in results if r['status'] == 'no_references')
    created = sum(1 for r in results if r.get('created_refs', False))
    total_removed = sum(r.get('removed', 0) for r in results)
    
    print(f"Total versions processed: {total_versions}")
    print(f"Successfully processed: {success}")
    print(f"No references found: {no_refs}")
    print(f"New refs.bib created: {created}")
    print(f"Total unused entries removed: {total_removed}")


if __name__ == '__main__':
    main()
