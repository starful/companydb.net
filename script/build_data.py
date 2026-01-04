import sys
import os

# 현재 스크립트의 상위 폴더(프로젝트 루트)를 sys.path에 추가하여 app 패키지를 찾을 수 있게 함
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import frontmatter
import google.generativeai as genai
from dotenv import load_dotenv
import time
import re
import json
from datetime import datetime
import argparse

# app/config.py 에서 설정 가져오기
from app.config import (
    CSV_PATH, CONTENT_DIR, DATA_DIR, INDEX_PATH, 
    SITEMAP_PATH, DOMAIN, DAILY_LIMIT, CATEGORIES
)

# --- AI 설정 ---
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = genai.GenerativeModel('gemini-1.5-flash')

# --- 헬퍼 함수 ---
def slugify(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')

# --- 핵심 기능 함수들 ---

def generate_new_content():
    """(Daily Task) CSV를 읽어 새로운 .md 리포트를 생성합니다."""
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
        # 이미 파일이 존재하면 건너뜀 (파일명에 cid가 포함된 경우)
        if any(f.startswith(cid) for f in os.listdir(CONTENT_DIR)):
            continue

        print(f"   [ {count+1} / {DAILY_LIMIT} ] '{row['name']}' 리포트 생성 중...")
        
        prompt = f"""
        Act as a Senior Business Analyst. Analyze the following company and provide a B2B report.
        - Company: {row['name']}
        - Location: {row['location']}
        - Gov Info: {row['subsidy_titles'] if pd.notna(row['subsidy_titles']) else "Verified SME"}

        [Output Instructions]
        Line 1: A formal English name. If none is found, REPEAT the original Japanese name.
        Line 2: Choose the ONE most appropriate category from this list: {', '.join(CATEGORIES)}. Output in the format "Category: [Chosen Category]".
        Line 3: ---BODY---
        Line 4 and beyond: Full Detailed Markdown Report.

        [Analyst's Note Instructions]
        - At the VERY BEGINNING of the markdown body, create a short, insightful "Analyst's Note".
        - This note must be formatted as a Markdown blockquote.
        - It should summarize the company's core B2B value proposition in 2-3 sentences.

        [Content Focus & Formatting Rules]
        - Professional B2B perspective. Be verbose.
        - Use standard Markdown: headings (##), lists (*), bolding (**).
        """
        
        try:
            response = MODEL.generate_content(prompt)
            full_response = response.text.strip()

            if "---BODY---" in full_response:
                header_part, ai_content = full_response.split("---BODY---", 1)
            else:
                # 구분자가 없을 경우의 예외 처리
                lines = full_response.split('\n')
                header_part = lines[0]
                ai_content = "\n".join(lines[1:])

            header_lines = header_part.strip().split('\n')
            ai_en_name = header_lines[0].strip()
            
            # 카테고리 추출
            ai_category = "Services" # 기본값
            if len(header_lines) > 1 and "Category:" in header_lines[1]:
                ai_category = header_lines[1].replace("Category:", "").strip()
                if ai_category not in CATEGORIES:
                    ai_category = "Services"

            # 영문명 검증 (영문이 아니면 원본 일본어 이름 사용)
            if not ai_en_name.isascii():
                ai_en_name = str(row['name'])

            file_slug = slugify(ai_en_name)
            file_name = f"{cid}_{file_slug}.md" if file_slug else f"{cid}.md"
            file_path = os.path.join(CONTENT_DIR, file_name)

            metadata = {
                "id": cid,
                "title": str(row['name']),
                "title_en": ai_en_name,
                "address": str(row['location']),
                "subsidies": int(row['subsidy_count']),
                "category": ai_category,
                "contact": f"https://www.google.com/search?q={row['name']}+contact+website"
            }
            
            post = frontmatter.Post(ai_content.strip(), **metadata)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(frontmatter.dumps(post))
            
            print(f"   ✅ 완료: {file_name} (Category: {ai_category})")
            count += 1
            time.sleep(5) # API 속도 제한 고려
            
        except Exception as e:
            print(f"   ❌ 에러 발생: {e}")
            time.sleep(10)
    
    if count == 0:
        print("생성할 새로운 기업이 없습니다.")


def migrate_missing_categories():
    """(Migration Task) 기존 .md 파일에 카테고리 정보가 없으면 추가합니다."""
    print("🚀 기존 마크다운 파일에 대한 카테고리 마이그레이션을 시작합니다...")
    if not os.path.exists(CSV_PATH):
        print(f"❌ 원본 데이터 파일({CSV_PATH})을 찾을 수 없어 중단합니다.")
        return

    # CSV 데이터 로드
    df = pd.read_csv(CSV_PATH)
    df['id'] = 'jp_' + df['corporate_number'].astype(str)
    df.set_index('id', inplace=True)
    company_data_map = df.to_dict('index')

    files_to_update = [f for f in os.listdir(CONTENT_DIR) if f.endswith('.md')]
    total_files = len(files_to_update)
    updated_count = 0
    print(f"총 {total_files}개의 파일을 대상으로 검사를 시작합니다.")

    for i, filename in enumerate(files_to_update):
        file_path = os.path.join(CONTENT_DIR, filename)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                post = frontmatter.load(f)
            
            # 이미 유효한 카테고리가 있으면 패스
            if 'category' in post.metadata and post.metadata['category'] in CATEGORIES:
                continue
            
            company_id = post.metadata.get('id')
            if not company_id or company_id not in company_data_map:
                print(f"   ⚠️ [{i+1}/{total_files}] '{filename}' 원본 데이터 누락. 건너뜁니다.")
                continue

            row = company_data_map[company_id]
            print(f"   - [{i+1}/{total_files}] '{filename}' 카테고리 분류 중...")
            
            prompt = f"""
            Analyze the company info and choose ONE category from: {', '.join(CATEGORIES)}.
            - Company: {row['name']}
            - Info: {post.content[:500]}
            Output ONLY the chosen category name.
            """
            
            response = MODEL.generate_content(prompt)
            ai_category = response.text.strip()
            
            if ai_category not in CATEGORIES:
                print(f"     -> 경고: AI가 유효하지 않은 카테고리('{ai_category}')를 반환하여 'Services'로 대체합니다.")
                ai_category = "Services"
            
            post.metadata['category'] = ai_category
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(frontmatter.dumps(post))
                
            print(f"     -> ✅ 완료. 카테고리: {ai_category}")
            updated_count += 1
            time.sleep(2)
            
        except Exception as e:
            print(f"   ❌ [{i+1}/{total_files}] '{filename}' 처리 중 오류: {e}")
            continue
            
    if updated_count == 0:
        print("모든 파일에 이미 유효한 카테고리가 존재합니다.")
    else:
        print(f"\n✅ 총 {updated_count}개의 파일에 카테고리를 추가했습니다.")


def update_index_and_sitemap():
    """(Final Task) 검색 인덱스와 사이트맵을 최신 상태로 재구성합니다."""
    if not os.path.exists(CONTENT_DIR):
        print(f"⚠️ 콘텐츠 폴더가 없습니다: {CONTENT_DIR}")
        return
    
    os.makedirs(DATA_DIR, exist_ok=True)
    # sitemap이 저장될 static 폴더 확보 (config.py의 경로 의존)
    static_dir_path = os.path.dirname(SITEMAP_PATH)
    os.makedirs(static_dir_path, exist_ok=True)

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
                
                # 검색 인덱스 데이터
                index_data.append({
                    "id": post.metadata.get('id', ''),
                    "file": file_slug,
                    "n": post.metadata.get('title', ''),
                    "en": post.metadata.get('title_en', ''),
                    "l": str(post.metadata.get('address', ''))[:30],
                    "s": post.metadata.get('subsidies', 0),
                    "c": post.metadata.get('category', 'Services')
                })

                # 사이트맵 URL
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
                print(f"⚠️ {filename} 처리 중 오류: {e}")
                continue
    
    # JSON 인덱스 저장
    with open(INDEX_PATH, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)
    print(f"✅ 검색 인덱스 갱신 완료 ({len(index_data)}개 기업)")

    # Sitemap XML 저장
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
    print(f"✅ 사이트맵 생성 완료 ({len(sitemap_urls)}개 링크) -> {SITEMAP_PATH}")


# --- 메인 실행 로직 ---
if __name__ == "__main__":
    # 명령줄 인수 파서 설정
    parser = argparse.ArgumentParser(description="CompanyDB 콘텐츠 관리 스크립트")
    parser.add_argument("command", choices=["daily", "migrate", "rebuild", "index"], help="실행할 작업을 선택합니다.")
    
    args = parser.parse_args()
    
    print("="*40)
    print(f"  CompanyDB 콘텐츠 관리: '{args.command}' 작업 시작")
    print("="*40)

    # 선택된 작업에 따라 함수 실행
    if args.command == "daily":
        generate_new_content()
        update_index_and_sitemap()
    elif args.command == "migrate":
        migrate_missing_categories()
        update_index_and_sitemap()
    elif args.command == "rebuild":
        generate_new_content()
        migrate_missing_categories()
        update_index_and_sitemap()
    elif args.command == "index":
        update_index_and_sitemap()

    print("\n🎉 모든 작업이 성공적으로 완료되었습니다!")
    print("="*40)