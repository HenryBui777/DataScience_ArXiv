
import os
import re
import json
import shutil
from pathlib import Path

# Config
SOURCE_DIR = Path(r"D:\23120257\23120257")
TARGET_DIR = Path(r"D:\23120257\data_modelling")
TARGET_COUNT = 3000

# Thresholds
MIN_BIB_ENTRIES = 15
MIN_REF_CANDIDATES = 15

# 5 bài manual cố định 
MANUAL_PAPERS = [
    "2411-10224",
    "2411-10231", 
    "2411-10232",
    "2411-10261",
    "2411-10281"
]


def count_bib_entries(bib_path: Path) -> int:
    """Đếm số bib entries trong file .bib"""
    try:
        with open(bib_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        return len(re.findall(r'@\w+\s*\{', content))
    except:
        return 0


def count_references(json_path: Path) -> int:
    """Đếm số arXiv IDs trong references.json"""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            return len(data)
        return 0
    except:
        return 0


def has_bibitem_in_tex(tex_dir: Path) -> bool:
    if not tex_dir.exists():
        return False
    
    for tex_file in tex_dir.rglob('*.tex'):
        try:
            with open(tex_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            if r'\bibitem' in content:
                return True
        except:
            continue
    return False


def check_paper_criteria(paper_dir: Path) -> dict:
    refs_bib = paper_dir / 'refs.bib'
    refs_json = paper_dir / 'references.json'
    tex_dir = paper_dir / 'tex'
    
    result = {
        'paper_id': paper_dir.name,
        'valid': False,
        'bib_count': 0,
        'ref_count': 0,
        'has_bibitem': False,
        'reason': ''
    }
    
    if not refs_bib.exists():
        result['reason'] = 'no refs.bib'
        return result
    
    bib_count = count_bib_entries(refs_bib)
    result['bib_count'] = bib_count
    
    if bib_count < MIN_BIB_ENTRIES:
        result['reason'] = f'bib entries < {MIN_BIB_ENTRIES}'
        return result
    
    if not refs_json.exists():
        result['reason'] = 'no references.json'
        return result
    
    ref_count = count_references(refs_json)
    result['ref_count'] = ref_count
    
    if ref_count < MIN_REF_CANDIDATES:
        result['reason'] = f'ref candidates < {MIN_REF_CANDIDATES}'
        return result
    
    has_bibitem = has_bibitem_in_tex(tex_dir)
    result['has_bibitem'] = has_bibitem
    
    if has_bibitem:
        result['reason'] = 'has \\bibitem in tex'
        return result
    
    result['valid'] = True
    result['reason'] = 'OK'
    return result


def copy_paper_data(paper_dir: Path, target_dir: Path):
    """Copy refs.bib, references.json và hierarchy.json sang target folder"""
    paper_target = target_dir / paper_dir.name
    paper_target.mkdir(parents=True, exist_ok=True)
    
    # Copy refs.bib
    src_bib = paper_dir / 'refs.bib'
    dst_bib = paper_target / 'refs.bib'
    if src_bib.exists():
        shutil.copy2(src_bib, dst_bib)
    
    # Copy references.json
    src_json = paper_dir / 'references.json'
    dst_json = paper_target / 'references.json'
    if src_json.exists():
        shutil.copy2(src_json, dst_json)
    
    # Copy hierarchy.json
    src_hierarchy = paper_dir / 'hierarchy.json'
    dst_hierarchy = paper_target / 'hierarchy.json'
    if src_hierarchy.exists():
        shutil.copy2(src_hierarchy, dst_hierarchy)


def main():
    print(f"Source: {SOURCE_DIR}")
    print(f"Target: {TARGET_DIR}")
    print(f"Manual papers: {len(MANUAL_PAPERS)}")
    print(f"Additional papers: {TARGET_COUNT}")
    print(f"Criteria: bib >= {MIN_BIB_ENTRIES}, refs >= {MIN_REF_CANDIDATES}, no \\bibitem")
    print("-" * 50)
    
    # Create target directory
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    
    # Step 1: Copy 5 manual papers first
    print(f"\nCopying {len(MANUAL_PAPERS)} manual papers...")
    manual_copied = 0
    for paper_id in MANUAL_PAPERS:
        paper_dir = SOURCE_DIR / paper_id
        if paper_dir.exists():
            copy_paper_data(paper_dir, TARGET_DIR)
            manual_copied += 1
            print(f"  Copied {paper_id}")
        else:
            print(f"  WARNING: {paper_id} not found!")
    
    print(f"Manual papers copied: {manual_copied}")
    
    # Step 2: Scan and select additional papers
    print(f"\nScanning for {TARGET_COUNT} additional papers...")
    
    paper_dirs = sorted([d for d in SOURCE_DIR.iterdir() if d.is_dir()])
    total = len(paper_dirs)
    
    valid_papers = []
    invalid_reasons = {}
    
    for i, paper_dir in enumerate(paper_dirs):
        if (i + 1) % 500 == 0:
            print(f"  Scanned {i + 1}/{total}...")
        
        # Skip manual papers
        if paper_dir.name in MANUAL_PAPERS:
            continue
        
        result = check_paper_criteria(paper_dir)
        
        if result['valid']:
            valid_papers.append(result)
        else:
            reason = result['reason']
            invalid_reasons[reason] = invalid_reasons.get(reason, 0) + 1
    
    print(f"\nFound {len(valid_papers)} valid papers (excluding manual)")
    print("\nInvalid reasons:")
    for reason, count in sorted(invalid_reasons.items(), key=lambda x: -x[1]):
        print(f"  {reason}: {count}")
    
    # Select papers
    selected = valid_papers[:TARGET_COUNT]
    
    if len(selected) < TARGET_COUNT:
        print(f"\nWARNING: Only {len(selected)} papers available (need {TARGET_COUNT})")
    
    # Copy selected papers
    print(f"\nCopying {len(selected)} additional papers...")
    
    for i, paper in enumerate(selected):
        paper_dir = SOURCE_DIR / paper['paper_id']
        copy_paper_data(paper_dir, TARGET_DIR)
        
        if (i + 1) % 100 == 0:
            print(f"  Copied {i + 1}/{len(selected)}...")
    
    total_copied = manual_copied + len(selected)
    print(f"\nDone! Total copied: {total_copied} papers")
    print(f"  - Manual: {manual_copied}")
    print(f"  - Additional: {len(selected)}")
    
    # Save summary
    summary_path = TARGET_DIR / 'selection_summary.json'
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump({
            'manual_papers': MANUAL_PAPERS,
            'total_scanned': total,
            'total_valid': len(valid_papers),
            'total_selected': len(selected),
            'total_copied': total_copied,
            'papers': selected
        }, f, indent=2)
    print(f"Summary saved to: {summary_path}")


if __name__ == '__main__':
    main()
