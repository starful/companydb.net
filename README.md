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

## 🛠️ 開発履歴（2025年7月）

### ✅ 1. 検索画面（`search.html`）
- モバイル対応のレスポンシブデザインを導入
- 入力時にローディングアニメーション（`#loading`）を表示、検索中は`footer`を非表示
- 入力が空の場合、フェードインエフェクトによるエラーメッセージを表示（`.error-message`）
- ロゴ画像をモバイル中央配置（`.logo { text-align: center; }`）
- `sessionStorage` を利用して履歴遷移時のローディング表示を抑制

### ✅ 2. 一覧画面（`list.html`）
- 表の最大幅を960pxに制限し、レスポンシブに対応
- 法人名クリック時、キーワード・ページ情報をURLパラメータとして保持
- `.halfwidth` クラスを対象とした「全角→半角」自動変換スクリプトを導入

### ✅ 3. 詳細画面（`detail.html`）
- 詳細表示テーブルの幅を720pxに制限し、モバイル最適化
- 一覧ページへの戻りリンクにキーワードとページ番号のパラメータを維持
- `.halfwidth` クラスの自動変換処理を適用

### ✅ その他共通仕様
- 全体フォント: `'Segoe UI', Tahoma, Geneva, Verdana, sans-serif`
- 背景色: `#f8f9fa`、ボタン色: `#1a73e8`（ホバー時は `#0c59cf`）
- 使用Bootstrapバージョン: v4.5.2

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
gcloud run deploy houjin-web   --image=gcr.io/starful-258005/houjin-web   --region=asia-northeast1   --platform=managed   --cpu=2   --memory=512Mi   --min-instances=1   --max-instances=10   --allow-unauthenticated   --service-account=houjin-web@starful-258005.iam.gserviceaccount.com   --add-cloudsql-instances=starful-258005:asia-northeast1:companydb   --update-env-vars DB_USER=companydb,DB_PASSWORD=xxxxxx,DB_NAME=companydb,INSTANCE_CONNECTION_NAME=starful-258005:asia-northeast1:companydb
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