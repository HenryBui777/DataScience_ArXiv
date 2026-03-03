
import json
import re
from pathlib import Path

class LatexNormalizer:
    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        
        # các lệnh layout và căn chỉnh
        self.layout_cmds = [
            r"\\centering\b", r"\\raggedright\b", r"\\raggedleft\b", 
            r"\\flushleft\b", r"\\flushright\b", r"\\noindent\b", r"\\indent\b"
        ]
        
        # các lệnh khoảng cách không có tham số
        self.spacing_no_args = [
            r"\\hfill\b", r"\\vfill\b", 
            r"\\smallskip\b", r"\\medskip\b", r"\\bigskip\b"
        ]
        
        # các lệnh khoảng cách có tham số
        self.spacing_with_args = ["vspace", "hspace", "vskip", "hskip"]
        
        # các lệnh ngắt trang/dòng
        self.break_cmds = [
            r"\\clearpage\b", r"\\newpage\b", r"\\pagebreak\b", r"\\nopagebreak\b",
            r"\\linebreak\b", r"\\nolinebreak\b"
        ]
        
        # các vị trí float [htbp]
        self.float_positions = r"\[[htbp!]+\]"
        
        # các lệnh font size
        self.font_size_cmds = [
            r"\\tiny\b", r"\\scriptsize\b", r"\\footnotesize\b",
            r"\\small\b", r"\\normalsize\b", 
            r"\\large\b", r"\\Large\b", r"\\LARGE\b", r"\\huge\b", r"\\Huge\b"
        ]
        
        # các lệnh font family/series
        self.font_family_cmds = [
            r"\\bfseries\b", r"\\itshape\b", r"\\rmfamily\b",
            r"\\sffamily\b", r"\\ttfamily\b"
        ]
        
        # các lệnh định dạng text (cần unwrap)
        self.text_format_cmds = [
            "textbf", "textit", "emph", "underline", "textsc", 
            "textsf", "texttt", "textmd", "textrm", "textsl", "textup"
        ]
        
        # các lệnh box (cần unwrap)
        self.box_cmds = [
            "mbox", "makebox", "fbox", "framebox", "parbox"
        ]
        
        # các lệnh resize/scale (cần unwrap)
        self.resize_cmds = ["resizebox", "scalebox"]
        
        # các lệnh structural (cần xóa)
        self.structural_cmds = [
            r"\\section\*?\{[^}]*\}", r"\\subsection\*?\{[^}]*\}",
            r"\\subsubsection\*?\{[^}]*\}", r"\\paragraph\*?\{[^}]*\}",
            r"\\subparagraph\*?\{[^}]*\}", r"\\chapter\*?\{[^}]*\}",
            r"\\part\*?\{[^}]*\}", r"\\appendix\b",
            r"\\begin\{document\}", r"\\end\{document\}",
            r"\\maketitle\b", r"\\tableofcontents\b"
        ]
        
        # các lệnh định dạng math (cần unwrap)
        self.math_format_cmds = [
            "mathbf", "mathit", "mathrm", "mathbb", "mathcal", 
            "mathfrak", "mathsf", "mathtt", "boldsymbol", "bm",
            "text", "textrm"
        ]
        
        # các nested math environments (cần unwrap)
        self.nested_math_envs = [
            "aligned", "split", "cases", "array", "matrix",
            "pmatrix", "bmatrix", "vmatrix", "Vmatrix"
        ]
        
        # các lệnh table structure
        self.table_cmds = [
            r"\\hline\b", r"\\cline\{[^}]*\}", 
            r"\\midrule\b", r"\\toprule\b", r"\\bottomrule\b", 
            r"\\cmidrule\{[^}]*\}"
        ]
        
        # patterns cho inline math
        self.inline_patterns = [
            (re.compile(r"\\\\\((.+?)\\\\\)", re.DOTALL), "paren"),      # \(...\)
            (re.compile(r"\\begin\{math\}(.+?)\\end\{math\}", re.DOTALL), "env")  # \begin{math}
        ]
        
        # patterns cho block math
        self.block_patterns = [
            (re.compile(r"\$\$(.+?)\$\$", re.DOTALL), "dollars"),        # $$...$$
            (re.compile(r"\\\\\[(.+?)\\\\\]", re.DOTALL), "brackets"),   # \[...\]
            (re.compile(r"\\begin\{displaymath\}(.+?)\\end\{displaymath\}", re.DOTALL), "displaymath"),
            (re.compile(r"\\begin\{align\*?\}(.+?)\\end\{align\*?\}", re.DOTALL), "align"),
            (re.compile(r"\\begin\{gather\*?\}(.+?)\\end\{gather\*?\}", re.DOTALL), "gather"),
            (re.compile(r"\\begin\{multline\*?\}(.+?)\\end\{multline\*?\}", re.DOTALL), "multline"),
        ]

    def process_all_papers(self):
        """xử lý tất cả các papers trong thư mục data"""
        print(f"Thư mục dữ liệu: {self.data_dir.absolute()}")
        if not self.data_dir.exists():
            print("Thư mục không tồn tại!")
            return

        papers = sorted([d for d in self.data_dir.iterdir() if d.is_dir()])
        print(f"Tìm thấy {len(papers)} papers.")

        for paper_dir in papers:
            json_path = paper_dir / "hierarchy.json"
            if not json_path.exists():
                continue
                
            print(f"Đang xử lý: {paper_dir.name}")
            
            # load hierarchy.json
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # normalize
            normalized_data = self.normalize_hierarchy(data)
            
            # lưu lại trực tiếp vào hierarchy.json
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(normalized_data, f, indent=2, ensure_ascii=False)

    def fix_malformed_latex(self, text: str) -> str:
        """sửa các latex command thiếu dấu đóng ngoặc }"""
        if not text:
            return text
        
        # đếm số lượng { và }
        open_braces = text.count('{')
        close_braces = text.count('}')
        
        # nếu thiếu dấu đóng, thêm vào cuối
        if open_braces > close_braces:
            missing = open_braces - close_braces
            text += '}' * missing
        
        return text

    def get_context(self, elem_id: str) -> str:
        """xác định context của element dựa trên id"""
        if elem_id.startswith("table-"):
            return "table"
        elif elem_id.startswith("formula-"):
            return "formula"
        else:
            return "other"

    def normalize_hierarchy(self, data: dict) -> dict:
        """chuẩn hóa toàn bộ hierarchy json"""
        elements = data.get("elements", {})
        new_elements = {}
        
        for elem_id, content in elements.items():
            if not isinstance(content, str):
                new_elements[elem_id] = content
                continue
            
            context = self.get_context(elem_id)
            
            # bước 0: fix malformed latex
            content = self.fix_malformed_latex(content)
            
            # bước 1: cleanup latex patterns
            cleaned = self.cleanup_latex(content, context)
            
            # bước 2: normalize math
            if context == "formula":
                normalized = self.normalize_formula(cleaned)
            else:
                normalized = self.normalize_text_with_math(cleaned)
            
            new_elements[elem_id] = normalized.strip()
        
        data["elements"] = new_elements
        return data

    def cleanup_latex(self, text: str, context: str) -> str:
        """xóa/unwrap các latex patterns không cần thiết"""
        if not text:
            return ""
        
        # 1. xóa layout commands
        for cmd in self.layout_cmds:
            text = re.sub(cmd, " ", text)
        
        # 2. xóa spacing commands
        for cmd in self.spacing_no_args:
            text = re.sub(cmd, " ", text)
        
        for cmd in self.spacing_with_args:
            text = re.sub(rf"\\{cmd}\{{[^}}]*\}}", " ", text)
            text = re.sub(rf"\\{cmd}\s+\S+", " ", text)
        
        # 3. xóa break commands
        for cmd in self.break_cmds:
            text = re.sub(cmd, " ", text)
        
        # 4. xóa float positions
        text = re.sub(self.float_positions, "", text)
        
        # 5. xóa font size commands
        for cmd in self.font_size_cmds:
            text = re.sub(cmd, " ", text)
        
        # 6. xóa font family commands
        for cmd in self.font_family_cmds:
            text = re.sub(cmd, " ", text)
        
        # 7. xóa structural commands
        for cmd in self.structural_cmds:
            text = re.sub(cmd, " ", text)
        
        # 8. unwrap text formatting
        for cmd in self.text_format_cmds:
            text = self.unwrap_command(text, cmd)
        
        # 9. unwrap boxes
        for cmd in self.box_cmds:
            text = self.unwrap_command(text, cmd)
        
        # 10. unwrap resize/scale
        for cmd in self.resize_cmds:
            text = self.unwrap_command(text, cmd)
        
        # 11. xử lý table commands (chỉ xóa nếu không phải table context)
        if context != "table":
            for cmd in self.table_cmds:
                text = re.sub(cmd, " ", text)
            # xóa \\ và & trong non-table context
            text = re.sub(r"(?<!\\)\\\\(?!\\)", " ", text)  # \\ nhưng không phải \\\ hoặc \\\\
            text = re.sub(r"(?<!\\)&", " ", text)  # & không có \ phía trước
        
        # 12. cleanup whitespace
        text = re.sub(r"\s+", " ", text)
        
        return text

    def unwrap_command(self, text: str, cmd: str) -> str:
        """unwrap latex command: \cmd{content} -> content"""
        # unwrap đệ quy để xử lý nested commands
        pattern = re.compile(rf"\\{cmd}\{{([^{{}}]*)\}}", re.DOTALL)
        max_iterations = 10  # tránh vòng lặp vô hạn
        
        for _ in range(max_iterations):
            new_text = pattern.sub(r"\1", text)
            if new_text == text:
                break
            text = new_text
        
        return text

    def unwrap_math_formatting(self, text: str) -> str:
        """xóa các lệnh định dạng math: \mathbf{x} -> x"""
        for cmd in self.math_format_cmds:
            text = self.unwrap_command(text, cmd)
        return text

    def unwrap_nested_math_envs(self, text: str) -> str:
        r"""unwrap nested math environments: \begin{aligned}...\end{aligned} -> ..."""
        for env in self.nested_math_envs:
            # unwrap \begin{env}...\end{env}
            pattern = re.compile(rf"\\begin\{{{env}\*?\}}(.+?)\\end\{{{env}\*?\}}", re.DOTALL)
            max_iterations = 5
            for _ in range(max_iterations):
                new_text = pattern.sub(r"\1", text)
                if new_text == text:
                    break
                text = new_text
        return text

    def normalize_text_with_math(self, text: str) -> str:
        """chuẩn hóa text có chứa inline/block math"""
        
        # normalize inline math: \(...\), \begin{math} -> $...$
        for pattern, ptype in self.inline_patterns:
            def replace_inline(match):
                content = match.group(1).strip()
                content = self.unwrap_math_formatting(content)
                content = self.unwrap_nested_math_envs(content)
                return f"${content}$"
            text = pattern.sub(replace_inline, text)
        
        # normalize block math: $$, \[, align, gather, multline -> \begin{equation}
        for pattern, ptype in self.block_patterns:
            def replace_block(match):
                content = match.group(1).strip()
                
                # xử lý multiline environments (align, gather, multline)
                if ptype in ["align", "gather", "multline"]:
                    # split theo \\ và xóa alignment markers &
                    lines = re.split(r"\\\\", content)
                    equations = []
                    for line in lines:
                        line = re.sub(r"&", " ", line).strip()  # xóa alignment markers
                        line = self.unwrap_math_formatting(line)
                        line = self.unwrap_nested_math_envs(line)
                        if line and not re.match(r"^\s*$", line):
                            equations.append(f"\\begin{{equation}}{line}\\end{{equation}}")
                    return "\n".join(equations) if equations else ""
                else:
                    # single equation
                    content = self.unwrap_math_formatting(content)
                    content = self.unwrap_nested_math_envs(content)
                    return f"\\begin{{equation}}{content}\\end{{equation}}"
            
            text = pattern.sub(replace_block, text)
        
        return text

    def normalize_formula(self, text: str) -> str:
        """chuẩn hóa nội dung formula element (toàn bộ là math)"""
        text = text.strip()
        
        # kiểm tra xem đã có wrapper chưa
        if text.startswith("\\begin{equation"):
            # đã có equation wrapper, chỉ cần unwrap math formatting bên trong
            text = self.unwrap_math_formatting(text)
            text = self.unwrap_nested_math_envs(text)
            return text
        
        # kiểm tra các multiline environments
        for pattern, ptype in self.block_patterns:
            match = pattern.match(text)
            if match:
                content = match.group(1).strip()
                
                if ptype in ["align", "gather", "multline"]:
                    # split multiline thành nhiều equations
                    lines = re.split(r"\\\\", content)
                    equations = []
                    for line in lines:
                        line = re.sub(r"&", " ", line).strip()
                        line = self.unwrap_math_formatting(line)
                        line = self.unwrap_nested_math_envs(line)
                        if line and not re.match(r"^\s*$", line):
                            equations.append(f"\\begin{{equation}}{line}\\end{{equation}}")
                    return "\n".join(equations) if equations else text
                else:
                    # single equation
                    content = self.unwrap_math_formatting(content)
                    content = self.unwrap_nested_math_envs(content)
                    return f"\\begin{{equation}}{content}\\end{{equation}}"
        
        # nếu không có wrapper nào, assume là raw math và wrap vào equation
        text = self.unwrap_math_formatting(text)
        text = self.unwrap_nested_math_envs(text)
        return f"\\begin{{equation}}{text}\\end{{equation}}"

if __name__ == "__main__":
    # chạy normalization
    current_dir = Path(__file__).parent
    data_dir = current_dir.parent / "23120257"

    if data_dir.exists():
        normalizer = LatexNormalizer(str(data_dir))
        normalizer.process_all_papers()
    else:
        print(f"Không tìm thấy thư mục: {data_dir}")
