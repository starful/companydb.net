FROM python:3.11-slim

# 작업 디렉토리 설정
WORKDIR /app

# requirements.txt 복사 및 설치 확인 로그 추가
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip show google-cloud-aiplatform || (echo '❌ vertexai 설치 실패!' && exit 1)

# 전체 프로젝트 복사
COPY . .

# 애플리케이션 실행
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
