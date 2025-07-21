FROM python:3.11-slim

# 필수 시스템 패키지 설치 (WeasyPrint 의존성 포함)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libcairo2 \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    libxml2 \
    libxslt1.1 \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# 작업 디렉토리 설정
WORKDIR /app

# requirements.txt 복사 및 Python 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip show google-cloud-aiplatform || (echo '❌ vertexai 설치 실패!' && exit 1)

# 전체 프로젝트 복사
COPY . .

# Cloud Run 포트 설정
EXPOSE 8080

# FastAPI 앱 실행
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
