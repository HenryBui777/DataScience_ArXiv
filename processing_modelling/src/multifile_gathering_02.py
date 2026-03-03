from __future__ import annotations
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# ============================================================
# Config
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_ROOT = BASE_DIR.parent / "23120257"   # thư mục chứa data

# True = xóa các file .tex không phải main sau khi flatten xong 
DO_DELETE = True

# ============================================================
# Regex patterns cho các loại input/include file có thể có
# - "include" sẽ bị ảnh hưởng bởi includeonly
# - "input" thì không bị includeonly ảnh hưởng 
# ============================================================

INCLUDE_CMD_SPECS: List[Tuple[str, str]] = [
    ("input",   r"\\input\s*\{(?P<file>[^}]+)\}"),
    ("include", r"\\include\s*\{(?P<file>[^}]+)\}"),
    ("input",   r"\\InputIfFileExists\s*\{(?P<file>[^}]+)\}\s*\{[^}]*\}\s*\{[^}]*\}"),
    ("input",   r"\\subfile\s*\{(?P<file>[^}]+)\}"),
    ("input",   r"\\import\s*\{(?P<path>[^}]+)\}\s*\{(?P<file>[^}]+)\}"),
    ("input",   r"\\inputfrom\s*\{(?P<path>[^}]+)\}\s*\{(?P<file>[^}]+)\}"),
    ("input",   r"\\subimport\s*\{(?P<path>[^}]+)\}\s*\{(?P<file>[^}]+)\}"),
]

INCLUDEONLY_PATTERN = r"\\includeonly\s*\{(?P<list>[^}]+)\}"

# ============================================================
# Regex patterns cho các loại comment thường gặp
# ============================================================

COMMENT_ENV_RE = re.compile(
    r"\\begin\{comment\}.*?\\end\{comment\}",
    re.DOTALL | re.IGNORECASE
)

# \iffalse ... \fi (hay gặp để comment block)
IFFALSE_BLOCK_RE = re.compile(
    r"\\iffalse\b.*?\\fi\b",
    re.DOTALL | re.IGNORECASE
)

# ============================================================
# Helpers
# ============================================================

def strip_tex_comments(tex: str) -> str:
    """
    Xóa comment trong LaTeX để:
    - Không bắt nhầm các lệnh include/input nằm trong comment
    - Làm sạch output main sau flatten (theo yêu cầu m)

    Quy ước:
    - Xóa block \\begin{comment}...\\end{comment}
    - Xóa block \\iffalse ... \\fi
    - Với comment theo dòng: cắt từ dấu % trở đi
      (trừ trường hợp \\% là kí tự percent literal)
    """
    tex = COMMENT_ENV_RE.sub("", tex)
    tex = IFFALSE_BLOCK_RE.sub("", tex)

    out_lines: List[str] = []
    for line in tex.splitlines():
        i = 0
        while True:
            j = line.find("%", i)
            if j == -1:
                out_lines.append(line)
                break
            # \% là percent literal, không phải comment
            if j > 0 and line[j - 1] == "\\":
                i = j + 1
                continue
            out_lines.append(line[:j])
            break

    return "\n".join(out_lines)


def normalize_ref(s: str) -> str:
    """Chuẩn hóa tên file trong lệnh include/input: strip, bỏ quote."""
    return s.strip().strip('"').strip("'").strip()


def split_brace_list(s: str) -> List[str]:
    """Tách a,b,c trong \\includeonly{a,b,c}."""
    return [p.strip() for p in s.split(",") if p.strip()]


def build_tex_index(version_dir: Path) -> Dict[str, List[Path]]:
    """
    Tạo index để resolve nhanh file tex:
    - theo relative path (vd: sections/intro.tex)
    - theo filename (vd: intro.tex)
    - theo stem (vd: intro)
    """
    idx: Dict[str, List[Path]] = {}
    for p in version_dir.rglob("*.tex"):
        rel = p.relative_to(version_dir).as_posix()
        idx.setdefault(rel, []).append(p)
        idx.setdefault(p.name, []).append(p)
        idx.setdefault(p.stem, []).append(p)
    return idx


def resolve_tex_target(
    raw_ref: str,
    version_dir: Path,
    idx: Dict[str, List[Path]],
    import_path: Optional[str] = None,
) -> Optional[Path]:
    """
    Resolve ref trong \\input/\\include/... thành file .tex thật.
    Có xử lí đường dẫn:
    - ref có thể là "chap1" hoặc "chap1.tex"
    - ref có thể có path "sections/chap1"
    - các lệnh import/subimport/inputfrom có thêm import_path
    """
    ref = normalize_ref(raw_ref)
    if not ref:
        return None

    # ghép path nếu có (import/subimport/inputfrom)
    if import_path:
        ref = (Path(normalize_ref(import_path)) / ref).as_posix()

    # Chuẩn hóa ./ và //
    ref = Path(ref).as_posix()

    candidates: List[str] = []
    candidates.append(ref)
    if not ref.endswith(".tex"):
        candidates.append(ref + ".tex")

    base = Path(ref).name
    candidates.append(base)
    if not base.endswith(".tex"):
        candidates.append(base + ".tex")
    candidates.append(Path(base).stem)

    for c in candidates:
        if c in idx:
            # ưu tiên .tex
            for p in idx[c]:
                if p.suffix.lower() == ".tex":
                    return p
            return idx[c][0]

    # fallback: thử join trực tiếp theo filesystem (phòng hờ index miss)
    p1 = version_dir / ref
    if p1.exists() and p1.is_file() and p1.suffix.lower() == ".tex":
        return p1
    if not ref.endswith(".tex"):
        p2 = version_dir / (ref + ".tex")
        if p2.exists() and p2.is_file():
            return p2

    return None


def extract_includeonly(text_no_comments: str) -> Optional[Set[str]]:
    """
    Lấy danh sách file trong \\includeonly (nếu có).
    Trả về set các stem (vd: {"chap1","chap2"}).
    Lưu ý: includeonly chỉ ảnh hưởng \\include, không ảnh hưởng \\input.
    """
    m = re.search(INCLUDEONLY_PATTERN, text_no_comments, re.IGNORECASE)
    if not m:
        return None
    items = split_brace_list(m.group("list"))
    stems = {Path(x).stem for x in items if x.strip()}
    return stems if stems else None


def is_main_tex(tex_path: Path) -> bool:
    """
    File được coi là main nếu (sau khi bỏ comment) có:
    - \\begin{document}
    - \\end{document}
    """
    try:
        raw = tex_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    t = strip_tex_comments(raw)
    return ("\\begin{document}" in t) and ("\\end{document}" in t)


def find_main_tex_files(version_dir: Path) -> List[Path]:
    """Tìm tất cả file main trong 1 version."""
    return [p for p in version_dir.rglob("*.tex") if is_main_tex(p)]


# ============================================================
# Flatten logic: inline toàn file + xử lí includeonly
# ============================================================

def flatten_tex_content(
    cur_file: Path,
    version_dir: Path,
    idx: Dict[str, List[Path]],
    include_cmd_res: List[Tuple[str, re.Pattern]],
    includeonly_names: Optional[Set[str]],
    visiting: Optional[Set[Path]] = None,
) -> str:
    """
    Trả về nội dung file cur_file sau khi:
    - bỏ comment để tránh bắt nhầm pattern
    - inline các lệnh input/include/import/... bằng nội dung file target
    - áp dụng includeonly cho \\include:
        + nếu không thuộc includeonly => bỏ luôn dòng include (replace = "")
    - bỏ luôn dòng \\includeonly{...} (vì sau flatten không còn ý nghĩa)
    - làm đệ quy cho các file con
    """
    if visiting is None:
        visiting = set()

    if cur_file in visiting:
        # tránh vòng lặp include
        return ""

    visiting.add(cur_file)

    raw = cur_file.read_text(encoding="utf-8", errors="ignore")
    # trước tiên strip comment để tránh match nhầm trong comment
    text = strip_tex_comments(raw)

    # bỏ includeonly line khỏi text luôn
    text = re.sub(INCLUDEONLY_PATTERN, "", text, flags=re.IGNORECASE)

    def repl(match: re.Match, kind: str) -> str:
        # kind: "input" hoặc "include"
        gd = match.groupdict()
        ref = normalize_ref(gd.get("file") or "")
        imp = normalize_ref(gd.get("path") or "") if "path" in gd else None

        resolved = resolve_tex_target(ref, version_dir, idx, import_path=imp)
        # Nếu resolve fail thì bỏ lệnh (đừng crash)
        if not resolved or not resolved.exists():
            return ""

        # Nếu là \include thì áp includeonly
        if kind == "include" and includeonly_names is not None:
            # includeonly list so theo stem
            if resolved.stem not in includeonly_names:
                return ""  # bỏ luôn dòng include của file không được include

        # Inline nội dung file con (đệ quy)
        child = flatten_tex_content(
            resolved,
            version_dir,
            idx,
            include_cmd_res,
            includeonly_names=None,  # includeonly chỉ đọc từ file main
            visiting=visiting,
        )
        return child

    # Lặp nhiều vòng cho tới khi không còn pattern nữa
    changed = True
    while changed:
        changed = False
        for kind, rx in include_cmd_res:
            new_text, n = rx.subn(lambda m: repl(m, kind), text)
            if n > 0:
                changed = True
                text = new_text

    # Sau khi inline xong: strip comment lần nữa để output sạch 
    text = strip_tex_comments(text)

    visiting.remove(cur_file)
    return text


# ============================================================
# Process 1 version
# ============================================================

def process_version(paper_id: str, version_dir: Path) -> None:
    tex_files = sorted(version_dir.rglob("*.tex"))
    if not tex_files:
        return

    main_files = find_main_tex_files(version_dir)
    if not main_files:
        return

    idx = build_tex_index(version_dir)

    include_cmd_res: List[Tuple[str, re.Pattern]] = [
        (kind, re.compile(pat, re.IGNORECASE))
        for (kind, pat) in INCLUDE_CMD_SPECS
    ]

    # ---- Flatten từng main file ----
    written_mains: List[Path] = []
    for main in sorted(main_files, key=lambda x: x.name.lower()):
        raw_main = main.read_text(encoding="utf-8", errors="ignore")
        main_no_comments = strip_tex_comments(raw_main)
        includeonly = extract_includeonly(main_no_comments)

        flattened = flatten_tex_content(
            cur_file=main,
            version_dir=version_dir,
            idx=idx,
            include_cmd_res=include_cmd_res,
            includeonly_names=includeonly,
            visiting=set(),
        )

        # Ghi đè main file sau flatten (và đã remove comment)
        main.write_text(flattened, encoding="utf-8", errors="ignore")
        written_mains.append(main)

    # ---- Xóa cuối version: chỉ giữ file main ----
    # Theo yêu cầu: sau cùng version chỉ còn các file .tex chứa begin/end document
    # Các file .tex khác sẽ bị xóa 
    keep_set = set(written_mains)
    to_delete = [p for p in tex_files if p not in keep_set]

    # ---- Print ngắn gọn ----
    print(f"[PAPER] {paper_id}")
    print(f"  [VERSION] {version_dir.name}")
    print("  MAIN:")
    for m in written_mains:
        print(f"    - {m.relative_to(version_dir).as_posix()}")

    if not to_delete:
        print("  UNUSED: 0")
        return

    tag = "DELETED" if DO_DELETE else "WOULD_DELETE"
    print(f"  UNUSED ({len(to_delete)}) -> {tag}:")
    for p in sorted(to_delete, key=lambda x: x.as_posix().lower()):
        rel = p.relative_to(version_dir).as_posix()
        print(f"    - {rel}")
        if DO_DELETE:
            p.unlink(missing_ok=True)


# ============================================================
# Entry point
# ============================================================

def main():
    if not DATA_ROOT.exists():
        print(f"[ERR] DATA_ROOT not found: {DATA_ROOT}")
        return

    mode = "DELETE" if DO_DELETE else "PREVIEW_ONLY"
    print(f"[INFO] DATA_ROOT = {DATA_ROOT.name}")
    print(f"[MODE] {mode}")

    # DATA_ROOT/paper_id/tex/version_dir/...
    for paper_dir in sorted(DATA_ROOT.iterdir(), key=lambda x: x.name):
        if not paper_dir.is_dir():
            continue

        tex_root = paper_dir / "tex"
        if not tex_root.exists():
            continue

        versions = [d for d in tex_root.iterdir() if d.is_dir()]
        if not versions:
            continue

        for vdir in sorted(versions, key=lambda x: x.name.lower()):
            process_version(paper_dir.name, vdir)

    print("\n[DONE]")


if __name__ == "__main__":
    main()
