#pip install unidecode
"""
bib deduplication - xử lý 4 trường hợp duplicate:
1. cùng key + cùng content → xóa 1
2. cùng key + content na ná → unionize fields
3. khác key + cùng content → chọn 1 key, update hierarchy.json
4. khác key + content na ná → unionize + chọn 1 key
"""

import os
import re
import json
from pathlib import Path
from difflib import SequenceMatcher

DATA_DIR = Path(r"D:\23120257\23120257")
SIMILARITY_THRESHOLD = 0.85

def parse_bib_file(bib_path):
    """đọc file .bib → dict entries"""
    entries = {}
    if not bib_path.exists():
        return entries
    
    content = bib_path.read_text(encoding='utf-8', errors='ignore')
    entry_pattern = re.compile(r'@(\w+)\s*\{([^,]+),([^@]*?)\n\}', re.DOTALL)
    
    for match in entry_pattern.finditer(content):
        entry_type = match.group(1).lower()
        key = match.group(2).strip()
        fields_raw = match.group(3)
        
        fields = {'_type': entry_type}
        field_pattern = re.compile(r'(\w+)\s*=\s*\{([^}]*)\}', re.DOTALL)
        for fm in field_pattern.finditer(fields_raw):
            fields[fm.group(1).lower()] = fm.group(2).strip()
        
        entries[key] = fields
    
    return entries

def write_bib_file(bib_path, entries):
    """ghi dict entries → file .bib"""
    lines = []
    for key, fields in entries.items():
        entry_type = fields.get('_type', 'misc')
        lines.append(f"@{entry_type}{{{key},")
        for fname, fval in fields.items():
            if not fname.startswith('_'):
                lines.append(f"  {fname} = {{{fval}}},")
        lines.append("}")
        lines.append("")
    
    bib_path.write_text('\n'.join(lines), encoding='utf-8')

def normalize_text(text):
    """chuẩn hóa text để so sánh"""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def calculate_similarity(text1, text2):
    """tính độ tương đồng giữa 2 string"""
    t1, t2 = normalize_text(text1), normalize_text(text2)
    if not t1 or not t2:
        return 0.0
    return SequenceMatcher(None, t1, t2).ratio()

def entries_similar(entry1, entry2, threshold=SIMILARITY_THRESHOLD):
    """kiểm tra 2 entries có tương tự không (dựa trên title, author, year)"""
    title_sim = calculate_similarity(entry1.get('title', ''), entry2.get('title', ''))
    author_sim = calculate_similarity(entry1.get('author', ''), entry2.get('author', ''))
    year1, year2 = entry1.get('year', ''), entry2.get('year', '')
    year_match = (year1 == year2) or (not year1 and not year2)
    
    if title_sim > 0.9 and author_sim > 0.8:
        return True
    if author_sim > 0.9 and year_match and title_sim > 0.7:
        return True
    
    combined = title_sim * 0.5 + author_sim * 0.4 + (1.0 if year_match else 0.0) * 0.1
    return combined >= threshold

def entries_identical(entry1, entry2):
    """kiểm tra 2 entries có hoàn toàn giống nhau không"""
    keys1 = {k for k in entry1 if not k.startswith('_')}
    keys2 = {k for k in entry2 if not k.startswith('_')}
    
    if keys1 != keys2:
        return False
    
    for k in keys1:
        if normalize_text(entry1.get(k, '')) != normalize_text(entry2.get(k, '')):
            return False
    return True

def unionize_entries(entry1, entry2):
    """merge 2 entries, ưu tiên giá trị dài hơn"""
    merged = {'_type': entry1.get('_type', entry2.get('_type', 'misc'))}
    all_fields = set(entry1.keys()) | set(entry2.keys())
    
    for field in all_fields:
        if field.startswith('_'):
            continue
        val1, val2 = entry1.get(field, ''), entry2.get(field, '')
        if not val1:
            merged[field] = val2
        elif not val2:
            merged[field] = val1
        else:
            merged[field] = val1 if len(val1) >= len(val2) else val2
    
    return merged

def update_hierarchy_json(hierarchy_path, old_key, new_key):
    """thay thế citation key trong hierarchy.json"""
    if not hierarchy_path.exists():
        return False
    
    try:
        content = hierarchy_path.read_text(encoding='utf-8')
        updated = content.replace(f'\\cite{{{old_key}}}', f'\\cite{{{new_key}}}')
        updated = updated.replace(f'\\citep{{{old_key}}}', f'\\citep{{{new_key}}}')
        updated = updated.replace(f'\\citet{{{old_key}}}', f'\\citet{{{new_key}}}')
        
        # xử lý multi-cite
        updated = re.sub(
            rf'(\\cite[pt]?\{{[^}}]*)\b{re.escape(old_key)}\b([^}}]*\}})',
            rf'\1{new_key}\2',
            updated
        )
        
        if updated != content:
            hierarchy_path.write_text(updated, encoding='utf-8')
            return True
    except Exception as e:
        print(f"  lỗi update hierarchy: {e}")
    
    return False

def deduplicate_bib(bib_path, hierarchy_path=None):
    """deduplicate entries trong 1 file .bib"""
    entries = parse_bib_file(bib_path)
    if not entries:
        return 0
    
    keys = list(entries.keys())
    to_remove = set()
    key_mapping = {}
    
    for i in range(len(keys)):
        if keys[i] in to_remove:
            continue
        for j in range(i + 1, len(keys)):
            if keys[j] in to_remove:
                continue
            
            key1, key2 = keys[i], keys[j]
            entry1, entry2 = entries[key1], entries[key2]
            identical = entries_identical(entry1, entry2)
            similar = entries_similar(entry1, entry2)
            
            if identical:
                to_remove.add(key2)
                key_mapping[key2] = key1
            elif similar:
                entries[key1] = unionize_entries(entry1, entry2)
                to_remove.add(key2)
                key_mapping[key2] = key1
    
    for key in to_remove:
        del entries[key]
    
    if hierarchy_path and key_mapping:
        for old_key, new_key in key_mapping.items():
            update_hierarchy_json(hierarchy_path, old_key, new_key)
    
    if to_remove:
        write_bib_file(bib_path, entries)
        return len(to_remove)
    
    return 0

def extract_citation_keys_from_hierarchy(hierarchy_path):
    """trích xuất các citation keys được dùng trong hierarchy.json"""
    keys = set()
    if not hierarchy_path.exists():
        return keys
    
    try:
        content = hierarchy_path.read_text(encoding='utf-8')
        cite_pattern = re.compile(r'\\cite[pt]?\{([^}]+)\}')
        for match in cite_pattern.finditer(content):
            for ck in match.group(1).split(','):
                keys.add(ck.strip())
    except Exception as e:
        print(f"  lỗi đọc hierarchy: {e}")
    
    return keys

def merge_bib_entries(entries_list):
    """gộp nhiều dict entries thành 1"""
    merged = {}
    for entries in entries_list:
        for key, fields in entries.items():
            if key not in merged:
                merged[key] = fields
            else:
                merged[key] = unionize_entries(merged[key], fields)
    return merged

def filter_unused_entries(entries, used_keys):
    """xóa entries không được cite trong hierarchy.json"""
    keys_to_remove = [k for k in entries if k not in used_keys]
    for key in keys_to_remove:
        del entries[key]
    return len(keys_to_remove)

def process_all_papers():
    """xử lý tất cả papers: dedupe versions → tạo refs.bib → filter unused"""
    total_removed_versions = 0
    total_removed_refs = 0
    total_removed_unused = 0
    total_papers = 0
    
    for paper_dir in DATA_DIR.iterdir():
        if not paper_dir.is_dir() or not paper_dir.name.startswith('2411-'):
            continue
        
        tex_dir = paper_dir / 'tex'
        if not tex_dir.exists():
            continue
        
        print(f"\npaper: {paper_dir.name}")
        total_papers += 1
        
        # phase 1: dedupe từng version.bib
        version_entries_list = []
        all_hierarchy_paths = []
        
        for version_dir in sorted(tex_dir.iterdir()):
            if not version_dir.is_dir():
                continue
            
            bib_file = version_dir / f"{version_dir.name}.bib"
            hierarchy_file = version_dir / "hierarchy.json"
            
            if not bib_file.exists():
                continue
            
            removed = deduplicate_bib(
                bib_file, 
                hierarchy_file if hierarchy_file.exists() else None
            )
            if removed > 0:
                print(f"  {version_dir.name}: xóa {removed} duplicates")
                total_removed_versions += removed
            
            entries = parse_bib_file(bib_file)
            version_entries_list.append(entries)
            
            if hierarchy_file.exists():
                all_hierarchy_paths.append(hierarchy_file)
        
        if not version_entries_list:
            continue
        
        # phase 2: tạo refs.bib ở cấp paper
        refs_bib_path = paper_dir / "refs.bib"
        merged_entries = merge_bib_entries(version_entries_list)
        
        # dedupe refs.bib
        keys = list(merged_entries.keys())
        to_remove = set()
        key_mapping = {}
        
        for i in range(len(keys)):
            if keys[i] in to_remove:
                continue
            for j in range(i + 1, len(keys)):
                if keys[j] in to_remove:
                    continue
                
                key1, key2 = keys[i], keys[j]
                entry1, entry2 = merged_entries[key1], merged_entries[key2]
                
                if entries_identical(entry1, entry2) or entries_similar(entry1, entry2):
                    merged_entries[key1] = unionize_entries(entry1, entry2)
                    to_remove.add(key2)
                    key_mapping[key2] = key1
        
        for key in to_remove:
            del merged_entries[key]
        total_removed_refs += len(to_remove)
        
        if key_mapping:
            for hierarchy_path in all_hierarchy_paths:
                for old_key, new_key in key_mapping.items():
                    update_hierarchy_json(hierarchy_path, old_key, new_key)
        
        # phase 3: xóa entries không được dùng
        # đọc hierarchy.json ở cấp paper
        paper_hierarchy = paper_dir / "hierarchy.json"
        all_used_keys = set()
        
        if paper_hierarchy.exists():
            all_used_keys.update(extract_citation_keys_from_hierarchy(paper_hierarchy))
        
        for hierarchy_path in all_hierarchy_paths:
            all_used_keys.update(extract_citation_keys_from_hierarchy(hierarchy_path))
        
        if all_used_keys:
            removed_unused = filter_unused_entries(merged_entries, all_used_keys)
            if removed_unused > 0:
                print(f"  refs.bib: xóa {removed_unused} unused entries")
                total_removed_unused += removed_unused
        
        write_bib_file(refs_bib_path, merged_entries)
        print(f"  tạo refs.bib với {len(merged_entries)} entries")
    
    print(f"\n{'='*60}")
    print(f"tổng kết")
    print(f"{'='*60}")
    print(f"papers: {total_papers}")
    print(f"duplicates xóa (version): {total_removed_versions}")
    print(f"duplicates xóa (refs.bib): {total_removed_refs}")
    print(f"unused entries xóa: {total_removed_unused}")

if __name__ == '__main__':
    process_all_papers()
