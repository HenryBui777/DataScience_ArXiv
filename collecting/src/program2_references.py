# Cài đặt thư viện cần thiết

import os, json, time, requests, random, csv
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import psutil
# ========================  CẤU HÌNH ========================
# Thư mục chứa dữ liệu đầu vào (đã crawl từ Giai đoạn 1)
BASE_DIR = Path("D:/23120257")
BASE_DIR.mkdir(parents=True, exist_ok=True)



# ========================  SEMANTIC SCHOLAR API ========================

# Nhập API key của bạn tại đây:
API_KEY = "AQhxAYRK4e6rL5J7gNEwa7xDqGxYbFFy6AI0d3np"  #  thay bằng key thật

# Tạo session HTTP chung
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "x-api-key": API_KEY  # <--- thêm dòng này
})

STATS_FILE_REF = BASE_DIR / "statistics_program2.csv"

# Endpoint chính của Semantic Scholar API
SEMANTIC_API = "https://api.semanticscholar.org/graph/v1/paper/arXiv:{}"

# Tạo file CSV nếu chưa có
if not STATS_FILE_REF.exists():
    with open(STATS_FILE_REF, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "arxiv_id", "success_rate", "ref_numbers",
            "runtime_sec", "ram_usage_mb", "disk_usage_mb"
        ])

# ======================== HÀM CHÍNH GỌI API ========================

def fetch_references(arxiv_id: str, max_retries: int = 5):
    """
    Gọi Semantic Scholar API để lấy danh sách references cho 1 paper cụ thể.
    - Nếu HTTP 429 → tự động chờ ngẫu nhiên rồi thử lại.
    - Trả về dict chứa các paper tham chiếu có arXiv ID.
    """

    url = SEMANTIC_API.format(arxiv_id)
    params = {
        "fields": (
            "references.title,references.authors,references.externalIds,"
            "references.venue,references.paperId,references.publicationDate,"
            "references.corpusId,references.fieldsOfStudy"
        )
    }

    for attempt in range(1, max_retries + 1):
        try:
            res = session.get(url, params=params, timeout=20)

            #  Thành công → phân tích JSON trả về
            if res.status_code == 200:
                data = res.json() or {}
                refs_raw = data.get("references", [])
                refs = {}
            # Lọc ra những reference có arXiv ID
                for r in refs_raw:
                    ext = r.get("externalIds") or {}
                    ref_arx = ext.get("ArXiv") or ext.get("arXiv")
                    if not ref_arx:
                        continue

                    key = ref_arx.replace(".", "-")
                    refs[key] = {
                        "title": r.get("title", "").strip(),
                        "authors": [a.get("name") for a in (r.get("authors") or []) if isinstance(a, dict)],
                        "publication_date": r.get("publicationDate") or "",
                        "venue": r.get("venue") or "arXiv reference",
                        "semantic_scholar_id": r.get("paperId") or "",
                        "corpus_id": r.get("corpusId") or "",
                        "category": ", ".join(r.get("fieldsOfStudy", []) or [])
                    }

                return refs

            #  Nếu bị rate limit
            elif res.status_code == 429:
                wait_time = random.uniform(6, 10)
                print(f"[WARN] {arxiv_id}: HTTP 429 (Rate limit) → chờ {wait_time:.1f}s rồi thử lại ({attempt}/{max_retries})")
                time.sleep(wait_time)
                continue
           #  Lỗi HTTP khác (404, 500, …)
            else:
                print(f"[WARN] {arxiv_id}: HTTP {res.status_code}")
                return {}
          # Nếu gặp lỗi mạng hoặc timeout
        except Exception as e:
            print(f"[ERROR] {arxiv_id} (thử {attempt}/{max_retries}): {e}")
            time.sleep(5)

    # Nếu hết số lần retry mà vẫn lỗi
    print(f"[FAIL] {arxiv_id}: quá số lần retry ({max_retries})")
    return {}


# ======================== HÀM XỬ LÝ MỖI PAPER ========================

def process_one_reference(folder: Path, delay: float = 3.0):
  """
    Tạo file `references.json` cho 1 paper cụ thể.
    - Lấy ID từ tên thư mục 
    - Bỏ qua nếu file đã tồn tại.
     Các chỉ số thống kê:
      - success_rate: 1 nếu có reference, 0 nếu không
      - ref_numbers: tổng số reference lấy được
      - runtime_sec: thời gian xử lý 1 paper
      - ram_usage_mb: dung lượng RAM sử dụng
      - disk_usage_mb: kích thước file references.json
    """
   # Nếu đã có file thì bỏ qua
  arxiv_id = folder.name.replace("-", ".")
  ref_file = folder / "references.json"
    
    # Ghi nhận thời gian và RAM ban đầu
  t0 = time.time()
  process = psutil.Process(os.getpid())
  ram_before = process.memory_info().rss
  success_flag = 0
  ref_numbers = 0 
  disk_usage = 0
  

  if ref_file.exists():
        print(f"[SKIP] {arxiv_id}: đã có references.json")
        return
  
 # Gọi API để lấy dữ liệu
  refs = fetch_references(arxiv_id)

# Ghi ra file JSON
  with open(ref_file, "w", encoding="utf-8") as f:
        json.dump(refs, f, indent=2, ensure_ascii=False)

# Đếm số reference và đánh dấu thành công
  ref_numbers = len(refs)
  if ref_numbers > 0:
        success_flag = 1

# Tính toán RAM, disk, runtime
  runtime = time.time() - t0
  ram_after = process.memory_info().rss
  ram_used_mb = (ram_after - ram_before) / (1024 * 1024)
  disk_usage = ref_file.stat().st_size if ref_file.exists() else 0
  disk_usage_mb = disk_usage / (1024 * 1024)

   #  BỔ SUNG: Ghi dòng thống kê vào CSV
  with open(STATS_FILE_REF, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            arxiv_id, success_flag, ref_numbers,
            round(runtime, 2), round(ram_used_mb, 2),
            round(disk_usage_mb, 2)
        ])

    # >>> Ghi log ra màn hình
  print(f"[DONE] {arxiv_id} | success={success_flag} | refs={ref_numbers} | runtime={runtime:.2f}s | RAM={ram_used_mb:.2f}MB | disk={disk_usage_mb:.2f}MB")

  print(f"[DONE] {arxiv_id}: {len(refs)} references")
  time.sleep(delay)

# ======================== HÀM XỬ LÝ SONG SONG ========================
def run_program2(parallelism=8, delay=5.0):
    """
    📘 Hàm: run_program2
    --------------------
    Chức năng:
      - Duyệt qua tất cả các thư mục paper trong BASE_DIR
      - Gọi process_one_references() cho mỗi paper song song bằng ThreadPoolExecutor
      - Ghi log và tổng kết sau khi hoàn tất
    """
    folders = [p for p in BASE_DIR.iterdir() if p.is_dir()]
    print(f"[INFO] Tổng số paper cần xử lý: {len(folders)}")

    #  Chạy đa luồng
    with ThreadPoolExecutor(max_workers=parallelism) as ex:
        futs = [ex.submit(process_one_reference, f) for f in folders]
        for f in as_completed(futs):
            f.result()
            time.sleep(delay)

    print("\n=== PROGRAM 2 HOÀN TẤT ===")

# ======================== THỰC THI CHÍNH ========================
run_program2()
