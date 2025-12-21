import os
import json
import frontmatter

CONTENT_DIR = 'app/content'
INDEX_PATH = 'data/search_index.json'

def update_index():
    # 폴더가 없으면 생성 (에러 방지)
    if not os.path.exists(CONTENT_DIR):
        print(f"⚠️ 폴더가 없습니다: {CONTENT_DIR}")
        return

    index_data = []
    
    for filename in os.listdir(CONTENT_DIR):
        if filename.endswith('.md'):
            try:
                # try 블록 시작: 에러가 발생할 수 있는 코드
                with open(os.path.join(CONTENT_DIR, filename), 'r', encoding='utf-8') as f:
                    post = frontmatter.load(f)
                    
                    # 메타데이터 추출
                    index_data.append({
                        "id": post.metadata.get('id', ''),
                        "file": filename.replace(".md", ""), # 파일명에서 확장자 제거
                        "n": post.metadata.get('title', ''),
                        "en": post.metadata.get('title_en', ''),
                        "l": str(post.metadata.get('address', ''))[:30],
                        "s": post.metadata.get('subsidies', 0)
                    })
            except Exception as e:
                # 에러 발생 시 해당 파일은 건너뜀
                print(f"⚠️ Skipping {filename}: {e}")
                continue
    
    # JSON 파일 저장
    os.makedirs(os.path.dirname(INDEX_PATH), exist_ok=True)
    with open(INDEX_PATH, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)
        
    print(f"✅ 검색 인덱스 갱신 완료 ({len(index_data)}개 기업)")

if __name__ == "__main__":
    update_index()