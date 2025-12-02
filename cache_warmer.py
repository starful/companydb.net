import os
import json
from google.cloud import storage
from google.api_core.exceptions import NotFound
from hatena_client import fetch_all_hatena_posts

# --- Configuration ---
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME')
CACHE_FILE_NAME = "companydb_posts.json"
APP_DOMAIN = os.getenv('APP_DOMAIN')

def main():
    """Main execution function"""
    if not APP_DOMAIN or not GCS_BUCKET_NAME:
        print("Error: Missing required env vars (APP_DOMAIN, GCS_BUCKET_NAME).")
        exit(1)

    storage_client = storage.Client()
    bucket = storage_client.bucket(GCS_BUCKET_NAME)

    # 1. Load existing data from GCS
    existing_posts = []
    try:
        blob = bucket.blob(CACHE_FILE_NAME)
        if blob.exists():
            print("Downloading existing data from GCS...")
            data_string = blob.download_as_text()
            existing_posts = json.loads(data_string)
            print(f"Loaded {len(existing_posts)} existing posts.")
        else:
            print("No existing data in GCS. Starting full fetch.")
    except Exception as e:
        print(f"Warning during GCS read: {e}")
        existing_posts = []

    # 2. Call Hatena API
    all_posts = fetch_all_hatena_posts(existing_posts)

    if not all_posts:
        print("Warning: No data fetched. Skipping GCS update.")
        return

    # 3. Upload results to GCS
    try:
        json_data = json.dumps(all_posts, ensure_ascii=False)
        blob = bucket.blob(CACHE_FILE_NAME)
        blob.upload_from_string(json_data, content_type='application/json')
        print(f"Success: Saved {len(all_posts)} posts to GCS.")
    except Exception as e:
        print(f"Critical Error: GCS upload failed - {e}")
        exit(1)

if __name__ == "__main__":
    main()