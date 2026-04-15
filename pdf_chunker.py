import hashlib
from langchain_core.documents import Document
from utils import detect_language, normalize_text

CHILD_MAX_CHARS  = 600
PARENT_MAX_CHARS = 2400
OVERLAP_RATIO    = 0.15
TABLE_MAX_CHARS  = 2500


class HierarchicalChunker:
    """
    Parent-Child 청킹 전략.

    child (CHILD_MAX_CHARS ≈ 600자): 벡터 DB 검색 단위
    parent (PARENT_MAX_CHARS ≈ 2400자): parent_text 메타데이터로 저장,
                                         LLM 컨텍스트 전달용

    표 이중 청킹:
        table_md → Markdown 원본 (정확한 값 검색)
        table_nl → 자연어 요약   (의미 기반 검색)
    """

    def __init__(
        self,
        child_max:     int   = CHILD_MAX_CHARS,
        parent_max:    int   = PARENT_MAX_CHARS,
        overlap_ratio: float = OVERLAP_RATIO,
    ):
        self.child_max     = child_max
        self.parent_max    = parent_max
        self.overlap       = int(child_max * overlap_ratio)
        self._seen_hashes: set[str] = set()

    def _content_hash(self, text: str) -> str:
        return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]

    def _is_duplicate(self, text: str) -> bool:
        h = self._content_hash(text)
        if h in self._seen_hashes:
            return True
        self._seen_hashes.add(h)
        return False

    def chunk(self, parsed_items: list[dict], base_metadata: dict) -> list[Document]:
        all_docs: list[Document] = []

        parent_buffer:   list[str] = []
        section_heading: str       = ""
        page_start:      int       = 1
        parent_index:    int       = 0

        def flush_parent() -> list[dict]:
            nonlocal parent_buffer, section_heading, page_start, parent_index
            if not parent_buffer:
                return []
            parent_text = "\n".join(parent_buffer)
            chunks      = self._split_text(parent_text, self.parent_max)
            results = []
            for p in chunks:
                if not p.strip():
                    continue
                results.append({
                    "parent_text": p,
                    "heading"    : section_heading,
                    "page"       : page_start,
                    "is_ocr"     : False,
                })
                parent_index += 1
            parent_buffer.clear()
            return results

        pending_parents: list[dict] = []
        table_items:     list[dict] = []

        for item in parsed_items:
            itype   = item["type"]
            content = item["content"]
            page    = item["page"]
            hlevel  = item.get("heading_level")

            if itype in ("table_md", "table_nl"):
                pending_parents.extend(flush_parent())
                table_items.append(item)

            elif itype == "ocr":
                pending_parents.extend(flush_parent())
                pending_parents.append({
                    "parent_text": content,
                    "heading"    : section_heading,
                    "page"       : page,
                    "is_ocr"     : True,
                })
                parent_index += 1

            else:  # text
                if hlevel is not None:
                    pending_parents.extend(flush_parent())
                    section_heading = content
                    page_start      = page
                    parent_buffer.append(content)
                else:
                    if not parent_buffer:
                        page_start = page
                    parent_buffer.append(content)
                    if sum(len(s) for s in parent_buffer) > self.parent_max * 2:
                        pending_parents.extend(flush_parent())

        pending_parents.extend(flush_parent())

        # parent → child
        for pinfo in pending_parents:
            parent_txt = pinfo["parent_text"]
            heading    = pinfo.get("heading", "")
            page       = pinfo.get("page", 1)
            is_ocr     = pinfo.get("is_ocr", False)

            for c_idx, child in enumerate(self._split_text(parent_txt, self.child_max)):
                if not child.strip() or self._is_duplicate(child):
                    continue
                lang = detect_language(child)
                norm = normalize_text(child, lang)
                if not norm.strip():
                    continue
                all_docs.append(Document(
                    page_content=norm,
                    metadata={
                        **base_metadata,
                        "chunk_type"     : "ocr" if is_ocr else "text",
                        "section_heading": heading,
                        "page"           : page,
                        "language"       : lang,
                        "child_index"    : c_idx,
                        "parent_text"    : parent_txt,
                    },
                ))

        # 표 청킹
        for titem in table_items:
            itype   = titem["type"]
            content = titem["content"]
            page    = titem["page"]
            section = titem.get("section", "")

            if itype == "table_md":
                for idx, tc in enumerate(self._split_table(content)):
                    if self._is_duplicate(tc):
                        continue
                    lang = detect_language(tc)
                    all_docs.append(Document(
                        page_content=tc,
                        metadata={
                            **base_metadata,
                            "chunk_type"     : "table_md",
                            "section_heading": section,
                            "page"           : page,
                            "language"       : lang,
                            "child_index"    : idx,
                            "parent_text"    : content,
                        },
                    ))
            else:  # table_nl
                if self._is_duplicate(content):
                    continue
                lang = detect_language(content)
                norm = normalize_text(content, lang)
                if not norm.strip():
                    continue
                all_docs.append(Document(
                    page_content=norm,
                    metadata={
                        **base_metadata,
                        "chunk_type"     : "table_nl",
                        "section_heading": section,
                        "page"           : page,
                        "language"       : lang,
                        "child_index"    : 0,
                    },
                ))

        return all_docs

    def _split_text(self, text: str, max_chars: int) -> list[str]:
        if len(text) <= max_chars:
            return [text] if text.strip() else []
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = start + max_chars
            if end >= len(text):
                tail = text[start:].strip()
                if tail:
                    chunks.append(tail)
                break
            for sep in ("\n\n", "\n", ". ", " "):
                pos = text.rfind(sep, start, end)
                if pos > start:
                    split_at = pos + len(sep)
                    break
            else:
                split_at = end
            chunk = text[start:split_at].strip()
            if chunk:
                chunks.append(chunk)
            start = max(start + 1, split_at - self.overlap)
        return chunks

    def _split_table(self, md_table: str) -> list[str]:
        if len(md_table) <= TABLE_MAX_CHARS:
            return [md_table]
        lines = md_table.split("\n")
        if len(lines) < 3:
            return [md_table]
        header_lines = lines[:2]
        data_lines   = lines[2:]
        chunks: list[str] = []
        batch:  list[str] = []
        batch_chars = sum(len(h) + 1 for h in header_lines)
        for line in data_lines:
            if batch_chars + len(line) + 1 > TABLE_MAX_CHARS and batch:
                chunks.append("\n".join(header_lines + batch))
                batch       = []
                batch_chars = sum(len(h) + 1 for h in header_lines)
            batch.append(line)
            batch_chars += len(line) + 1
        if batch:
            chunks.append("\n".join(header_lines + batch))
        return chunks if chunks else [md_table]