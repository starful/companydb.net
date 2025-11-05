# app.py

import os
import json
import redis
from flask import Flask, render_template, request, make_response
from datetime import datetime, timezone

app = Flask(__name__)

# --- Redis 설정 ---
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_DB = int(os.getenv('REDIS_DB', 0))

try:
    redis_client = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
    redis_client.ping()
    print("Redis에 성공적으로 연결되었습니다.")
except redis.exceptions.ConnectionError as e:
    print(f"Redis 연결 오류: {e}. Redis 없이 애플리케이션을 실행합니다.")
    redis_client = None

# --- 캐시 키 설정 ---
REDIS_ALL_POSTS_KEY = "all_hatena_posts"

def get_posts_from_cache():
    """Redis 캐시에서 모든 게시물 목록을 가져옵니다. 캐시가 없으면 빈 리스트를 반환합니다."""
    if redis_client:
        cached_data = redis_client.get(REDIS_ALL_POSTS_KEY)
        if cached_data:
            print("Redis 캐시에서 게시물 데이터를 로드합니다.")
            return json.loads(cached_data)
    print("경고: Redis 캐시가 비어있습니다. 백그라운드 Job이 실행될 때까지 기다려주세요.")
    return []

@app.route('/')
def index():
    """메인 검색 페이지를 렌더링합니다."""
    description = "companyDB는 はてなブログ(하테나 블로그)의 게시물을 빠르게 검색하고 탐색할 수 있는 웹 애플리케이션입니다. 원하는 키워드로 신속하게 정보를 찾아보세요."
    return render_template('index.html', description=description)

@app.route('/list')
def list_results():
    """검색 결과를 보여주는 페이지를 렌더링합니다."""
    query = request.args.get('keyword', '').lower()
    page_title = f"「{query}」의 검색 결과 - companyDB"
    description = f"「{query}」에 대한 companyDB의 검색 결과 목록입니다. はてなブログ(하테나 블로그)의 관련 게시물을 빠르게 찾아보세요."
    
    if not query:
        return render_template('index.html', error="검색어를 입력해주세요.")
    
    try:
        all_posts = get_posts_from_cache()
        search_results = [
            post for post in all_posts 
            if query in post.get('title', '').lower() or query in post.get('content', '').lower()
        ]
        
        return render_template('list.html', 
                               keyword=request.args.get('keyword', ''), 
                               results=search_results,
                               page_title=page_title,
                               description=description)
    except Exception as e:
        error_message = f"데이터를 처리하는 중 오류가 발생했습니다: {e}"
        print(error_message) # 서버 로그에 오류 기록
        return render_template('list.html', 
                               keyword=request.args.get('keyword', ''), 
                               error=error_message,
                               page_title=page_title,
                               description=description)

@app.route('/sitemap.xml')
def sitemap_xml():
    """동적으로 sitemap.xml을 생성합니다."""
    try:
        all_posts = get_posts_from_cache()
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