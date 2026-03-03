# Introduction to Data Science – Lab 01  

**Giáo viên hướng dẫn:** Thầy Huỳnh Lâm Hải Đăng

**Tên đề tài:** Crawl dữ liệu metadata, full-text source và references metadata của các bài nghiên cứu khoa học trên trang web arXiv
---


##  Arxiv & Semantic Scholar Scraper  


**Mục tiêu:** 

Xây dựng hệ thống thu thập dữ liệu bài báo từ **arXiv.org** và **Semantic Scholar**, phục vụ cho việc phân tích dữ liệu.

Hệ thống gồm 3 chương trình:  
1. **Program 1 – arXiv Scraper:** Crawl metadata, tải toàn bộ source `.tex`, `.bib` của mỗi bài báo từ **arXiv.org**.
2. **Program 2 – References Scraper:** Thu thập danh sách references từ **Semantic Scholar**.  
3. **Program 3 – Analyze Statistics:** Tổng hợp, tính toán các chỉ số thống kê và vẽ biểu đồ hiệu năng.

---

## Cấu trúc thư mục

```
23120257/
│
├── src/                                # chứa source 
│   ├── program1_arxiv.py               # Program 1
│   ├── program2_references.py          # Program 2
│   ├── analyze_statistics.py           # Program 3
│   ├── requirements.txt                # thư viện import
│   └── ggcolab.ipynb                   # Google Colab
│
├── statistics_program1.csv             # Kết quả thống kê của chương trình 1 (nếu chạy program 1)
├── statistics_program2.csv             # Kết quả thống kê của chương trình 2 (nếu chạy program 2)
├── summary_statistics.txt              # Báo cáo tổng hợp cuối cùng (nếu chạy program 3)
│
├── <yymm-id>/                          # dir bài báo
│   ├── tex/                            # Source.tex/.bib
│   │   ├── <yymm-id>v<version>/        # từng version
│   │   │   ├── *.tex                   # Các file TeX
│   │   │   ├── *.bib                   # File bib
│   │   │   └── <subfolders>/           # Các thư mục phụ
│   │   │       ├── *.tex
│   │   │       └── *.bib
│   │   │
│   │   └── ... (recursively theo cấu trúc gốc của source arXiv)
│   │
│   ├── metadata.json                   # Metadata của bài báo
│   └── references.json                 # Danh sách references từ Semantic Scholar
│
├── README.md                           # Hướng dẫn setup & chạy code
└── Report.docx          # Báo cáo chính 

```
##  Environment Setup  

### 🔹 Yêu cầu hệ thống
- Python **>= 3.12**
- Hệ điều hành **Windows** hoặc **Google Colab CPU-only**


---

### 🔹 Tạo môi trường ảo & cài đặt thư viện

```bash
cd 23120257/src
python -m venv venv312
venv312\Scripts\activate
pip install -r requirements.txt

```

##  Hướng dẫn chạy code  

⚠️ Chú ý:

- Ba chương trình hoạt động độc lập nên có thể chạy riêng từng phần.

- Không khuyến khích chạy Program 1 và Program 2 cùng lúc vì cả hai đều truy cập API song song → dễ gây rate limit.

- Khi chạy trên Google Colab, chỉ cần dùng file ggcolab.ipynb (đã gom sẵn 3 cell tương ứng 3 chương trình).

- Base directory mặc định là `D:/23120257`, start month và end month là `24-11` (tháng 11 năm 2024), start ID và end ID lần lượt là `10222` và `15211`.
- API key là "AQhxAYRK4e6rL5J7gNEwa7xDqGxYbFFy6AI0d3np"
---

###  **1️⃣ Chạy tải source và giải nén (Program 1 – arXiv)**
```bash
python src/program1_arxiv.py

```
- Các file .tex và .bib được tải và giải nén sẽ ghi vào từng thư mục <arxiv-id>/tex/ trong thư mục chính.

- File thống kê tạo ra: statistics_program1.csv.

- Có thể thay đổi số lượng process chạy song song tùy theo cấu hình máy, tuy nhiên không khuyến khích quá 4 process để tránh rate limit hoặc nghẽn truyền dữ liệu.

- Nên đặt delay ≥ 1.5s giữa mỗi request để tránh bị chặn bởi arXiv API.

- Trong hàm main(10222, 10242, delay=2.5, parallelism=8), tham số 1 là start ID, tham số 2 là end ID, tham số delay là số giây nghĩ giữa mỗi request, tham số parallellism là số luồng chạy song song. 

### **2️⃣ Chạy tải references từ Semantic Scholar (Program 2 – References)**
```bash
python src/program2_references.py
```
- Các file references.json sẽ được lưu trong từng thư mục <arxiv-id>/.

- File thống kê tạo ra: statistics_program2.csv.

- Có thể thay đổi số process song song nhưng khuyến nghị không vượt quá 4 luồng.

- Mỗi phần tử trong danh sách reference tương ứng một request riêng → nếu số lượng references lớn, thời gian xử lý sẽ lâu hơn.

- Trong hàm run_program2(parallelism=8, delay=5.0), tham số delay là số giây nghĩ giữa mỗi request, tham số parallellism là số luồng chạy song song và hàm sẽ thêm references.json vào những thư mục của arXiv đã tạo ở chương trình 1.

###  3️⃣ Chạy phân tích và vẽ biểu đồ (Program 3 – Analyze Statistics)
```bash
python src/analyze_statistics.py
```
- Kết quả thống kê tổng hợp được ghi vào file:
→ summary_statistics.txt

- Các biểu đồ được sinh tự động:

1. Pie chart – tỉ lệ crawl thành công (Program 1)

2. Pie chart – tỉ lệ reference crawl thành công (Program 2)

3. Line chart – RAM sử dụng theo thời gian

