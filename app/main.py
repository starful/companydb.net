import os
import json
import markdown
import frontmatter
from datetime import datetime
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

# 헬퍼 함수
def get_index_data():
    if not os.path.exists(INDEX_PATH):
        return []
    try:
        with open(INDEX_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

@app.get("/")
async def home(request: Request):
    latest_companies = []
    total_count = 0
    last_updated = datetime.now().strftime("%Y-%m-%d")

    if os.path.exists(INDEX_PATH):
        try:
            mtime = os.path.getmtime(INDEX_PATH)
            last_updated = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
            index_data = get_index_data()
            if index_data:
                total_count = len(index_data)
                latest_companies = index_data[-8:][::-1]
        except ValueError:
            pass

    return templates.TemplateResponse("index.html", {
        "request": request, 
        "latest": latest_companies,
        "total_count": "{:,}".format(total_count),
        "last_updated": last_updated
    })

@app.get("/search")
async def search(request: Request, q: str = ""):
    results = []
    if q:
        index_data = get_index_data()
        q_lower = q.lower()
        results = [c for c in index_data if q_lower in c['n'].lower() or q_lower in c.get('en','').lower()]
    
    return templates.TemplateResponse("index.html", {"request": request, "results": results, "query": q})

@app.get("/company/{file_id}")
async def detail(request: Request, file_id: str):
    md_path = os.path.join(CONTENT_DIR, f"{file_id}.md")
    if not os.path.exists(md_path):
        raise HTTPException(status_code=404, detail="Company report not found")
        
    with open(md_path, 'r', encoding='utf-8') as f:
        post = frontmatter.load(f)
        content_html = markdown.markdown(post.content)
        
    return templates.TemplateResponse("detail.html", {
        "request": request, 
        "company": post.metadata, 
        "content": content_html
    })

@app.get("/location/{location_slug}")
async def location_hub(request: Request, location_slug: str):
    location_info = HUB_DATA["locations"].get(location_slug)
    if not location_info:
        raise HTTPException(status_code=404, detail="Location not found")

    index_data = get_index_data()
    results = [c for c in index_data if location_info["term"] in c.get('l', '')]
    
    return templates.TemplateResponse("hub.html", {
        "request": request,
        "title": f"Companies in {location_info['name']}",
        "results": results
    })

@app.get("/category/{category_slug}")
async def category_hub(request: Request, category_slug: str):
    category_info = HUB_DATA["categories"].get(category_slug.lower())
    if not category_info:
        raise HTTPException(status_code=404, detail="Category not found")
        
    index_data = get_index_data()
    category_name = category_info["name"]
    results = [c for c in index_data if c.get('c', '').lower() == category_name.lower()]

    return templates.TemplateResponse("hub.html", {
        "request": request,
        "title": f"{category_name} Companies",
        "results": results
    })

# 정적 페이지 라우트 통합
@app.get("/{page_name}")
async def static_page(request: Request, page_name: str):
    if page_name in ["privacy", "about"]:
        return templates.TemplateResponse(f"{page_name}.html", {"request": request})
    
    # robots.txt, sitemap.xml, ads.txt 처리
    if page_name == "robots.txt":
        return PlainTextResponse("User-agent: *\nAllow: /\nSitemap: https://companydb.net/sitemap.xml")
    
    if page_name == "sitemap.xml":
        if os.path.exists(SITEMAP_PATH):
            return FileResponse(SITEMAP_PATH, media_type="application/xml")
        raise HTTPException(status_code=404, detail="Sitemap not found")

    # ▼▼▼ [수정된 부분] ads.txt 파일을 static 폴더에서 서빙하는 로직 추가 ▼▼▼
    if page_name == "ads.txt":
        ads_path = os.path.join(STATIC_DIR, "ads.txt")
        if os.path.exists(ads_path):
            return FileResponse(ads_path, media_type="text/plain")
        raise HTTPException(status_code=404, detail="ads.txt not found")
    # ▲▲▲ [여기까지 수정됨] ▲▲▲
        
    raise HTTPException(status_code=404, detail="Page not found")