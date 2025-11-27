import os
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import base64
import hashlib
from datetime import datetime, timezone
import random
import re
import time

# --- (상단 함수들은 이전과 동일) ---
HATENA_USERNAME = os.getenv('HATENA_USERNAME')
HATENA_BLOG_ID = os.getenv('HATENA_BLOG_ID')
HATENA_API_KEY = os.getenv('HATENA_API_KEY')
APP_DOMAIN = os.getenv('APP_DOMAIN', '')

def create_wsse_header(username, api_key):
    nonce = hashlib.sha1(str(random.random()).encode()).digest()
    created = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    digest_base = nonce + created.encode() + api_key.encode()
    digest = hashlib.sha1(digest_base).digest()
    return f'UsernameToken Username="{username}", PasswordDigest="{base64.b64encode(digest).decode()}", Nonce="{base64.b64encode(nonce).decode()}", Created="{created}"'

def clean_text_for_summary(text):
    text = re.sub(r'\[f:id:.*?\]', '', text)
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
    text = text.replace('**', '').replace('##', '').replace('`', '')
    text = text.replace('TL;DR', '').strip()
    return re.sub(r'\n{2,}', '\n', text)

def fetch_full_post_details(entry_id, public_link):
    entry_url = f"https://blog.hatena.ne.jp/{HATENA_USERNAME}/{HATENA_BLOG_ID}/atom/entry/{entry_id}"
    headers = {'X-WSSE': create_wsse_header(HATENA_USERNAME, HATENA_API_KEY)}
    api_response = requests.get(entry_url, headers=headers, timeout=15)
    api_response.raise_for_status()
    root = ET.fromstring(api_response.content)
    ns = {'atom': 'http://www.w3.org/2005/Atom'}
    content_html = root.find('atom:content', ns).text
    soup_content = BeautifulSoup(content_html, 'html.parser')
    content_text = soup_content.get_text()
    thumbnail_url = f"{APP_DOMAIN}/static/companydb_logo.png"
    try:
        page_response = requests.get(public_link, timeout=10)
        page_response.raise_for_status()
        soup_page = BeautifulSoup(page_response.text, 'html.parser')
        og_image_tag = soup_page.find('meta', property='og:image')
        if og_image_tag and og_image_tag.get('content'):
            thumbnail_url = og_image_tag['content']
    except Exception as e:
        print(f"경고: 썸네일 가져오기 실패: {public_link}, {e}")
    cleaned_text = clean_text_for_summary(content_text)
    summary = (cleaned_text[:120] + '...') if len(cleaned_text) > 120 else cleaned_text
    return {'content': content_text, 'thumbnail': thumbnail_url, 'summary': summary}


# ▼▼▼ [핵심 수정] 삭제 처리 로직이 포함된 새로운 함수 ▼▼▼
def fetch_all_hatena_posts(existing_posts=None):
    if existing_posts is None:
        existing_posts = []

    # 기존 데이터를 ID 기반 딕셔너리로 변환 (빠른 조회 및 수정용)
    existing_map = {post.get('id'): post for post in existing_posts if post.get('id')}
    
    # API를 통해 확인된 글의 ID를 저장할 집합(set)
    live_post_ids = set()

    print("Hatena API에서 최신 게시물 목록을 확인합니다.")
    url = f"https://blog.hatena.ne.jp/{HATENA_USERNAME}/{HATENA_BLOG_ID}/atom/entry"
    
    processed_count = 0
    skipped_count = 0
    draft_skipped_count = 0

    try:
        while url:
            headers = {'X-WSSE': create_wsse_header(HATENA_USERNAME, HATENA_API_KEY)}
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            root = ET.fromstring(response.content)
            ns = {'atom': 'http://www.w3.org/2005/Atom', 'app': 'http://www.w3.org/2007/app'}
            
            entries = root.findall('atom:entry', ns)
            if not entries:
                break

            for entry in entries:
                control = entry.find('app:control', ns)
                if control is not None:
                    draft = control.find('app:draft', ns)
                    if draft is not None and draft.text == 'yes':
                        draft_skipped_count += 1
                        continue

                entry_id = entry.find('atom:id', ns).text.split('-')[-1]
                live_post_ids.add(entry_id) # API에 존재하는 글 ID로 기록
                
                title = entry.find('atom:title', ns).text
                updated = entry.find('atom:updated', ns).text

                # 기존 데이터에 없거나, 수정 시간이 다르면 새로 가져오기
                if entry_id not in existing_map or existing_map[entry_id].get('updated') != updated:
                    print(f"  [Fetch] 신규/수정 글 처리 중: {title}")
                    link = entry.find('atom:link[@rel="alternate"]', ns).get('href')
                    details = fetch_full_post_details(entry_id, link)
                    
                    # 기존 맵에 데이터 추가 또는 갱신
                    existing_map[entry_id] = {
                        'id': entry_id, 'updated': updated, 'title': title,
                        'link': link, 'content': details['content'],
                        'thumbnail': details['thumbnail'], 'summary': details['summary']
                    }
                    processed_count += 1
                    time.sleep(0.5)
                else:
                    skipped_count += 1 # 변경 없음

            next_link = root.find('atom:link[@rel="next"]', ns)
            url = next_link.get('href') if next_link is not None else None
            if url:
                print("다음 목록 페이지 확인 중...")
                time.sleep(0.5)

    except Exception as e:
        print(f"치명적 오류: Hatena API 처리 중단 - {e}")
        print("오류로 인해 기존 데이터를 그대로 반환합니다.")
        return existing_posts # 오류 발생 시, 안전하게 기존 데이터를 반환

    # --- [삭제 처리 로직] ---
    # 기존 데이터의 모든 ID 집합
    existing_post_ids = set(existing_map.keys())
    # 삭제된 글 ID 집합 = (기존 ID) - (API에 존재하는 ID)
    deleted_post_ids = existing_post_ids - live_post_ids
    
    if deleted_post_ids:
        print(f"삭제된 글 {len(deleted_post_ids)}건을 데이터에서 제거합니다.")
        for post_id in deleted_post_ids:
            del existing_map[post_id] # 맵에서 삭제된 글 제거
            
    final_posts_data = list(existing_map.values())

    print(f"처리 완료: 신규/수정 {processed_count}건, 유지 {skipped_count}건, 비공개 제외 {draft_skipped_count}건, 삭제 {len(deleted_post_ids)}건.")
    print(f"최종 데이터: 총 {len(final_posts_data)}건")
    return final_posts_data