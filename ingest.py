import os
import re
import pickle
import time
import shutil
from dotenv import load_dotenv
from langchain_community.document_loaders import PDFPlumberLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_upstage import UpstageEmbeddings
from langchain_chroma import Chroma
from langchain_classic.embeddings import CacheBackedEmbeddings
from langchain_classic.storage import LocalFileStore

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "PDF")
VECTORSTORE_DIR = os.path.join(BASE_DIR, "vectorstore")
EMBEDDING_CACHE_DIR = os.path.join(BASE_DIR, "embedding_cache")
BM25_CACHE_FILE = os.path.join(VECTORSTORE_DIR, "bm25_docs.pkl")


def parse_filename_metadata(filename: str) -> dict:
    name = os.path.splitext(filename)[0]
    parts = name.split('_')

    if len(parts) >= 3:
        raw_year = parts[0]
        year_digits = re.sub(r'\D', '', raw_year)
        year = '공통' if (not year_digits or year_digits == '0000') else year_digits
        company = parts[1]
        doc_category = ''.join(parts[2:])
    elif len(parts) == 2:
        raw_year = parts[0]
        year_digits = re.sub(r'\D', '', raw_year)
        year = '공통' if (not year_digits or year_digits == '0000') else year_digits
        company = parts[1]
        doc_category = '문서'
    else:
        year = '공통'
        company = '알수없음'
        doc_category = '문서'

    return {'year': year, 'company': company, 'doc_category': doc_category}


def main():
    if not os.path.exists(DATA_DIR):
        print(f"❌ 폴더를 찾을 수 없습니다: {DATA_DIR}")
        return

    if os.path.exists(VECTORSTORE_DIR):
        shutil.rmtree(VECTORSTORE_DIR)
    os.makedirs(VECTORSTORE_DIR, exist_ok=True)
    os.makedirs(EMBEDDING_CACHE_DIR, exist_ok=True)

    pdf_files = [f for f in os.listdir(DATA_DIR) if f.lower().endswith('.pdf')]
    if not pdf_files:
        print(f"❌ PDF 파일이 없습니다: {DATA_DIR}")
        return

    print(f"🚀 총 {len(pdf_files)}개 PDF 처리 시작...")

    all_docs = []
    for filename in pdf_files:
        try:
            loader = PDFPlumberLoader(os.path.join(DATA_DIR, filename))
            pages = loader.load()
            meta = parse_filename_metadata(filename)
            for page in pages:
                page.metadata.update(meta)
                page.metadata['source_file'] = filename
            all_docs.extend(pages)
        except Exception as e:
            print(f"⚠️ {filename} 로드 실패: {e}")

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=150,
        separators=["\n\n", "\n", ".", " ", ""]
    )
    split_docs = text_splitter.split_documents(all_docs)
    total_chunks = len(split_docs)
    print(f"✅ 총 {total_chunks}개 청크 생성")

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

    print(f"🎉 완료! {total_chunks}개 청크 저장됨")


if __name__ == "__main__":
    main()