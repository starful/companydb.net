
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import mysql.connector
import os
import math

app = FastAPI()
templates = Jinja2Templates(directory="templates")
templates.env.globals.update(zip=zip)

def get_connection():
    return mysql.connector.connect(
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        unix_socket=f"/cloudsql/{os.getenv('INSTANCE_CONNECTION_NAME')}"
    )

@app.get("/", response_class=HTMLResponse)
async def list_corporations(request: Request, page: int = 1, keyword: str = ""):
    page_size = 20
    offset = (page - 1) * page_size
    conn = get_connection()
    cursor = conn.cursor()

    like_query = "%" + keyword + "%"
    if keyword:
        cursor.execute("SELECT COUNT(*) FROM houjin_corporations WHERE name COLLATE utf8mb4_unicode_ci LIKE %s", (like_query,))
    else:
        cursor.execute("SELECT COUNT(*) FROM houjin_corporations")
    total_count = cursor.fetchone()[0]
    total_pages = max(1, math.ceil(total_count / page_size))

    if keyword:
        cursor.execute("""
            SELECT corp_number, name, pref_name, city_name, street_number, assignment_date
            FROM houjin_corporations
            WHERE name COLLATE utf8mb4_unicode_ci LIKE %s
            ORDER BY assignment_date DESC
            LIMIT %s OFFSET %s
        """, (like_query, page_size, offset))
    else:
        cursor.execute("""
            SELECT corp_number, name, pref_name, city_name, street_number, assignment_date
            FROM houjin_corporations
            ORDER BY assignment_date DESC
            LIMIT %s OFFSET %s
        """, (page_size, offset))

    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    return templates.TemplateResponse("list.html", {
        "request": request,
        "rows": rows,
        "page": page,
        "total_pages": total_pages,
        "keyword": keyword
    })

@app.get("/corp/{corp_number}", response_class=HTMLResponse)
async def corp_detail(request: Request, corp_number: str):
    corp_number = corp_number.zfill(13)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT *
        FROM houjin_corporations
        WHERE corp_number = %s
    """, (corp_number,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    column_names = [
        "シーケンス番号", "法人番号", "処理区分", "訂正区分", "更新日", "変更日", "商号", "商号画像ID",
        "法人種別", "都道府県", "市区町村", "丁目番地", "住所画像ID", "都道府県コード", "市区町村コード", "郵便番号",
        "国外所在地", "国外所在地画像ID", "閉鎖日", "閉鎖事由", "承継法人番号", "変更事由", "登記記録の閉鎖等年月日",
        "最新フラグ", "英語名称", "英語都道府県", "英語市区町村", "英語丁目番地", "英語国外所在地", "フリガナ", "非表示フラグ",
        "予備項目1", "予備項目2", "予備項目3", "予備項目4", "予備項目5"
    ]

    return templates.TemplateResponse("detail.html", {
        "request": request,
        "row": row,
        "columns": column_names
    })
