# hatena_client.py

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

# --- 환경 변수 설정 ---
HATENA_USERNAME = os.getenv('HATENA_USERNAME')
HATENA_BLOG_ID = os.getenv('HATENA_BLOG_ID')
HATENA_API_KEY = os.getenv('HATENA_API_KEY')
# Cloud Run 서비스의 URL을 환경변수로부터 받아옵니다.
# 예: "https://companydb-xxxxx-uc.a.run.app"
APP_DOMAIN = os.getenv('APP_DOMAIN', '')

def create_wsse_header(username, api_key):
    """WSSE 인증 헤더를 생성합니다."""
    nonce = hashlib.sha1(str(random.random()).encode()).digest()
    created = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    digest_base = nonce + created.encode() + api_key.encode()
    digest = hashlib.sha1(digest_base).digest()
    return f'UsernameToken Username="{username}", PasswordDigest="{base64.b64encode(digest).decode()}", Nonce="{base64.b64encode(nonce).decode()}", Created="{created}"'

def clean_text_for_summary(text):
    """본문 텍스트에서 불필요한 마크다운/하테나 구문을 제거하여 요약용으로 정리합니다."""
    text = re.sub(r'\[f:id:.*?\]', '', text) # 하테나 포토라이프 구문 제거
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE) # 마크다운 헤더 제거
    text = text.replace('**', '').replace('##', '').replace('`', '') # 기타 마크다운 제거
    text = text.replace('TL;DR', '').strip()
    return re.sub(r'\n{2,}', '\n', text) # 여러 줄바꿈을 하나로 축소

def fetch_full_post_details(entry_id, public_link):
    """
    개별 게시물 ID를 사용하여 상세 정보(본문, 썸네일, 요약)를 가져옵니다.
    이 함수는 외부 API와 통신합니다.
    """
    entry_url = f"https://blog.hatena.ne.jp/{HATENA_USERNAME}/{HATENA_BLOG_ID}/atom/entry/{entry_id}"
    headers = {'X-WSSE': create_wsse_header(HATENA_USERNAME, HATENA_API_KEY)}
    
    # AtomPub API 호출
    api_response = requests.get(entry_url, headers=headers, timeout=15)
    api_response.raise_for_status() # 오류 발생 시 예외를 던짐
    
    root = ET.fromstring(api_response.content)
    ns = {'atom': 'http://www.w3.org/2005/Atom'}
    content_html = root.find('atom:content', ns).text
    soup_content = BeautifulSoup(content_html, 'html.parser')
    content_text = soup_content.get_text()

    # 기본 썸네일은 로고 이미지의 절대 경로로 설정
    thumbnail_url = f"{APP_DOMAIN}/static/companydb_logo.png"
    
    try:
        # 공개 페이지에서 og:image 메타 태그를 파싱하여 썸네일 URL을 가져옴
        page_response = requests.get(public_link, timeout=10)
        if page_response.status_code == 200:
            soup_page = BeautifulSoup(page_response.text, 'html.parser')
            og_image_tag = soup_page.find('meta', property='og:image')
            if og_image_tag and og_image_tag.get('content'):
                thumbnail_url = og_image_tag['content']
    except requests.exceptions.RequestException as e:
        print(f"경고: og:image를 가져오는 데 실패했습니다: {public_link}, 오류: {e}")
        
    cleaned_text = clean_text_for_summary(content_text)
    summary = (cleaned_text[:120] + '...') if len(cleaned_text) > 120 else cleaned_text
    
    return {'content': content_text, 'thumbnail': thumbnail_url, 'summary': summary}

def fetch_all_hatena_posts():
    """
    하테나 블로그의 모든 게시물 정보를 가져오는 메인 로직입니다.
    페이지네이션을 따라 모든 게시물 메타데이터를 수집한 후, 각 게시물의 상세 정보를 가져옵니다.
    """
    print("Hatena API에서 모든 게시물 메타데이터를 가져옵니다.")
    post_meta_list = []
    url = f"https://blog.hatena.ne.jp/{HATENA_USERNAME}/{HATENA_BLOG_ID}/atom/entry"
    
    while url:
        headers = {'X-WSSE': create_wsse_header(HATENA_USERNAME, HATENA_API_KEY)}
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        root = ET.fromstring(response.content)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        
        for entry in root.findall('atom:entry', ns):
            id_tag = entry.find('atom:id', ns)
            entry_id = id_tag.text.split('-')[-1]
            title = entry.find('atom:title', ns).text
            link = entry.find('atom:link[@rel="alternate"]', ns).get('href')
            post_meta_list.append({'id': entry_id, 'title': title, 'link': link})
            
        next_link = root.find('atom:link[@rel="next"]', ns)
        url = next_link.get('href') if next_link is not None else None
        if url:
            print(f"다음 페이지로 이동: {url}")
            time.sleep(0.5)

    print(f"총 {len(post_meta_list)}개의 게시물 메타데이터를 찾았습니다. 이제 각 게시물의 상세 정보를 가져옵니다.")
    
    all_posts_data = []
    for i, meta in enumerate(post_meta_list):
        try:
            details = fetch_full_post_details(meta['id'], meta['link'])
            all_posts_data.append({
                'title': meta['title'],
                'link': meta['link'],
                'content': details['content'],
                'thumbnail': details['thumbnail'],
                'summary': details['summary']
            })
            print(f"  ({i+1}/{len(post_meta_list)}) 처리 완료: {meta['title']}")
            time.sleep(0.2) # API 과부하 방지를 위한 짧은 대기
        except Exception as e:
            print(f"  오류: ID {meta['id']} ({meta['title']})의 상세 정보 가져오기 실패 - {e}")
            
    return all_posts_data