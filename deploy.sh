#!/bin/bash
# CompanyDB deployment helper (okadmin Hub contract).

set -euo pipefail

GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
GCP_PROJECT_ID="${GCP_PROJECT_ID:-starful-258005}"
SITE_URL="${SITE_URL:-https://companydb.net}"
GITHUB_REPO="${GITHUB_REPO:-https://github.com/starful/companydb.net}"
COMMIT_MSG="chore: companydb content update $(date '+%Y-%m-%d %H:%M') (Admin Sync)"

MODE="full"
DO_GIT=false
DO_CLOUD_DEPLOY=false

print_step() {
    echo ""
    echo -e "${BOLD}${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}${CYAN}  $1${NC}"
    echo -e "${BOLD}${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}
print_ok()   { echo -e "${GREEN}  ✅ $1${NC}"; }
print_info() { echo -e "  ℹ️  $1"; }
print_warn() { echo -e "${YELLOW}  ⚠️  $1${NC}"; }

usage() {
    cat <<'EOF'
Usage: ./deploy.sh [MODE] [OPTIONS]

Modes (default: full)
  --full           Rebuild missing universe pages + index, then optional git/deploy
  --content-only   Rebuild missing universe pages + index
  --deploy-only    Trigger Cloud Build deploy only

Options
  --with-git       Commit and push generated changes
  --with-deploy    Trigger deploy after selected mode
  --help           Show this help

Environment overrides
  GCP_PROJECT_ID   Default: starful-258005
  SITE_URL         Default: Cloud Run URL
EOF
}

require_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Missing required command: $1" >&2
        exit 1
    fi
}

generate_content() {
    print_step "STEP A: Universe build (skip existing)"
    python3 script/build_company_page.py --universe
    print_ok "Universe build completed"
}

build_index() {
    print_step "STEP B: Index + compare"
    python3 script/build_company_page.py --index
    print_ok "Index/compare written"
}

git_push_changes() {
    print_step "STEP C: Commit and push changes"
    if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        print_warn "Not a git repo — skip push"
        return 0
    fi
    if ! git rev-parse HEAD >/dev/null 2>&1; then
        print_warn "No commits yet — skip push (create initial commit first)"
        return 0
    fi
    if ! git remote get-url origin >/dev/null 2>&1; then
        print_warn "No origin remote — skip push"
        return 0
    fi
    git add -A
    if git diff --cached --quiet; then
        print_info "No changes detected, skipping git push"
        return 0
    fi
    git commit -m "$COMMIT_MSG"
    branch="$(git rev-parse --abbrev-ref HEAD)"
    git push -u origin "$branch"
    print_ok "Git push completed → $GITHUB_REPO"
}

deploy_cloud_run() {
    print_step "STEP D: Trigger Cloud Build"
    gcloud builds submit --project "$GCP_PROJECT_ID"
    print_ok "Cloud Build deployment completed"
}

for arg in "$@"; do
    case "$arg" in
        --full) MODE="full" ;;
        --content-only) MODE="content-only" ;;
        --deploy-only) MODE="deploy-only" ;;
        --with-git) DO_GIT=true ;;
        --with-deploy) DO_CLOUD_DEPLOY=true ;;
        --help|-h) usage; exit 0 ;;
        *)
            echo "Unknown argument: $arg" >&2
            usage
            exit 1
            ;;
    esac
done

cd "$PROJECT_ROOT"
START_TIME=$SECONDS

print_info "Mode: $MODE"
print_info "Project: $GCP_PROJECT_ID"
print_info "Site: $SITE_URL"

require_cmd python3
require_cmd gcloud

case "$MODE" in
    full|content-only)
        generate_content
        build_index
        ;;
    deploy-only)
        DO_CLOUD_DEPLOY=true
        ;;
esac

if [ "$DO_GIT" = true ]; then
    require_cmd git
    git_push_changes
fi

if [ "$DO_CLOUD_DEPLOY" = true ]; then
    deploy_cloud_run
fi

ELAPSED=$((SECONDS - START_TIME))
echo -e "\n${BOLD}${GREEN}Done in $((ELAPSED/60))m $((ELAPSED%60))s${NC}"
echo -e "  🌐 Live: $SITE_URL"
