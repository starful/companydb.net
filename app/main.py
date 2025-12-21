import os
import json
import markdown
import frontmatter
from fastapi import FastAPI, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, PlainTextResponse  # <--- [중요] 이 줄이 추가되었습니다!

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
    if os.path.exists(INDEX_PATH):
        try:
            with open(INDEX_PATH, 'r', encoding='utf-8') as f:
                index_data = json.load(f)
                if index_data:
                    # 최신순 정렬 (데이터가 쌓이면 뒤에서부터)
                    latest_companies = index_data[-4:][::-1]
        except (json.JSONDecodeError, ValueError):
            pass
    return templates.TemplateResponse("index.html", {"request": request, "latest": latest_companies})

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
    # 경로 생성
    md_path = os.path.join(BASE_DIR, "app", "content", f"{file_id}.md")
    
    # [디버깅] 파일이 없으면 서버 내부 상황을 출력
    if not os.path.exists(md_path):
        content_dir = os.path.dirname(md_path)
        print(f"❌ [ERROR] File not found: {md_path}")
        print(f"📂 [DEBUG] Looking in folder: {content_dir}")
        
        if os.path.exists(content_dir):
            files = os.listdir(content_dir)
            print(f"📄 [DEBUG] Files currently in folder ({len(files)} total):")
            print(files[:10]) # 처음 10개만 출력
        else:
            print("😱 [DEBUG] Content folder does not exist!")

        raise HTTPException(status_code=404, detail="Company report not found")
        
    with open(md_path, 'r', encoding='utf-8') as f:
        post = frontmatter.load(f)
        content_html = markdown.markdown(post.content)
        
    return templates.TemplateResponse("detail.html", {
        "request": request, 
        "company": post.metadata, 
        "content": content_html
    })

# --- SEO 관련 라우트 추가 ---
@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots():
    content = """User-agent: *
Allow: /
Sitemap: https://companydb.net/sitemap.xml
"""
    return content

@app.get("/sitemap.xml", response_class=FileResponse)
async def sitemap():
    sitemap_path = os.path.join(BASE_DIR, "app", "static", "sitemap.xml")
    if os.path.exists(sitemap_path):
        return FileResponse(sitemap_path, media_type="application/xml")
    else:
        raise HTTPException(status_code=404, detail="Sitemap not found")