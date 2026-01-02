import pandas as pd
import os
import frontmatter
import google.generativeai as genai
from dotenv import load_dotenv
import time
import re
import json
from datetime import datetime

# run_daily_update.py와 동일한 설정 및 함수를 가져옵니다.
from run_daily_update import update_index_and_sitemap, slugify, CATEGORIES, CSV_PATH, CONTENT_DIR

# --- AI 및 기본 설정 ---
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = genai.GenerativeModel('gemini-2.0-flash')

def add_category_to_existing_files():
    """
    기존 .md 파일들을 순회하며 'category' 메타데이터가 없는 경우,
    AI를 통해 카테고리를 분류하고 파일에 추가합니다.
    """
    print("🚀 기존 마크다운 파일에 대한 카테고리 업데이트를 시작합니다...")
    
    if not os.path.exists(CSV_PATH):
        print(f"❌ 원본 데이터 파일({CSV_PATH})을 찾을 수 없어 스크립트를 중단합니다.")
        return

    # CSV 데이터를 미리 메모리에 로드하여 빠른 조회를 가능하게 합니다.
    df = pd.read_csv(CSV_PATH)
    df['id'] = 'jp_' + df['corporate_number'].astype(str)
    df.set_index('id', inplace=True)
    company_data_map = df.to_dict('index')

    files_to_update = [f for f in os.listdir(CONTENT_DIR) if f.endswith('.md')]
    total_files = len(files_to_update)
    print(f"총 {total_files}개의 파일을 대상으로 검사를 시작합니다.")

    for i, filename in enumerate(files_to_update):
        file_path = os.path.join(CONTENT_DIR, filename)
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                post = frontmatter.load(f)

            # 이미 유효한 카테고리가 있으면 건너뜁니다.
            if 'category' in post.metadata and post.metadata['category'] in CATEGORIES:
                continue

            company_id = post.metadata.get('id')
            if not company_id or company_id not in company_data_map:
                print(f"   ⚠️ [{i+1}/{total_files}] '{filename}'의 원본 데이터를 찾을 수 없어 건너뜁니다.")
                continue

            row = company_data_map[company_id]
            print(f"   - [{i+1}/{total_files}] '{filename}' 카테고리 분류 중...")

            # 카테고리 분류만을 위한 경량화된 프롬프트
            prompt = f"""
            Analyze the following company information and choose the ONE most appropriate category from this list: {', '.join(CATEGORIES)}.
            - Company Name: {row['name']}
            - Main Business Info: {post.content[:500]}

            Output ONLY the chosen category name, and nothing else.
            """
            
            response = MODEL.generate_content(prompt)
            ai_category = response.text.strip()

            # AI가 목록에 없는 값을 생성할 경우를 대비한 안전장치
            if ai_category not in CATEGORIES:
                print(f"     -> AI가 유효하지 않은 카테고리('{ai_category}')를 반환하여 'Services'로 대체합니다.")
                ai_category = "Services"
            
            # 메타데이터에 카테고리 추가
            post.metadata['category'] = ai_category

            # 업데이트된 내용으로 파일 다시 저장
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(frontmatter.dumps(post))
            
            print(f"     -> ✅ 완료. 카테고리: {ai_category}")
            time.sleep(2) # API 과호출 방지를 위한 딜레이

        except Exception as e:
            print(f"   ❌ [{i+1}/{total_files}] '{filename}' 처리 중 오류 발생: {e}")
            continue

    print("\n✅ 모든 파일의 카테고리 업데이트가 완료되었습니다.")


if __name__ == "__main__":
    # 1. 기존 파일에 카테고리 정보 추가
    add_category_to_existing_files()
    
    # 2. 업데이트된 내용을 바탕으로 검색 인덱스 및 사이트맵 재구성
    update_index_and_sitemap()
    
    print("\n🎉 모든 마이그레이션 작업이 성공적으로 완료되었습니다!")