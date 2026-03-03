import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import defaultdict


class LaTeXHierarchyParser:
    """parser latex với sequential parsing"""

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)

        # Section levels (cao → thấp)
        self.SECTION_LEVELS = [
            ("part", r"\\part\*?\s*\{"),
            ("chapter", r"\\chapter\*?\s*\{"),
            ("section", r"\\section\*?\s*\{"),
            ("subsection", r"\\subsection\*?\s*\{"),
            ("subsubsection", r"\\subsubsection\*?\s*\{"),
            ("paragraph", r"\\paragraph\*?\s*\{"),
            ("subparagraph", r"\\subparagraph\*?\s*\{"),
        ]

        self.CONTAINER_ENVS = [
            "abstract", "appendix", "theorem", "lemma", "proposition",
            "corollary", "definition", "example", "remark", "note",
            "proof", "claim", "conjecture", "axiom", "quote", "quotation",
            "acknowledgements", "acknowledgement", "acks",
        ]

        self.LEAF_ENVS = ["verbatim", "lstlisting", "algorithm", "algorithmic"]

        self.EXCLUDE_KEYWORDS = ["reference", "bibliography", "works cited"]

    def process_all_papers(self):
        """xử lý tất cả papers"""
        papers = sorted([d for d in self.data_dir.iterdir() if d.is_dir()])
        stats = {'total': 0, 'success': 0, 'failed': 0, 'total_elements': 0}
        
        for paper_dir in papers:
            paper_id = paper_dir.name
            result = self.process_paper(paper_id, paper_dir)
            stats['total'] += 1
            if result:
                stats['success'] += 1
                stats['total_elements'] += result  # result is element count
            else:
                stats['failed'] += 1
        
        return stats

    def process_paper(self, paper_id: str, paper_path: Path) -> bool:
        """xử lý một paper và merge tất cả versions"""
        all_elements: Dict[str, str] = {}
        all_hierarchies: Dict[str, Dict[str, Optional[str]]] = {}

        tex_root = paper_path / "tex"
        if not tex_root.exists():
            return False

        versions = sorted([d for d in tex_root.iterdir() if d.is_dir()])
        if not versions:
            return False

        # Kiểm tra cấu trúc v1 để quyết định đánh số
        use_numbering = False
        v1_dir = None
        for v in versions:
            if v.name.endswith("v1"):
                v1_dir = v
                break
        if not v1_dir and versions:
            v1_dir = versions[0]
            
        if v1_dir:
            v1_tex_files = [f for f in v1_dir.iterdir() if f.is_file() and f.suffix.lower() == ".tex"]
            if len(v1_tex_files) > 1:
                use_numbering = True
                print(f"{paper_id} | v1 có {len(v1_tex_files)} file tex -> ĐÁNH SỐ")

        # counter liên tục qua tất cả versions
        doc_counter = 0
        
        for version_dir in versions:
            version_name = version_dir.name
            version_match = re.search(r"v(\d+)$", version_name)
            version_num = version_match.group(1) if version_match else "1"

            print(f"{paper_id} | processing version: {version_name}")

            tex_files = [
                f for f in version_dir.iterdir()
                if f.is_file() and f.suffix.lower() == ".tex"
            ]
            if not tex_files:
                continue

            # xử lý từng tex file riêng, mỗi file có document node riêng
            version_elements = {}
            version_hierarchy = {}
            
            for tex_file in sorted(tex_files):
                content = self.read_file(tex_file)
                if not content.strip():
                    continue
                
                doc_counter += 1  # tăng counter liên tục qua versions
                
                if use_numbering:
                    doc_label = f"Document {doc_counter:02d}"
                    doc_suffix = f" {doc_counter:02d}"
                else:
                    doc_label = "Document"
                    doc_suffix = ""
                
                result = self.parse_document(content, paper_id, version_num, doc_counter, doc_label, doc_suffix)
                if result:
                    version_elements.update(result["elements"])
                    version_hierarchy.update(result["hierarchy"])
            
            if version_elements:
                all_elements.update(version_elements)
                all_hierarchies[version_num] = version_hierarchy

        if all_elements:
            hierarchy_data = {"elements": all_elements, "hierarchy": all_hierarchies}
            output_file = paper_path / "hierarchy.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(hierarchy_data, f, indent=2, ensure_ascii=False)
            return len(all_elements)  # trả về số elements

        return 0

    def read_file(self, filepath: Path) -> str:
        """đọc file tex với encoding utf-8 hoặc latin-1"""
        try:
            return filepath.read_text(encoding="utf-8")
        except Exception:
            try:
                return filepath.read_text(encoding="latin-1")
            except Exception:
                return ""

    def parse_document(self, content: str, paper_id: str, version_num: str = "1", 
                        doc_idx: int = 1, doc_label: str = "Document", doc_suffix: str = "") -> Optional[Dict]:
        """parse toàn bộ document theo thứ tự xuất hiện"""
        doc_match = re.search(
            r"\\begin\{document\}(.*?)\\end\{document\}", content, re.DOTALL
        )
        document_content = doc_match.group(1) if doc_match else content
        document_content = self.remove_bibliography(document_content)

        self.type_counters = defaultdict(int)
        self.paper_id = paper_id
        self.version_num = version_num
        self.doc_idx = doc_idx  # lưu doc_idx để dùng trong generate_id
        self.doc_num_suffix = doc_suffix  # suffix số để dùng cho Appendix, Abstract, Ack

        self.elements: Dict[str, str] = {}
        self.hierarchy: Dict[str, Optional[str]] = {}

        root_id = self.generate_id("document")
        self.elements[root_id] = doc_label  # dùng doc_label thay vì "Document"
        self.hierarchy[root_id] = None

        self.parse_sequential(document_content, root_id)

        return {"elements": self.elements, "hierarchy": self.hierarchy}

    def generate_id(self, elem_type: str) -> str:
        """tạo unique id cho element, bao gồm cả doc_idx để phân biệt tex files"""
        self.type_counters[elem_type] += 1
        # format: type-paper-v{version}-d{doc_idx}-{counter}
        return f"{elem_type}-{self.paper_id}-v{self.version_num}-d{self.doc_idx}-{self.type_counters[elem_type]}"

    def remove_bibliography(self, content: str) -> str:
        """xóa các phần bibliography khỏi content"""
        content = re.sub(
            r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}",
            "", content, flags=re.DOTALL
        )
        content = re.sub(r"\\bibliography\{[^}]*\}", "", content)
        content = re.sub(r"\\printbibliography(\[[^\]]*\])?", "", content)
        return content

    def is_excluded_section(self, title: str) -> bool:
        """kiểm tra xem section có phải là references/bibliography không"""
        title_lower = title.lower().strip()
        return any(kw in title_lower for kw in self.EXCLUDE_KEYWORDS)

    def has_real_content(self, content: str) -> bool:
        """kiểm tra xem content có nội dung text thực sự hay chỉ có labels/commands"""
        if not content or not content.strip():
            return False
        
        for level_name, level_pattern in self.SECTION_LEVELS:
            if re.search(level_pattern, content):
                return True
        
        if re.search(r"\\begin\{[^}]+\}", content):
            return True
        
        formula_patterns = [r"\$\$", r"\\\[", r"\\begin\{equation", r"\\begin\{align"]
        for pattern in formula_patterns:
            if re.search(pattern, content):
                return True
        
        text = content
        
        text = re.sub(r"\\label\{[^}]*\}", "", text)
        
        formatting_cmds = [
            "noindent", "indent", "centering", "raggedright", "raggedleft",
            "small", "footnotesize", "scriptsize", "tiny", "normalsize", 
            "large", "Large", "LARGE", "huge", "Huge",
            "vspace", "hspace", "vfill", "hfill", "medskip", "bigskip", "smallskip",
            "clearpage", "newpage", "pagebreak", "linebreak",
            "maketitle", "tableofcontents",
            "par", "newline", "break"
        ]
        
        for cmd in formatting_cmds:
            # match \cmd, \cmd{...}, \cmd[...]{...}, \cmd*{...}
            text = re.sub(rf"\\{cmd}\*?(\[[^\]]*\])?(\{{[^}}]*\}})?", "", text)
        
        # xóa các lệnh latex generic còn lại có dạng \command (không có arguments)
        # nhưng cẩn thận không xóa text bên trong {}
        text = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?(?=\s|$)", "", text)
        
        # xóa các ký tự đặc biệt latex standalone
        text = re.sub(r"\\[\\%&$#_{}~^]", "", text)
        
        # xóa line break commands như \\, \\[1ex]
        text = re.sub(r"\\\\(\[\d*[a-z]*\])?", "", text)
        
        # normalize whitespace
        text = re.sub(r"\s+", "", text)
        
        # nếu sau khi xóa hết commands mà còn text thì có nội dung thực
        return len(text) > 0

    def parse_sequential(self, content: str, parent_id: str):
        """parse content theo thứ tự: tìm sections, chia blocks, parse từng block"""
        if not content or not content.strip():
            return


        sections = []
        for level_name, level_pattern in self.SECTION_LEVELS:
            pattern = level_pattern.replace(r"\{", r"\{([^}]+)\}")
            for match in re.finditer(pattern, content):
                title = match.group(1).strip()
                if not self.is_excluded_section(title):
                    level_idx = [l[0] for l in self.SECTION_LEVELS].index(level_name)
                    sections.append({
                        "pos": match.start(),
                        "end_cmd": match.end(),  # end of \section{...} command
                        "type": level_name,
                        "level": level_idx,
                        "title": title,
                    })

        sections.sort(key=lambda x: x["pos"])
        
        appendix_match = re.search(r"\\appendix\b", content)
        appendix_pos = appendix_match.start() if appendix_match else None
        
        ack_pattern = r"\\(acknowledgements?|acks?)\b(?!\{)"
        ack_match = re.search(ack_pattern, content)
        
        if sections:
            present_levels = sorted(set(s["level"] for s in sections))
            level_remap = {old: new for new, old in enumerate(present_levels)}
            for s in sections:
                s["level"] = level_remap[s["level"]]

        if sections:
            first_section_pos = sections[0]["pos"]
            if first_section_pos > 0:
                preamble_content = content[:first_section_pos]
                self.parse_content_block(preamble_content, parent_id)

        section_stack = [{"id": parent_id, "level": -1, "end_pos": len(content)}]
        
        appendix_id = None
        if appendix_pos is not None:
            appendix_id = self.generate_id("appendix")
            self.elements[appendix_id] = f"Appendix{self.doc_num_suffix}"
            self.hierarchy[appendix_id] = parent_id
        
        ack_id = None
        if ack_match:
            ack_id = self.generate_id("acknowledgements")
            self.elements[ack_id] = f"Acknowledgements{self.doc_num_suffix}"
            self.hierarchy[ack_id] = parent_id
            ack_start = ack_match.end()
            ack_end = len(content)
            for sec in sections:
                if sec["pos"] > ack_start:
                    ack_end = sec["pos"]
                    break
            if appendix_pos and appendix_pos > ack_start and appendix_pos < ack_end:
                ack_end = appendix_pos
            ack_content = content[ack_start:ack_end]
            self.parse_content_block(ack_content, ack_id)

        for i, sec in enumerate(sections):
            # xác định vị trí kết thúc section
            if i + 1 < len(sections):
                sec_end = sections[i + 1]["pos"]
            else:
                sec_end = len(content)

            # pop stack về đúng parent level
            while section_stack and section_stack[-1]["level"] >= sec["level"]:
                section_stack.pop()

            current_parent = section_stack[-1]["id"]
            
            # nếu section sau \appendix thì parent là appendix container
            if appendix_id and appendix_pos is not None and sec["pos"] > appendix_pos:
                if section_stack[-1]["id"] == parent_id:
                    current_parent = appendix_id

            # content section từ end_cmd đến sec_end
            sec_content = content[sec["end_cmd"]:sec_end]

            # phát hiện acknowledgements từ title
            # sections trong appendix giữ nguyên type
            title_lower = sec["title"].lower()
            elem_type = sec["type"]
            
            if "acknowledgement" in title_lower or "acknowledgment" in title_lower:
                elem_type = "acknowledgements"
            
            # tạo section element
            sec_id = self.generate_id(elem_type)
            self.elements[sec_id] = sec["title"]
            self.hierarchy[sec_id] = current_parent

            # parse content của section này
            self.parse_content_block(sec_content, sec_id)

            # push section vào stack
            section_stack.append({"id": sec_id, "level": sec["level"], "end_pos": sec_end})

        # nếu không có sections, parse toàn bộ content
        if not sections:
            self.parse_content_block(content, parent_id)

    def parse_content_block(self, content: str, parent_id: str):
        """
        parse một block content:
        - tìm tất cả elements (containers, figures, tables, formulas, lists)
        - parse text giữa các elements thành sentences
        """
        if not content or not content.strip():
            return

        # tìm tất cả elements với vị trí
        all_items: List[Dict] = []

        # 1) các container environments
        for env_name in self.CONTAINER_ENVS:
            pattern = rf"\\begin\{{{env_name}\*?\}}(.*?)\\end\{{{env_name}\*?\}}"
            for match in re.finditer(pattern, content, re.DOTALL):
                all_items.append({
                    "pos": match.start(),
                    "end": match.end(),
                    "type": env_name,
                    "title": env_name.capitalize(),
                    "content": match.group(1).strip(),
                    "kind": "container",
                })

        # 1b) lệnh abstract (\abstract{...})
        for match in re.finditer(r"\\abstract\{", content):
            # tìm dấu đóng ngoặc nhọn
            start = match.start()
            brace_count = 0
            pos = match.end() - 1
            end_pos = -1
            
            while pos < len(content):
                if content[pos] == '{':
                    brace_count += 1
                elif content[pos] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_pos = pos + 1
                        break
                pos += 1
            
            if end_pos > 0:
                # lấy content giữa các ngoặc
                inner_content = content[match.end():end_pos-1].strip()
                all_items.append({
                    "pos": start,
                    "end": end_pos,
                    "type": "abstract",
                    "title": "Abstract",
                    "content": inner_content,
                    "kind": "container",
                })

        # 2) các leaf environments
        for env_name in self.LEAF_ENVS:
            pattern = rf"\\begin\{{{env_name}\*?\}}(.*?)\\end\{{{env_name}\*?\}}"
            for match in re.finditer(pattern, content, re.DOTALL):
                all_items.append({
                    "pos": match.start(),
                    "end": match.end(),
                    "type": env_name,
                    "title": env_name.capitalize(),
                    "content": match.group(1).strip(),
                    "kind": "leaf",
                })

        # 3) các figures
        for match in re.finditer(r"\\begin\{figure\*?\}(.*?)\\end\{figure\*?\}", content, re.DOTALL):
            inner = match.group(1)
            caption_match = re.search(r"\\caption\{([^}]+)\}", inner)
            title = (caption_match.group(1)[:50] + "...") if caption_match else "Figure"
            all_items.append({
                "pos": match.start(),
                "end": match.end(),
                "type": "figure",
                "title": title,
                "content": inner.strip(),
                "kind": "leaf",
            })

        # 4) các tables - lưu như figure
        for match in re.finditer(r"\\begin\{table\*?\}(.*?)\\end\{table\*?\}", content, re.DOTALL):
            inner = match.group(1)
            caption_match = re.search(r"\\caption\{([^}]+)\}", inner)
            title = (caption_match.group(1)[:50] + "...") if caption_match else "Table"
            all_items.append({
                "pos": match.start(),
                "end": match.end(),
                "type": "figure",  # quy về figure
                "title": title,
                "content": inner.strip(),
                "kind": "leaf",
            })

        # 5) formulas - đã xóa extraction riêng
        # các structured environments được xử lý trong parse_text_to_sentences


        # 6) các lists
        list_patterns = [
            (r"\\begin\{itemize\}(.*?)\\end\{itemize\}", "Itemize List"),
            (r"\\begin\{enumerate\}(.*?)\\end\{enumerate\}", "Enumerate List"),
            (r"\\begin\{description\}(.*?)\\end\{description\}", "Description List"),
            (r"\\begin\{alphlist\}(.*?)\\end\{alphlist\}", "Alpha List"),
            (r"\\begin\{romlist\}(.*?)\\end\{romlist\}", "Roman List"),
        ]
        for pattern, title in list_patterns:
            for match in re.finditer(pattern, content, re.DOTALL):
                all_items.append({
                    "pos": match.start(),
                    "end": match.end(),
                    "type": "list",
                    "title": title,
                    "content": match.group(1).strip(),
                    "kind": "list",
                })

        # sắp xếp theo vị trí
        all_items.sort(key=lambda x: x["pos"])

        # xóa các items lồng nhau
        filtered_items = []
        for item in all_items:
            is_nested = False
            for other in filtered_items:
                if other["pos"] < item["pos"] < item["end"] <= other["end"]:
                    is_nested = True
                    break
            if not is_nested:
                filtered_items.append(item)

        # parse content theo thứ tự
        current_pos = 0
        for item in filtered_items:
            # text trước item này
            if current_pos < item["pos"]:
                text_chunk = content[current_pos:item["pos"]]
                self.parse_text_to_sentences(text_chunk, parent_id)

            # parse item itself
            if item["kind"] == "container":
                elem_id = self.generate_id(item["type"])
                # thêm số suffix cho abstract, appendix, acknowledgement
                types_need_suffix = {"abstract", "appendix", "acknowledgement", "acknowledgements"}
                if item["type"] in types_need_suffix:
                    self.elements[elem_id] = f"{item['title']}{self.doc_num_suffix}"
                else:
                    self.elements[elem_id] = item["title"]
                self.hierarchy[elem_id] = parent_id
                if item["content"]:
                    self.parse_content_block(item["content"], elem_id)

            elif item["kind"] == "list":
                list_id = self.generate_id("list")
                self.elements[list_id] = item["title"]
                self.hierarchy[list_id] = parent_id
                if item["content"]:
                    self.parse_list_items(item["content"], list_id)

            elif item["kind"] == "leaf":
                elem_id = self.generate_id(item["type"])
                self.elements[elem_id] = item["content"]
                self.hierarchy[elem_id] = parent_id

            current_pos = item["end"]

        # text sau item cuối
        if current_pos < len(content):
            text_chunk = content[current_pos:]
            self.parse_text_to_sentences(text_chunk, parent_id)

    def parse_list_items(self, content: str, list_id: str):
        """parse các items trong list."""
        # split theo \item, bao gồm cả optional argument [...]
        items = re.split(r"\\item\b\s*(?:\[[^\]]*\])?\s*", content)

        for item_content in items[1:]:
            item_content = item_content.strip()
            
            # xóa \label{...} ở đầu item
            item_content = re.sub(r"^\\label\{[^}]*\}\s*", "", item_content)
            
            # tạo item node (kể cả khi rỗng)
            item_id = self.generate_id("item")
            self.elements[item_id] = "Item"
            self.hierarchy[item_id] = list_id

            # parse content bên trong item nếu có
            if item_content:
                self.parse_content_block(item_content, item_id)

    def clean_latex_for_sentence(self, text: str) -> str:
        """xóa latex metadata và formatting, giữ content bên trong"""
        # xóa các \label{} độc lập
        text = re.sub(r"\\label\{[^}]*\}", "", text)
        
        # xóa document metadata
        metadata_cmds = [
            "title", "author", "date", "affiliation", "address", "email", 
            "thanks", "dedicatory", "subjclass", "keywords"
        ]
        for cmd in metadata_cmds:
            text = re.sub(rf"\\{cmd}(\[[^\]]*\])?\{{[^}}]*\}}", "", text)
        
        # xóa các lệnh structural
        structural_cmds = ["maketitle", "tableofcontents", "clearpage", "newpage", "pagebreak"]
        for cmd in structural_cmds:
            text = re.sub(rf"\\{cmd}", "", text)
        
        # xóa các lệnh spacing
        spacing_cmds = ["smallskip", "medskip", "bigskip", "vspace", "hspace", "noindent"]
        for cmd in spacing_cmds:
            text = re.sub(rf"\\{cmd}(\{{[^}}]*\}})?", "", text)
        
        # xóa các lệnh ngắt dòng
        text = re.sub(r"\\\\(\[\d*[a-z]*\])?", " ", text)
        
        # xóa formatting commands nhưng giữ content
        formatting_cmds = ["textit", "textbf", "emph", "textrm", "textsf", "texttt", 
                          "textsl", "textsc", "underline", "textup"]
        for cmd in formatting_cmds:
            # thay \cmd{content} bằng content
            text = re.sub(rf"\\{cmd}\{{([^}}]*)\}}", r"\1", text)
        
        # xóa dấu đóng ngoặc thừa
        text = re.sub(r"(?<![\\$])\}\s*(?![\\$])", " ", text)
        
        # chuẩn hóa khoảng trắng
        text = re.sub(r"\s+", " ", text).strip()
        
        return text


    def parse_text_to_sentences(self, text: str, parent_id: str):
        """parse text thành sentences với formula-aware logic"""
        if not text or not text.strip():
            return

        # tìm formulas trước khi clean
        # bao gồm cả $$...$$, \[...\] và structured environments
        formula_patterns = [
            (r"\$\$(.+?)\$\$\.?", "displaymath"),
            (r"\\\[(.+?)\\\]\.?", "displaymath"),
            (r"\\begin\{equation\*?\}(.*?)\\end\{equation\*?\}\.?", "equation"),
            (r"\\begin\{align\*?\}(.*?)\\end\{align\*?\}\.?", "align"),
            (r"\\begin\{gather\*?\}(.*?)\\end\{gather\*?\}\.?", "gather"),
            (r"\\begin\{multline\*?\}(.*?)\\end\{multline\*?\}\.?", "multline"),
            (r"\\begin\{eqnarray\*?\}(.*?)\\end\{eqnarray\*?\}\.?", "eqnarray"),
        ]
        
        formulas = []
        formula_idx = 0
        
        for pattern, pattern_type in formula_patterns:
            for match in re.finditer(pattern, text, re.DOTALL):
                placeholder = f"___FORMULA_{formula_idx}___"
                formulas.append({
                    'start': match.start(),
                    'end': match.end(),  # this now includes trailing period if present
                    'content': match.group(1).strip(),
                    'placeholder': placeholder,
                    'full_match': match.group(0),
                    'type': pattern_type  # store type to reconstruct correctly
                })
                formula_idx += 1
        
        # sắp xếp theo vị trí
        formulas.sort(key=lambda x: x['start'])
        
        # mask formulas trong text
        masked_text = text
        for formula in reversed(formulas):
            masked_text = (
                masked_text[:formula['start']] + 
                formula['placeholder'] + 
                masked_text[formula['end']:]
            )
        
        # clean latex và chuẩn hóa khoảng trắng
        masked_text = self.clean_latex_for_sentence(masked_text)
        
        if not masked_text:
            return
        
        # step 2b: mask abbreviations with periods to prevent incorrect splitting
        # e.g., i.e., etc., vs., Dr., Mr., Mrs., al., Fig., Eq., Ref., Vol.
        abbreviations_to_mask = [
            (r'\bi\.e\.', '___ABBR_IE___'),
            (r'\be\.g\.', '___ABBR_EG___'),
            (r'\betc\.', '___ABBR_ETC___'),
            (r'\bvs\.', '___ABBR_VS___'),
            (r'\bDr\.', '___ABBR_DR___'),
            (r'\bMr\.', '___ABBR_MR___'),
            (r'\bMrs\.', '___ABBR_MRS___'),
            (r'\bMs\.', '___ABBR_MS___'),
            (r'\bal\.', '___ABBR_AL___'),
            (r'\bFig\.', '___ABBR_FIG___'),
            (r'\bEq\.', '___ABBR_EQ___'),
            (r'\bRef\.', '___ABBR_REF___'),
            (r'\bVol\.', '___ABBR_VOL___'),
            (r'\bNo\.', '___ABBR_NO___'),
            (r'\bpp\.', '___ABBR_PP___'),
            (r'\bSect\.', '___ABBR_SECT___'),
        ]
        
        for pattern, placeholder in abbreviations_to_mask:
            masked_text = re.sub(pattern, placeholder, masked_text, flags=re.IGNORECASE)
        
        # smart split - không split nếu theo sau là formula
        parts = []
        current_part = ""
        i = 0
        while i < len(masked_text):
            current_part += masked_text[i]
            
            # check if we just added a complete formula placeholder
            # if formula content ends with '.', that's a sentence boundary
            for formula in formulas:
                if current_part.endswith(formula['placeholder']):
                    if formula['content'].rstrip().endswith('.'):
                        # formula ends with period = end of sentence
                        # split here (but finish current formula in this part)
                        parts.append(current_part)
                        current_part = ""
                        break
            
            # check if we're at a potential split point (`. `)
            if (i + 1 < len(masked_text) and 
                masked_text[i:i+2] == '. ' and
                i + 2 < len(masked_text)):
                
                # look ahead to see if next non-space char is placeholder or uppercase
                next_text = masked_text[i+2:].lstrip()
                
                # don't split if next part starts with placeholder
                # (means formula is continuation of current sentence)
                if next_text.startswith('___FORMULA_'):
                    # but check if that formula ends with period - if so, we should not merge
                    should_skip = True
                    for formula in formulas:
                        if next_text.startswith(formula['placeholder']):
                            if formula['content'].rstrip().endswith('.'):
                                # formula ends with period, so this is a sentence boundary
                                should_skip = False
                            break
                    
                    if should_skip:
                        # continue building current part
                        current_part += ' '
                        i += 2
                        continue
                
                # split here
                parts.append(current_part)
                current_part = ""
                i += 2
                continue
            
            i += 1
        
        # thêm phần cuối
        if current_part:
            parts.append(current_part)
        
        # các từ viết tắt phổ biến
        abbreviations = ['etc', 'Dr', 'Mr', 'Mrs', 'Ms', 'vs', 'Fig', 'Eq', 'Ref', 'Vol', 'al', 'e.g', 'i.e']
        
        # merge các phần bị split sai
        merged_parts = []
        i = 0
        while i < len(parts):
            current = parts[i]
            
            should_merge = False
            for abbr in abbreviations:
                if current.endswith(abbr) or current.endswith(abbr.lower()):
                    should_merge = True
                    break
            
            if len(current) > 0 and current[-1].isupper():
                should_merge = True
            
            if len(current) > 0 and current[-1].isdigit():
                should_merge = True
            
            # nếu phần tiếp ngắn quá thì merge
            if i + 1 < len(parts):
                next_part = parts[i + 1].strip()
                word_count = len(next_part.split())
                if word_count <= 3:  # "then", "similarly", etc. are likely fragments
                    should_merge = True
            
            if should_merge and i + 1 < len(parts):
                merged_parts.append(current + '. ' + parts[i + 1])
                i += 2
            else:
                merged_parts.append(current)
                i += 1
        
        # xử lý từng sentence  
        for part in merged_parts:
            part = part.strip()
            if not part:
                continue
            
            # thêm dấu chấm nếu thiếu
            if not part.endswith('.'):
                part += '.'
            
            # validate: phải bắt đầu bằng chữ hoa hoặc placeholder
            valid_start = (
                part[0].isupper() or 
                part.startswith('___FORMULA_') or
                part.startswith('___ABBR_')
            )
            if not part or not valid_start:
                continue
            
            # validate: phải có nội dung chữ cái
            alpha_text = re.sub(r'___FORMULA_\d+___', '', part)
            if not any(c.isalpha() for c in alpha_text):
                continue
            
            # validate: phải có ít nhất 3 từ
            words = alpha_text.split()
            if len(words) < 3:
                continue
            
            # thay placeholders bằng formula content thực
            sentence_with_formulas = part
            for formula in formulas:
                if formula['placeholder'] in sentence_with_formulas:
                    if formula['type'] == 'displaymath':
                        # wrap display math trong $$...$$
                        sentence_with_formulas = sentence_with_formulas.replace(
                            formula['placeholder'], 
                            f"$${formula['content']}$$"
                        )
                    else:
                        # reconstruct structured environments
                        env_name = formula['type']
                        block = f"\\begin{{{env_name}}}{formula['content']}\\end{{{env_name}}}"
                        sentence_with_formulas = sentence_with_formulas.replace(
                            formula['placeholder'], 
                            block
                        )
            
            # restore abbreviation placeholders
            abbreviation_restorations = [
                ('___ABBR_IE___', 'i.e.'),
                ('___ABBR_EG___', 'e.g.'),
                ('___ABBR_ETC___', 'etc.'),
                ('___ABBR_VS___', 'vs.'),
                ('___ABBR_DR___', 'Dr.'),
                ('___ABBR_MR___', 'Mr.'),
                ('___ABBR_MRS___', 'Mrs.'),
                ('___ABBR_MS___', 'Ms.'),
                ('___ABBR_AL___', 'al.'),
                ('___ABBR_FIG___', 'Fig.'),
                ('___ABBR_EQ___', 'Eq.'),
                ('___ABBR_REF___', 'Ref.'),
                ('___ABBR_VOL___', 'Vol.'),
                ('___ABBR_NO___', 'No.'),
                ('___ABBR_PP___', 'pp.'),
                ('___ABBR_SECT___', 'Sect.'),
            ]
            for placeholder, original in abbreviation_restorations:
                sentence_with_formulas = sentence_with_formulas.replace(placeholder, original)
            
            # tạo sentence element
            sent_id = self.generate_id("sent")
            self.elements[sent_id] = sentence_with_formulas
            self.hierarchy[sent_id] = parent_id
            
            # tạo formula elements như siblings
            for formula in formulas:
                if formula['placeholder'] in part:
                    formula_id = self.generate_id("formula")
                    self.elements[formula_id] = formula['content']
                    self.hierarchy[formula_id] = parent_id


def main():
    current_dir = Path(__file__).parent
    data_dir = current_dir.parent / "23120257"

    if not data_dir.exists():
        print(f"Data directory not found: {data_dir}")
        return

    print(f"Data directory: {data_dir}")
    print("-" * 50)
    
    parser = LaTeXHierarchyParser(str(data_dir))
    stats = parser.process_all_papers()
    
    print("\n" + "=" * 50)
    print("THỐNG KÊ KẾT QUẢ")
    print("=" * 50)
    print(f"Tổng papers: {stats['total']}")
    print(f"Thành công: {stats['success']}")
    print(f"Thất bại: {stats['failed']}")
    print(f"Tổng nodes: {stats['total_elements']}")
    if stats['total'] > 0:
        success_rate = stats['success'] / stats['total'] * 100
        print(f"Tỉ lệ thành công: {success_rate:.1f}%")
    if stats['success'] > 0:
        avg_nodes = stats['total_elements'] / stats['success']
        print(f"Trung bình nodes/paper: {avg_nodes:.1f}")


if __name__ == "__main__":
    main()
