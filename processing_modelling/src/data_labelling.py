
import json
import re
import shutil
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from difflib import SequenceMatcher

# Config
DATA_DIR = Path(r"D:\23120257\data_modelling")
FIELD_THRESHOLD = 0.7  # Ngưỡng cho mỗi field (title, author)
MIN_MATCHES = 15  # Số cặp match tối thiểu để giữ paper


def normalize_for_matching(text: str) -> str:
    """Normalize text để so sánh"""
    if not text:
        return ""
    text = text.lower()
    # Remove common prefixes/suffixes
    text = re.sub(r'^(a|an|the)\s+', '', text)
    # Remove punctuation
    text = re.sub(r'[^\w\s]', ' ', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def text_similarity(text1: str, text2: str) -> float:
    """Tính similarity giữa 2 text (Sequence + Jaccard)"""
    t1 = normalize_for_matching(text1)
    t2 = normalize_for_matching(text2)
    if not t1 or not t2:
        return 0.0
    
    # SequenceMatcher similarity
    seq_sim = SequenceMatcher(None, t1, t2).ratio()
    
    # Jaccard similarity (token-based)
    tokens1 = t1.split()
    tokens2 = t2.split()
    if tokens1 and tokens2:
        set1 = set(tokens1)
        set2 = set(tokens2)
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        jac_sim = intersection / union if union > 0 else 0.0
    else:
        jac_sim = 0.0
    
    # Weighted combination: 60% sequence + 40% jaccard
    return 0.6 * seq_sim + 0.4 * jac_sim


def year_match(bib_year: str, ref_year: str, tolerance: int = 1) -> bool:
    """Check xem year có match không (với tolerance)"""
    if not bib_year or not ref_year:
        return True  # Nếu không có year thì skip check
    try:
        y1 = int(bib_year)
        y2 = int(ref_year)
        return abs(y1 - y2) <= tolerance
    except:
        return True


def find_best_match(bib_entry: Dict, candidates: Dict) -> Tuple[Optional[str], float]:
    """
    Tìm candidate tốt nhất cho bib entry
    Yêu cầu: title, author, year đều phải >= FIELD_THRESHOLD
    Returns: (arxiv_id, min_score) hoặc (None, 0)
    """
    bib_title = bib_entry.get('title_clean', '')
    bib_author = bib_entry.get('author_clean', '')
    bib_year = bib_entry.get('year', '')
    
    best_match = None
    best_min_score = 0.0
    
    for arxiv_id, candidate in candidates.items():
        cand_title = candidate.get('title_clean', '')
        cand_author = candidate.get('authors_clean', '')
        cand_year = candidate.get('year', '')
        
        # Title similarity (Sequence + Jaccard)
        title_sim = text_similarity(bib_title, cand_title)
        
        # Author similarity (Sequence + Jaccard)
        author_sim = text_similarity(bib_author, cand_author)
        
        # Chỉ cần title VÀ author >= threshold (year tùy chọn)
        if title_sim >= FIELD_THRESHOLD and author_sim >= FIELD_THRESHOLD:
            min_score = min(title_sim, author_sim)
            if min_score > best_min_score:
                best_min_score = min_score
                best_match = arxiv_id
    
    return best_match, best_min_score


def process_paper(paper_dir: Path, is_manual: bool) -> Dict:
    """
    Process một paper: match tất cả bib entries với candidates
    Returns: ground_truth data
    """
    paper_id = paper_dir.name
    
    # Load cleaned data
    refs_cleaned_path = paper_dir / 'refs_cleaned.json'
    candidates_cleaned_path = paper_dir / 'references_cleaned.json'
    original_refs_path = paper_dir / 'references.json'  # file gốc để verify
    
    if not refs_cleaned_path.exists() or not candidates_cleaned_path.exists():
        return None
    
    try:
        with open(refs_cleaned_path, 'r', encoding='utf-8') as f:
            bib_entries = json.load(f)
        with open(candidates_cleaned_path, 'r', encoding='utf-8') as f:
            candidates = json.load(f)
        # Load file gốc để verify
        original_ids = set()
        if original_refs_path.exists():
            with open(original_refs_path, 'r', encoding='utf-8') as f:
                original_refs = json.load(f)
                original_ids = set(original_refs.keys())
    except Exception as e:
        print(f"  Error loading {paper_id}: {e}")
        return None
    
    # Match each bib entry
    labels = {}
    
    for bib_key, bib_entry in bib_entries.items():
        best_match, score = find_best_match(bib_entry, candidates)
        
        if best_match:  # Đã pass threshold trong find_best_match
            # Verify ID tồn tại trong file gốc
            if original_ids and best_match in original_ids:
                labels[bib_key] = best_match
            elif not original_ids:
                labels[bib_key] = best_match
    
    return labels, len(bib_entries), len(candidates), len(labels)


def save_ground_truth(paper_dir: Path, labels: Dict):
    """Save ground_truth.json - chỉ chứa labels"""
    output_path = paper_dir / 'ground_truth.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(labels, f, indent=2, ensure_ascii=False)


def main():
    print(f"Data directory: {DATA_DIR}")
    print(f"Field threshold: {FIELD_THRESHOLD}")
    print("-" * 50)
    
    # Get all paper directories
    paper_dirs = sorted([d for d in DATA_DIR.iterdir() if d.is_dir()])
    total = len(paper_dirs)
    
    print(f"Processing {total} papers...")
    
    stats = {
        'processed': 0,
        'papers_with_enough_matches': 0,
        'deleted': 0
    }
    
    # Process ALL papers
    for i, paper_dir in enumerate(paper_dirs):
        result = process_paper(paper_dir, is_manual=False)
        
        if result:
            labels, num_bib, num_cand, num_matches = result
            
            if num_matches >= MIN_MATCHES:
                save_ground_truth(paper_dir, labels)
                stats['processed'] += 1
                stats['papers_with_enough_matches'] += 1
            else:
                # Xóa thư mục bài báo không đủ matches
                shutil.rmtree(paper_dir)
                stats['deleted'] += 1
        
        if (i + 1) % 100 == 0:
            print(f"  Processed {i + 1}/{total}...")
    
    print("\n" + "=" * 50)
    print("THỐNG KÊ KẾT QUẢ")
    print("=" * 50)
    print(f"Papers giữ lại (≥{MIN_MATCHES} matches): {stats['papers_with_enough_matches']}")
    print(f"Đã xóa (<{MIN_MATCHES} matches): {stats['deleted']}")


if __name__ == '__main__':
    main()

