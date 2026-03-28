import os
import json
import markdown
import frontmatter
from datetime import datetime
from itertools import groupby
from fastapi import FastAPI, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, PlainTextResponse

# 설정 파일 로드
from .config import (
    BASE_DIR, INDEX_PATH, SITEMAP_PATH, STATIC_DIR, 
    TEMPLATE_DIR, CONTENT_DIR, HUB_DATA
)

app = FastAPI()

# 정적 파일 및 템플릿 설정
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

# 헬퍼 함수: 인덱스 데이터 로드
def get_index_data():
    if not os.path.exists(INDEX_PATH):
        return []
    try:
        with open(INDEX_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
            if not content: return []
            data = json.loads(content)
            return data if isinstance(data, list) else []
    except Exception as e:
        print(f"Error loading index: {e}")
        return []

# 정렬 및 그룹화를 위한 안전한 키 추출 함수 (일본어 강제 매핑)
def get_safe_char(company):
    name = company.get('en') or company.get('n') or "Unknown"
    first_char = name.strip()[0].upper() if name.strip() else "A"
    
    # 1. 영문자이면 그대로 반환
    if 'A' <= first_char <= 'Z':
        return first_char
    
    # 2. 영문자가 아닌 경우(일본어 등) 아스키 코드 합산 후 나머지 연산으로 A~Z 매핑
    char_code = sum(ord(c) for c in first_char)
    mapped_char = chr(ord('A') + (char_code % 26))
    return mapped_char

@app.get("/")
async def home(request: Request):
    index_data = get_index_data()
    total_count = len(index_data)
    latest_companies = index_data[-8:][::-1] if index_data else []
    
    last_updated = datetime.now().strftime("%Y-%m-%d")
    if os.path.exists(INDEX_PATH):
        last_updated = datetime.fromtimestamp(os.path.getmtime(INDEX_PATH)).strftime("%Y-%m-%d")

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "latest": latest_companies,
            "total_count": "{:,}".format(total_count),
            "last_updated": last_updated
        }
    )

@app.get("/search")
async def search(request: Request, q: str = ""):
    results = []
    if q:
        index_data = get_index_data()
        q_lower = q.lower()
        results = [c for c in index_data if q_lower in c.get('n', '').lower() or q_lower in c.get('en', '').lower()]
    
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"results": results, "query": q}
    )

@app.get("/company/{file_id}")
async def detail(request: Request, file_id: str):
    md_path = os.path.join(CONTENT_DIR, f"{file_id}.md")

    if not os.path.exists(md_path):
        parts = file_id.split('_')
        if len(parts) >= 2:
            actual_id_prefix = f"{parts[0]}_{parts[1]}"
            for f in os.listdir(CONTENT_DIR):
                if f.startswith(actual_id_prefix) and f.endswith(".md"):
                    md_path = os.path.join(CONTENT_DIR, f)
                    break

    if not os.path.exists(md_path):
        raise HTTPException(status_code=404, detail="Company report not found")
        
    try:
        with open(md_path, 'r', encoding='utf-8') as f:
            post = frontmatter.load(f)
            company_data = post.metadata
            if 'id' not in company_data: company_data['id'] = file_id
            if 'title_en' not in company_data: company_data['title_en'] = company_data.get('title', 'Unknown')
            if 'subsidies' not in company_data: company_data['subsidies'] = 0
            if 'address' not in company_data: company_data['address'] = 'Unknown'

            content_html = markdown.markdown(post.content, extensions=['extra', 'tables', 'nl2br'])
            
        return templates.TemplateResponse(
            request=request,
            name="detail.html",
            context={"company": company_data, "content": content_html}
        )
    except Exception as e:
        print(f"Detail error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/category/{category_slug}")
async def category_hub(request: Request, category_slug: str):
    category_info = HUB_DATA["categories"].get(category_slug.lower())
    if not category_info:
        raise HTTPException(status_code=404, detail="Category not found")
        
    index_data = get_index_data()
    category_name = category_info["name"]
    
    filtered = [c for c in index_data if c.get('c', '').lower() == category_name.lower()]
    filtered.sort(key=lambda x: (x.get('en') or x.get('n') or "Unknown").strip().upper())

    grouped_results = {}
    for char, group in groupby(filtered, key=get_safe_char):
        if char not in grouped_results: grouped_results[char] = []
        grouped_results[char].extend(list(group))

    alphabet_keys = sorted(grouped_results.keys())

    return templates.TemplateResponse(
        request=request,
        name="hub.html",
        context={
            "title": f"{category_name} Industry",
            "category_name": category_name,
            "total_count": len(filtered),
            "total_subsidies": sum([int(c.get('s', 0)) for c in filtered]),
            "grouped_results": grouped_results,
            "alphabet": alphabet_keys
        }
    )

@app.get("/{page_name}")
async def static_page(request: Request, page_name: str):
    if page_name in ["privacy", "about"]:
        return templates.TemplateResponse(request=request, name=f"{page_name}.html", context={})
    
    if page_name == "robots.txt":
        return PlainTextResponse("User-agent: *\nAllow: /\nSitemap: https://companydb.net/sitemap.xml")
    
    if page_name == "sitemap.xml":
        return FileResponse(SITEMAP_PATH, media_type="application/xml") if os.path.exists(SITEMAP_PATH) else HTTPException(404)
        
    if page_name == "ads.txt":
        ads_path = os.path.join(STATIC_DIR, "ads.txt")
        return FileResponse(ads_path, media_type="text/plain") if os.path.exists(ads_path) else HTTPException(404)
        
    raise HTTPException(status_code=404, detail="Page not found")