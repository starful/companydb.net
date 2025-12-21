FROM python:3.11-slim

WORKDIR /code

# 환경변수 설정
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# 1. 의존성 설치 (자주 바뀌지 않으므로 상단에 배치하여 캐시 활용)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2. 로컬에서 이미 생성된 데이터와 소스 코드를 통째로 복사 (이게 핵심!)
# 로컬의 app/content 및 data/search_index.json이 그대로 이미지에 들어감
COPY . .

# 3. 실행 (빌드 시점에 AI 호출인 RUN python script/build_data.py는 삭제!)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]