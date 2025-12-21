import os
import json
import markdown
import frontmatter
from fastapi import FastAPI, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# 프로젝트 루트(/code) 경로 확보
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 정적 파일 마운트 (이 경로가 정확해야 스타일이 먹힙니다)
# /code/app/static 폴더를 /static 주소로 연결
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "app", "static")), name="static")

# 템플릿 설정
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "app", "templates"))

INDEX_PATH = os.path.join(BASE_DIR, "data", "search_index.json")

@app.get("/")
async def home(request: Request):
    latest_companies = []
    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, 'r', encoding='utf-8') as f:
            index_data = json.load(f)
            latest_companies = index_data[-4:][::-1]
    return templates.TemplateResponse("index.html", {"request": request, "latest": latest_companies})

@app.get("/search")
async def search(request: Request, q: str = ""):
    results = []
    if q and os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, 'r', encoding='utf-8') as f:
            index_data = json.load(f)
            results = [c for c in index_data if q.lower() in c['n'].lower() or q.lower() in c.get('en','').lower()]
    return templates.TemplateResponse("index.html", {"request": request, "results": results, "query": q})

@app.get("/company/{file_id}")
async def detail(request: Request, file_id: str):
    md_path = os.path.join(BASE_DIR, "app", "content", f"{file_id}.md")
    if not os.path.exists(md_path):
        raise HTTPException(status_code=404)
    with open(md_path, 'r', encoding='utf-8') as f:
        post = frontmatter.load(f)
        content_html = markdown.markdown(post.content)
    return templates.TemplateResponse("detail.html", {"request": request, "company": post.metadata, "content": content_html})