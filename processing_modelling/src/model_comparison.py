"""
Model Comparison - XGBoost vs Naive Bayes vs Logistic Regression
So sánh 3 mô hình với MRR metric
"""

import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import GaussianNB
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
import xgboost as xgb
from sklearn.metrics import f1_score, accuracy_score, precision_score, recall_score

# Config
DATA_DIR = Path(r"D:\23120257\data_modelling")
FEATURES_FILE = DATA_DIR / "features.csv"
N_PAPERS = 100

FEATURE_COLS = [
    'title_seq_sim', 'title_jaccard', 'title_levenshtein', 'author_jaccard',
    'title_tfidf_sim', 'author_tfidf_sim',
    'title_ngram_overlap', 'title_trigram_overlap',
    'first_author_match', 'num_common_authors', 'author_count_diff',
    'year_diff', 'year_exact_match',
    'title_len_ratio', 'combined_score'
]

def calculate_mrr(test_df, proba, feature_cols):
    """Tính Mean Reciprocal Rank"""
    test_df = test_df.copy()
    test_df['proba'] = proba
    
    reciprocal_ranks = []
    for bib_key in test_df['bib_key'].unique():
        bib_df = test_df[test_df['bib_key'] == bib_key]
        
        # Sort by probability descending
        bib_df = bib_df.sort_values('proba', ascending=False).reset_index(drop=True)
        
        # Find rank of correct answer (label=1)
        correct_idx = bib_df[bib_df['label'] == 1].index
        if len(correct_idx) > 0:
            rank = correct_idx[0] + 1  # 1-indexed
            reciprocal_ranks.append(1.0 / rank)
        else:
            reciprocal_ranks.append(0.0)
    
    return np.mean(reciprocal_ranks) if reciprocal_ranks else 0.0

# Load data
print("Loading data...")
df = pd.read_csv(FEATURES_FILE)

# Random 100 papers
all_papers = df['paper_id'].unique()
np.random.seed(42)
selected_papers = np.random.choice(all_papers, size=min(N_PAPERS, len(all_papers)), replace=False)
df = df[df['paper_id'].isin(selected_papers)]

print(f"Papers: {len(selected_papers)}, Pairs: {len(df)}")

# Split 80/20 by paper
train_papers, test_papers = train_test_split(selected_papers, test_size=0.2, random_state=42)
train_df = df[df['paper_id'].isin(train_papers)]
test_df = df[df['paper_id'].isin(test_papers)]

X_train, y_train = train_df[FEATURE_COLS], train_df['label']
X_test, y_test = test_df[FEATURE_COLS], test_df['label']

# Class weight
pos = y_train.sum()
neg = len(y_train) - pos
weight = neg / pos if pos > 0 else 1

# Scale for LR and NB
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

print(f"\nTrain: {len(train_df)} pairs, Test: {len(test_df)} pairs")

# Train 3 models
print("\nTraining models...")

# 1. XGBoost
xgb_model = xgb.XGBClassifier(scale_pos_weight=weight, random_state=42, eval_metric='logloss')
xgb_model.fit(X_train, y_train)
xgb_pred = xgb_model.predict(X_test)
xgb_proba = xgb_model.predict_proba(X_test)[:, 1]

# 2. Naive Bayes (weaker baseline)
nb_model = GaussianNB()
nb_model.fit(X_train_scaled, y_train)
nb_pred = nb_model.predict(X_test_scaled)
nb_proba = nb_model.predict_proba(X_test_scaled)[:, 1]

# 3. Logistic Regression
lr_model = LogisticRegression(class_weight={0:1, 1:weight}, max_iter=1000, random_state=42)
lr_model.fit(X_train_scaled, y_train)
lr_pred = lr_model.predict(X_test_scaled)
lr_proba = lr_model.predict_proba(X_test_scaled)[:, 1]

# Calculate MRR
xgb_mrr = calculate_mrr(test_df, xgb_proba, FEATURE_COLS)
nb_mrr = calculate_mrr(test_df, nb_proba, FEATURE_COLS)
lr_mrr = calculate_mrr(test_df, lr_proba, FEATURE_COLS)

# Results
print("\n" + "=" * 65)
print("RESULTS")
print("=" * 65)
print(f"{'Model':<20} {'F1':>8} {'Accuracy':>10} {'Precision':>10} {'Recall':>8} {'MRR':>8}")
print("-" * 65)

for name, pred, proba, mrr in [
    ('XGBoost', xgb_pred, xgb_proba, xgb_mrr), 
    ('Naive Bayes', nb_pred, nb_proba, nb_mrr), 
    ('Logistic Regression', lr_pred, lr_proba, lr_mrr)
]:
    f1 = f1_score(y_test, pred)
    acc = accuracy_score(y_test, pred)
    prec = precision_score(y_test, pred, zero_division=0)
    rec = recall_score(y_test, pred)
    print(f"{name:<20} {f1:>8.4f} {acc:>10.4f} {prec:>10.4f} {rec:>8.4f} {mrr:>8.4f}")

print("=" * 65)
