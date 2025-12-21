### README.md

```markdown
# 🏢 CompanyDB - Premium SME Intelligence Platform

**CompanyDB** is an AI-powered business intelligence platform that provides deep-dive analysis reports for small and medium-sized enterprises (SMEs) in Japan and Korea. By leveraging **Google Gemini 2.0 Flash**, it generates comprehensive corporate profiles to bridge the gap between local high-tech SMEs and global buyers.

![CompanyDB Screenshot](app/static/img/companydb_logo.png)

## ✨ Key Features

*   **🔍 AI-Powered Deep Analysis**: Generates 4,000+ character strategic reports covering industry context, regional advantages, and reliability analysis.
*   **📂 Static File Architecture**: Ultra-fast performance using pre-generated Markdown content without a heavy database server.
*   **🌍 Global Search**: Supports searching by company names in both English and Japanese.
*   **🚀 Cloud Native**: Deployable on Google Cloud Run with CI/CD integration via Cloud Build.
*   **📱 Responsive UI**: Professional B2B design optimized for desktop and mobile.

## 🛠️ Tech Stack

*   **Backend**: Python 3.11, FastAPI, Uvicorn
*   **AI Engine**: Google Gemini 2.0 Flash
*   **Frontend**: HTML5, CSS3, Jinja2 Templates
*   **Data Processing**: Pandas, Frontmatter
*   **Infrastructure**: Google Cloud Run, Cloud Build, Artifact Registry

## 📂 Project Structure

```text
companydb/
├── app/                        # Main Application
│   ├── main.py                 # FastAPI Application & Routes
│   ├── content/                # AI-Generated Markdown Reports (.md)
│   ├── static/                 # Static Assets (CSS, Images)
│   └── templates/              # HTML Templates (Jinja2)
├── data/                       # Data Sources
│   ├── Total_Premium_Japan_SMEs.csv  # Raw Company Data
│   └── search_index.json       # Search Index (Generated)
├── script/                     # Automation Scripts
│   ├── generate_daily.py       # AI Content Generator
│   └── update_index.py         # Search Index Updater
├── cloudbuild.yaml             # Google Cloud Build Config
├── Dockerfile                  # Docker Image Configuration
├── requirements.txt            # Python Dependencies
└── .env                        # Environment Variables (Not in Repo)
```

## 🚀 How to Run Locally

### 1. Prerequisites
- Python 3.11+
- Google Cloud Project with Gemini API enabled

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/starful/companydb.net.git
cd companydb

# Install dependencies
pip install -r requirements.txt
```

### 3. Setup Environment
Create a `.env` file in the root directory:
```ini
GEMINI_API_KEY=your_google_gemini_api_key
```

### 4. Generate Data (Local)
To generate AI reports and build the search index:
```bash
# 1. Generate 10 new company reports
python script/generate_daily.py

# 2. Update search index
python script/update_index.py
```

### 5. Run Server
```bash
uvicorn app.main:app --reload
```
Visit `http://127.0.0.1:8000` in your browser.

## ☁️ Deployment (Google Cloud Run)

This project uses **Google Cloud Build** for CI/CD.

### Deploy Command
```bash
gcloud builds submit --config cloudbuild.yaml \
  --substitutions=_REGION="us-central1",_GCS_BUCKET_NAME="companydb-data",_APP_DOMAIN="https://companydb.net"
```
*(Note: Ensure you have run `generate_daily.py` and `update_index.py` locally before deploying, as the build process simply copies the generated content.)*

## 📝 License

This project is licensed under the MIT License.
```