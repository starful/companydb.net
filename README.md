# companyDB – High-Speed Hatena Blog Search (GCS Edition)

**companyDB** is a web application designed for searching and browsing Hatena Blog articles.

Originally built with Redis, this version uses **Google Cloud Storage (GCS)** for cost-effective data persistence. The application fetches blog data via a Cloud Run Job, stores it as a JSON file in GCS, and the web app caches it in memory for fast retrieval.

![screenshot](static/companydb_logo.png)

---

## 🔍 Features

- **Cost-Effective Architecture:** Replaced Redis with Google Cloud Storage + In-Memory Caching. No VPC Connector required.
- **SEO Optimized:** Includes dynamic `sitemap.xml`, JSON-LD, and Open Graph tags.
- **Visual Results:** Automatically fetches and displays thumbnails.
- **Responsive Design:** Optimized for desktop and mobile via Bootstrap.

---

## 🖥️ Tech Stack

| Technology | Description |
| :--- | :--- |
| **Flask** | A lightweight web framework for Python (v3.9). |
| **Google Cloud Storage** | Stores the parsed blog data (`companydb_posts.json`). |
| **Cloud Run Service** | Hosts the web application (Serverless). |
| **Cloud Run Jobs** | Runs the background task (`cache_warmer.py`) to fetch data and upload to GCS. |

---

## 🚀 Release & Update Process

### **Step 1: Create GCS Bucket**
Create a standard Google Cloud Storage bucket to store the cache file.
```bash
export GCR_PROJECT_ID="YOUR_GCP_PROJECT_ID"
export BUCKET_NAME="${GCR_PROJECT_ID}-companydb-cache"

# Create the bucket (Standard class, us-central1 region recommended)
gcloud storage buckets create gs://${BUCKET_NAME} --location=us-central1