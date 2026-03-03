from __future__ import annotations
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# ============================================================
# Config
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_ROOT = BASE_DIR.parent / "23120257"   # thư mục chứa data
DO_DELETE = True                   # True = xóa file unused, False = chỉ in

# ============================================================
# Regex patterns cho các loại input file có thể có
# - includeonly chỉ chặn \include{...}
# - includeonly không chặn \input{...}, \import{...}, \subfile{...}, ...
# ============================================================

INCLUDE_CMD_SPECS: List[Tuple[str, str]] = [
    ("input",  r"\\input\s*\{(?P<file>[^}]+)\}"),
    ("include", r"\\include\s*\{(?P<file>[^}]+)\}"),
    ("input",  r"\\InputIfFileExists\s*\{(?P<file>[^}]+)\}\s*\{[^}]*\}\s*\{[^}]*\}"),
    ("input",  r"\\subfile\s*\{(?P<file>[^}]+)\}"),
    ("input",  r"\\import\s*\{(?P<path>[^}]+)\}\s*\{(?P<file>[^}]+)\}"),
    ("input",  r"\\inputfrom\s*\{(?P<path>[^}]+)\}\s*\{(?P<file>[^}]+)\}"),
    ("input",  r"\\subimport\s*\{(?P<path>[^}]+)\}\s*\{(?P<file>[^}]+)\}"),
]

INCLUDEONLY_PATTERN = r"\\includeonly\s*\{(?P<list>[^}]+)\}"

# ============================================================
# Regex patterns cho các loại comment có thể có
# ============================================================
COMMENT_ENV_RE = re.compile(
    r"\\begin\{comment\}.*?\\end\{comment\}",
    re.DOTALL | re.IGNORECASE
)

# ============================================================
# Helpers
# ============================================================

def strip_tex_comments(tex: str) -> str:
    """Loại bỏ comment LaTeX (% và environment comment)."""
    tex = COMMENT_ENV_RE.sub("", tex)
    out = []
    for line in tex.splitlines():
        i = 0
        while True:
            j = line.find("%", i)
            if j == -1:
                out.append(line)
                break
            if j > 0 and line[j - 1] == "\\":
                i = j + 1
                continue
            out.append(line[:j])
            break
    return "\n".join(out)


def normalize_ref(s: str) -> str:
    """Chuẩn hóa tên file trong lệnh include/input."""
    return s.strip().strip('"').strip("'").strip()


def split_brace_list(s: str) -> List[str]:
    """Tách a,b,c trong \\includeonly{a,b,c}."""
    return [p.strip() for p in s.split(",") if p.strip()]


def build_tex_index(version_dir: Path) -> Dict[str, List[Path]]:
    """
    Tạo index để resolve nhanh file tex:
    - theo relative path
    - theo filename
    - theo stem
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
    """Resolve ref trong \\input/\\include thành file .tex thật."""
    ref = normalize_ref(raw_ref)
    if not ref:
        return None

    if import_path:
        ref = (Path(import_path) / ref).as_posix()

    candidates = []
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
            for p in idx[c]:
                if p.suffix == ".tex":
                    return p
            return idx[c][0]

    return None


def extract_includeonly(text: str) -> Optional[Set[str]]:
    """Lấy danh sách file trong \\includeonly (nếu có)."""
    m = re.search(INCLUDEONLY_PATTERN, text, re.IGNORECASE)
    if not m:
        return None
    return {Path(x).stem for x in split_brace_list(m.group("list"))}


# ============================================================
# Main detection
# ============================================================

def is_probably_main(tex_path: Path) -> bool:
    """
    File được coi là main nếu có:
    - \\documentclass
    - \\begin{document}
    """
    text = strip_tex_comments(
        tex_path.read_text(encoding="utf-8", errors="ignore")
    )
    return ("\\documentclass" in text) and ("\\begin{document}" in text)


def find_main_tex_files(version_dir: Path) -> List[Path]:
    """Tìm tất cả file main trong 1 version."""
    return [p for p in version_dir.rglob("*.tex") if is_probably_main(p)]


# ============================================================
# DFS include traversal
# ============================================================

def traverse_includes(
    start_file: Path,
    version_dir: Path,
    idx: Dict[str, List[Path]],
    include_cmd_res: List[Tuple[str, re.Pattern]],
    includeonly_names: Optional[Set[str]],
) -> Set[Path]:
    """
    DFS từ file main để tìm toàn bộ file .tex được sử dụng.

    - includeonly (nếu có) chỉ áp dụng cho lệnh \\include{...}
    - các lệnh kiểu \\input, \\import, \\subfile... vẫn follow bình thường
    """
    used: Set[Path] = set()
    stack = [start_file]

    while stack:
        cur = stack.pop()
        if cur in used:
            continue
        used.add(cur)

        text = strip_tex_comments(
            cur.read_text(encoding="utf-8", errors="ignore")
        )

        for cmd_type, rx in include_cmd_res:
            for m in rx.finditer(text):
                if "path" in m.groupdict():
                    ref = normalize_ref(m.group("file"))
                    imp = normalize_ref(m.group("path"))
                    resolved = resolve_tex_target(ref, version_dir, idx, imp)
                else:
                    ref = normalize_ref(m.group("file"))
                    resolved = resolve_tex_target(ref, version_dir, idx)

                # includeonly filter: CHỈ chặn \\include{...}
                if cmd_type == "include" and includeonly_names is not None:
                    name = resolved.stem if resolved else Path(ref).stem
                    if name not in includeonly_names:
                        continue

                if resolved and resolved not in used:
                    stack.append(resolved)

    return used


# ============================================================
# Process 1 version
# ============================================================

def process_version(version_dir: Path) -> None:
    tex_files = sorted(version_dir.rglob("*.tex"))
    if not tex_files:
        return

    main_files = find_main_tex_files(version_dir)
    if not main_files:
        return

    idx = build_tex_index(version_dir)
    include_cmd_res: List[Tuple[str, re.Pattern]] = [
        (cmd, re.compile(pat, re.IGNORECASE)) for cmd, pat in INCLUDE_CMD_SPECS
    ]

    used_all: Set[Path] = set()

    for main in main_files:
        text = strip_tex_comments(
            main.read_text(encoding="utf-8", errors="ignore")
        )
        includeonly = extract_includeonly(text)
        used = traverse_includes(main, version_dir, idx, include_cmd_res, includeonly)
        used_all |= used

    unused = [p for p in tex_files if p not in used_all]

    print(f"  [VERSION] {version_dir.name}")
    print("    MAIN:")
    for m in sorted(main_files, key=lambda x: x.name.lower()):
        print(f"      - {m.name}")

    if not unused:
        print("    UNUSED (0)")
        return

    tag = "DELETED" if DO_DELETE else "WOULD_DELETE"
    print(f"    UNUSED ({len(unused)}) -> {tag}:")
    for p in sorted(unused, key=lambda x: x.name.lower()):
        print(f"      - {p.name}")
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

    for paper_dir in sorted(DATA_ROOT.iterdir()):
        tex_root = paper_dir / "tex"
        if not tex_root.exists():
            continue

        versions = [d for d in tex_root.iterdir() if d.is_dir()]
        if not versions:
            continue

        print(f"\n[PAPER] {paper_dir.name}")
        for v in sorted(versions, key=lambda x: x.name.lower()):
            process_version(v)

    print("\n[DONE]")


if __name__ == "__main__":
    main()
