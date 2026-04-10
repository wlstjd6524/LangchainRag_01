import os
import tempfile
import boto3
import pandas as pd
import sqlite3
from dotenv import load_dotenv

load_dotenv()

S3_BUCKET      = os.getenv("S3_BUCKET",      "esg-agent-bucket")
S3_CSV_PREFIX  = os.getenv("S3_CSV_PREFIX",  "data/")
S3_DB_PREFIX   = os.getenv("S3_DB_PREFIX",   "db/")
AWS_REGION     = os.getenv("AWS_REGION",     "ap-northeast-2")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "emission_factor.db")

TABLE_NAME_MAP = {
    "cleaned_korea_lci_db.csv":       "korea_lci",
    "master_defra_scope3_korean.csv": "defra_scope3",
    "master_epa_spend_korean.csv":    "epa_spend",
}


def get_s3_client():
    return boto3.client(
        "s3",
        region_name=AWS_REGION,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )


def download_csvs_from_s3(s3, tmp_dir: str) -> list[str]:
    """s3://esg-agent-bucket/excel/ 에서 CSV 파일 다운로드"""
    paginator = s3.get_paginator("list_objects_v2")
    pages     = paginator.paginate(Bucket=S3_BUCKET, Prefix=S3_CSV_PREFIX)

    downloaded = []
    for page in pages:
        for obj in page.get("Contents", []):
            key      = obj["Key"]
            filename = os.path.basename(key)
            if not filename.lower().endswith(".csv"):
                continue
            if filename not in TABLE_NAME_MAP:
                print(f"  ⏭️  {filename} : 매핑 없음, 스킵")
                continue
            local_path = os.path.join(tmp_dir, filename)
            print(f"  ⬇️  다운로드: s3://{S3_BUCKET}/{key}")
            s3.download_file(S3_BUCKET, key, local_path)
            downloaded.append(local_path)

    return downloaded


def csv_to_sqlite(csv_paths: list[str]) -> list[str]:
    """CSV 파일들을 SQLite DB로 저장"""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn   = sqlite3.connect(DB_PATH)
    tables = []

    for local_path in csv_paths:
        filename   = os.path.basename(local_path)
        table_name = TABLE_NAME_MAP[filename]

        try:
            df = pd.read_csv(local_path)

            if df.empty:
                print(f"  ⚠️  {filename} : 빈 파일 스킵")
                continue

            df.to_sql(table_name, conn, if_exists="replace", index=False)
            tables.append(table_name)
            print(f"  ✅ {filename} → [{table_name}] ({len(df)}행 × {len(df.columns)}열)")
            print(f"      컬럼: {df.columns.tolist()}")

        except Exception as e:
            print(f"  ⚠️  {filename} 처리 실패: {e}")

    conn.close()
    return tables


def upload_db_to_s3(s3):
    """SQLite DB를 S3에 업로드"""
    s3_key = f"{S3_DB_PREFIX}emission_factor.db"
    print(f"  ⬆️  업로드: s3://{S3_BUCKET}/{s3_key}")
    s3.upload_file(DB_PATH, S3_BUCKET, s3_key)


def main():
    missing = [v for v in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"] if not os.getenv(v)]
    if missing:
        print(f"❌ .env에 다음 값이 없습니다: {', '.join(missing)}")
        return

    s3 = get_s3_client()

    # S3 → 임시 폴더로 CSV 다운로드
    with tempfile.TemporaryDirectory() as tmp_dir:
        csv_paths = download_csvs_from_s3(s3, tmp_dir)

        if not csv_paths:
            print(f"❌ s3://{S3_BUCKET}/{S3_CSV_PREFIX} 에 CSV 파일이 없습니다.")
            return

        print(f"\n🚀 총 {len(csv_paths)}개 CSV 파일 처리 시작...\n")

        tables = csv_to_sqlite(csv_paths)

    if not tables:
        print("❌ 생성된 테이블이 없습니다.")
        return

    print(f"\n☁️  S3 업로드 중: s3://{S3_BUCKET}/{S3_DB_PREFIX}")
    upload_db_to_s3(s3)

    print(f"\n🎉 완료! {len(tables)}개 테이블 → s3://{S3_BUCKET}/{S3_DB_PREFIX}emission_factor.db")


if __name__ == "__main__":
    main()