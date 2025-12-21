import os
import json
import frontmatter
from datetime import datetime

CONTENT_DIR = 'app/content'
DATA_DIR = 'data'
INDEX_PATH = os.path.join(DATA_DIR, 'search_index.json')
SITEMAP_PATH = 'app/static/sitemap.xml' # 정적 폴더에 저장
DOMAIN = "https://companydb.net" # 실제 도메인

def update_index_and_sitemap():
    # 폴더 확인
    if not os.path.exists(CONTENT_DIR):
        print(f"⚠️ 폴더가 없습니다: {CONTENT_DIR}")
        return
    
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs('app/static', exist_ok=True)

    index_data = []
    sitemap_urls = []
    
    # 1. 파일 스캔 및 데이터 추출
    for filename in os.listdir(CONTENT_DIR):
        if filename.endswith('.md'):
            try:
                file_path = os.path.join(CONTENT_DIR, filename)
                with open(file_path, 'r', encoding='utf-8') as f:
                    post = frontmatter.load(f)
                    
                    file_slug = filename.replace(".md", "")
                    
                    # 검색 인덱스 데이터
                    index_data.append({
                        "id": post.metadata.get('id', ''),
                        "file": file_slug,
                        "n": post.metadata.get('title', ''),
                        "en": post.metadata.get('title_en', ''),
                        "l": str(post.metadata.get('address', ''))[:30],
                        "s": post.metadata.get('subsidies', 0)
                    })

                    # 사이트맵 URL 추가
                    # 최종 수정일(Last Modified) 가져오기
                    mtime = os.path.getmtime(file_path)
                    lastmod = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')
                    
                    sitemap_urls.append(f"""
    <url>
        <loc>{DOMAIN}/company/{file_slug}</loc>
        <lastmod>{lastmod}</lastmod>
        <changefreq>weekly</changefreq>
        <priority>0.8</priority>
    </url>""")

            except Exception as e:
                print(f"⚠️ Skipping {filename}: {e}")
                continue
    
    # 2. 검색 인덱스(JSON) 저장
    with open(INDEX_PATH, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)
    print(f"✅ 검색 인덱스 갱신 완료 ({len(index_data)}개 기업)")

    # 3. 사이트맵(XML) 생성 및 저장
    sitemap_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>{DOMAIN}/</loc>
        <changefreq>daily</changefreq>
        <priority>1.0</priority>
    </url>
    {''.join(sitemap_urls)}
</urlset>"""

    with open(SITEMAP_PATH, 'w', encoding='utf-8') as f:
        f.write(sitemap_content)
    print(f"✅ 사이트맵 생성 완료: {SITEMAP_PATH} ({len(sitemap_urls)}개 링크)")

if __name__ == "__main__":
    update_index_and_sitemap()