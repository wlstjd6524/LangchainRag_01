import re
import unicodedata
from typing import Optional
from konlpy.tag import Okt
from langdetect import detect_langs, LangDetectException


def detect_language(text: str) -> str:
    """계층적 언어 감지: 한글 비율 1차 → langdetect 2차"""
    if not text or not text.strip():
        return "unknown"
    ko_chars    = len(re.findall(r"[\uAC00-\uD7A3\u1100-\u11FF\u3130-\u318F]", text))
    ascii_chars = len(re.findall(r"[A-Za-z]", text))
    total       = ko_chars + ascii_chars
    if total == 0:
        return "unknown"
    ko_ratio = ko_chars / total
    if ko_ratio >= 0.70:
        return "ko"
    if ko_ratio <= 0.30:
        return "en"
    try:
        langs   = detect_langs(text[:500])
        top_map = {l.lang: l.prob for l in langs}
        if top_map.get("ko", 0) >= 0.5:
            return "mixed_ko"
        if top_map.get("en", 0) >= 0.5:
            return "mixed_en"
    except LangDetectException:
        pass
    return "mixed"


_FULLWIDTH_TABLE = str.maketrans(
    "！＂＃＄％＆＇（）＊＋，－．／０１２３４５６７８９：；＜＝＞？＠"
    "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
    "［＼］＾＿｀ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ｛｜｝～",
    '!"#$%&\'()*+,-./'
    "0123456789:;<=>?@"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~",
)

def normalize_text(text: str, lang: str = "ko") -> str:
    """유니코드 정규화 + 특수공백 제거 + 전각→반각 + 연속공백 정리"""
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"[\u00A0\u2000-\u200B\u3000\uFEFF]", " ", text)
    text = re.sub(r"[^\S\n\t ]", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    if lang in ("ko", "mixed_ko", "mixed", "mixed_en"):
        text = text.translate(_FULLWIDTH_TABLE)
    return text.strip()


_okt: Optional[Okt] = None

def _get_okt() -> Okt:
    global _okt
    if _okt is None:
        _okt = Okt()
    return _okt

def morpheme_tokenize(text: str) -> list[str]:
    """한국어 형태소 + 영어 소문자 하이브리드 토큰화 (BM25 전용)"""
    tokens: list[str] = []
    okt      = _get_okt()
    segments = re.split(r"([A-Za-z][A-Za-z0-9\-\.]*(?:\s+[A-Za-z][A-Za-z0-9\-\.]*)*)", text)
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        if re.match(r"^[A-Za-z]", seg):
            tokens.extend(w.lower() for w in seg.split() if len(w) > 1)
        else:
            try:
                morphs = okt.pos(seg, norm=True, stem=True)
                tokens.extend(
                    word for word, pos in morphs
                    if pos in ("Noun", "Alpha", "Number", "Foreign") and len(word) > 1
                )
            except Exception:
                tokens.extend(seg.split())
    return [t for t in tokens if t.strip()]