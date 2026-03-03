"""
text deduplication - xử lý elements trong hierarchy.json:
1. Với paper có v1 có nhiều file tex: v1 documents được đánh số (Document 01, 02...)
2. Documents v2+ không đánh số -> match với v1 documents bằng Overlap Coefficient
3. Reparent children của v2+ documents sang v1 documents tương ứng
4. Discard v2+ documents
5. Dedupe các elements còn lại bằng exact content match
"""

import json
import re
from pathlib import Path
from collections import defaultdict

DATA_DIR = Path(r"D:\23120257\23120257")

def normalize_text(text):
    """chuẩn hóa text để so sánh"""
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r'\s+', ' ', text)
    return text

def get_type(element_id):
    """lấy type từ element id"""
    return element_id.split('-')[0]

def get_version(element_id):
    """lấy version từ element id, vd: document-2411-10227-v1-d1-0 → 1"""
    match = re.search(r'-v(\d+)-', element_id)
    return int(match.group(1)) if match else 1

def is_numbered_document(content):
    """kiểm tra document có đánh số không (Document 01, Document 02...)"""
    return bool(re.search(r'\s+\d{2}$', content))

# các type luôn cần đánh số để phân biệt (vì value = type name)
TYPES_ALWAYS_NUMBER = {
    'theorem', 'remark', 'quote', 'quotation', 'proposition', 'proof',
    'note', 'lemma', 'item', 'example', 'definition',
    'corollary', 'conjecture', 'claim', 'axiom'
}

# ==== HELPER FUNCTIONS ====

def get_direct_children(parent_id, hierarchy):
    """lấy danh sách children trực tiếp (level 1) của 1 element"""
    children = []
    for version_data in hierarchy.values():
        for child_id, p_id in version_data.items():
            if p_id == parent_id:
                children.append(child_id)
    return children

def get_children_content_set(parent_id, elements, hierarchy):
    """lấy set content của tất cả children trực tiếp của 1 element"""
    children = get_direct_children(parent_id, hierarchy)
    content_set = set()
    for child_id in children:
        if child_id in elements:
            content_set.add(normalize_text(elements[child_id]))
    return content_set

def calculate_overlap_coefficient(set1, set2):
    """tính Overlap Coefficient: |A ∩ B| / min(|A|, |B|)"""
    if not set1 or not set2:
        return 0.0
    intersection = len(set1 & set2)
    min_size = min(len(set1), len(set2))
    return intersection / min_size if min_size > 0 else 0.0

def find_best_matching_v1_doc(v2_doc_id, v1_docs, elements, hierarchy):
    """tìm v1 document phù hợp nhất với v2 document dựa trên overlap coefficient"""
    v2_children_set = get_children_content_set(v2_doc_id, elements, hierarchy)
    
    best_match = None
    best_score = 0.0
    
    for v1_doc_id in v1_docs:
        v1_children_set = get_children_content_set(v1_doc_id, elements, hierarchy)
        score = calculate_overlap_coefficient(v2_children_set, v1_children_set)
        
        if score > best_score:
            best_score = score
            best_match = v1_doc_id
    
    return best_match, best_score

# ==== MAIN PROCESSING FUNCTIONS ====

def merge_versions(elements, hierarchy):
    """
    Merge v2+ documents vào v1 documents.
    - v1 documents: giữ nguyên (đã có số nếu cần)
    - v2+ documents: match với v1, reparent children, sau đó discard
    """
    # 1. Tìm tất cả documents
    all_docs = {eid: elements[eid] for eid in elements if get_type(eid) == 'document'}
    
    if len(all_docs) <= 1:
        return elements, hierarchy  # chỉ có 1 document, không cần merge
    
    # 2. Phân loại v1 docs vs v2+ docs
    v1_docs = []
    v2plus_docs = []
    
    for doc_id, content in all_docs.items():
        version = get_version(doc_id)
        if version == 1:
            v1_docs.append(doc_id)
        else:
            v2plus_docs.append(doc_id)
    
    if not v1_docs or not v2plus_docs:
        return elements, hierarchy  # không có v2+ để merge
    
    # 3. Với mỗi v2+ doc, tìm v1 doc tương ứng và reparent children
    reparent_map = {}  # old_parent -> new_parent
    docs_to_remove = set()
    
    for v2_doc_id in v2plus_docs:
        best_v1_doc, score = find_best_matching_v1_doc(v2_doc_id, v1_docs, elements, hierarchy)
        
        if best_v1_doc and score >= 0.5:  # threshold 50%
            reparent_map[v2_doc_id] = best_v1_doc
            docs_to_remove.add(v2_doc_id)
    
    # 4. Cập nhật hierarchy: reparent children của v2+ docs
    new_hierarchy = {}
    for version, relations in hierarchy.items():
        new_relations = {}
        for child_id, parent_id in relations.items():
            # Nếu parent là v2+ doc cần reparent -> đổi sang v1 doc
            if parent_id in reparent_map:
                new_relations[child_id] = reparent_map[parent_id]
            else:
                new_relations[child_id] = parent_id
        new_hierarchy[version] = new_relations
    
    # 5. Xóa v2+ documents khỏi elements
    new_elements = {eid: content for eid, content in elements.items() 
                    if eid not in docs_to_remove}
    
    # 6. Xóa v2+ documents khỏi hierarchy (các entry có child là doc bị xóa)
    for version in new_hierarchy:
        new_hierarchy[version] = {child: parent 
                                   for child, parent in new_hierarchy[version].items()
                                   if child not in docs_to_remove}
    
    return new_elements, new_hierarchy

def add_number_suffix(elements, hierarchy):
    """với TYPES_ALWAYS_NUMBER: thêm số nếu có value trùng"""
    updated_elements = dict(elements)
    
    content_groups = defaultdict(list)
    for elem_id, content in elements.items():
        elem_type = get_type(elem_id)
        if elem_type in TYPES_ALWAYS_NUMBER:
            norm_content = normalize_text(content)
            content_groups[norm_content].append(elem_id)
    
    for norm_content, elem_ids in content_groups.items():
        if len(elem_ids) <= 1:
            continue
        elem_ids_sorted = sorted(elem_ids)
        for idx, elem_id in enumerate(elem_ids_sorted, start=1):
            original_content = elements[elem_id]
            updated_elements[elem_id] = f"{original_content} {idx:02d}"
            
    return updated_elements

def dedupe_elements(elements, hierarchy):
    """dedupe các elements có cùng content (exact match)"""
    content_groups = defaultdict(list)
    
    for elem_id, content in elements.items():
        elem_type = get_type(elem_id)
        key = (elem_type, content)
        content_groups[key].append(elem_id)
    
    id_mapping = {}
    new_elements = {}
    counters = defaultdict(int)
    
    for (elem_type, content), elem_ids in content_groups.items():
        paper_id = extract_paper_id(elem_ids[0])
        counters[elem_type] += 1
        new_id = f"{elem_type}-{paper_id}-{counters[elem_type]:03d}"
        
        for old_id in elem_ids:
            id_mapping[old_id] = new_id
        
        new_elements[new_id] = content
    
    return new_elements, id_mapping

def extract_paper_id(element_id):
    """trích xuất paper id từ element id"""
    parts = element_id.split('-')
    if len(parts) >= 2:
        return parts[1]
    return "unknown"

def update_hierarchy(hierarchy, id_mapping):
    """cập nhật hierarchy với id mapping mới"""
    new_hierarchy = {}
    
    for version, relations in hierarchy.items():
        new_hierarchy[version] = {}
        for child_id, parent_id in relations.items():
            new_child = id_mapping.get(child_id, child_id)
            new_parent = id_mapping.get(parent_id, parent_id)
            new_hierarchy[version][new_child] = new_parent
    
    return new_hierarchy

def process_paper(paper_dir):
    """xử lý 1 paper - ghi đè hierarchy.json"""
    hierarchy_path = paper_dir / 'hierarchy.json'
    
    if not hierarchy_path.exists():
        return None
    
    try:
        with open(hierarchy_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError:
        print(f"Lỗi đọc file: {hierarchy_path}")
        return None
    
    elements = data.get('elements', {})
    hierarchy = data.get('hierarchy', {})
    original_count = len(elements)
    
    # Step 1: Merge v2+ documents vào v1
    elements, hierarchy = merge_versions(elements, hierarchy)
    
    # Step 2: Thêm số cho TYPES_ALWAYS_NUMBER
    elements = add_number_suffix(elements, hierarchy)
    
    # Step 3: Dedupe exact match
    new_elements, id_mapping = dedupe_elements(elements, hierarchy)
    
    # Step 4: Update hierarchy
    new_hierarchy = update_hierarchy(hierarchy, id_mapping)
    
    # Ghi đè hierarchy.json
    output = {'elements': new_elements, 'hierarchy': new_hierarchy}
    try:
        with open(hierarchy_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Lỗi ghi file {hierarchy_path}: {e}")
        return None
    
    new_count = len(new_elements)
    print(f"  {paper_dir.name}: {original_count} → {new_count} (-{original_count - new_count})")
    
    return original_count, new_count

def process_all_papers():
    """chạy trên toàn bộ data"""
    total_original = 0
    total_new = 0
    processed = 0
    
    print("Chạy text deduplication trên TOÀN BỘ data, ghi vào hierarchy.json...")
    
    for paper_dir in sorted(DATA_DIR.iterdir()):
        if not paper_dir.is_dir() or not paper_dir.name.startswith('2411-'):
            continue
        
        result = process_paper(paper_dir)
        if result:
            orig, new = result
            total_original += orig
            total_new += new
            processed += 1
            
            if processed % 100 == 0:
                print(f"Đã xử lý {processed} papers...")
    
    print(f"\n{'='*60}")
    print(f"Tổng kết: {processed} papers")
    print(f"Elements: {total_original} → {total_new} (-{total_original - total_new})")

if __name__ == '__main__':
    process_all_papers()
