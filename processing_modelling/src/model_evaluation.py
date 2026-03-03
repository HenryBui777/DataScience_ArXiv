"""
Model Evaluation Script for Reference Matching
- Load pred.json from each paper
- Calculate MRR và Hit Rate cho train/valid/test
"""

import json
import numpy as np
import sys
from pathlib import Path

# Config
DATA_DIR = Path(r"D:\23120257\data_modelling")
LOG_FILE = DATA_DIR / "evaluation_log.txt"

# Logger
class Logger:
    def __init__(self, filepath):
        self.terminal = sys.stdout
        self.log = open(filepath, 'w', encoding='utf-8')
    
    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
    
    def flush(self):
        self.terminal.flush()
        self.log.flush()

sys.stdout = Logger(LOG_FILE)


def calculate_mrr(predictions: dict, ground_truth: dict) -> float:
    """Calculate Mean Reciprocal Rank"""
    reciprocal_ranks = []
    
    for bib_key, true_id in ground_truth.items():
        if bib_key in predictions:
            pred_list = predictions[bib_key]
            if true_id in pred_list:
                rank = pred_list.index(true_id) + 1
                rr = 1.0 / rank
            else:
                rr = 0.0
            reciprocal_ranks.append(rr)
    
    return np.mean(reciprocal_ranks) if reciprocal_ranks else 0.0


def calculate_hit_rate(predictions: dict, ground_truth: dict, k: int) -> float:
    """Calculate Hit Rate at K (Top-K accuracy)"""
    hits = 0
    total = 0
    
    for bib_key, true_id in ground_truth.items():
        if bib_key in predictions:
            pred_list = predictions[bib_key][:k]
            if true_id in pred_list:
                hits += 1
            total += 1
    
    return hits / total if total > 0 else 0.0


def load_papers_by_partition():
    """Load all pred.json and group by partition"""
    partitions = {'train': [], 'valid': [], 'test': []}
    
    for paper_dir in DATA_DIR.iterdir():
        if not paper_dir.is_dir():
            continue
        
        pred_path = paper_dir / "pred.json"
        if not pred_path.exists():
            continue
        
        with open(pred_path, 'r', encoding='utf-8') as f:
            pred_data = json.load(f)
        
        partition = pred_data.get('partition', 'train')
        partitions[partition].append({
            'paper_id': paper_dir.name,
            'ground_truth': pred_data.get('groundtruth', {}),
            'predictions': pred_data.get('prediction', {})
        })
    
    return partitions


def evaluate_partition(partition_name: str, papers: list, show_detail: bool = True):
    """Evaluate a partition (train/valid/test)"""
    all_predictions = {}
    all_ground_truth = {}
    paper_mrrs = []
    
    for paper in papers:
        paper_id = paper['paper_id']
        ground_truth = paper['ground_truth']
        predictions = paper['predictions']
        
        # Calculate MRR per paper
        paper_mrr = calculate_mrr(predictions, ground_truth)
        paper_mrrs.append((paper_id, paper_mrr, len(ground_truth)))
        
        # Collect for overall
        for k, v in ground_truth.items():
            all_ground_truth[f"{paper_id}_{k}"] = v
        for k, v in predictions.items():
            all_predictions[f"{paper_id}_{k}"] = v
    
    # Calculate overall metrics
    mrr = calculate_mrr(all_predictions, all_ground_truth)
    hit1 = calculate_hit_rate(all_predictions, all_ground_truth, k=1)
    hit3 = calculate_hit_rate(all_predictions, all_ground_truth, k=3)
    hit5 = calculate_hit_rate(all_predictions, all_ground_truth, k=5)
    total_refs = len(all_ground_truth)
    
    # Print results
    print(f"\n{'='*50}")
    print(f"{partition_name.upper()} SET ({len(papers)} papers, {total_refs} refs)")
    print(f"{'='*50}")
    
    if show_detail and len(papers) <= 10:
        print(f"\nMRR từng paper:")
        for paper_id, p_mrr, n_refs in paper_mrrs:
            print(f"  {paper_id}: MRR = {p_mrr:.4f} ({n_refs} refs)")
    
    print(f"\n{'Metric':<25} {'Value':>10}")
    print("-" * 37)
    print(f"{'MRR':<25} {mrr:>10.4f}")
    print(f"{'Hit@1 (Matching Top-1)':<25} {hit1:>10.2%}")
    print(f"{'Hit@3 (Matching Top-3)':<25} {hit3:>10.2%}")
    print(f"{'Hit@5 (Matching Top-5)':<25} {hit5:>10.2%}")
    
    return mrr, hit1, hit5


def main():
    print("=" * 50)
    print("MODEL EVALUATION")
    print("=" * 50)
    
    # Load all papers grouped by partition
    print("\nLoading predictions...")
    partitions = load_papers_by_partition()
    
    print(f"Train: {len(partitions['train'])} papers")
    print(f"Valid: {len(partitions['valid'])} papers")
    print(f"Test: {len(partitions['test'])} papers")
    
    # Evaluate each partition
    train_mrr, train_hit1, train_hit5 = evaluate_partition("Train", partitions['train'], show_detail=False)
    valid_mrr, valid_hit1, valid_hit5 = evaluate_partition("Valid", partitions['valid'], show_detail=True)
    test_mrr, test_hit1, test_hit5 = evaluate_partition("Test", partitions['test'], show_detail=True)
    
    # Summary
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    print(f"\n{'Partition':<10} {'MRR':>10} {'Hit@1':>10} {'Hit@5':>10}")
    print("-" * 42)
    print(f"{'Train':<10} {train_mrr:>10.4f} {train_hit1:>10.2%} {train_hit5:>10.2%}")
    print(f"{'Valid':<10} {valid_mrr:>10.4f} {valid_hit1:>10.2%} {valid_hit5:>10.2%}")
    print(f"{'Test':<10} {test_mrr:>10.4f} {test_hit1:>10.2%} {test_hit5:>10.2%}")
    
    print(f"\nLog saved to: {LOG_FILE}")


if __name__ == '__main__':
    main()
