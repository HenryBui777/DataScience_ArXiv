# ========================  CELL 3 – PHÂN TÍCH & VẼ BIỂU ĐỒ ========================
# Chức năng:
#   - Đọc dữ liệu thống kê từ statistics_program1.csv và statistics_program2.csv
#   - Tính toán các chỉ số tổng hợp cho chương trình 1 & 2
#   - Ghi toàn bộ thông tin ra file text summary_statistics.txt
#   - Vẽ 3 biểu đồ: 2 pie chart (success rate), 1 line chart (RAM theo thời gian)

import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
import os

BASE_DIR = Path("D:/23120257")
CSV1 = BASE_DIR / "statistics_program1.csv"
CSV2 = BASE_DIR / "statistics_program2.csv"
SUMMARY_FILE = BASE_DIR / "summary_statistics.txt"

# Hàm lấy kích thích tổng của output 
def get_dir_size(path: Path) -> float:
    """Tính tổng dung lượng thư mục (MB), bao gồm tất cả file con."""
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = Path(dirpath) / f
            if fp.is_file():
                total += fp.stat().st_size
    return total / (1024 * 1024)  # Đổi sang MB

def get_final_output_size(base_dir: Path) -> float:
    """Tính dung lượng output cuối cùng (MB), trừ 2 file CSV thống kê."""
    total_size = get_dir_size(base_dir)
    csv_files = [
        BASE_DIR / "statistics_program1.csv",
        BASE_DIR / "statistics_program2.csv",
        BASE_DIR / "summary_statistics.txt"
    ]
    csv_total = sum(f.stat().st_size for f in csv_files if f.exists()) / (1024 * 1024)
    return total_size - csv_total

final_output_disk = get_final_output_size(BASE_DIR)

# ======================== ĐỌC DỮ LIỆU ========================
df1 = pd.read_csv(CSV1)
df2 = pd.read_csv(CSV2)

# ======================== PHÂN TÍCH CHƯƠNG TRÌNH 1 ========================
total_papers_1 = len(df1)
success_papers_1 = df1["success_rate"].sum()
overall_success_rate_1 = success_papers_1 / total_papers_1 if total_papers_1 else 0

avg_size_before = df1["size_before_figures"].mean()
avg_size_after = df1["size_after_figures"].mean()
avg_runtime_1 = df1["runtime_sec"].mean()
total_runtime_1 = df1["runtime_sec"].sum()
max_ram_1 = df1["ram_usage_mb"].max()
max_disk_1 = df1["disk_usage_mb"].max()
avg_ram_1 = df1["ram_usage_mb"].mean()

# ======================== PHÂN TÍCH CHƯƠNG TRÌNH 2 ========================
total_papers_2 = len(df2)
success_papers_2 = df2["success_rate"].sum()
overall_success_rate_2 = success_papers_2 / total_papers_2 if total_papers_2 else 0

avg_ref_per_paper = df2["ref_numbers"].mean()
avg_runtime_2 = df2["runtime_sec"].mean()
total_runtime_2 = df2["runtime_sec"].sum()
max_ram_2 = df2["ram_usage_mb"].max()
max_disk_2 = df2["disk_usage_mb"].max()
avg_ram_2 = df2["ram_usage_mb"].mean()

# ======================== TỔNG HỢP CẢ 2 CHƯƠNG TRÌNH ========================
total_runtime_all = total_runtime_1 + total_runtime_2
avg_runtime_all = avg_runtime_1 + avg_runtime_2
max_ram_all = max_ram_1 + max_ram_2
avg_ram_all = avg_ram_1 + avg_ram_2

# ======================== GHI FILE SUMMARY ========================
with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
    f.write("===== PROGRAM 1 – ARXIV CRAWLER =====\n")
    f.write(f"• Tổng số bài báo xử lý: {total_papers_1}\n")
    f.write(f"• Số bài crawl thành công: {success_papers_1}\n")
    f.write(f"• Overall success rate: {overall_success_rate_1:.2%}\n")
    f.write(f"• Kích thước trung bình trước khi loại figures: {avg_size_before:.2f} bytes\n")
    f.write(f"• Kích thước trung bình sau khi loại figures: {avg_size_after:.2f} bytes\n")
    f.write(f"• Thời gian trung bình xử lý 1 bài: {avg_runtime_1:.2f} s\n")
    f.write(f"• Tổng thời gian crawl: {total_runtime_1:.2f} s\n")
    f.write(f"• Maximum RAM sử dụng: {max_ram_1:.2f} MB\n")
    f.write(f"• Maximum Disk sử dụng: {max_disk_1:.2f} MB\n")
    f.write(f"• Trung bình RAM cho 1 bài: {avg_ram_1:.2f} MB\n\n")

    f.write("===== PROGRAM 2 – REFERENCES CRAWLER =====\n")
    f.write(f"• Tổng số bài xử lý: {total_papers_2}\n")
    f.write(f"• Số bài references thành công: {success_papers_2}\n")
    f.write(f"• Overall success rate: {overall_success_rate_2:.2%}\n")
    f.write(f"• Số references trung bình mỗi paper: {avg_ref_per_paper:.2f}\n")
    f.write(f"• Thời gian trung bình xử lý 1 bài: {avg_runtime_2:.2f} s\n")
    f.write(f"• Tổng thời gian crawl references: {total_runtime_2:.2f} s\n")
    f.write(f"• Maximum RAM sử dụng: {max_ram_2:.2f} MB\n")
    f.write(f"• Maximum Disk sử dụng: {max_disk_2:.2f} MB\n")
    f.write(f"• Trung bình RAM cho 1 bài: {avg_ram_2:.2f} MB\n\n")

    f.write("===== TỔNG HỢP CẢ 2 CHƯƠNG TRÌNH =====\n")
    f.write(f"• Tổng thời gian crawl (1+2): {total_runtime_all:.2f} s\n")
    f.write(f"• Thời gian trung bình 1 bài (1+2): {avg_runtime_all:.2f} s\n")
    f.write(f"• Tổng RAM sử dụng (1+2): {max_ram_all:.2f} MB\n")
    f.write(f"• Trung bình RAM mỗi bài (1+2): {avg_ram_all:.2f} MB\n")
    f.write(f"• Final output storage size: {final_output_disk:.2f} MB\n")
print(f" Đã ghi báo cáo tổng hợp vào {SUMMARY_FILE}")

# ======================== VẼ BIỂU ĐỒ ========================

# --- Pie chart – Success rate chương trình 1 ---
plt.figure(figsize=(5,5))
plt.pie(
    [success_papers_1, total_papers_1 - success_papers_1],
    labels=["Success (1)", "Fail (0)"],
    autopct="%1.1f%%",
    colors=["#4CAF50", "#F44336"]
)
plt.title("Tỉ lệ crawl thành công – Program 1 (Arxiv)")
plt.show()

# --- Pie chart – Success rate chương trình 2 ---
plt.figure(figsize=(5,5))
plt.pie(
    [success_papers_2, total_papers_2 - success_papers_2],
    labels=["Success (1)", "Fail (0)"],
    autopct="%1.1f%%",
    colors=["#2196F3", "#FFC107"]
)
plt.title("Tỉ lệ crawl references thành công – Program 2 (Semantic Scholar)")
plt.show()

# --- Line chart – RAM sử dụng theo thời gian (Program 1 + 2) ---
plt.figure(figsize=(8,5))
plt.plot(df1["ram_usage_mb"], label="Program 1 – Arxiv", marker="o")
plt.plot(df2["ram_usage_mb"], label="Program 2 – References", marker="x")
plt.xlabel("Paper index")
plt.ylabel("RAM sử dụng (MB)")
plt.title("Biểu đồ RAM sử dụng theo thời gian (Program 1 & 2)")
plt.legend()
plt.grid(True)
plt.show()
