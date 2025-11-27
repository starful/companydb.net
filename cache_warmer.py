import os
import json
from google.cloud import storage
from google.api_core.exceptions import NotFound
from hatena_client import fetch_all_hatena_posts

# --- 설정 ---
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME')
CACHE_FILE_NAME = "companydb_posts.json"
APP_DOMAIN = os.getenv('APP_DOMAIN')

def main():
    """스크립트의 메인 실행 함수"""
    if not APP_DOMAIN or not GCS_BUCKET_NAME:
        print("오류: 필수 환경 변수(APP_DOMAIN, GCS_BUCKET_NAME)가 없습니다.")
        exit(1)

    storage_client = storage.Client()
    bucket = storage_client.bucket(GCS_BUCKET_NAME)

    # 1. GCS에서 기존 데이터 가져오기 (증분 업데이트를 위해)
    existing_posts = []
    try:
        blob = bucket.blob(CACHE_FILE_NAME)
        if blob.exists():
            print("GCS에서 기존 데이터를 다운로드합니다...")
            data_string = blob.download_as_text()
            existing_posts = json.loads(data_string)
            print(f"기존 데이터 {len(existing_posts)}건을 로드했습니다.")
        else:
            print("GCS에 기존 데이터가 없습니다. 전체 수집을 진행합니다.")
    except Exception as e:
        print(f"GCS 읽기 중 경고(무시 가능): {e}")
        existing_posts = []

    # 2. Hatena API 호출 (기존 데이터를 넘겨줌)
    all_posts = fetch_all_hatena_posts(existing_posts)

    if not all_posts:
        print("경고: 수집된 데이터가 없습니다. GCS를 업데이트하지 않습니다.")
        return

    # 3. 결과 GCS 업로드
    try:
        json_data = json.dumps(all_posts, ensure_ascii=False)
        blob = bucket.blob(CACHE_FILE_NAME)
        blob.upload_from_string(json_data, content_type='application/json')
        print(f"성공: 총 {len(all_posts)}개의 게시물을 GCS에 저장했습니다.")
    except Exception as e:
        print(f"치명적 오류: GCS 업로드 실패 - {e}")
        exit(1)

if __name__ == "__main__":
    main()