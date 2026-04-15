import logging
import os
import tempfile
from typing import Optional

import pdfplumber

try:
    from doctr.io import DocumentFile
    from doctr.models import ocr_predictor
    DOCTR_AVAILABLE = True
except ImportError:
    DOCTR_AVAILABLE = False

logger = logging.getLogger(__name__)

OCR_TEXT_DENSITY = 0.05
COLUMN_GAP_MIN   = 30


class StructuredPDFParser:
    """
    표·다단 레이아웃 보고서 특화 PDF 파서.

    처리 순서 (페이지별):
    1. 스캔 페이지 감지 → DocTR OCR 폴백
    2. 표 추출 → Markdown 변환 (table_md) + 자연어 요약 (table_nl)
    3. 본문에서 표 영역 제외 (±5pt 여백 확장)
    4. 다단 감지: x-좌표 분포로 열 경계 탐지
    5. 열 단위 읽기 순서 복원 (좌→우, 각 열 내 상→하)
    6. 폰트 크기 분석 → 헤딩 레벨 태깅
    7. 현재 섹션 헤딩 추적 → 표 컨텍스트 연결
    """

    _ocr_model = None

    @classmethod
    def _get_ocr_model(cls):
        if cls._ocr_model is None:
            if not DOCTR_AVAILABLE:
                logger.warning("doctr 패키지 없음. OCR 폴백 비활성화.")
                return None
            logger.info("DocTR OCR 모델 초기화 중...")
            cls._ocr_model = ocr_predictor(
                det_arch="db_resnet50",
                reco_arch="crnn_vgg16_bn",
                pretrained=True,
            )
        return cls._ocr_model

    @staticmethod
    def _is_scan_page(page: pdfplumber.page.Page) -> bool:
        words = page.extract_words()
        if not words:
            return True
        text_area = sum((w["x1"] - w["x0"]) * (w["bottom"] - w["top"]) for w in words)
        page_area = (page.width or 1) * (page.height or 1)
        return (text_area / page_area) < OCR_TEXT_DENSITY

    @staticmethod
    def _table_to_markdown(table: list[list]) -> str:
        if not table or not table[0]:
            return ""
        col_count = max(len(row) for row in table)
        prev_row  = [""] * col_count
        filled    = []
        for row in table:
            padded  = list(row) + [None] * (col_count - len(row))
            new_row = []
            for j, cell in enumerate(padded):
                if cell is None or str(cell).strip() == "":
                    new_row.append(prev_row[j])
                else:
                    new_row.append(str(cell).strip().replace("\n", " "))
            prev_row = new_row
            filled.append(new_row)

        cleaned = [row for row in filled if any(v for v in row)]
        if not cleaned:
            return ""

        header    = cleaned[0]
        separator = ["---"] * col_count
        lines = [
            "| " + " | ".join(header)    + " |",
            "| " + " | ".join(separator) + " |",
        ]
        lines.extend("| " + " | ".join(row) + " |" for row in cleaned[1:])
        return "\n".join(lines)

    @staticmethod
    def _generate_table_nl_summary(md_table: str, section_heading: str) -> str:
        lines = [l for l in md_table.split("\n") if l.strip()]
        if len(lines) < 2:
            return ""
        headers       = [h.strip() for h in lines[0].strip("|").split("|") if h.strip()]
        num_data_rows = max(0, len(lines) - 2)
        parts = []
        if section_heading:
            parts.append(f"[{section_heading}]에 관한 표")
        else:
            parts.append("표 데이터")
        if headers:
            col_str = ", ".join(headers[:6])
            if len(headers) > 6:
                col_str += f" 외 {len(headers) - 6}개 열"
            parts.append(f"열 구성: {col_str}")
        parts.append(f"총 {num_data_rows}행의 데이터 포함")
        if len(lines) > 2:
            first_row = [v.strip() for v in lines[2].strip("|").split("|") if v.strip()]
            if first_row and len(first_row[0]) <= 50:
                parts.append(f"첫 항목: {first_row[0]}")
        return " | ".join(parts)

    @staticmethod
    def _detect_heading(line_chars: list[dict], avg_font_size: float) -> Optional[int]:
        if not line_chars or avg_font_size <= 0:
            return None
        sizes = [c.get("size", 0) for c in line_chars if c.get("size", 0) > 0]
        if not sizes:
            return None
        ratio = max(sizes) / avg_font_size
        if ratio >= 1.60:
            return 1
        if ratio >= 1.30:
            return 2
        if ratio >= 1.10:
            return 3
        return None

    @staticmethod
    def _detect_and_sort_columns(lines: list[dict], page_width: float) -> list[dict]:
        if not lines:
            return lines
        mid = (page_width or 595) / 2
        left_lines, right_lines, mid_lines = [], [], []
        for ln in lines:
            x0 = ln.get("x0") or 0
            x1 = ln.get("x1") or page_width or 595
            xc = (x0 + x1) / 2
            if xc < mid - COLUMN_GAP_MIN / 2:
                left_lines.append(ln)
            elif xc > mid + COLUMN_GAP_MIN / 2:
                right_lines.append(ln)
            else:
                mid_lines.append(ln)
        if len(left_lines) >= 3 and len(right_lines) >= 3:
            mid_sorted   = sorted(mid_lines,   key=lambda x: x.get("top", 0))
            left_sorted  = sorted(left_lines,  key=lambda x: x.get("top", 0))
            right_sorted = sorted(right_lines, key=lambda x: x.get("top", 0))
            return mid_sorted + left_sorted + right_sorted
        return sorted(lines, key=lambda x: x.get("top", 0))

    def _ocr_page(self, pdf_path: str, zero_based_page: int) -> str:
        """
        DocTR OCR.
        numpy 배열 대신 임시 PNG 파일 경로로 전달하여
        'unsupported object type for argument file' 오류 해결.
        """
        model = self._get_ocr_model()
        if model is None:
            return ""
        try:
            from pdf2image import convert_from_path

            images = convert_from_path(
                pdf_path,
                first_page=zero_based_page + 1,
                last_page=zero_based_page + 1,
                dpi=200,
            )
            if not images:
                return ""

            tmp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp_path = tmp_file.name
            tmp_file.close()

            try:
                images[0].save(tmp_path)
                doc    = DocumentFile.from_images([tmp_path])
                result = model(doc)

                lines_text: list[str] = []
                for ocr_page in result.pages:
                    for block in ocr_page.blocks:
                        for line in block.lines:
                            lines_text.append(
                                " ".join(w.value for w in line.words)
                            )
                return "\n".join(lines_text)

            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        except Exception as e:
            logger.warning(f"OCR 실패 (페이지 {zero_based_page + 1}): {e}")
            return ""

    def parse_pdf(self, pdf_path: str) -> list[dict]:
        results: list[dict] = []

        with pdfplumber.open(pdf_path) as pdf:
            current_section = ""

            for page_num, page in enumerate(pdf.pages, start=1):

                # 1. 스캔 페이지 → OCR
                if self._is_scan_page(page):
                    logger.debug(f"  페이지 {page_num}: 스캔 감지 → OCR")
                    ocr_text = self._ocr_page(pdf_path, page_num - 1)
                    if ocr_text.strip():
                        results.append({
                            "type": "ocr", "content": ocr_text,
                            "page": page_num, "heading_level": None,
                            "section": current_section, "bbox": None,
                        })
                    continue

                # 2. 표 추출
                table_bboxes: list[tuple] = []
                try:
                    tables = page.find_tables()
                except Exception:
                    tables = []

                for tbl in tables:
                    try:
                        md = self._table_to_markdown(tbl.extract())
                    except Exception:
                        continue
                    if not md.strip():
                        continue
                    bbox = tbl.bbox
                    table_bboxes.append(bbox)
                    results.append({
                        "type": "table_md", "content": md,
                        "page": page_num, "heading_level": None,
                        "section": current_section, "bbox": bbox,
                    })
                    nl = self._generate_table_nl_summary(md, current_section)
                    if nl.strip():
                        results.append({
                            "type": "table_nl", "content": nl,
                            "page": page_num, "heading_level": None,
                            "section": current_section, "bbox": bbox,
                        })

                # 3. 본문 텍스트 (표 영역 제외 ±5pt)
                text_page = page
                for bbox in table_bboxes:
                    x0b, y0b, x1b, y1b = bbox
                    try:
                        text_page = text_page.filter(
                            lambda obj,
                            _x0=x0b, _y0=y0b, _x1=x1b, _y1=y1b: not (
                                obj.get("x0",   999) >= _x0 - 5 and
                                obj.get("x1",    -1) <= _x1 + 5 and
                                obj.get("top",  999) >= _y0 - 5 and
                                obj.get("bottom", -1) <= _y1 + 5
                            )
                        )
                    except Exception:
                        pass

                # 4. 평균 폰트 크기 계산
                all_chars  = getattr(text_page, "chars", [])
                font_sizes = [c.get("size", 0) for c in all_chars if c.get("size", 0) > 0]
                avg_font_size = sum(font_sizes) / len(font_sizes) if font_sizes else 10.0

                # 5. 라인 추출 + 다단 재정렬
                try:
                    raw_lines = text_page.extract_text_lines(layout=True) or []
                except Exception:
                    raw_lines = []

                sorted_lines = self._detect_and_sort_columns(
                    raw_lines, float(page.width or 595)
                )

                if sorted_lines:
                    for line_info in sorted_lines:
                        line_text = line_info.get("text", "").strip()
                        if not line_text:
                            continue
                        line_top   = line_info.get("top", -9999)
                        line_chars = [
                            c for c in all_chars
                            if abs(c.get("top", 0) - line_top) < 5
                        ]
                        heading_level = self._detect_heading(line_chars, avg_font_size)
                        if heading_level is not None:
                            current_section = line_text
                        results.append({
                            "type": "text",
                            "content": line_text,
                            "page": page_num,
                            "heading_level": heading_level,
                            "section": current_section,
                            "bbox": (
                                line_info.get("x0"), line_info.get("top"),
                                line_info.get("x1"), line_info.get("bottom"),
                            ),
                        })
                else:
                    raw = text_page.extract_text() or ""
                    if raw.strip():
                        results.append({
                            "type": "text", "content": raw,
                            "page": page_num, "heading_level": None,
                            "section": current_section, "bbox": None,
                        })

        return results