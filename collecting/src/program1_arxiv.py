


# Cài thư viện cần thiết


# ======================== PHẦN CHÍNH ========================
import ssl
ssl._create_default_https_context = ssl._create_unverified_context

# ---- Thư viện chuẩn ----
import os, tarfile, json, time, requests, feedparser, re, gzip, shutil, csv, psutil
import arxiv
from bs4 import BeautifulSoup
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---- Cấu hình ----
BASE_DIR = Path("D:/23120257")
BASE_DIR.mkdir(parents=True, exist_ok=True)
START_MONTH = "2024-11"
STATS_FILE = BASE_DIR / "statistics_program1.csv"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; ArxivDownloader/1.0; +https://arxiv.org)"
})

# Nếu file thống kê chưa tồn tại → tạo header
if not STATS_FILE.exists():
    with open(STATS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "arxiv_id", "success_rate", "size_before_figures",
            "size_after_figures", "runtime_sec",
            "ram_usage_mb", "disk_usage_mb"
        ])

# ---------------------- HÀM HỖ TRỢ ----------------------
"""Tạo thư mục nếu chưa tồn tại."""
def safe_mkdir(path: Path):
    path.mkdir(parents=True, exist_ok=True)



def fetch_versions_html(arxiv_id: str):
    """Lấy danh sách các phiên bản v1, v2, ... từ HTML arXiv."""
    url = f"https://arxiv.org/abs/{arxiv_id}"
    try:
        res = session.get(url, timeout=10)
        if res.status_code != 200:
            return ["v1"]
        soup = BeautifulSoup(res.text, "html.parser")
        history = soup.find("div", {"class": "submission-history"})
        if not history:
            return ["v1"]
         # Regex tìm các ký hiệu [v1], [v2], ...
        versions = re.findall(r"\[(v\d+)\]", history.text)
        return versions or ["v1"]
    except Exception:
        return ["v1"]


"""Lấy các ngày revised (v2 trở đi)."""
def fetch_revised_dates(arxiv_id: str, submission_date: str):
    url = f"https://arxiv.org/abs/{arxiv_id}"
    try:
        res = session.get(url, timeout=10)
        if res.status_code != 200:
            return []
        soup = BeautifulSoup(res.text, "html.parser")
        history = soup.find("div", {"class": "submission-history"})
        if not history:
            return []
        dates = set()
        # Regex trích ngày “Wed, 13 Nov 2024 00:00:00 UTC”
        date_lines = re.findall(r"\[(v\d+)\]\s+(.*?)UTC", history.text)
        for _, text_date in date_lines:
            try:
                dt = datetime.strptime(text_date.strip(), "%a, %d %b %Y %H:%M:%S")
                d = dt.strftime("%Y-%m-%d")
            except ValueError:
              # fallback nếu format khác
                m = re.search(r"\d{1,2} \w+ \d{4}", text_date)
                if not m:
                    continue
                dt = datetime.strptime(m.group(), "%d %b %Y")
                d = dt.strftime("%Y-%m-%d")
            if d != submission_date:
                dates.add(d)
        return sorted(list(dates))
    except Exception:
        return []


"""Lấy metadata từ arxiv API (title, authors, date, category...)."""
def fetch_metadata(arxiv_id: str):
    try:
        search = arxiv.Search(id_list=[arxiv_id], max_results=1)
        result = next(arxiv.Client(page_size=1, delay_seconds=0.5).results(search))
        submission_date = result.published.strftime("%Y-%m-%d")
        revised_dates = fetch_revised_dates(arxiv_id, submission_date)
        cats = ", ".join(result.categories) if result.categories else "Unknown"
        metadata = {
            "title": result.title.strip(),
            "authors": [a.name for a in result.authors],
            "summary": result.summary.strip(),
            "submission_date": submission_date,
            "revised_dates": revised_dates,
            "publication_venue": result.journal_ref or "arXiv preprint",
            "pdf_url": result.pdf_url,
            "category": cats
        }
        return metadata, result
    except Exception as e:
        print(f"[ERROR] {arxiv_id}: {e}")
        return None, None


def get_gzip_original_name(gz_path: Path) -> str | None:
    """
    Đọc tên file gốc (FNAME) từ header .gz nếu có.
    Trả về None nếu không có tên hoặc lỗi định dạng.
    """
    try:
        with open(gz_path, "rb") as f:
            # Magic bytes
            if f.read(2) != b"\x1f\x8b":
                return None
            method = f.read(1)
            flg = ord(f.read(1))
            f.read(6)  # mtime + extra flags + OS

            # Nếu có FEXTRA (bit 2)
            if flg & 0x04:
                xlen = int.from_bytes(f.read(2), "little")
                f.read(xlen)

            # Nếu có FNAME (bit 3)
            if flg & 0x08:
                original_name = b""
                while True:
                    ch = f.read(1)
                    if not ch or ch == b"\x00":
                        break
                    original_name += ch
                return original_name.decode("utf-8", errors="ignore")

            # Nếu có FCOMMENT (bit 4)
            if flg & 0x10:
                while True:
                    if f.read(1) == b"\x00":
                        break

        return None
    except Exception:
        return None



def is_tar_gz(file_path: Path) -> bool:
    """
    Kiểm tra file .gz có phải là tar archive (tar.gz) hay không.
    → True nếu là .tar.gz
    → False nếu chỉ là .gz nén 1 file duy nhất (.tex, .bib, ...)
    """
    try:
        with gzip.open(file_path, 'rb') as f:
            header = f.read(512)  # đọc 512 byte đầu tiên
            return b'ustar' in header  # dấu hiệu đặc trưng của file tar
    except Exception:
        return False


def extract_file(tar_path: Path, dest_dir: Path):
    """
    Giải nén file nén (.tar.gz hoặc .gz) vào dest_dir, chỉ giữ .tex và .bib.
    Phân biệt loại file dựa trên phần mở rộng tạm thời (tar.gz hoặc gz).
    """
    print(f"    [INFO] Bắt đầu giải nén file: {tar_path.name}")
    if is_tar_gz(tar_path):
        # Xử lý .tar.gz (archive)
        try:
            with tarfile.open(tar_path, "r:gz") as tar:
                for member in tar.getmembers():    # duyệt từng entry trong tarball
                    name = member.name.lower()     # tên file viết thường
                    if any(name.endswith(ext) for ext in [".tex", ".bib"]):
                        tar.extract(member, path=dest_dir)     # chỉ extract .tex/.bib
        except Exception as e:
            print(f"    [WARN] Lỗi giải nén .tar.gz {tar_path.name}: {e}")

    else: # Nếu file có phần mở rộng .gz
        try:
            original_name = get_gzip_original_name(tar_path) # Đọc tên file gốc từ header GZIP
            if original_name is None:   # Nếu không có tên gốc trong header
                original_name = Path(tar_path.stem).name  # fallback dùng tên file nén bỏ đuôi .gz

            # Loại bỏ đường dẫn (nếu có)
            original_name = os.path.basename(original_name)
            output_path = dest_dir / original_name   # Tạo đường dẫn lưu file giải nén

            with gzip.open(tar_path, "rb") as f_in, open(output_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)        #  Giải nén nội dung từ .gz ra file thật
        except Exception as e:
            print(f"    [WARN] Lỗi giải nén .gz {tar_path.name}: {e}")


def measure_dir_size(path: Path) -> int:
    """Tính tổng dung lượng (byte) của thư mục."""
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += (Path(root) / f).stat().st_size
            except FileNotFoundError:
                pass
    return total



"""Tải tất cả phiên bản (v1, v2,...) và giải nén ra tex/."""
def download_versions(result, arxiv_id: str, save_root: Path):
    try:
        versions = fetch_versions_html(arxiv_id)
        print(f"    [INFO] Phát hiện {len(versions)} phiên bản cho {arxiv_id}")

        tex_root = save_root / "tex"
        safe_mkdir(tex_root)

        # biến đo kích thước source & trạng thái tải thành công hay không
        size_before = 0
        size_after = 0
        success_flag = 0

        for ver_label in versions:
            print(f"    [INFO] Đang tải source cho {arxiv_id}{ver_label} ...")
            source_url = f"https://arxiv.org/e-print/{arxiv_id}{ver_label}"
            version_folder = f"{arxiv_id.replace('.', '-')}{ver_label}"
            ver_path = tex_root / version_folder
            safe_mkdir(ver_path)

            try:
              # --- Tải file nén .tar.gz ---
                res = session.get(source_url, timeout=20)
                if res.status_code != 200:
                    print(f"    [WARN] {arxiv_id}{ver_label}: HTTP {res.status_code}, bỏ qua.")
                    continue

                head = res.content[:4]
                if not (head.startswith(b"\x1f\x8b") or head.startswith(b"PK")):
                    print(f"    [WARN] {arxiv_id}{ver_label}: Không phải file nén hợp lệ (startswith={head!r})")
                    continue

                tmp = save_root / f"{arxiv_id}{ver_label}.tar.gz"
                with open(tmp, "wb") as f:
                    f.write(res.content)

                 #  tính size trước khi lọc hình
                size_before += tmp.stat().st_size


                  # --- Giải nén ---
                tmp_extract = save_root / f"temp_extract_{ver_label}"
                safe_mkdir(tmp_extract)
                extract_file(tmp, tmp_extract)

                tex_count = bib_count = 0
                 # --- Lọc chỉ .tex và .bib ---
                for root, _, files in os.walk(tmp_extract):
                    for file in files:
                        src = Path(root) / file
                        ext = file.lower().strip()
                        if ext.endswith(".tex") or ext.endswith(".bib"):
                            shutil.move(str(src), ver_path / file)
                            if ext.endswith(".tex"):
                                tex_count += 1
                            else:
                                bib_count += 1
                os.remove(tmp)
                shutil.rmtree(tmp_extract, ignore_errors=True)

                # Nếu không có file thì xoá folder rỗng
                if tex_count == 0 and bib_count == 0:
                    shutil.rmtree(ver_path, ignore_errors=True)
                    print(f"    [INFO] Version {version_folder} không có file .tex/.bib → bỏ qua.")
                else:
                    success_flag = 1  # success nếu có tex/bib
                    print(f"    [DONE] {version_folder}: {tex_count} tex, {bib_count} bib")
            except Exception as e:
                print(f"    [ERROR] {arxiv_id}{ver_label}: {e}")
                shutil.rmtree(ver_path, ignore_errors=True)


        size_after = measure_dir_size(tex_root) # kích thước sau khi lọc hình
        
        # Xóa nếu thư mục tex trống
        if not any(tex_root.glob("**/*")):
            shutil.rmtree(tex_root, ignore_errors=True)
        
        # >>> BỔ SUNG: trả về dữ liệu thống kê
        return success_flag, size_before, size_after

    except Exception as e:
        print(f"[ERROR] Không thể xử lý versions của {arxiv_id}: {e}")
        return 0, 0, 0

# ---------------------- CHẠY SONG SONG ----------------------
def process_one(arxiv_id: str, delay: float = 2.0):
  """Xử lý 1 paper: lấy metadata + tải version."""
  print(f"\n[INFO] === {arxiv_id} ===")
    #  đo thời gian và RAM ban đầu
  t0 = time.time()
  process = psutil.Process(os.getpid())
  ram_before = process.memory_info().rss
  

  metadata, result = fetch_metadata(arxiv_id)
  if not metadata:
        print(f"[WARN] {arxiv_id}: bỏ qua.")
        return

  paper_dir = BASE_DIR / arxiv_id.replace(".", "-")
  safe_mkdir(paper_dir)

     # Ghi metadata.json
  with open(paper_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

     # Gọi tải các version của paper
  success_flag, size_before, size_after = download_versions(result, arxiv_id, paper_dir)
  time.sleep(delay)
  

    #  đo thời gian, RAM, disk
  runtime = time.time() - t0
  ram_after = process.memory_info().rss
  ram_used_mb = (ram_after - ram_before) / (1024 * 1024)
  disk_usage_mb = (size_before + size_after) / (1024 * 1024)

    # > ghi dòng thống kê vào CSV
  with open(STATS_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            arxiv_id, success_flag, size_before, size_after,
            round(runtime, 2), round(ram_used_mb, 2),
            round(disk_usage_mb, 2)
        ])

  print(f"[DONE] {arxiv_id} | success={success_flag} | runtime={runtime:.1f}s | RAM={ram_used_mb:.1f}MB | size_after={size_after/1e6:.2f}MB")



def main(start_id: int, end_id: int, delay: float = 2.0, parallelism: int = 4):
 """Chạy song song nhiều ID theo khoảng chỉ định."""
 prefix = START_MONTH[2:].replace("-", "")
 all_ids = [f"{prefix}.{i:05d}" for i in range(start_id, end_id + 1)]
 print(f"[INFO] Xử lý {len(all_ids)} paper ({parallelism} luồng song song)\n")

# ThreadPoolExecutor → chạy đa luồng
 with ThreadPoolExecutor(max_workers=parallelism) as executor:
        futures = [executor.submit(process_one, arxiv_id, delay) for arxiv_id in all_ids]
        for fut in as_completed(futures):
            fut.result()
 print("\n=== HOÀN TẤT ===")

# ---------------------- THỰC THI ----------------------
main(10222, 10227, delay=2.5, parallelism=3)
