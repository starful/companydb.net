# companyDB – High-Speed Hatena Blog Search

**companyDB** is a web application designed for high-speed searching and browsing of Hatena Blog articles. It achieves its speed by pre-generating a search cache.

The user interface is localized for Japanese users, supporting keyword searches for specific corporate or technical blog posts. Caching is handled by a Cloud Run Job, and the application is built with **Google Cloud Run**, **Flask**, and **Redis** (Memorystore).

![screenshot](static/companydb_logo.png)

---

## 🔍 Features

- **High-Speed Search:** Instant results powered by Redis caching.
- **SEO Optimized:** Includes dynamic `sitemap.xml`, JSON-LD structured data, and Open Graph tags.
- **Visual Results:** Automatically fetches and displays thumbnails from blog posts.
- **Responsive Design:** Optimized for both desktop and mobile devices using Bootstrap.
- **Google Analytics 4:** Integrated support for traffic tracking.

---

## 🖥️ Tech Stack

| Technology | Description |
| :--- | :--- |
| **Flask** | A lightweight web framework for Python (v3.9). |
| **Redis** | Caches parsed API responses for read-heavy workloads. |
| **Cloud Run Service** | Hosts the user-facing web application (Serverless). |
| **Cloud Run Jobs** | Runs the background task (`cache_warmer.py`) to fetch and parse Hatena Blog data. |

---

## 🚀 Release & Update Process

Follow these steps to deploy the application or update it after code changes.

### **Step 1: Set Environment Variables**
Set the following variables in your terminal. **You must modify the values below to match your Google Cloud environment and Hatena Blog credentials.**

```bash
# --- User Configuration (MODIFY THESE) ---
export GCR_PROJECT_ID="YOUR_GCP_PROJECT_ID"         # e.g., "starful-258005"
export VPC_CONNECTOR_NAME="YOUR_VPC_CONNECTOR_NAME" # e.g., "companydb-vpc-connector"
export REDIS_HOST="YOUR_REDIS_IP"                   # e.g., "10.167.33.139"
export HATENA_USERNAME="YOUR_HATENA_ID"             # e.g., "starful"
export HATENA_BLOG_ID="YOUR_BLOG_DOMAIN"            # e.g., "starful.biz"
export HATENA_API_KEY="YOUR_HATENA_API_KEY"         # Your AtomPub API Key
# -----------------------------------------

# --- System Configuration (No need to change) ---
export REGION="us-central1"
export SERVICE_NAME="companydb"
export SERVICE_IMAGE_TAG="gcr.io/${GCR_PROJECT_ID}/${SERVICE_NAME}:v1"
export JOB_NAME="companydb-warmer"
export JOB_IMAGE_TAG="gcr.io/${GCR_PROJECT_ID}/${JOB_NAME}:v1"
```

### **Step 2: Build the Web Application Image**
Run this when you modify `app.py` or files in `templates/`.

```bash
gcloud builds submit --tag ${SERVICE_IMAGE_TAG}
```

### **Step 3: Build the Cache Generation Job Image**
Run this when you modify `cache_warmer.py` or `hatena_client.py`.

> **⚠️ Important:** The `cloudbuild.yaml` file currently contains a hardcoded image name (`gcr.io/starful-258005/...`). Before running the command below, please open `cloudbuild.yaml` and update the image name to match your `${GCR_PROJECT_ID}`.

```bash
gcloud builds submit --config cloudbuild.yaml .
```

### **Step 4: Deploy/Update Cloud Run Service and Job**
Deploy the built images to Cloud Run. This step configures the service URL and links the background job.

```bash
# 1. Deploy the Web Service
gcloud run deploy ${SERVICE_NAME} \
  --image ${SERVICE_IMAGE_TAG} \
  --region ${REGION} \
  --platform managed \
  --cpu=2 \
  --memory=512Mi \
  --min-instances=1 \
  --max-instances=10 \
  --allow-unauthenticated \
  --set-env-vars="HATENA_USERNAME=${HATENA_USERNAME},HATENA_BLOG_ID=${HATENA_BLOG_ID},HATENA_API_KEY=${HATENA_API_KEY},REDIS_HOST=${REDIS_HOST},REDIS_PORT=6379" \
  --vpc-connector "${VPC_CONNECTOR_NAME}"

# 2. Capture the Service URL
export SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --platform managed --region ${REGION} --format 'value(status.url)')
echo "Deployed Service URL: ${SERVICE_URL}"

# 3. Update (or Create) the Cloud Run Job
# Note: We pass the SERVICE_URL as APP_DOMAIN so the job can generate correct thumbnail links.
gcloud run jobs update ${JOB_NAME} \
  --image ${JOB_IMAGE_TAG} \
  --region ${REGION} \
  --task-timeout=15m \
  --set-env-vars="APP_DOMAIN=${SERVICE_URL},HATENA_USERNAME=${HATENA_USERNAME},HATENA_BLOG_ID=${HATENA_BLOG_ID},HATENA_API_KEY=${HATENA_API_KEY},REDIS_HOST=${REDIS_HOST},REDIS_PORT=6379" \
  --vpc-connector "${VPC_CONNECTOR_NAME}"
```
*Note: If the job does not exist yet, replace `update` with `create` in the command above.*

### **Step 5: Generate the Redis Cache**
Execute the job to fetch blog posts and populate the Redis cache.

```bash
gcloud run jobs execute ${JOB_NAME} --region ${REGION} --wait
```

---

## 🛠️ Environment Variables

These variables are configured in Cloud Run.

| Variable Name | Description |
| :--- | :--- |
| `APP_DOMAIN` | The URL of the deployed service. Used by the Job to generate internal thumbnail links. |
| `HATENA_USERNAME` | Your Hatena ID. |
| `HATENA_BLOG_ID` | Your Blog domain (e.g., `example.hatenablog.com`). |
| `HATENA_API_KEY` | The AtomPub API Key found in your Hatena Blog settings. |
| `REDIS_HOST` | IP address of the Redis instance. |
| `REDIS_PORT` | Redis port (Default: `6379`). |
| `REDIS_DB` | Redis Database index (Default: `0`). |

---

## 📄 License

MIT License