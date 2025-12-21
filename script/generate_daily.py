import pandas as pd
import os
import frontmatter
import google.generativeai as genai
from dotenv import load_dotenv
import time
import re

# 설정 로드
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.0-flash')

CSV_PATH = 'data/Total_Premium_Japan_SMEs.csv'
CONTENT_DIR = 'app/content'
DAILY_LIMIT = 10

def slugify(text):
    """영어 회사명을 파일명으로 변환"""
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')

def generate_md():
    df = pd.read_csv(CSV_PATH)
    os.makedirs(CONTENT_DIR, exist_ok=True)
    
    count = 0
    print(f"🚀 장문 리포트 생성 시작 (JSON 미사용, 텍스트 스트리밍 방식)")

    for _, row in df.iterrows():
        if count >= DAILY_LIMIT: break
        
        cid = f"jp_{row['corporate_number']}"
        existing_files = [f for f in os.listdir(CONTENT_DIR) if f.startswith(cid)]
        if existing_files: continue

        print(f"📝 [{count+1}/{DAILY_LIMIT}] {row['name']} 분석 중...")
        
        # AI에게 JSON 대신 구조화된 일반 텍스트를 요구
        prompt = f"""
        Act as a Senior Business Analyst. Write a 4,000+ character B2B analysis report for:
        - Company: {row['name']}
        - Location: {row['location']}
        - Gov Info: {row['subsidy_titles'] if pd.notna(row['subsidy_titles']) else "Verified SME"}

        [Output Instructions]
        Line 1: Formal English Name (Only the name, nothing else)
        Line 2: ---BODY---
        Line 3 and beyond: Full Detailed Markdown Report (Min 4,000 chars)

        [Content Focus]
        - Professional B2B perspective.
        - Analyze Industry Context, Monozukuri/Quality, Regional Advantage.
        - Be extremely verbose to exceed 4,000 characters.
        """
        
        try:
            response = model.generate_content(prompt)
            full_response = response.text.strip()

            # 구분자(---BODY---)를 기준으로 이름과 본문을 나눔
            if "---BODY---" in full_response:
                parts = full_response.split("---BODY---")
                ai_en_name = parts[0].strip()
                ai_content = parts[1].strip()
            else:
                # 구분자가 없을 경우 첫 줄을 이름으로 간주
                lines = full_response.split('\n')
                ai_en_name = lines[0].strip()
                ai_content = "\n".join(lines[1:]).strip()

            # 파일명 생성 (ID + 영어 이름)
            file_slug = slugify(ai_en_name)
            file_name = f"{cid}_{file_slug}.md"
            file_path = os.path.join(CONTENT_DIR, file_name)

            # 메타데이터 구성 (상세페이지 상단에 표시될 정보들)
            metadata = {
                "id": cid,
                "title": str(row['name']),
                "title_en": ai_en_name,
                "address": str(row['location']),
                "subsidies": int(row['subsidy_count']),
                "category": "Japan SME",
                "contact": f"https://www.google.com/search?q={row['name']}+contact+website"
            }
            
            # YAML Frontmatter와 본문을 합쳐서 .md 파일 저장
            post = frontmatter.Post(ai_content, **metadata)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(frontmatter.dumps(post))
            
            print(f"   ✅ 완료: {file_name} ({len(ai_content)} chars)")
            count += 1
            time.sleep(5) # 할당량 보호
            
        except Exception as e:
            print(f"   ❌ 에러: {e}")
            time.sleep(10)

    print(f"\n🏁 작업 종료.")

if __name__ == "__main__":
    generate_md()