# companyDB – High-Speed Hatena Blog Search

**companyDB** is a web application designed for high-speed searching and browsing of Hatena Blog articles. It achieves its speed by pre-generating a search cache.

Caching is handled by a Cloud Run Job that you can trigger manually. The application is built with Google Cloud Run, Flask, and Redis (Google Cloud Memorystore).

![screenshot](static/companydb_logo.png)

---

## 🔍 Features

- Keyword search for blog articles.
- Search results displayed with thumbnails.
- **Fast search speeds powered by background cache generation.**
- Responsive design for mobile compatibility.

---

## 🖥️ Tech Stack

| Technology | Description |
| :--- | :--- |
| **Flask** | A lightweight web framework for Python. |
| **Redis** | Caches API responses (using Memorystore for Redis). |
| **Cloud Run Service** | Execution environment for the user-facing web application. |
| **Cloud Run Jobs** | Runs the background task that generates the cache. |

---

## 🚀 Release & Update Process

After modifying the code, run the following commands from Step 1 to Step 5 in order. This will build and deploy the new version, and generate the cache.

---

### **Step 1: Set Environment Variables**
First, set the following environment variables in your terminal. **You must replace the placeholder values in the first three variables with your own.**

```bash
# --- Start here ---
# ▼▼▼▼▼ Modify the values for the 3 variables below to match your environment ▼▼▼▼▼
export VPC_CONNECTOR_NAME="YOUR_VPC_CONNECTOR_NAME" # e.g., "companydb-vpc-connector"
export REDIS_HOST="YOUR_REDIS_IP"                   # e.g., "10.167.33.139"
export HATENA_API_KEY="your_hatena_api_key"         # Your actual Hatena API key
# ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

# --- You do not need to modify the values below ---
export GCR_PROJECT_ID="starful-258005"
export REGION="us-central1"
export SERVICE_NAME="companydb"
export SERVICE_IMAGE_TAG="gcr.io/${GCR_PROJECT_ID}/${SERVICE_NAME}:v1"
export JOB_NAME="companydb-warmer"
export JOB_IMAGE_TAG="gcr.io/${GCR_PROJECT_ID}/${JOB_NAME}:v1"
# --- Copy this entire block and paste it into your terminal ---
```

### **Step 2: Build the Web Application Image**
This step is necessary when you modify web application code, such as `app.py` or files in the `templates` directory.

```bash
gcloud builds submit --tag ${SERVICE_IMAGE_TAG}
```

### **Step 3: Build the Cache Generation Job Image**
This step is necessary when you modify cache generation code, such as `cache_warmer.py` or `hatena_client.py`.

```bash
gcloud builds submit --config cloudbuild.yaml .
```

### **Step 4: Deploy/Update the Cloud Run Service and Job**
Deploy the newly built images to Cloud Run. This process will determine the final URL for your web service.

```bash
# 1. Deploy the web service (run this first to generate the URL)
gcloud run deploy ${SERVICE_NAME} \
  --image ${SERVICE_IMAGE_TAG} \
  --region ${REGION} \
  --platform managed \
  --cpu=2 \
  --memory=512Mi \
  --min-instances=1 \
  --max-instances=10 \
  --allow-unauthenticated \
  --set-env-vars="HATENA_USERNAME=starful,HATENA_BLOG_ID=starful.biz,HATENA_API_KEY=${HATENA_API_KEY},REDIS_HOST=${REDIS_HOST},REDIS_PORT=6379" \
  --vpc-connector "${VPC_CONNECTOR_NAME}"

# 2. Get the URL of the deployed web service
export SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --platform managed --region ${REGION} --format 'value(status.url)')
echo "Deployed Service URL: ${SERVICE_URL}"

# 3. Update or create the Cloud Run Job (using SERVICE_URL as APP_DOMAIN)
#    (If the job doesn't exist, use 'create' instead of 'update')
gcloud run jobs update ${JOB_NAME} \
  --image ${JOB_IMAGE_TAG} \
  --region ${REGION} \
  --task-timeout=15m \
  --set-env-vars="APP_DOMAIN=${SERVICE_URL},HATENA_USERNAME=starful,HATENA_BLOG_ID=starful.biz,HATENA_API_KEY=${HATENA_API_KEY},REDIS_HOST=${REDIS_HOST},REDIS_PORT=6379" \
  --vpc-connector "${VPC_CONNECTOR_NAME}"
```
> **Note for initial deployment:** You might need to use `create` instead of `update` for the `gcloud run jobs` command if the job doesn't exist yet. If the `update` command fails, simply replace it with `create` and run it again.

### **Step 5: Generate the Redis Cache**
After the deployment is complete, run the following command to store the latest blog data in Redis.

```bash
gcloud run jobs execute ${JOB_NAME} --region ${REGION} --wait
```

---
> After successfully completing all 5 steps, the new version release is complete.

---

## 🛠️ Environment Variables Explained

These environment variables are set for both the Cloud Run Service and the Job.

| Variable Name | Description |
| :--- | :--- |
| `APP_DOMAIN` | The full URL of the deployed Cloud Run service (e.g., `https://companydb-xxxxx-uc.a.run.app`). |
| `HATENA_USERNAME` | Your Hatena Blog username (starful). |
| `HATENA_BLOG_ID` | Your Hatena Blog ID (starful.biz). |
| `HATENA_API_KEY` | Your Hatena Blog AtomPub API key. |
| `REDIS_HOST` | The IP address of your Memorystore for Redis instance. |
| `REDIS_PORT` | The port number for Redis (default: `6379`). |

---

## 📄 License

MIT License