import google.generativeai as genai
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("❌ API Key가 없습니다. .env 파일을 확인해주세요.")
else:
    genai.configure(api_key=api_key)
    
    print(f"🔍 API Key: {api_key[:5]}... 로 사용 가능한 모델 조회 중...\n")
    
    try:
        found = False
        for m in genai.list_models():
            # 텍스트 생성(generateContent)이 가능한 모델만 출력
            if 'generateContent' in m.supported_generation_methods:
                print(f"✅ {m.name}")
                found = True
        
        if not found:
            print("⚠️ 사용 가능한 모델이 하나도 없습니다. API 키 권한을 확인하세요.")
            
    except Exception as e:
        print(f"❌ 에러 발생: {e}")