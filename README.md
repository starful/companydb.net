# companyDB – 法人番号検索サービス

**companyDB** は日本の法人番号データベースを検索・閲覧できるウェブアプリケーションです。  
Google Cloud Run + FastAPI + MySQL + Jinja2 により構築されています。

![screenshot](static/companydb_logo.png)

---

## 🔍 機能一覧

- 法人名による検索
- 検索結果のページネーション表示
- 法人詳細情報の閲覧
- すべてのテキストは自動的に「全角 → 半角」に変換

---

## 🖥️ 技術スタック

| 技術        | 内容                              |
|-------------|-----------------------------------|
| **FastAPI** | Python製の高速Webフレームワーク   |
| **Jinja2**  | HTMLテンプレートレンダリング       |
| **MySQL**   | 法人データ保存                     |
| **Cloud Run** | GCPのマネージドコンテナ実行環境 |
| **Bootstrap** | UIスタイリング                  |

---

## 🗂️ ディレクトリ構成

```
.
├── main.py                  # FastAPI アプリケーション本体
├── requirements.txt        # 依存パッケージ一覧
├── static/                 # 静的ファイル (ロゴなど)
│   └── companydb_logo.png
├── templates/              # HTMLテンプレート
│   ├── search.html         # 検索画面
│   ├── list.html           # 検索結果一覧
│   └── detail.html         # 法人詳細ページ
```

---

## 🚀 デプロイ手順（Cloud Run）

1. Docker イメージのビルドとアップロード：

```bash
gcloud builds submit --tag gcr.io/starful-258005/houjin-web
```

2. Cloud Run にデプロイ：

```bash
gcloud run deploy houjin-web \
  --image=gcr.io/starful-258005/houjin-web \
  --region=asia-northeast1 \
  --platform=managed \
  --cpu=2 \
  --memory=512Mi \
  --min-instances=1 \
  --max-instances=10 \
  --allow-unauthenticated \
  --service-account=houjin-web@starful-258005.iam.gserviceaccount.com \
  --add-cloudsql-instances=starful-258005:asia-northeast1:companydb \
  --update-env-vars DB_USER=companydb,DB_PASSWORD=xxxxxx,DB_NAME=companydb,INSTANCE_CONNECTION_NAME=starful-258005:asia-northeast1:companydb
```

---

## 🛠️ 環境変数

Cloud Run に設定する `.env` / 環境変数:

| 変数名                    | 説明                           |
|---------------------------|--------------------------------|
| `DB_USER`                 | MySQLユーザー名                 |
| `DB_PASSWORD`             | MySQLパスワード                |
| `DB_NAME`                 | データベース名                 |
| `INSTANCE_CONNECTION_NAME` | Cloud SQL の接続名（例：project:region:instance）|

---

## 📸 UI フロー

1. `/search` → 検索画面（Google風 UI）
2. `/list?keyword=XXX` → 法人名一覧ページ
3. `/corp/{法人番号}` → 詳細表示ページ

---

## 📄 ライセンス

MIT License