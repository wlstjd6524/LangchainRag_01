import os
import pickle
import shutil
from typing import Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from langchain_upstage import UpstageEmbeddings
from langchain_chroma import Chroma
from langchain_community.retrievers import BM25Retriever
from langchain_classic.retrievers import EnsembleRetriever
import boto3
from langchain_core.documents import Document
from utils import morpheme_tokenize
from rank_bm25 import BM25Okapi

load_dotenv()

S3_BUCKET        = os.getenv("S3_BUCKET",        "esg-agent-bucket")
S3_OUTPUT_PREFIX = os.getenv("S3_OUTPUT_PREFIX", "vectorstore/")
AWS_REGION       = os.getenv("AWS_REGION",       "ap-northeast-2")

BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
VECTORSTORE_DIR = os.path.join(BASE_DIR, "vectorstore")
BM25_CACHE_FILE = os.path.join(VECTORSTORE_DIR, "bm25_docs.pkl")


def _download_vectorstore_from_s3():
    """S3의 vectorstore/ 를 로컬에 동기화"""
    if os.path.exists(VECTORSTORE_DIR):
        shutil.rmtree(VECTORSTORE_DIR)
    os.makedirs(VECTORSTORE_DIR, exist_ok=True)

    s3 = boto3.client(
        "s3",
        region_name=AWS_REGION,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )

    paginator = s3.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=S3_BUCKET, Prefix=S3_OUTPUT_PREFIX)

    downloaded_count = 0
    for page in pages:
        for obj in page.get("Contents", []):
            key = obj["Key"]
            relative = os.path.relpath(key, S3_OUTPUT_PREFIX)
            local_path = os.path.join(VECTORSTORE_DIR, relative)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            s3.download_file(S3_BUCKET, key, local_path)
            downloaded_count += 1

    return downloaded_count


def _build_bm25_retriever(
    docs: list[Document],
    tokenized: list[list[str]],
    k: int = 5,
) -> BM25Retriever:
    """
    pre-tokenized corpus로 BM25Okapi 인덱스를 직접 구성하고 BM25Retriever를 반환한다.
    쿼리 시에도 morpheme_tokenize가 적용된다.
    """
    bm25_index = BM25Okapi(tokenized)
    retriever  = BM25Retriever(
        vectorizer = bm25_index,
        docs = docs,
        k = k,
        preprocess_func = morpheme_tokenize,
    )
    return retriever


_db_ready = False
vectorstore = None
docs: list[Document] = []
tokenized_corpus: list[list[str]] = []
bm25_retriever = None

try:
    print("☁️  S3에서 벡터 DB 다운로드 중...")
    count = _download_vectorstore_from_s3()
    print(f"✅ {count}개 파일 다운로드 완료")

    print("[1/3] Chroma 벡터 DB 로드 중...")
    embeddings = UpstageEmbeddings(model="solar-embedding-1-large-passage")
    vectorstore = Chroma(persist_directory=VECTORSTORE_DIR, embedding_function=embeddings)
    print(f"[1/3] Chroma 로드 완료")

    print("[2/3] BM25 캐시 로드 중...")
    with open(BM25_CACHE_FILE, "rb") as f:
        raw = pickle.load(f)

    if isinstance(raw, dict):
        docs = raw["docs"]
        tokenized_corpus = raw["tokenized"]
        print("[2/3] BM25 캐시 로드 완료 (문서 {len(docs)}개, 형태소 토큰 캐시 보유)")
    else:
        # 레거시 list 포맷: 형태소 재토큰화 필요 (시간 소요)
        docs = raw
        print(f"[2/3] 레거시 BM25 캐시 감지 (문서 {len(docs)}개) — 형태소 재토큰화 중...")
        print(" ※ 이 작업은 문서 수에 따라 수 분이 걸릴 수 있습니다.")
        print(" ※ ingest.py를 재실행하면 다음부터는 이 단계가 생략됩니다.")
        tokenized_corpus = []
        for i, d in enumerate(docs):
            tokenized_corpus.append(morpheme_tokenize(d.page_content))
            if (i + 1) % 100 == 0:
                print(f"    토큰화 진행: {i + 1}/{len(docs)}")
        print(f"[2/3] 형태소 재토큰화 완료")

    print("[3/3] BM25 인덱스 구성 중...")
    bm25_retriever = _build_bm25_retriever(docs, tokenized_corpus, k=5)
    print("[3/3] BM25 인덱스 구성 완료")

    _db_ready = True
    print("✅ RAG DB 로드 완료")

except Exception as e:
    print(f"⚠️ RAG DB 로드 실패: {e}\ningest.py를 먼저 실행해주세요.")


def _get_filtered_bm25(
    year: Optional[str] = None,
    company: Optional[str] = None,
    doc_category: Optional[str] = None,
) -> BM25Retriever:
    """
    메타데이터 조건에 맞는 문서만으로 BM25 인덱스 재구성.
    pre-tokenized corpus를 재사용하므로 빠름.
    """
    if not any([year, company, doc_category]):
        return bm25_retriever

    filtered_pairs = [
        (doc, tok)
        for doc, tok in zip(docs, tokenized_corpus)
        if (not year or doc.metadata.get("year") == year)
        and (not company or doc.metadata.get("company") == company)
        and (not doc_category or doc.metadata.get("doc_category") == doc_category)
    ]

    if not filtered_pairs:
        return bm25_retriever

    filtered_docs, filtered_tok = zip(*filtered_pairs)
    return _build_bm25_retriever(list(filtered_docs), list(filtered_tok), k=5)


class ESGRagInput(BaseModel):
    query: str = Field(description="검색할 질문이나 핵심 키워드")
    year: Optional[str] = Field(
        default=None,
        description="4자리 연도 (예: '2024', '2025'). 연도 무관 가이드라인은 '공통'."
    )
    company: Optional[str] = Field(
        default=None,
        description="기업명 (예: 'SK하이닉스', 'SK텔레콤', 'SKC'). 공통 가이드라인은 '공통'."
    )
    doc_category: Optional[str] = Field(
        default=None,
        description="문서 카테고리 (예: '지속가능경영보고서', 'TCFD보고서', 'TNFD보고서', "
                    "'인권경영보고서', '기업지배구조보고서', 'K-ESG가이드라인', '기후정보공개보고서')"
    )


@tool("search_esg_guideline", args_schema=ESGRagInput)
def search_pdf_tool(
    query: str,
    year: Optional[str] = None,
    company: Optional[str] = None,
    doc_category: Optional[str] = None,
) -> str:
    """
    ESG 가이드라인, 지속가능경영보고서 등에서 환경(E), 사회(S), 지배구조(G) 데이터를 검색합니다.
    연도, 기업명, 문서 종류로 필터링하여 정밀한 검색이 가능합니다.
    """
    if not _db_ready:
        return "⚠️ RAG 데이터베이스가 초기화되지 않았습니다. ingest.py를 먼저 실행해주세요."

    def build_filter(y, c, d):
        conditions = []
        if y: conditions.append({"year": y})
        if c: conditions.append({"company": c})
        if d: conditions.append({"doc_category": d})
        if len(conditions) == 0: return {}
        if len(conditions) == 1: return conditions[0]
        return {"$and": conditions}

    def run_search(y, c, d):
        f = build_filter(y, c, d)
        search_kwargs = {"k": 5}
        if f:
            search_kwargs["filter"] = f
        vector_retriever = vectorstore.as_retriever(search_kwargs=search_kwargs)
        active_bm25 = _get_filtered_bm25(y, c, d) if f else bm25_retriever
        ensemble = EnsembleRetriever(
            retrievers=[active_bm25, vector_retriever],
            weights=[0.5, 0.5]
        )
        return ensemble.invoke(query)

    attempts = [
        (year, company, doc_category),
        (year, company, None),
        (None, company, None),
        (None, None, None),
    ]

    results = []
    for y, c, d in attempts:
        results = run_search(y, c, d)
        if results:
            break

    if not results:
        return "검색 결과가 없습니다. 다른 키워드로 다시 시도해보세요."

    formatted_results = []
    for i, doc in enumerate(results):
        meta = doc.metadata
        source = (f"[출처 {i+1}] {meta.get('company', '공통')} "
                  f"{meta.get('year', '')} - {meta.get('doc_category', '문서')}")
        formatted_results.append(f"--- {source} ---\n{doc.page_content}\n")

    return "\n\n".join(formatted_results)