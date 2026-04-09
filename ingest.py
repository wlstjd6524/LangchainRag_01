import os
import re
import pickle
import time
import shutil
import tempfile
import boto3
from dotenv import load_dotenv
from langchain_community.document_loaders import PDFPlumberLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_upstage import UpstageEmbeddings
from langchain_chroma import Chroma
from langchain_classic.embeddings import CacheBackedEmbeddings
from langchain_classic.storage import LocalFileStore

load_dotenv()

S3_BUCKET        = os.getenv("S3_BUCKET",        "esg-agent-bucket")
S3_PDF_PREFIX    = os.getenv("S3_PDF_PREFIX",    "pdf/")
S3_OUTPUT_PREFIX = os.getenv("S3_OUTPUT_PREFIX", "vectorstore/")
AWS_REGION       = os.getenv("AWS_REGION",       "ap-northeast-2")
BASE_DIR            = os.path.dirname(os.path.abspath(__file__))
VECTORSTORE_DIR     = os.path.join(BASE_DIR, "vectorstore")
EMBEDDING_CACHE_DIR = os.path.join(BASE_DIR, "embedding_cache")
BM25_CACHE_FILE     = os.path.join(VECTORSTORE_DIR, "bm25_docs.pkl")


def get_s3_client():
    return boto3.client(
        "s3",
        region_name=AWS_REGION,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )


def download_pdfs_from_s3(s3, tmp_dir: str) -> list[str]:
    """s3://esg-agent-bucket/pdf/ 에서 PDF를 임시 폴더로 다운로드"""
    paginator = s3.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=S3_BUCKET, Prefix=S3_PDF_PREFIX)

    downloaded = []
    for page in pages:
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.lower().endswith(".pdf"):
                continue
            filename = os.path.basename(key)
            local_path = os.path.join(tmp_dir, filename)
            print(f"  ⬇️  다운로드: s3://{S3_BUCKET}/{key}")
            s3.download_file(S3_BUCKET, key, local_path)
            downloaded.append(local_path)

    return downloaded


def upload_dir_to_s3(s3, local_dir: str, s3_prefix: str):
    """로컬 디렉토리 전체를 s3://esg-agent-bucket/vectorstore/ 에 업로드"""
    for root, _, files in os.walk(local_dir):
        for filename in files:
            local_path = os.path.join(root, filename)
            relative = os.path.relpath(local_path, local_dir)
            s3_key = os.path.join(s3_prefix, relative).replace("\\", "/")
            print(f"  ⬆️  업로드: s3://{S3_BUCKET}/{s3_key}")
            s3.upload_file(local_path, S3_BUCKET, s3_key)


def parse_filename_metadata(filename: str) -> dict:
    name = os.path.splitext(filename)[0]
    parts = name.split("_")

    if len(parts) >= 3:
        raw_year = parts[0]
        year_digits = re.sub(r"\D", "", raw_year)
        year = "공통" if (not year_digits or year_digits == "0000") else year_digits
        company = parts[1]
        doc_category = "".join(parts[2:])
    elif len(parts) == 2:
        raw_year = parts[0]
        year_digits = re.sub(r"\D", "", raw_year)
        year = "공통" if (not year_digits or year_digits == "0000") else year_digits
        company = parts[1]
        doc_category = "문서"
    else:
        year = "공통"
        company = "알수없음"
        doc_category = "문서"

    return {"year": year, "company": company, "doc_category": doc_category}


def main():
    if os.path.exists(VECTORSTORE_DIR):
        shutil.rmtree(VECTORSTORE_DIR)
    os.makedirs(VECTORSTORE_DIR, exist_ok=True)
    os.makedirs(EMBEDDING_CACHE_DIR, exist_ok=True)

    s3 = get_s3_client()
    with tempfile.TemporaryDirectory() as tmp_dir:
        pdf_files = download_pdfs_from_s3(s3, tmp_dir)

        if not pdf_files:
            print(f"❌ s3://{S3_BUCKET}/{S3_PDF_PREFIX} 에 PDF가 없습니다.")
            return

        print(f"\n🚀 총 {len(pdf_files)}개 PDF 처리 시작...\n")

        all_docs = []
        for local_path in pdf_files:
            filename = os.path.basename(local_path)
            try:
                loader = PDFPlumberLoader(local_path)
                pages = loader.load()
                meta = parse_filename_metadata(filename)
                for page in pages:
                    page.metadata.update(meta)
                    page.metadata["source_file"] = filename
                all_docs.extend(pages)
                print(f"  ✅ {filename} ({len(pages)}페이지)")
            except Exception as e:
                print(f"  ⚠️  {filename} 로드 실패: {e}")

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=150,
        separators=["\n\n", "\n", ".", " ", ""]
    )
    split_docs = text_splitter.split_documents(all_docs)
    total_chunks = len(split_docs)
    print(f"\n✅ 총 {total_chunks}개 청크 생성\n")

    raw_embeddings = UpstageEmbeddings(model="solar-embedding-1-large-passage")
    store = LocalFileStore(EMBEDDING_CACHE_DIR)
    embeddings = CacheBackedEmbeddings.from_bytes_store(
        underlying_embeddings=raw_embeddings,
        document_embedding_cache=store,
        namespace="esg-upstage"
    )

    print("💎 임베딩 및 벡터 DB 저장 시작...")
    batch_size = 100
    vectorstore = None
    for i in range(0, total_chunks, batch_size):
        batch = split_docs[i: i + batch_size]
        try:
            if vectorstore is None:
                vectorstore = Chroma.from_documents(
                    documents=batch,
                    embedding=embeddings,
                    persist_directory=VECTORSTORE_DIR
                )
            else:
                vectorstore.add_documents(batch)
            print(f"  {min(i + batch_size, total_chunks)} / {total_chunks}")
            time.sleep(0.1)
        except Exception as e:
            print(f"❌ 배치 처리 실패 (index {i}): {e}")
            return

    with open(BM25_CACHE_FILE, "wb") as f:
        pickle.dump(split_docs, f)
    print("✅ BM25 캐시 저장 완료")

    print(f"\n☁️  S3 업로드 중: s3://{S3_BUCKET}/{S3_OUTPUT_PREFIX}")
    upload_dir_to_s3(s3, VECTORSTORE_DIR, S3_OUTPUT_PREFIX)

    print(f"\n🎉 완료! {total_chunks}개 청크 → s3://{S3_BUCKET}/{S3_OUTPUT_PREFIX}")


if __name__ == "__main__":
    main()