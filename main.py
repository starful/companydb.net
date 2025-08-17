from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from weasyprint import HTML
import tempfile
import mysql.connector
import os
import math
import json
import logging
import textwrap
import re
import hashlib
import datetime as dt
from typing import Optional

import vertexai
from vertexai.generative_models import GenerativeModel  # SafetySetting 제거
from google.cloud import storage
from fastapi import APIRouter

# ---------------------------
# 초기 설정
# ---------------------------
logging.basicConfig(level=logging.INFO)
app = FastAPI()

templates = Jinja2Templates(directory="templates")
templates.env.globals.update(zip=zip)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ---------------------------
# Vertex AI / GCS 초기화 (환경변수 기반, 단 1회)
# ---------------------------
PROJECT_ID = os.getenv("PROJECT_ID", "starful-258005")
REGION = os.getenv("REGION", "us-central1")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
REPORT_BUCKET = os.getenv("REPORT_BUCKET", "companydb-ai-reports")

vertexai.init(project=PROJECT_ID, location=REGION)
_gemini = GenerativeModel(GEMINI_MODEL)
_gcs_client = storage.Client()

def get_connection():
    return mysql.connector.connect(
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        unix_socket=f"/cloudsql/{os.getenv('INSTANCE_CONNECTION_NAME')}"
    )

# ---------------------------
# 공용(GCS) 유틸
# ---------------------------
def _prompt_hash(company_id: str, report_type: str, prompt: str) -> str:
    return hashlib.sha256(f"{str(company_id)}:{report_type}:{prompt}".encode()).hexdigest()

def _gcs_key(company_id: str, report_type: str, p_hash: str) -> str:
    return f"company/{str(company_id)}/reports/{report_type}/{p_hash}.json"

def _gcs_latest_key(company_id: str, report_type: str) -> str:
    return f"company/{str(company_id)}/reports/{report_type}/latest.txt"

def _download_json(bucket_name: str, key: str) -> Optional[dict]:
    bkt = _gcs_client.bucket(bucket_name)
    blob = bkt.blob(key)
    if not blob.exists():
        return None
    return json.loads(blob.download_as_text())

def _upload_json(bucket_name: str, key: str, payload: dict, meta: dict):
    bkt = _gcs_client.bucket(bucket_name)
    blob = bkt.blob(key)
    blob.metadata = meta or {}
    blob.upload_from_string(json.dumps(payload, ensure_ascii=False), content_type="application/json")

def _upload_text(bucket_name: str, key: str, text: str):
    bkt = _gcs_client.bucket(bucket_name)
    blob = bkt.blob(key)
    blob.upload_from_string(text, content_type="text/plain")

# ---------------------------
# JSON 유틸: 펜스 제거 + 관대한 파싱
# ---------------------------
def _strip_code_fences(s: str) -> str:
    if not isinstance(s, str):
        return s
    s = s.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*```$", "", s)
    return s.strip()

def _parse_json_relaxed(raw: str):
    if raw is None:
        return None
    text = _strip_code_fences(raw)
    if "{" in text and "}" in text:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end+1]
    try:
        return json.loads(text)
    except Exception:
        return None

# ---------------------------
# Gemini 생성 유틸 (JSON 우선 + 폴백 + 재시도)
# ---------------------------
def _has_text(resp) -> bool:
    try:
        return bool(getattr(resp, "text", None)) and bool(resp.text.strip())
    except Exception:
        return False

def _gen_json_with_retries(prompt: str, max_retries: int = 2):
    """
    1) JSON 응답 시도 (response_mime_type=application/json)
    2) 텍스트 응답 시도 (response_mime_type=text/plain)
    3) 모두 실패 시 최소 스텁 반환
    """
    last_raw = ""
    # 단계 1: JSON 모드
    for attempt in range(max_retries):
        try:
            resp = _gemini.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.2,
                    "max_output_tokens": 4096,
                    "response_mime_type": "application/json",
                },
            )
            if not _has_text(resp):
                continue
            last_raw = (resp.text or "").strip()
            parsed = _parse_json_relaxed(last_raw)
            if parsed is not None:
                return {"ok": True, "parsed": parsed, "raw": last_raw, "blocked": False}
        except Exception as e:
            logging.warning("JSON mode attempt %d failed: %s", attempt + 1, e)

    # 단계 2: 텍스트 모드
    for attempt in range(max_retries):
        try:
            resp = _gemini.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.1,
                    "max_output_tokens": 4096,
                    "response_mime_type": "text/plain",
                },
            )
            if not _has_text(resp):
                continue
            last_raw = (resp.text or "").strip()
            parsed = _parse_json_relaxed(last_raw)
            if parsed is not None:
                return {"ok": True, "parsed": parsed, "raw": last_raw, "blocked": False}
            return {"ok": True, "parsed": None, "raw": last_raw, "blocked": False}
        except Exception as e:
            logging.warning("TEXT mode attempt %d failed: %s", attempt + 1, e)

    # 단계 3: 완전 실패
    return {
        "ok": False,
        "parsed": None,
        "raw": last_raw,
        "blocked": True,
        "fallback": {"error": "Model response blocked or empty", "raw_text": last_raw},
    }

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
        return templates.TemplateResponse("detail.html", {"request": request, "row": None})

    column_names = ["シーケンス番号", "法人番号", "処理区分", "訂正区分", "更新日", "変更日", "商号", "商号画像ID",
                    "法人種別", "都道府県", "市区町村", "丁目番地", "住所画像ID", "都道府県コード", "市区町村コード", "郵便番号",
                    "国外所在地", "国外所在地画像ID", "閉鎖日", "閉鎖事由", "承継法人番号", "変更事由", "登記記録の閉鎖等年月日",
                    "最新フラグ", "英語名称", "英語都道府県", "英語市区町村", "英語丁目番地", "英語国外所在地", "フリガナ", "非表示フラグ",
                    "予備項目1", "予備項目2", "予備項目3", "予備項目4", "予備項目5"]

    prompt = get_summary_prompt(row[6])

    # Gemini 호출 (재시도 + 폴백)
    result = _gen_json_with_retries(prompt, max_retries=2)
    if result["ok"]:
        if result["parsed"] is not None:
            summary_json = result["parsed"]
        else:
            summary_json = {"raw_text": result["raw"]}
    else:
        logging.error("Gemini生成に失敗しました: blocked or empty response")
        summary_json = result["fallback"]

    # --- 상세 페이지에서 보인 결과를 GCS에 즉시 보존 ---
    try:
        report_type = "detail"
        p_hash = _prompt_hash(corp_number, report_type, prompt)
        key = _gcs_key(corp_number, report_type, p_hash)
        if _download_json(REPORT_BUCKET, key) is None:
            now_iso = dt.datetime.utcnow().isoformat() + "Z"
            content_to_save = summary_json
            payload = {
                "company_id": corp_number,
                "report_type": report_type,
                "prompt_hash": p_hash,
                "model": GEMINI_MODEL,
                "created_at": now_iso,
                "content": content_to_save,
            }
            meta = {"company_id": str(corp_number), "report_type": report_type, "created_at": now_iso}
            _upload_json(REPORT_BUCKET, key, payload, meta)
            _upload_text(REPORT_BUCKET, _gcs_latest_key(corp_number, report_type), p_hash)
    except Exception as e:
        logging.warning("GCS保存に失敗しました: %s", e)
    # --- GCS 보존 끝 ---

    return templates.TemplateResponse("detail.html", {
        "request": request,
        "row": row,
        "columns": column_names,
        "ai_summary": summary_json
    })


@app.get("/api/company_summary")
async def company_summary(corp: str):
    prompt = get_summary_prompt(corp)

    result = _gen_json_with_retries(prompt, max_retries=2)
    if result["ok"]:
        content_to_return = result["parsed"] if result["parsed"] is not None else {"raw_text": result["raw"]}
    else:
        logging.exception("Gemini例外発生: blocked or empty")
        content_to_return = result["fallback"]

    # GCS 보존 (report_type="api")
    try:
        report_type = "api"
        p_hash = _prompt_hash(corp, report_type, prompt)
        key = _gcs_key(corp, report_type, p_hash)
        if _download_json(REPORT_BUCKET, key) is None:
            now_iso = dt.datetime.utcnow().isoformat() + "Z"
            payload = {
                "company_id": corp,
                "report_type": report_type,
                "prompt_hash": p_hash,
                "model": GEMINI_MODEL,
                "created_at": now_iso,
                "content": content_to_return,
            }
            meta = {"company_id": str(corp), "report_type": report_type, "created_at": now_iso}
            _upload_json(REPORT_BUCKET, key, payload, meta)
            _upload_text(REPORT_BUCKET, _gcs_latest_key(corp, report_type), p_hash)
    except Exception as e:
        logging.warning("GCS保存(api)に失敗: %s", e)

    return JSONResponse(content=content_to_return)

def get_summary_prompt(company_name: str) -> str:
    return f"""
        次の企業に関する情報を要約してください。

        会社名: {company_name}

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
        - すべてのキーと文字列はダブルクォーテーション(")で囲んでください
        - マークダウン（例：```json）は含めないでください
        - 構文エラーのない、完全なJSON形式のみを出力してください
    """

@app.post("/corp/{corp_number}/pdf")
async def generate_pdf(request: Request, corp_number: str):
    form = await request.form()
    summary_json = json.loads(form.get("summary_json", "{}"))
    row_data = json.loads(form.get("row", "{}"))

    html_content = templates.get_template("detail.html").render(
        request=request,
        row=row_data,
        columns=[],
        ai_summary=summary_json
    )

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        HTML(string=html_content).write_pdf(tmp_file.name)
        return FileResponse(
            tmp_file.name,
            filename=f"{row_data[6]}_会社情報.pdf",
            media_type="application/pdf"
        )

# ====== GCS 단독 AI 레포트 기능 (생성/목록/단건/최신) ======
router = APIRouter()

@router.post("/companies/{company_id}/ai-report/generate")
async def generate_ai_report(company_id: int, request: Request, report_type: str = Query("default"), force: bool = Query(False)):
    form = await request.form()
    user_prompt = form.get("prompt") or f"会社ID {company_id} の事業概要・強み・リスクを投資家向けに要約してください。"

    p_hash = _prompt_hash(str(company_id), report_type, user_prompt)
    key = _gcs_key(str(company_id), report_type, p_hash)
    blob = _gcs_client.bucket(REPORT_BUCKET).blob(key)

    if not force and blob.exists():
        data = json.loads(blob.download_as_text())
        preview_src = data.get("content")
        if isinstance(preview_src, (dict, list)):
            preview_src = json.dumps(preview_src, ensure_ascii=False)
        return JSONResponse({"reused": True, "key": key, "preview": (preview_src or "")[:200], "hash": p_hash})

    gen = _gen_json_with_retries(user_prompt, max_retries=2)
    content_to_save = (gen["parsed"] if gen["ok"] and gen["parsed"] is not None
                       else (gen["raw"] if gen["ok"] else gen["fallback"]))
    if isinstance(content_to_save, str):
        content_to_save = {"raw_text": content_to_save}

    now_iso = dt.datetime.utcnow().isoformat() + "Z"
    payload = {
        "company_id": str(company_id),
        "report_type": report_type,
        "prompt_hash": p_hash,
        "model": GEMINI_MODEL,
        "created_at": now_iso,
        "content": content_to_save,
    }
    meta = {"company_id": str(company_id), "report_type": report_type, "created_at": now_iso}
    _upload_json(REPORT_BUCKET, key, payload, meta)
    _upload_text(REPORT_BUCKET, _gcs_latest_key(str(company_id), report_type), p_hash)

    preview_src = json.dumps(content_to_save, ensure_ascii=False)
    return JSONResponse({"reused": False, "key": key, "preview": preview_src[:200], "hash": p_hash})


@router.get("/companies/{company_id}/ai-report/generate")
async def generate_ai_report_get(company_id: int, report_type: str = Query("default"), force: bool = Query(False), prompt: str = ""):
    user_prompt = prompt or f"会社ID {company_id} の事業概要・強み・リスクを投資家向けに要約してください。"

    p_hash = _prompt_hash(str(company_id), report_type, user_prompt)
    key = _gcs_key(str(company_id), report_type, p_hash)
    blob = _gcs_client.bucket(REPORT_BUCKET).blob(key)

    if not force and blob.exists():
        data = json.loads(blob.download_as_text())
        preview_src = data.get("content")
        if isinstance(preview_src, (dict, list)):
            preview_src = json.dumps(preview_src, ensure_ascii=False)
        return JSONResponse({"reused": True, "key": key, "preview": (preview_src or "")[:200], "hash": p_hash})

    gen = _gen_json_with_retries(user_prompt, max_retries=2)
    content_to_save = (gen["parsed"] if gen["ok"] and gen["parsed"] is not None
                       else (gen["raw"] if gen["ok"] else gen["fallback"]))
    if isinstance(content_to_save, str):
        content_to_save = {"raw_text": content_to_save}

    now_iso = dt.datetime.utcnow().isoformat() + "Z"
    payload = {
        "company_id": str(company_id),
        "report_type": report_type,
        "prompt_hash": p_hash,
        "model": GEMINI_MODEL,
        "created_at": now_iso,
        "content": content_to_save,
    }
    meta = {"company_id": str(company_id), "report_type": report_type, "created_at": now_iso}
    _upload_json(REPORT_BUCKET, key, payload, meta)
    _upload_text(REPORT_BUCKET, _gcs_latest_key(str(company_id), report_type), p_hash)

    preview_src = json.dumps(content_to_save, ensure_ascii=False)
    return JSONResponse({"reused": False, "key": key, "preview": preview_src[:200], "hash": p_hash})


@router.get("/companies/{company_id}/ai-report")
async def list_ai_reports(company_id: int, report_type: str = Query("default"), limit: int = Query(20, ge=1, le=200), page_token: Optional[str] = None):
    prefix = f"company/{str(company_id)}/reports/{report_type}/"
    it = _gcs_client.list_blobs(REPORT_BUCKET, prefix=prefix, page_token=page_token, max_results=limit)
    items = []
    next_token = it.next_page_token

    for blob in it:
        if blob.name.endswith("latest.txt"):
            continue
        items.append({
            "key": blob.name,
            "updated": blob.updated.isoformat() if blob.updated else None,
            "meta": blob.metadata or {},
        })

    items.sort(key=lambda x: x["meta"].get("created_at", x["updated"] or ""), reverse=True)

    return JSONResponse({"items": items, "next_page_token": next_token})

@router.get("/api/ai-reports/{company_id}/{report_type}/{p_hash}")
async def get_ai_report(company_id: int, report_type: str, p_hash: str):
    key = _gcs_key(str(company_id), report_type, p_hash)
    data = _download_json(REPORT_BUCKET, key)
    if not data:
        raise HTTPException(status_code=404, detail="not found")
    return JSONResponse(data)

@router.get("/companies/{company_id}/ai-report/latest")
async def get_latest_ai_report(company_id: int, report_type: str = Query("default")):
    latest_key = _gcs_latest_key(str(company_id), report_type)
    blob = _gcs_client.bucket(REPORT_BUCKET).blob(latest_key)
    if not blob.exists():
        return JSONResponse({"message": "no latest"}, status_code=404)
    p_hash = blob.download_as_text().strip()
    data = _download_json(REPORT_BUCKET, _gcs_key(str(company_id), report_type, p_hash))
    if not data:
        return JSONResponse({"message": "stale pointer"}, status_code=404)
    return JSONResponse(data)

# 라우터 등록
app.include_router(router)
# ====== /GCS 단독 AI 레포트 기능 끝 ======
