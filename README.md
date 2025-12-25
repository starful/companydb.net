# CompanyDB | Global SME Intelligence Platform

**CompanyDB** is a strategic intelligence platform that provides AI-verified analysis reports on premium Japanese SMEs. It leverages **Google Gemini 2.0 Flash** to transform raw corporate data into comprehensive B2B insights, bridging the gap between Japanese manufacturing excellence and global investors/partners.

## 🚀 Key Features

-   **AI-Powered Analysis**: Automatically generates detailed 4,000+ character strategic reports using Gemini 2.0.
-   **Hybrid Architecture**: Combines Static Site Generation (SSG) for performance with Server-Side Rendering (SSR) for search.
-   **SEO Optimized**: Dynamic sitemap generation (`sitemap.xml`), meta tags, and Open Graph support for maximum visibility.
-   **Live Data Dashboard**: Real-time display of indexed companies and weekly update status.
-   **B2B Focused**: Specialized content filtering for government subsidies, patents, and "Monozukuri" capabilities.

## 🛠 Tech Stack

-   **Backend**: Python, FastAPI
-   **Frontend**: Jinja2 Templates, Custom CSS (Responsive)
-   **AI Engine**: Google Gemini 2.0 Flash
-   **Data Storage**: Markdown (Content), JSON (Search Index)
-   **Infrastructure**: Docker, Google Cloud Run, Cloud Build

## 📂 Project Structure

```bash
.
├── app/
│   ├── content/        # Generated Markdown reports (Database)
│   ├── static/         # CSS, Images, Sitemap
│   ├── templates/      # HTML Jinja2 Templates
│   └── main.py         # FastAPI Application entry point
├── data/
│   ├── Total_Premium_Japan_SMEs.csv  # Source Master Data
│   └── search_index.json             # Search Index (Auto-generated)
├── script/
│   ├── generate_daily.py   # AI Content Generator (CSV -> MD)
│   └── update_index.py     # Indexer & Sitemap Generator (MD -> JSON/XML)
├── cloudbuild.yaml     # CI/CD Configuration
└── Dockerfile          # Container Definition
```

## ⚡️ Data Pipeline & Workflow

This project follows a 3-step daily workflow to maintain data freshness:

### 1. Generate Content (Local)
Reads the master CSV and uses AI to write detailed Markdown reports.
```bash
python script/generate_daily.py
```

### 2. Update Index & Sitemap (Local)
Scans generated Markdown files to build the search index and SEO sitemap.
```bash
python script/update_index.py
```

### 3. Deploy (Cloud)
Deploys the application with the latest static assets to Google Cloud Run.
```bash
gcloud builds submit --config cloudbuild.yaml \
  --substitutions=_REGION="us-central1",_GCS_BUCKET_NAME="companydb-data",_APP_DOMAIN="https://companydb.net"
```

## 💻 Local Development

1.  **Clone the repository**
    ```bash
    git clone https://github.com/your-username/companydb.git
    cd companydb
    ```

2.  **Install dependencies**
    ```bash
    python -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

3.  **Set up Environment Variables**
    Create a `.env` file and add your Google Gemini API Key:
    ```
    GEMINI_API_KEY=your_api_key_here
    ```

4.  **Run the Server**
    ```bash
    uvicorn app.main:app --reload
    ```
    Visit `http://127.0.0.1:8000`

## 🔒 License

This project is proprietary software. All rights reserved.