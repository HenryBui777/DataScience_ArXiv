"""
EDA - Phân tích dữ liệu các nhóm đặc trưng
Vẽ biểu đồ so sánh positive vs negative cho từng nhóm feature
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

# Config
DATA_DIR = Path(r"D:\23120257\data_modelling")
FEATURES_FILE = DATA_DIR / "features.csv"

# Load data
print("Loading data...")
df = pd.read_csv(FEATURES_FILE)
print(f"Total pairs: {len(df)}")
print(f"Positive: {df['label'].sum()}, Negative: {len(df) - df['label'].sum()}")

# Sample để vẽ nhanh hơn
pos_df = df[df['label'] == 1].sample(min(5000, len(df[df['label'] == 1])), random_state=42)
neg_df = df[df['label'] == 0].sample(min(5000, len(df[df['label'] == 0])), random_state=42)

# ============================================================
# NHÓM 1: TITLE FEATURES
# ============================================================
print("\n" + "=" * 50)
print("NHÓM 1: TITLE FEATURES")
print("=" * 50)

title_features = ['title_seq_sim', 'title_jaccard', 'title_levenshtein', 
                  'title_tfidf_sim', 'title_ngram_overlap', 'title_trigram_overlap', 'title_len_ratio']

fig, axes = plt.subplots(2, 4, figsize=(16, 8))
axes = axes.flatten()

for i, feat in enumerate(title_features):
    ax = axes[i]
    ax.hist(pos_df[feat], bins=30, alpha=0.7, label='Positive', color='green', density=True)
    ax.hist(neg_df[feat], bins=30, alpha=0.7, label='Negative', color='red', density=True)
    ax.set_xlabel(feat)
    ax.set_ylabel('Density')
    ax.legend()
    
    # Print stats
    print(f"{feat}:")
    print(f"  Positive - Mean: {pos_df[feat].mean():.4f}, Std: {pos_df[feat].std():.4f}")
    print(f"  Negative - Mean: {neg_df[feat].mean():.4f}, Std: {neg_df[feat].std():.4f}")

axes[-1].axis('off')  # Hide empty subplot
plt.suptitle('Title Features: Positive vs Negative', fontsize=14)
plt.tight_layout()
plt.savefig(DATA_DIR / 'eda_title_features.png', dpi=150)
plt.close()
print(f"\nSaved: eda_title_features.png")

# ============================================================
# NHÓM 2: AUTHOR FEATURES
# ============================================================
print("\n" + "=" * 50)
print("NHÓM 2: AUTHOR FEATURES")
print("=" * 50)

author_features = ['author_jaccard', 'author_tfidf_sim', 'first_author_match', 
                   'num_common_authors', 'author_count_diff']

fig, axes = plt.subplots(2, 3, figsize=(14, 8))
axes = axes.flatten()

for i, feat in enumerate(author_features):
    ax = axes[i]
    ax.hist(pos_df[feat], bins=30, alpha=0.7, label='Positive', color='green', density=True)
    ax.hist(neg_df[feat], bins=30, alpha=0.7, label='Negative', color='red', density=True)
    ax.set_xlabel(feat)
    ax.set_ylabel('Density')
    ax.legend()
    
    print(f"{feat}:")
    print(f"  Positive - Mean: {pos_df[feat].mean():.4f}, Std: {pos_df[feat].std():.4f}")
    print(f"  Negative - Mean: {neg_df[feat].mean():.4f}, Std: {neg_df[feat].std():.4f}")

axes[-1].axis('off')
plt.suptitle('Author Features: Positive vs Negative', fontsize=14)
plt.tight_layout()
plt.savefig(DATA_DIR / 'eda_author_features.png', dpi=150)
plt.close()
print(f"\nSaved: eda_author_features.png")

# ============================================================
# NHÓM 3: YEAR FEATURES
# ============================================================
print("\n" + "=" * 50)
print("NHÓM 3: YEAR FEATURES")
print("=" * 50)

year_features = ['year_diff', 'year_exact_match']

fig, axes = plt.subplots(1, 2, figsize=(12, 5))

for i, feat in enumerate(year_features):
    ax = axes[i]
    ax.hist(pos_df[feat], bins=30, alpha=0.7, label='Positive', color='green', density=True)
    ax.hist(neg_df[feat], bins=30, alpha=0.7, label='Negative', color='red', density=True)
    ax.set_xlabel(feat)
    ax.set_ylabel('Density')
    ax.legend()
    
    print(f"{feat}:")
    print(f"  Positive - Mean: {pos_df[feat].mean():.4f}, Std: {pos_df[feat].std():.4f}")
    print(f"  Negative - Mean: {neg_df[feat].mean():.4f}, Std: {neg_df[feat].std():.4f}")

plt.suptitle('Year Features: Positive vs Negative', fontsize=14)
plt.tight_layout()
plt.savefig(DATA_DIR / 'eda_year_features.png', dpi=150)
plt.close()
print(f"\nSaved: eda_year_features.png")

# ============================================================
# COMBINED SCORE
# ============================================================
print("\n" + "=" * 50)
print("COMBINED SCORE")
print("=" * 50)

plt.figure(figsize=(10, 5))
plt.hist(pos_df['combined_score'], bins=50, alpha=0.7, label='Positive', color='green', density=True)
plt.hist(neg_df['combined_score'], bins=50, alpha=0.7, label='Negative', color='red', density=True)
plt.xlabel('combined_score')
plt.ylabel('Density')
plt.title('Combined Score: Positive vs Negative')
plt.legend()
plt.savefig(DATA_DIR / 'eda_combined_score.png', dpi=150)
plt.close()

print(f"combined_score:")
print(f"  Positive - Mean: {pos_df['combined_score'].mean():.4f}, Std: {pos_df['combined_score'].std():.4f}")
print(f"  Negative - Mean: {neg_df['combined_score'].mean():.4f}, Std: {neg_df['combined_score'].std():.4f}")
print(f"\nSaved: eda_combined_score.png")

# ============================================================
# CORRELATION HEATMAP
# ============================================================
print("\n" + "=" * 50)
print("CORRELATION MATRIX")
print("=" * 50)

all_features = title_features + author_features + year_features + ['combined_score', 'label']
corr = df[all_features].corr()

plt.figure(figsize=(14, 12))
plt.imshow(corr, cmap='RdBu_r', aspect='auto', vmin=-1, vmax=1)
plt.colorbar(label='Correlation')
plt.xticks(range(len(all_features)), all_features, rotation=45, ha='right')
plt.yticks(range(len(all_features)), all_features)
plt.title('Feature Correlation Matrix')
plt.tight_layout()
plt.savefig(DATA_DIR / 'eda_correlation.png', dpi=150)
plt.close()
print(f"\nSaved: eda_correlation.png")

print("\n" + "=" * 50)
print("EDA COMPLETE!")
print("=" * 50)
print("Output files:")
print("  - eda_title_features.png")
print("  - eda_author_features.png")
print("  - eda_year_features.png")
print("  - eda_combined_score.png")
print("  - eda_correlation.png")
