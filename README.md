# DataScience_ArXiv

## Project Structure

```
├── data/                        # Source papers (optional files below)
│   └── {paper_id}/
│       ├── hierarchy.json       # (Optional)
│       ├── refs.bib             # (Optional)
│       ├── metadata.json        # (Optional)
│       ├── references.json      # (Optional)
│       └── pred.json            # (Optional)
│
├── processing_modelling/        # Processed data & Modelling
│   ├── src/                     # Source code
│   │   ├── bib_deduplication.py
│   │   ├── data_cleaning.py
│   │   ├── data_labelling.py
│   │   ├── data_selection.py
│   │   ├── eda.py
│   │   ├── feature_engineering.py
│   │   ├── hierarchy_construction.py
│   │   ├── model_comparison.py
│   │   ├── model_evaluation.py
│   │   ├── model_training.py
│   │   ├── multifile_gathering_01.py
│   │   ├── multifile_gathering_02.py
│   │   ├── normalization_format_math.py
│   │   ├── reference_extraction.py
│   │   ├── requirements.txt
│   │   └── text_deduplication.py
│   ├── README.md
│   └── Report.pdf               # Data processing and modelling report
│
└── collecting/                  # Data collection module
    ├── src/                     # Source code
    │   ├── program1_arxiv.py
    │   ├── program2_references.py
    │   ├── analyze_statistics.py
    │   └── ggcolab.ipynb
    ├── README.md
    └── Report.docx              # Data collection report
```

### Note on `{paper_id}`
The paper directory is named follows the arXiv **YYMM-NNNNN** format (e.g., `2411-10222`), where:
- **YYMM**: Year and Month of publication (e.g., `2411` represents November 2024).
- **NNNNN**: A unique identifier for the paper within that month.
