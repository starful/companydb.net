import os
import json
import markdown
import frontmatter
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, PlainTextResponse

app = FastAPI()

# 프로젝트 루트(/code) 경로 확보
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 정적 파일 마운트
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "app", "static")), name="static")

# 템플릿 설정
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "app", "templates"))

INDEX_PATH = os.path.join(BASE_DIR, "data", "search_index.json")

@app.get("/")
async def home(request: Request):
    latest_companies = []
    total_count = 0
    last_updated = datetime.now().strftime("%Y-%m-%d") # 기본값

    if os.path.exists(INDEX_PATH):
        try:
            mtime = os.path.getmtime(INDEX_PATH)
            last_updated = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
            with open(INDEX_PATH, 'r', encoding='utf-8') as f:
                index_data = json.load(f)
                if index_data:
                    total_count = len(index_data)
                    latest_companies = index_data[-8:][::-1]
        except (json.JSONDecodeError, ValueError):
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
    if q and os.path.exists(INDEX_PATH):
        try:
            with open(INDEX_PATH, 'r', encoding='utf-8') as f:
                index_data = json.load(f)
                results = [c for c in index_data if q.lower() in c['n'].lower() or q.lower() in c.get('en','').lower()]
        except:
            pass
    return templates.TemplateResponse("index.html", {"request": request, "results": results, "query": q})

@app.get("/company/{file_id}")
async def detail(request: Request, file_id: str):
    md_path = os.path.join(BASE_DIR, "app", "content", f"{file_id}.md")
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

HUB_DATA = {
    "locations": { "tokyo": {"name": "Tokyo", "term": "東京"}, "kanagawa": {"name": "Kanagawa", "term": "神奈川"}, "osaka": {"name": "Osaka", "term": "大阪"}, "aichi": {"name": "Aichi", "term": "愛知"}},
    "categories": { "manufacturing": {"name": "Manufacturing", "term": "manufacturing"}, "technology": {"name": "Technology", "term": "technology"}, "electronics": {"name": "Electronics", "term": "electronics"}, "medical": {"name": "Medical", "term": "medical"}}
}

def get_index_data():
    if not os.path.exists(INDEX_PATH): return []
    try:
        with open(INDEX_PATH, 'r', encoding='utf-8') as f: return json.load(f)
    except: return []

@app.get("/location/{location_slug}")
async def location_hub(request: Request, location_slug: str):
    location_info = HUB_DATA["locations"].get(location_slug)
    if not location_info: raise HTTPException(status_code=404, detail="Location not found")
    results = [c for c in get_index_data() if location_info["term"] in c.get('l', '')]
    title = f"Companies in {location_info['name']}"
    return templates.TemplateResponse("hub.html", {"request": request, "title": title, "results": results})

@app.get("/category/{category_slug}")
async def category_hub(request: Request, category_slug: str):
    category_info = HUB_DATA["categories"].get(category_slug)
    if not category_info: raise HTTPException(status_code=404, detail="Category not found")
    search_term = category_info["term"].lower()
    results = [c for c in get_index_data() if search_term in c.get('n', '').lower() or search_term in c.get('en', '').lower()]
    title = f"{category_info['name']} Companies"
    return templates.TemplateResponse("hub.html", {"request": request, "title": title, "results": results})

@app.get("/privacy")
async def privacy_policy(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request})

# ▼▼▼ [추가됨] About Us 페이지를 위한 라우트 ▼▼▼
@app.get("/about")
async def about_us(request: Request):
    return templates.TemplateResponse("about.html", {"request": request})
# ▲▲▲ [추가됨] 끝 ▲▲▲

@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots():
    return "User-agent: *\nAllow: /\nSitemap: https://companydb.net/sitemap.xml"

@app.get("/sitemap.xml", response_class=FileResponse)
async def sitemap():
    sitemap_path = os.path.join(BASE_DIR, "app", "static", "sitemap.xml")
    if os.path.exists(sitemap_path):
        return FileResponse(sitemap_path, media_type="application/xml")
    raise HTTPException(status_code=404, detail="Sitemap not found")