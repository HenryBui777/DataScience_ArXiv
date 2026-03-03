# Introduction to Data Science – Lab 01  

**Instructor:** Mr. Huynh Lam Hai Dang

**Topic:** Scraping metadata, full-text source, and references metadata of scientific papers from arXiv
---


##  Arxiv & Semantic Scholar Scraper  


**Objective:** 

Build a system to collect research papers from **arXiv.org** and **Semantic Scholar** for data analysis.

The system consists of 3 programs:  
1. **Program 1 – arXiv Scraper:** Scrapes metadata and downloads all `.tex` and `.bib` source files for each paper from **arXiv.org**.
2. **Program 2 – References Scraper:** Collects reference lists from **Semantic Scholar**.  
3. **Program 3 – Analyze Statistics:** Aggregates and calculates statistical indices and plots performance charts.

---

## Directory Structure

```
├── src/                                # Source code 
│   ├── program1_arxiv.py               # Program 1
│   ├── program2_references.py          # Program 2
│   ├── analyze_statistics.py           # Program 3
│   ├── requirements.txt                # Import libraries
│   └── ggcolab.ipynb                   # Google Colab

```
##  Environment Setup  

### 🔹 System Requirements
- Python **>= 3.12**
- Operating System: **Windows** or **Google Colab CPU-only**


---

### 🔹 Virtual Environment & Library Installation

```bash
cd src
python -m venv venv312
venv312\Scripts\activate
pip install -r requirements.txt

```

## Running the Code  

⚠️ Note:

- The three programs operate independently and can be run separately.
- Avoid running Program 1 and Program 2 simultaneously as both access APIs in parallel, which may lead to rate limiting.
- When running on Google Colab, simply use the `ggcolab.ipynb` file (pre-configured with 3 cells corresponding to the 3 programs).
- The default base directory is `D:/23120257`, start month and end month are `24-11` (November 2024), start ID and end ID are `10222` and `15211` respectively.
- API key is "AQhxAYRK4e6rL5J7gNEwa7xDqGxYbFFy6AI0d3np"
###  **1️⃣ Run Source Download and Extraction (Program 1 – arXiv)**
```bash
python src/program1_arxiv.py
```
- Downloaded and extracted `.tex` and `.bib` files will be written to individual `{arxiv-id}/tex/` folders in the main directory.
- Generated statistics file: `statistics_program1.csv`.
- The number of parallel processes can be changed based on machine configuration; however, more than 4 processes are not recommended to avoid rate limits or data transmission bottlenecks.
- A delay of ≥ 1.5s between each request is recommended to avoid being blocked by the arXiv API.
- In the `main(10222, 10242, delay=2.5, parallelism=8)` function: parameter 1 is start ID, parameter 2 is end ID, `delay` is the rest time between requests, and `parallelism` is the number of parallel threads.

### **2️⃣ Run Reference Download from Semantic Scholar (Program 2 – References)**
```bash
python src/program2_references.py
```
- `references.json` files will be saved in each `{arxiv-id}/` folder.
- Generated statistics file: `statistics_program2.csv`.
- The number of parallel processes can be changed, but it is recommended not to exceed 4 threads.
- Each item in the reference list corresponds to a separate request → if the number of references is large, processing time will be longer.
- In the `run_program2(parallelism=8, delay=5.0)` function: `delay` is the rest time between requests, `parallelism` is the number of parallel threads, and the function will add `references.json` to the arXiv folders created in Program 1.

###  3️⃣ Run Analysis and Plotting (Program 3 – Analyze Statistics)
```bash
python src/analyze_statistics.py
```
- Aggregated statistics results are recorded in:
→ `summary_statistics.txt`

- Automatically generated charts:
1. Pie chart – successful crawl rate (Program 1)
2. Pie chart – successful reference crawl rate (Program 2)
3. Line chart – RAM usage over time

