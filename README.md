# companyDB – はてなブログ高速検索

**companyDB** は、はてなブログの記事を事前にキャッシュとして生成し、高速に検索・閲覧するためのウェブアプリケーションです。  
Cloud Run Jobsを利用して手動でキャッシュを生成・更新することで、常に高速な検索を実現します。  
Google Cloud Run + Flask + Redis (Google Cloud Memorystore) で構築されています。

![screenshot](static/companydb_logo.png)

---

## 🔍 機能一覧

- キーワードによるブログ記事の検索
- 検索結果のサムネイル付き一覧表示
- **バックグラウンドでのキャッシュ生成による高速検索**
- レスポンシブデザインによるモバイル対応

---

## 🖥️ 技術スタック

| 技術 | 内容 |
| :--- | :--- |
| **Flask** | Python製の軽量Webフレームワーク |
| **Redis** | APIレスポンスのキャッシュ (Memorystore for Redis) |
| **Cloud Run Service** | ユーザー向けWebアプリケーションの実行環境 |
| **Cloud Run Jobs** | キャッシュを生成するバックグラウンドタスクの実行 |

---

## 🚀 릴리스 및 업데이트 절차 (Release & Update Process)

코드를 수정한 후, 아래의 명령어를 **1번부터 5번까지 순서대로 실행**하면 새로운 버전이 빌드되고 배포되며, 캐시까지 자동으로 생성됩니다.

---

### **1단계: 환경 변수 설정**
먼저, 터미널에서 사용할 환경 변수를 설정합니다. **각 변수의 `""` 안에 자신의 환경에 맞는 값을 입력하세요.**

```bash
# --- 여기서부터 ---
export GCR_PROJECT_ID="starful-258005"
export REGION="us-central1"

# Cloud Run Service 관련 설정
export SERVICE_NAME="companydb"
export SERVICE_IMAGE_TAG="gcr.io/${GCR_PROJECT_ID}/${SERVICE_NAME}:v1"

# Cloud Run Job 관련 설정
export JOB_NAME="companydb-warmer"
export JOB_IMAGE_TAG="gcr.io/${GCR_PROJECT_ID}/${JOB_NAME}:v1"

# 인프라 관련 설정 (직접 입력)
export VPC_CONNECTOR_NAME="YOUR_VPC_CONNECTOR_NAME" # 예: "companydb-vpc-connector"
export REDIS_HOST="YOUR_REDIS_IP"                   # 예: "10.167.33.139"

# はてなブログ API 키 (직접 입력)
export HATENA_API_KEY="your_hatena_api_key"
# --- 여기까지 복사하여 터미널에 붙여넣기 ---
```

### **2단계: 웹 애플리케이션 이미지 빌드**
`app.py`나 `templates` 파일 등 웹 애플리케이션 관련 코드를 수정했을 때 필요한 단계입니다.

```bash
gcloud builds submit --tag ${SERVICE_IMAGE_TAG}
```

### **3단계: 캐시 생성 Job 이미지 빌드**
`cache_warmer.py`나 `hatena_client.py` 등 캐시 생성 관련 코드를 수정했을 때 필요한 단계입니다.

```bash
gcloud builds submit --config cloudbuild.yaml .
```

### **4단계: Cloud Run 서비스 및 Job 배포/업데이트**
새로 빌드한 이미지를 Cloud Run에 배포합니다. 이 과정에서 웹 서비스의 최종 URL이 결정됩니다.

```bash
# 1. 웹 서비스 배포 (URL 생성을 위해 먼저 실행)
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

# 2. 배포된 웹 서비스의 URL을 가져옴
export SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --platform managed --region ${REGION} --format 'value(status.url)')
echo "배포된 서비스 URL: ${SERVICE_URL}"

# 3. Cloud Run Job 업데이트 또는 생성 (SERVICE_URL을 APP_DOMAIN으로 사용)
#   (만약 Job이 없다면 'update' 대신 'create'를 사용하세요)
gcloud run jobs update ${JOB_NAME} \
  --image ${JOB_IMAGE_TAG} \
  --region ${REGION} \
  --task-timeout=15m \
  --set-env-vars="APP_DOMAIN=${SERVICE_URL},HATENA_USERNAME=starful,HATENA_BLOG_ID=starful.biz,HATENA_API_KEY=${HATENA_API_KEY},REDIS_HOST=${REDIS_HOST},REDIS_PORT=6379" \
  --vpc-connector "${VPC_CONNECTOR_NAME}"
```> **최초 배포 시:** `gcloud run jobs update` 명령어 대신 `create`를 사용해야 할 수 있습니다. 오류가 발생하면 `update`를 `create`로 변경하여 실행하세요.

### **5단계: Redis 캐시 생성 실행**
배포가 완료된 후, 아래 명령어를 실행하여 Redis에 최신 블로그 데이터를 저장합니다.

```bash
gcloud run jobs execute ${JOB_NAME} --region ${REGION} --wait
```

---
> 위 5단계를 모두 성공적으로 마치면, 새로운 버전의 릴리스가 완료됩니다.

---

## 🛠️ 환경 변수 설명

Cloud Run 서비스와 Job에 공통으로 설정되는 환경 변수입니다.

| 変数名 | 説明 |
| :--- | :--- |
| `APP_DOMAIN` | 데프로이된 Cloud Run 서비스의 완전한 URL (例: `https://companydb-xxxxx-uc.a.run.app`) |
| `HATENA_USERNAME` | はてなブログのユーザー名 (starful) |
| `HATENA_BLOG_ID` | はてなブログのID (starful.biz) |
| `HATENA_API_KEY` | はてなブログ AtomPub APIキー |
| `REDIS_HOST` | Memorystore for Redis のIPアドレス |
| `REDIS_PORT` | Redis のポート番号（デフォルト: `6379`） |

---

## 📄 라이센스

MIT License