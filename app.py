import os
import json
import time
from datetime import datetime, timezone, timedelta
from flask import Flask, render_template, request, make_response, jsonify
from google.cloud import storage

app = Flask(__name__)

# --- GCS 설정 ---
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME')
CACHE_FILE_NAME = "companydb_posts.json"
CACHE_TTL = 300  # 5분

# --- 캐시를 클래스로 캡슐화 ---
class InMemoryCache:
    def __init__(self, ttl):
        self.data = []
        self.last_updated = 0
        self.last_updated_str = ""
        self.ttl = ttl

    def is_valid(self):
        return self.data and (time.time() - self.last_updated < self.ttl)

    def get_data(self):
        return self.data

    def update(self, posts, updated_date_str):
        self.data = posts
        self.last_updated = time.time()
        self.last_updated_str = updated_date_str
        print(f"성공: {len(posts)}개의 게시물을 캐시에 로드했습니다. (날짜: {updated_date_str})")

cache = InMemoryCache(ttl=CACHE_TTL)

def get_posts_from_gcs():
    if cache.is_valid():
        return cache.get_data()
    if not GCS_BUCKET_NAME:
        print("오류: GCS_BUCKET_NAME 환경 변수가 설정되지 않았습니다.")
        return []
    print("GCS에서 최신 데이터를 다운로드합니다...")
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.get_blob(CACHE_FILE_NAME)
        if blob:
            data_string = blob.download_as_text()
            posts = json.loads(data_string)
            if blob.updated:
                utc_time = blob.updated
                jst_time = utc_time + timedelta(hours=9)
                date_str = jst_time.strftime('%Y/%m/%d')
            else:
                date_str = datetime.now(timezone(timedelta(hours=9))).strftime('%Y/%m/%d')
            cache.update(posts, date_str)
            return posts
        else:
             print("경고: GCS 파일을 찾을 수 없습니다.")
             return []
    except Exception as e:
        print(f"GCS 읽기 오류: {e}")
        return cache.get_data() if cache.get_data() else []

@app.route('/')
def index():
    """
    메인 애플리케이션 셸(Shell)을 렌더링합니다.
    URL에 keyword 파라미터가 있으면, 해당 검색어로 초기 데이터를 함께 전달합니다.
    """
    get_posts_from_gcs() # 캐시 워밍업
    update_date = cache.last_updated_str
    if not update_date:
         update_date = datetime.now(timezone(timedelta(hours=9))).strftime('%Y/%m/%d')
    
    # 초기 검색어 처리
    keyword = request.args.get('keyword', '').lower()
    initial_results = []
    if keyword:
        all_posts = cache.get_data()
        initial_results = [
            post for post in all_posts
            if keyword in post.get('title', '').lower() or keyword in post.get('content', '').lower()
        ]

    return render_template('index.html', 
                           update_date=update_date,
                           keyword=keyword,
                           initial_results=initial_results)

@app.route('/search')
def search_api():
    """단일 페이지 내에서 비동기 검색을 위한 API 엔드포인트."""
    query = request.args.get('keyword', '').lower()
    if not query:
        return jsonify({"error": "Keyword is required"}), 400

    all_posts = get_posts_from_gcs()
    search_results = [
        post for post in all_posts
        if query in post.get('title', '').lower() or query in post.get('content', '').lower()
    ]
    return jsonify(search_results)

@app.route('/sitemap.xml')
def sitemap_xml():
    try:
        all_posts = get_posts_from_gcs()
        lastmod_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        sitemap_content = render_template('sitemap.xml',
                                          posts=all_posts,
                                          lastmod=lastmod_date,
                                          domain_url=request.url_root)
        response = make_response(sitemap_content)
        response.headers["Content-Type"] = "application/xml"
        return response
    except Exception as e:
        print(f"사이트맵 생성 중 오류 발생: {e}")
        return "Sitemap generation error", 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=True)