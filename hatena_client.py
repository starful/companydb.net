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

# --- (Existing functions) ---
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
        print(f"Warning: Failed to fetch thumbnail: {public_link}, {e}")
    cleaned_text = clean_text_for_summary(content_text)
    summary = (cleaned_text[:120] + '...') if len(cleaned_text) > 120 else cleaned_text
    return {'content': content_text, 'thumbnail': thumbnail_url, 'summary': summary}


# ▼▼▼ [Modified] Fetch with deletion logic ▼▼▼
def fetch_all_hatena_posts(existing_posts=None):
    if existing_posts is None:
        existing_posts = []

    # Convert list to ID-based dictionary map
    existing_map = {post.get('id'): post for post in existing_posts if post.get('id')}
    
    # Set to track live posts from API
    live_post_ids = set()

    print("Checking latest posts from Hatena API...")
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
                live_post_ids.add(entry_id) # Mark as live
                
                title = entry.find('atom:title', ns).text
                updated = entry.find('atom:updated', ns).text

                # Fetch new or updated posts
                if entry_id not in existing_map or existing_map[entry_id].get('updated') != updated:
                    print(f"  [Fetch] Processing new/updated post: {title}")
                    link = entry.find('atom:link[@rel="alternate"]', ns).get('href')
                    details = fetch_full_post_details(entry_id, link)
                    
                    # Update map
                    existing_map[entry_id] = {
                        'id': entry_id, 'updated': updated, 'title': title,
                        'link': link, 'content': details['content'],
                        'thumbnail': details['thumbnail'], 'summary': details['summary']
                    }
                    processed_count += 1
                    time.sleep(0.5)
                else:
                    skipped_count += 1 # No change

            next_link = root.find('atom:link[@rel="next"]', ns)
            url = next_link.get('href') if next_link is not None else None
            if url:
                print("Checking next page...")
                time.sleep(0.5)

    except Exception as e:
        print(f"Critical Error: Hatena API Process Interrupted - {e}")
        print("Returning existing data due to error.")
        return existing_posts

    # --- [Deletion Logic] ---
    existing_post_ids = set(existing_map.keys())
    deleted_post_ids = existing_post_ids - live_post_ids
    
    if deleted_post_ids:
        print(f"Removing {len(deleted_post_ids)} deleted posts.")
        for post_id in deleted_post_ids:
            del existing_map[post_id]
            
    final_posts_data = list(existing_map.values())

    print(f"Process Complete: New/Upd {processed_count}, Skip {skipped_count}, Drafts {draft_skipped_count}, Del {len(deleted_post_ids)}.")
    print(f"Final Data: Total {len(final_posts_data)} posts")
    return final_posts_data