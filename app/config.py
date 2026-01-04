import os

# 기본 경로 설정
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONTENT_DIR = os.path.join(BASE_DIR, "app", "content")
STATIC_DIR = os.path.join(BASE_DIR, "app", "static")
TEMPLATE_DIR = os.path.join(BASE_DIR, "app", "templates")

# 데이터 파일 경로
CSV_PATH = os.path.join(DATA_DIR, "Total_Premium_Japan_SMEs.csv")
INDEX_PATH = os.path.join(DATA_DIR, "search_index.json")
SITEMAP_PATH = os.path.join(STATIC_DIR, "sitemap.xml")

# 서비스 설정
DOMAIN = "https://companydb.net"
DAILY_LIMIT = 10

# 카테고리 정의 (AI 생성 및 웹 필터링 공통 사용)
CATEGORIES = [
    "Manufacturing", "Technology", "Electronics", 
    "Medical", "Construction", "Services"
]

# 허브 페이지 데이터 정의
HUB_DATA = {
    "locations": {
        "tokyo": {"name": "Tokyo", "term": "東京"},
        "kanagawa": {"name": "Kanagawa", "term": "神奈川"},
        "osaka": {"name": "Osaka", "term": "大阪"},
        "aichi": {"name": "Aichi", "term": "愛知"}
    },
    "categories": {
        # 대소문자 매핑을 자동화하거나 명시적으로 정의
        c.lower(): {"name": c, "term": c.lower()} for c in CATEGORIES
    }
}