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

## 2. Project Structure

```
23120257/
├── 23120257/                    # Source papers (5000 papers)
│   └── {paper_id}/
│       ├── hierarchy.json
│       ├── metadata.json
│       ├── refs.bib
│       ├── references.json
│       └── pred.json
│
├── data_modelling/              # Processed data (636 papers)
│   └── {paper_id}/
│       ├── refs_cleaned.json
│       ├── references_cleaned.json
│       ├── ground_truth.json
│       └── pred.json
│
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
│
├── README.md
└── Report.pdf                   # User report
```

---

## 3. Source Files Description

### 3.1 Hierarchical Parsing 

| File | Description |
|------|-------------|
| `multifile_gathering_01.py` | Tìm main .tex file từ nhiều .tex files |
| `multifile_gathering_02.py` | Xử lý `\input`, `\include` để gom nội dung |
| `hierarchy_construction.py` | Parse LaTeX → cấu trúc phân cấp `hierarchy.json` |
| `normalization_format_math.py` | Chuẩn hóa inline/block math, xóa LaTeX commands không cần |
| `reference_extraction.py` | Trích xuất `\bibitem` → BibTeX format |
| `bib_deduplication.py` | Xử lý duplicate bib entries, tạo `refs.bib` |
| `text_deduplication.py` | Xử lý duplicate text content trong hierarchy |

### 3.2 Reference Matching 

| File | Description |
|------|-------------|
| `data_selection.py` | Chọn papers có đủ dữ liệu cho training |
| `data_cleaning.py` | Text preprocessing: lowercasing, stopword removal |
| `data_labelling.py` | Tạo `ground_truth.json` từ matching rules |
| `feature_engineering.py` | Tạo 15 features cho mỗi (bib, candidate) pair |
| `eda.py` | Phân tích dữ liệu các nhóm features, vẽ biểu đồ so sánh positive/negative |
| `model_comparison.py` | So sánh XGBoost vs Naive Bayes vs Logistic Regression |
| `model_training.py` | Train XGBoost + GridSearchCV + Early stopping |
| `model_evaluation.py` | Tính MRR và Hit Rate trên train/valid/test |

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
