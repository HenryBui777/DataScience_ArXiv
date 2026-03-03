"""
Data Modeling Script for Reference Matching
- Split data: Train/Valid/Test
- Train XGBoost classifier with GridSearchCV
- Predict Top 5 candidates
- Output pred.json for each paper
"""

import json
import pandas as pd
import numpy as np
import sys
from pathlib import Path
from sklearn.model_selection import train_test_split
import xgboost as xgb
from collections import defaultdict
from sklearn.model_selection import GridSearchCV
from sklearn.metrics import f1_score, accuracy_score

# Config
DATA_DIR = Path(r"D:\23120257\data_modelling")
FEATURES_FILE = DATA_DIR / "features.csv"
LOG_FILE = DATA_DIR / "training_log.txt"

# Custom print function to log to both console and file
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

# Setup logging
sys.stdout = Logger(LOG_FILE)

# 5 bài manual (từ data_selection.py)
MANUAL_PAPERS = [
    "2411-10224",
    "2411-10231", 
    "2411-10232",
    "2411-10261",
    "2411-10281"
]

# Feature columns (phải khớp với feature_engineering.py)
FEATURE_COLS = [
    'title_seq_sim', 'title_jaccard', 'title_levenshtein', 'author_jaccard',
    'title_tfidf_sim', 'author_tfidf_sim',
    'title_ngram_overlap', 'title_trigram_overlap',
    'first_author_match', 'num_common_authors', 'author_count_diff',
    'year_diff', 'year_exact_match',
    'title_len_ratio', 'combined_score'
]


def split_papers_by_partition(df: pd.DataFrame):
    """
    Split papers into train/valid/test
    - Test: 1 manual + 1 auto
    - Valid: 1 manual + 1 auto
    - Train: còn lại
    """
    all_papers = df['paper_id'].unique().tolist()
    
    # Tách manual và auto papers
    manual = [p for p in all_papers if p in MANUAL_PAPERS]
    auto = [p for p in all_papers if p not in MANUAL_PAPERS]
    
    print(f"Manual papers: {len(manual)}")
    print(f"Auto papers: {len(auto)}")
    
    # Split
    # Test: 1 manual + 1 auto
    test_papers = [manual[0], auto[0]]
    
    # Valid: 1 manual + 1 auto
    valid_papers = [manual[1], auto[1]]
    
    # Train: còn lại
    train_papers = manual[2:] + auto[2:]
    
    return train_papers, valid_papers, test_papers


def create_partitioned_data(df: pd.DataFrame):
    """Create train/valid/test DataFrames"""
    train_papers, valid_papers, test_papers = split_papers_by_partition(df)
    
    train_df = df[df['paper_id'].isin(train_papers)]
    valid_df = df[df['paper_id'].isin(valid_papers)]
    test_df = df[df['paper_id'].isin(test_papers)]
    
    print(f"\nData split:")
    print(f"  Train: {len(train_papers)} papers, {len(train_df)} pairs")
    print(f"  Valid: {len(valid_papers)} papers, {len(valid_df)} pairs")
    print(f"  Test: {len(test_papers)} papers, {len(test_df)} pairs")
    
    return train_df, valid_df, test_df, train_papers, valid_papers, test_papers


def train_xgboost(train_df: pd.DataFrame, valid_df: pd.DataFrame):
    """Train XGBoost classifier with GridSearchCV"""
   
    
    X_train = train_df[FEATURE_COLS]
    y_train = train_df['label']
    
    X_valid = valid_df[FEATURE_COLS]
    y_valid = valid_df['label']
    
    # Handle imbalanced data
    pos_count = y_train.sum()
    neg_count = len(y_train) - pos_count
    scale_pos_weight = neg_count / pos_count if pos_count > 0 else 1
    
    print(f"\nTraining XGBoost with GridSearchCV...")
    print(f"  Positive: {pos_count}, Negative: {neg_count}")
    print(f"  scale_pos_weight: {scale_pos_weight:.2f}")
    
    # Hyperparameter grid
    param_grid = {
        'n_estimators': [50, 100, 200],
        'max_depth': [4, 6, 8],
        'learning_rate': [0.05, 0.1, 0.2]
    }
    
    base_model = xgb.XGBClassifier(
        scale_pos_weight=scale_pos_weight,
        random_state=42,
        use_label_encoder=False,
        eval_metric='logloss'
    )
    
    # GridSearchCV với 3-fold
    grid_search = GridSearchCV(
        base_model,
        param_grid,
        cv=3,
        scoring='f1',
        n_jobs=-1,
        verbose=1
    )
    
    print("\nSearching best hyperparameters...")
    grid_search.fit(X_train, y_train)
    
    best_params = grid_search.best_params_
    print(f"\nBest parameters: {best_params}")
    print(f"Best CV F1 score: {grid_search.best_score_:.4f}")
    
    # Retrain với best params + early stopping
    print("\nRetraining with early stopping...")
    model = xgb.XGBClassifier(
        n_estimators=best_params['n_estimators'] * 3,  # 3x để early stopping có room
        max_depth=best_params['max_depth'],
        learning_rate=best_params['learning_rate'],
        scale_pos_weight=scale_pos_weight,
        random_state=42,
        use_label_encoder=False,
        eval_metric='logloss',
        early_stopping_rounds=20
    )
    
    model.fit(
        X_train, y_train,
        eval_set=[(X_valid, y_valid)],
        verbose=False
    )
    
    print(f"  Best iteration: {model.best_iteration}")
    print(f"  Best score: {model.best_score:.4f}")
    
    # Evaluate on validation set
    y_pred = model.predict(X_valid)
    valid_f1 = f1_score(y_valid, y_pred)
    valid_acc = accuracy_score(y_valid, y_pred)
    print(f"\nValidation metrics:")
    print(f"  F1 Score: {valid_f1:.4f}")
    print(f"  Accuracy: {valid_acc:.4f}")
    
    # Feature importance
    print("\nFeature importance (top 10):")
    importance = pd.DataFrame({
        'feature': FEATURE_COLS,
        'importance': model.feature_importances_
    }).sort_values('importance', ascending=False)
    print(importance.head(10).to_string(index=False))
    
    return model


def predict_top5_for_paper(model, paper_df: pd.DataFrame, feature_cols: list) -> dict:
    """Predict Top 5 candidates for each bib entry"""
    X = paper_df[feature_cols]
    proba = model.predict_proba(X)[:, 1]
    
    paper_df = paper_df.copy()
    paper_df['score'] = proba
    
    predictions = {}
    for bib_key in paper_df['bib_key'].unique():
        bib_df = paper_df[paper_df['bib_key'] == bib_key]
        top5 = bib_df.nlargest(5, 'score')['candidate_id'].tolist()
        predictions[bib_key] = top5
    
    return predictions


def save_pred_json(paper_id: str, partition: str, ground_truth: dict, predictions: dict):
    """Save pred.json to both data_modelling and original 23120257"""
    import shutil
    
    output = {
        "partition": partition,
        "groundtruth": ground_truth,
        "prediction": predictions
    }
    
    # Save to data_modelling
    output_path = DATA_DIR / paper_id / "pred.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    # Copy to original 23120257
    original_path = Path(r"D:\23120257\23120257") / paper_id / "pred.json"
    if original_path.parent.exists():
        shutil.copy(output_path, original_path)


def save_partition_info(train_papers, valid_papers, test_papers):
    """Save partition info for model_evaluation.py"""
    info = {
        "train": train_papers,
        "valid": valid_papers,
        "test": test_papers
    }
    path = DATA_DIR / "partition_info.json"
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(info, f, indent=2)
    print(f"Partition info saved to: {path}")


def main():
    print("Loading features...")
    df = pd.read_csv(FEATURES_FILE)
    print(f"Loaded {len(df)} pairs from {df['paper_id'].nunique()} papers")
    
    # Split data
    train_df, valid_df, test_df, train_papers, valid_papers, test_papers = create_partitioned_data(df)
    
    # Save partition info for evaluation
    save_partition_info(train_papers, valid_papers, test_papers)
    
    # Train model
    model = train_xgboost(train_df, valid_df)
    
    # Save model
    model_path = DATA_DIR / "xgboost_model.json"
    model.save_model(model_path)
    print(f"\nModel saved to: {model_path}")
    
    # Generate predictions and save pred.json
    print("\n" + "=" * 50)
    print("GENERATING PREDICTIONS")
    print("=" * 50)
    
    for partition, papers in [("train", train_papers), ("valid", valid_papers), ("test", test_papers)]:
        print(f"\n{partition.upper()} SET ({len(papers)} papers):")
        
        for paper_id in papers:
            paper_df = df[df['paper_id'] == paper_id]
            if len(paper_df) == 0:
                continue
            
            # Load ground truth
            gt_path = DATA_DIR / paper_id / "ground_truth.json"
            if not gt_path.exists():
                continue
            
            with open(gt_path, 'r', encoding='utf-8') as f:
                ground_truth = json.load(f)
            
            # Predict
            predictions = predict_top5_for_paper(model, paper_df, FEATURE_COLS)
            
            # Save pred.json
            save_pred_json(paper_id, partition, ground_truth, predictions)
            print(f"  {paper_id}: saved pred.json")
    
    print("\n" + "=" * 50)
    print("TRAINING COMPLETE!")
    print("=" * 50)
    print("pred.json saved to each paper folder.")
    print("Next step: Run model_evaluation.py to calculate MRR")


if __name__ == '__main__':
    main()


