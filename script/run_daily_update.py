import pandas as pd
import os
import frontmatter
import google.generativeai as genai
from dotenv import load_dotenv
import time
import re
import json
from datetime import datetime

# --- 설정: 상수 모음 ---
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

MODEL = genai.GenerativeModel('gemini-1.5-flash')
DAILY_LIMIT = 10

# ▼▼▼ [수정됨] 일관된 카테고리 목록 정의 ▼▼▼
CATEGORIES = ["Manufacturing", "Technology", "Electronics", "Medical", "Construction", "Services"]

CSV_PATH = 'data/Total_Premium_Japan_SMEs.csv'
CONTENT_DIR = 'app/content'
DATA_DIR = 'data'
INDEX_PATH = os.path.join(DATA_DIR, 'search_index.json')
SITEMAP_PATH = 'app/static/sitemap.xml'
DOMAIN = "https://companydb.net"

def slugify(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')

def generate_new_content():
    if not os.path.exists(CSV_PATH):
        print(f"❌ 원본 데이터 파일이 없습니다: {CSV_PATH}")
        return

    df = pd.read_csv(CSV_PATH)
    os.makedirs(CONTENT_DIR, exist_ok=True)
    
    count = 0
    print(f"🚀 총 {len(df)}개 기업 중 최대 {DAILY_LIMIT}개의 신규 리포트 생성을 시작합니다.")

    for _, row in df.iterrows():
        if count >= DAILY_LIMIT:
            print(f" 일일 생성 제한({DAILY_LIMIT}개)에 도달했습니다.")
            break
        
        cid = f"jp_{row['corporate_number']}"
        if any(f.startswith(cid) for f in os.listdir(CONTENT_DIR)):
            continue

        print(f"   [ {count+1} / {DAILY_LIMIT} ] '{row['name']}' 리포트 생성 중...")
        
        # ▼▼▼ [수정됨] 카테고리 분류를 요청하는 프롬프트 강화 ▼▼▼
        prompt = f"""
        Act as a Senior Business Analyst. Analyze the following company and provide a B2B report.

        - Company: {row['name']}
        - Location: {row['location']}
        - Gov Info: {row['subsidy_titles'] if pd.notna(row['subsidy_titles']) else "Verified SME"}

        [Output Instructions]
        Line 1: A formal English name. If none is found, REPEAT the original Japanese name.
        Line 2: Choose the ONE most appropriate category from this list: {', '.join(CATEGORIES)}. Output in the format "Category: [Chosen Category]".
        Line 3: ---BODY---
        Line 4 and beyond: Full Detailed Markdown Report (Min 4,000 chars).

        [Analyst's Note Instructions]
        - At the VERY BEGINNING of the markdown body, create a short, insightful "Analyst's Note" blockquote.
        - This note should summarize the company's core B2B value proposition.

        [Content Focus & Formatting Rules]
        - Professional B2B perspective. Be verbose.
        - Use standard Markdown: headings (##), lists (*), etc.
        """
        # ▲▲▲ [수정됨] 끝 ▲▲▲
        
        try:
            response = MODEL.generate_content(prompt)
            full_response = response.text.strip()

            header_part, ai_content = full_response.split("---BODY---", 1)
            header_lines = header_part.strip().split('\n')

            ai_en_name = header_lines[0].strip()
            
            # 카테고리 추출 및 기본값 설정
            ai_category = "Services" # 기본값
            if len(header_lines) > 1 and "Category:" in header_lines[1]:
                ai_category = header_lines[1].replace("Category:", "").strip()
                # AI가 목록에 없는 값을 생성할 경우를 대비한 안전장치
                if ai_category not in CATEGORIES:
                    ai_category = "Services"

            if not ai_en_name.isascii():
                ai_en_name = str(row['name'])

            file_slug = slugify(ai_en_name)
            
            if file_slug:
                file_name = f"{cid}_{file_slug}.md"
            else:
                file_name = f"{cid}.md"
            
            file_path = os.path.join(CONTENT_DIR, file_name)

            metadata = {
                "id": cid,
                "title": str(row['name']),
                "title_en": ai_en_name,
                "address": str(row['location']),
                "subsidies": int(row['subsidy_count']),
                "category": ai_category, # AI가 분류한 카테고리 저장
                "contact": f"https://www.google.com/search?q={row['name']}+contact+website"
            }
            
            post = frontmatter.Post(ai_content.strip(), **metadata)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(frontmatter.dumps(post))
            
            print(f"   ✅ 완료: {file_name} (Category: {ai_category})")
            count += 1
            time.sleep(5)
            
        except Exception as e:
            print(f"   ❌ 에러 발생: {e}")
            time.sleep(10)
    
    if count == 0:
        print("생성할 새로운 기업이 없습니다.")

def update_index_and_sitemap():
    if not os.path.exists(CONTENT_DIR):
        print(f"⚠️ 콘텐츠 폴더가 없습니다: {CONTENT_DIR}")
        return
    
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs('app/static', exist_ok=True)

    index_data = []
    sitemap_urls = []
    
    print(f"\n🔍 '{CONTENT_DIR}' 폴더를 스캔하여 인덱싱을 시작합니다...")
    
    for filename in os.listdir(CONTENT_DIR):
        if filename.endswith('.md'):
            try:
                file_path = os.path.join(CONTENT_DIR, filename)
                with open(file_path, 'r', encoding='utf-8') as f:
                    post = frontmatter.load(f)
                    file_slug = filename.replace(".md", "")
                    
                    # ▼▼▼ [수정됨] 검색 인덱스에 카테고리('c') 필드 추가 ▼▼▼
                    index_data.append({
                        "id": post.metadata.get('id', ''),
                        "file": file_slug,
                        "n": post.metadata.get('title', ''),
                        "en": post.metadata.get('title_en', ''),
                        "l": str(post.metadata.get('address', ''))[:30],
                        "s": post.metadata.get('subsidies', 0),
                        "c": post.metadata.get('category', 'Services') # 카테고리 정보 추가
                    })
                    # ▲▲▲ [수정됨] 끝 ▲▲▲

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
                print(f"⚠️ {filename} 처리 중 오류 발생: {e}")
                continue
    
    with open(INDEX_PATH, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)
    print(f"✅ 검색 인덱스 갱신 완료 ({len(index_data)}개 기업)")

    sitemap_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>{DOMAIN}/</loc>
        <changefreq>daily</changefreq>
        <priority>1.0</priority>
    </url>
    {''.join(sitemap_urls)}
</urlset>"""
    with open(SITEMAP_PATH, 'w', encoding='utf-8') as f: f.write(sitemap_content)
    print(f"✅ 사이트맵 생성 완료: {SITEMAP_PATH} ({len(sitemap_urls)}개 링크)")

def main():
    print("="*40)
    print("  CompanyDB 일일 업데이트 프로세스 시작 ")
    print("="*40)
    generate_new_content()
    update_index_and_sitemap()
    print("\n🎉 모든 작업이 성공적으로 완료되었습니다!")
    print("="*40)

if __name__ == "__main__":
    main()