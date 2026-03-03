"""
Feature Engineering Script for Reference Matching
Tạo features từ refs_cleaned.json và references_cleaned.json
OPTIMIZED: Bỏ SBERT để chạy nhanh hơn, dùng TF-IDF thay thế
"""

import json
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple
from difflib import SequenceMatcher
import Levenshtein
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Config
DATA_DIR = Path(r"D:\23120257\data_modelling")
OUTPUT_FILE = DATA_DIR / "features.csv"


# SIMPLE STRING MATCHING FEATURES

def seq_matcher_sim(s1: str, s2: str) -> float:
    """SequenceMatcher similarity"""
    if not s1 or not s2:
        return 0.0
    return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()


def jaccard_sim(s1: str, s2: str) -> float:
    """Jaccard similarity on tokens"""
    if not s1 or not s2:
        return 0.0
    tokens1 = set(s1.lower().split())
    tokens2 = set(s2.lower().split())
    if not tokens1 or not tokens2:
        return 0.0
    intersection = len(tokens1 & tokens2)
    union = len(tokens1 | tokens2)
    return intersection / union if union > 0 else 0.0


def levenshtein_sim(s1: str, s2: str) -> float:
    """Normalized Levenshtein similarity"""
    if not s1 or not s2:
        return 0.0
    dist = Levenshtein.distance(s1.lower(), s2.lower())
    max_len = max(len(s1), len(s2))
    return 1 - (dist / max_len) if max_len > 0 else 0.0


# EMBEDDING FEATURES (dùng TF-IDF thay SBERT để nhanh hơn)

def tfidf_sim(s1: str, s2: str) -> float:
    """TF-IDF cosine similarity"""
    if not s1 or not s2:
        return 0.0
    try:
        vectorizer = TfidfVectorizer()
        tfidf = vectorizer.fit_transform([s1.lower(), s2.lower()])
        return float(cosine_similarity(tfidf[0], tfidf[1])[0][0])
    except:
        return 0.0


# N-GRAM FEATURES

def ngram_overlap(s1: str, s2: str, n: int = 2) -> float:
    """N-gram overlap ratio"""
    if not s1 or not s2:
        return 0.0
    
    def get_ngrams(text, n):
        tokens = text.lower().split()
        if len(tokens) < n:
            return set()
        return set(tuple(tokens[i:i+n]) for i in range(len(tokens) - n + 1))
    
    ngrams1 = get_ngrams(s1, n)
    ngrams2 = get_ngrams(s2, n)
    
    if not ngrams1 or not ngrams2:
        return 0.0
    
    intersection = len(ngrams1 & ngrams2)
    union = len(ngrams1 | ngrams2)
    return intersection / union if union > 0 else 0.0


# AUTHOR FEATURES

def first_author_match(authors1: str, authors2: str) -> int:
    """Check if first authors match"""
    if not authors1 or not authors2:
        return 0
    
    first1 = authors1.split(',')[0].strip().lower()
    first2 = authors2.split(',')[0].strip().lower()
    
    parts1 = first1.split()
    parts2 = first2.split()
    
    if parts1 and parts2:
        return 1 if parts1[-1] == parts2[-1] else 0
    return 0


def count_common_authors(authors1: str, authors2: str) -> int:
    """Count number of common author names"""
    if not authors1 or not authors2:
        return 0
    
    names1 = set(authors1.lower().replace(',', ' ').split())
    names2 = set(authors2.lower().replace(',', ' ').split())
    
    names1 = {n for n in names1 if len(n) > 2}
    names2 = {n for n in names2 if len(n) > 2}
    
    return len(names1 & names2)


def author_count_diff(authors1: str, authors2: str) -> int:
    """Difference in author count"""
    count1 = len(authors1.split(',')) if authors1 else 0
    count2 = len(authors2.split(',')) if authors2 else 0
    return abs(count1 - count2)


# YEAR FEATURES

def year_diff(year1: str, year2: str) -> int:
    """Absolute year difference"""
    try:
        y1 = int(year1) if year1 else 0
        y2 = int(year2) if year2 else 0
        if y1 == 0 or y2 == 0:
            return 10
        return abs(y1 - y2)
    except:
        return 10


def year_exact_match(year1: str, year2: str) -> int:
    """Check if years match exactly"""
    try:
        y1 = int(year1) if year1 else 0
        y2 = int(year2) if year2 else 0
        return 1 if y1 == y2 and y1 != 0 else 0
    except:
        return 0


# META FEATURES

def title_len_ratio(title1: str, title2: str) -> float:
    """Ratio of title lengths"""
    len1 = len(title1) if title1 else 1
    len2 = len(title2) if title2 else 1
    return min(len1, len2) / max(len1, len2)


# MAIN FEATURE EXTRACTION

def extract_features_for_pair(bib_entry: Dict, candidate: Dict) -> Dict:
    """Extract all features for one (bib, candidate) pair"""
    
    bib_title = bib_entry.get('title_clean', '')
    bib_author = bib_entry.get('author_clean', '')
    bib_year = bib_entry.get('year', '')
    
    cand_title = candidate.get('title_clean', '')
    cand_author = candidate.get('authors_clean', '')
    cand_year = candidate.get('year', '')
    
    features = {
        # Simple string matching
        'title_seq_sim': seq_matcher_sim(bib_title, cand_title),
        'title_jaccard': jaccard_sim(bib_title, cand_title),
        'title_levenshtein': levenshtein_sim(bib_title, cand_title),
        'author_jaccard': jaccard_sim(bib_author, cand_author),
        
        # Embeddings (TF-IDF thay SBERT)
        'title_tfidf_sim': tfidf_sim(bib_title, cand_title),
        'author_tfidf_sim': tfidf_sim(bib_author, cand_author),
        
        # N-gram
        'title_ngram_overlap': ngram_overlap(bib_title, cand_title, n=2),
        'title_trigram_overlap': ngram_overlap(bib_title, cand_title, n=3),
        
        # Author features
        'first_author_match': first_author_match(bib_author, cand_author),
        'num_common_authors': count_common_authors(bib_author, cand_author),
        'author_count_diff': author_count_diff(bib_author, cand_author),
        
        # Year features
        'year_diff': year_diff(bib_year, cand_year),
        'year_exact_match': year_exact_match(bib_year, cand_year),
        
        # Meta features
        'title_len_ratio': title_len_ratio(bib_title, cand_title),
        'combined_score': 0.7 * seq_matcher_sim(bib_title, cand_title) + 0.3 * jaccard_sim(bib_author, cand_author),
    }
    
    return features


def process_paper(paper_dir: Path, ground_truth: Dict) -> List[Dict]:
    """Process one paper and generate all (bib, candidate) pairs with features"""
    
    refs_cleaned = paper_dir / 'refs_cleaned.json'
    candidates_cleaned = paper_dir / 'references_cleaned.json'
    
    if not refs_cleaned.exists() or not candidates_cleaned.exists():
        return []
    
    try:
        with open(refs_cleaned, 'r', encoding='utf-8') as f:
            bib_entries = json.load(f)
        with open(candidates_cleaned, 'r', encoding='utf-8') as f:
            candidates = json.load(f)
    except:
        return []
    
    rows = []
    
    for bib_key, bib_entry in bib_entries.items():
        for cand_id, candidate in candidates.items():
            # Extract features
            features = extract_features_for_pair(bib_entry, candidate)
            
            # Add identifiers
            features['paper_id'] = paper_dir.name
            features['bib_key'] = bib_key
            features['candidate_id'] = cand_id
            
            # Add label (1 if match, 0 otherwise)
            label = 1 if ground_truth.get(bib_key) == cand_id else 0
            features['label'] = label
            
            rows.append(features)
    
    return rows


def main():
    print(f"Data directory: {DATA_DIR}")
    print("-" * 50)
    
    paper_dirs = sorted([d for d in DATA_DIR.iterdir() if d.is_dir()])
    total = len(paper_dirs)
    
    print(f"Processing {total} papers...")
    
    all_rows = []
    papers_processed = 0
    
    for i, paper_dir in enumerate(paper_dirs):
        # Load ground truth
        gt_path = paper_dir / 'ground_truth.json'
        if not gt_path.exists():
            continue
        
        try:
            with open(gt_path, 'r', encoding='utf-8') as f:
                ground_truth = json.load(f)
        except:
            continue
        
        # Process paper
        rows = process_paper(paper_dir, ground_truth)
        all_rows.extend(rows)
        papers_processed += 1
        
        # Progress mỗi 10 papers
        if (i + 1) % 10 == 0:
            print(f"  Processed {i + 1}/{total}... ({len(all_rows)} pairs)")
    
    # Create DataFrame and save
    df = pd.DataFrame(all_rows)
    df.to_csv(OUTPUT_FILE, index=False)
    
    print("\n" + "=" * 50)
    print("THỐNG KÊ")
    print("=" * 50)
    print(f"Papers processed: {papers_processed}")
    print(f"Total pairs: {len(df)}")
    print(f"Positive labels: {df['label'].sum()}")
    print(f"Negative labels: {len(df) - df['label'].sum()}")
    print(f"Positive ratio: {df['label'].mean()*100:.2f}%")
    print(f"\nSaved to: {OUTPUT_FILE}")


if __name__ == '__main__':
    main()
