from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import mysql.connector
import os
import math
import json
import logging
import textwrap
import re

import vertexai
from vertexai.generative_models import GenerativeModel

# ---------------------------
# 초기 설정
# ---------------------------
logging.basicConfig(level=logging.INFO)
app = FastAPI()

templates = Jinja2Templates(directory="templates")
templates.env.globals.update(zip=zip)
app.mount("/static", StaticFiles(directory="static"), name="static")

vertexai.init(project="starful-258005", location="us-central1")

def get_connection():
    return mysql.connector.connect(
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        unix_socket=f"/cloudsql/{os.getenv('INSTANCE_CONNECTION_NAME')}"
    )

# ---------------------------
# 라우팅
# ---------------------------
@app.get("/", response_class=HTMLResponse)
async def redirect_to_search():
    return RedirectResponse(url="/search")

@app.get("/search", response_class=HTMLResponse)
async def search_page(request: Request):
    return templates.TemplateResponse("search.html", {"request": request})

@app.get("/list", response_class=HTMLResponse)
async def list_corporations(request: Request, page: int = 1, keyword: str = ""):
    page_size = 20
    offset = (page - 1) * page_size
    conn = get_connection()
    cursor = conn.cursor()

    like_query = f"%{keyword}%"
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
    cursor.execute("SELECT * FROM houjin_corporations WHERE corp_number = %s", (corp_number,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    if not row:
        return templates.TemplateResponse("detail.html", {
            "request": request,
            "row": None
        })

    column_names = [
        "シーケンス番号", "法人番号", "処理区分", "訂正区分", "更新日", "変更日", "商号", "商号画像ID",
        "法人種別", "都道府県", "市区町村", "丁目番地", "住所画像ID", "都道府県コード", "市区町村コード", "郵便番号",
        "国外所在地", "国外所在地画像ID", "閉鎖日", "閉鎖事由", "承継法人番号", "変更事由", "登記記録の閉鎖等年月日",
        "最新フラグ", "英語名称", "英語都道府県", "英語市区町村", "英語丁目番地", "英語国外所在地", "フリガナ", "非表示フラグ",
        "予備項目1", "予備項目2", "予備項目3", "予備項目4", "予備項目5"
    ]

    model = GenerativeModel(model_name="gemini-2.5-flash")

    prompt = f"""
        次の企業に関する情報を要約してください。

        会社名: {row[6]}

        1. 企業概要（300字以内）
        2. 財務サマリ（300字以内）
        3. 成長性・競争力（300字以内）
        4. 投資関連情報（300字以内）
        5. SWOT分析（強み・弱み・機会・脅威をそれぞれ300字以内）
        6. 財務データ（売上・営業利益・負債比率を含む、2021～2023年の年度別。数値はJSONにまとめて "financials" に格納）
        7. 以下の項目もJSONに含めてください：
           - 売上高（2023年の全体像を簡潔に）
           - 営業利益（2023年の全体像を簡潔に）
           - 負債比率（%）
           - 主要取引先（可能であれば企業名や業種を記述）
           - 従業員数（数値で）
           - 事業内容（箇条書きでも構いません）
           - 特許認証（あれば技術・品質に関する特許や取得済みの認証など）
           - 公式サイト（存在する場合のみURL形式で）

        出力形式は以下のような正確なJSONにしてください：

        {{
          "企業概要": "...",
          "財務サマリ": "...",
          "成長性・競争力": "...",
          "投資関連情報": "...",
          "SWOT分析": {{
            "Strength": "...",
            "Weakness": "...",
            "Opportunity": "...",
            "Threat": "..."
          }},
          "financials": {{
            "2021": {{"revenue": 数値, "operating_income": 数値, "debt_ratio": 数値}},
            "2022": {{"revenue": 数値, "operating_income": 数値, "debt_ratio": 数値}},
            "2023": {{"revenue": 数値, "operating_income": 数値, "debt_ratio": 数値}}
          }},
          "売上高": "...",
          "営業利益": "...",
          "負債比率": "...",
          "主要取引先": "...",
          "従業員数": 数値,
          "事業内容": "...",
          "特許認証": "...",
          "公式サイト": "https://..."
        }}

        注意事項：
        - すべての **キーと文字列はダブルクォーテーション(")** で囲んでください
        - **マークダウン（例：```json）** は含めないでください
        - **構文エラーのない、完全なJSON形式のみ**を出力してください
    """

    try:
        response = model.generate_content(prompt)
        logging.info("Gemini response: %s", response.text)
        raw_text = response.text.strip()
        clean_text = re.sub(r"^```json\n?|```$", "", raw_text.strip(), flags=re.MULTILINE)
        summary_json = json.loads(clean_text)
    except Exception as e:
        logging.error("Gemini生成に失敗しました: %s", str(e))
        summary_json = {"企業概要": "Gemini生成に失敗しました"}

    return templates.TemplateResponse("detail.html", {
        "request": request,
        "row": row,
        "columns": column_names,
        "ai_summary": summary_json
    })

@app.get("/api/company_summary")
async def company_summary(corp: str):
    prompt = f"""
        次の企業に関する情報を要約してください。

        会社名: {row[6]}

        1. 企業概要（300字以内）
        2. 財務サマリ（300字以内）
        3. 成長性・競争力（300字以内）
        4. 投資関連情報（300字以内）
        5. SWOT分析（強み・弱み・機会・脅威をそれぞれ300字以内）
        6. 財務データ（売上・営業利益・負債比率を含む、2021～2023年の年度別。数値はJSONにまとめて "financials" に格納）
        7. 以下の項目もJSONに含めてください：
           - 売上高（2023年の全体像を簡潔に）
           - 営業利益（2023年の全体像を簡潔に）
           - 負債比率（%）
           - 主要取引先（可能であれば企業名や業種を記述）
           - 従業員数（数値で）
           - 事業内容（箇条書きでも構いません）
           - 特許認証（あれば技術・品質に関する特許や取得済みの認証など）
           - 公式サイト（存在する場合のみURL形式で）

        出力形式は以下のような正確なJSONにしてください：

        {{
          "企業概要": "...",
          "財務サマリ": "...",
          "成長性・競争力": "...",
          "投資関連情報": "...",
          "SWOT分析": {{
            "Strength": "...",
            "Weakness": "...",
            "Opportunity": "...",
            "Threat": "..."
          }},
          "financials": {{
            "2021": {{"revenue": 数値, "operating_income": 数値, "debt_ratio": 数値}},
            "2022": {{"revenue": 数値, "operating_income": 数値, "debt_ratio": 数値}},
            "2023": {{"revenue": 数値, "operating_income": 数値, "debt_ratio": 数値}}
          }},
          "売上高": "...",
          "営業利益": "...",
          "負債比率": "...",
          "主要取引先": "...",
          "従業員数": 数値,
          "事業内容": "...",
          "特許認証": "...",
          "公式サイト": "https://..."
        }}

        注意事項：
        - すべての **キーと文字列はダブルクォーテーション(")** で囲んでください
        - **マークダウン（例：```json）** は含めないでください
        - **構文エラーのない、完全なJSON形式のみ**を出力してください
    """

    try:
        model = GenerativeModel("gemini-2.5-flash")
        chat = model.start_chat()
        result = chat.send_message(
            prompt,
            generation_config={
                "temperature": 0.2,
                "max_output_tokens": 4096
            }
        )

        if not result.text:
            return JSONResponse(content={"error": "Geminiからの応答がありません"}, status_code=500)

        raw_text = result.text.strip()
        raw_text = re.sub(r"^```(json)?", "", raw_text, flags=re.IGNORECASE).strip()
        raw_text = re.sub(r"```$", "", raw_text).strip()

        try:
            return JSONResponse(content=json.loads(raw_text))
        except json.JSONDecodeError:
            left, right = raw_text.count("{"), raw_text.count("}")
            if left > right:
                fixed_text = raw_text + "}" * (left - right)
                try:
                    return JSONResponse(content=json.loads(fixed_text))
                except Exception:
                    pass

            return JSONResponse(content={
                "error": "Geminiの応答をJSONとして解析できません",
                "raw": raw_text
            }, status_code=500)

    except Exception as e:
        logging.exception("Gemini例外発生:")
        return JSONResponse(content={"error": str(e)}, status_code=500)
