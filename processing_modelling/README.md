# Hierarchical Parsing and Standardization & Reference Matching Pipeline

## 1. Environment Setup

### 1.1 Requirements

```
Python 3.12.7
```

### 1.2 Install Dependencies

```bash
pip install -r src/requirements.txt
```

---

## 2. Structure

```
├── src/                         # Source code
│   ├── multifile_gathering_01.py
│   ├── multifile_gathering_02.py
│   ├── hierarchy_construction.py
│   ├── normalization_format_math.py
│   ├── reference_extraction.py
│   ├── bib_deduplication.py
│   ├── text_deduplication.py
│   ├── data_selection.py
│   ├── data_cleaning.py
│   ├── data_labelling.py
│   ├── feature_engineering.py
│   ├── eda.py
│   ├── model_comparison.py
│   ├── model_training.py
│   ├── model_evaluation.py
│   └── requirements.txt

```

---

## 3. Source Files Description

### 3.1 Hierarchical Parsing 

| File | Description |
|------|-------------|
| `multifile_gathering_01.py` | Find main .tex file from multiple .tex files |
| `multifile_gathering_02.py` | Process `\input`, `\include` to gather content |
| `hierarchy_construction.py` | Parse LaTeX → hierarchical structure `hierarchy.json` |
| `normalization_format_math.py` | Normalize inline/block math, remove unnecessary LaTeX commands |
| `reference_extraction.py` | Extract `\bibitem` → BibTeX format |
| `bib_deduplication.py` | Handle duplicate bib entries, create `refs.bib` |
| `text_deduplication.py` | Handle duplicate text content in hierarchy |

### 3.2 Reference Matching 

| File | Description |
|------|-------------|
| `data_selection.py` | Select papers with sufficient data for training |
| `data_cleaning.py` | Text preprocessing: lowercasing, stopword removal |
| `data_labelling.py` | Create `ground_truth.json` based on matching rules |
| `feature_engineering.py` | Create 15 features for each (bib, candidate) pair |
| `eda.py` | Analyze feature groups, plot positive/negative comparison charts |
| `model_comparison.py` | Compare XGBoost vs Naive Bayes vs Logistic Regression |
| `model_training.py` | Train XGBoost + GridSearchCV + Early stopping |
| `model_evaluation.py` | Calculate MRR and Hit Rate on train/valid/test |

---

## 4. Pipeline Execution

### Step 1: Hierarchical Parsing 

```bash
py src/multifile_gathering_01.py
py src/multifile_gathering_02.py
py src/hierarchy_construction.py
py src/normalization_format_math.py
py src/reference_extraction.py
py src/bib_deduplication.py
py src/text_deduplication.py
```

### Step 2: Reference Matching 

```bash
py src/data_selection.py
py src/data_cleaning.py
py src/data_labelling.py
py src/feature_engineering.py
py src/eda.py
py src/model_comparison.py
py src/model_training.py
py src/model_evaluation.py
```

---

## 5. Data Split

| Set | Papers | Purpose |
|-----|--------|---------|
| Train | 632 | Model learning |
| Valid | 2 | Early stopping |
| Test | 2 | Final evaluation (MRR) |
