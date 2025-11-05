# cache_warmer.py

import os
import json
import redis
from hatena_client import fetch_all_hatena_posts # 공통 모듈에서 함수 임포트

# --- 설정 ---
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_DB = int(os.getenv('REDIS_DB', 0))
APP_DOMAIN = os.getenv('APP_DOMAIN') # APP_DOMAIN 환경 변수 확인

# 캐시 키
REDIS_ALL_POSTS_KEY = "all_hatena_posts"

def main():
    """스크립트의 메인 실행 함수"""
    # 필수 환경 변수 확인
    if not APP_DOMAIN:
        print("오류: APP_DOMAIN 환경 변수가 설정되지 않았습니다. Cloud Run Job 설정을 확인해주세요.")
        exit(1)

    # Redis 클라이언트 초기화
    try:
        redis_client = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
        redis_client.ping()
        print("성공: Redis에 연결되었습니다.")
    except Exception as e:
        print(f"치명적 오류: Redis에 연결할 수 없습니다 - {e}")
        exit(1) # Redis 연결 없이는 작업을 계속할 수 없으므로 종료

    # hatena_client 모듈을 사용하여 모든 게시물 데이터 가져오기
    all_posts = fetch_all_hatena_posts()

    # 가져온 데이터가 비어 있는지 확인
    if not all_posts:
        print("경고: Hatena로부터 가져온 게시물이 없습니다. API 키나 블로그 ID 설정을 확인해보세요. 캐시를 업데이트하지 않습니다.")
        return # 빈 데이터로 캐시를 덮어쓰지 않도록 함수 종료

    # 모든 게시물 데이터를 JSON으로 변환하여 Redis에 '영구적으로' 저장
    try:
        redis_client.set(
            REDIS_ALL_POSTS_KEY, 
            json.dumps(all_posts)
        )
        print(f"성공: 총 {len(all_posts)}개의 게시물을 Redis에 영구적으로 캐싱했습니다.")
    except Exception as e:
        print(f"치명적 오류: Redis에 데이터를 쓰는 중 오류가 발생했습니다 - {e}")
        exit(1)

# --- 이 스크립트의 메인 실행 부분 ---
if __name__ == "__main__":
    main()