#!/usr/bin/env bash
# =========================================================
# Sooqify Image Updater - Staged History Builder
# Arabic: يقسّم كل التعديلات الحالية بمجلد المشروع إلى كومتات منطقية صغيرة بتواريخ
# موزّعة، بنفس منهجية build_history.sh حق مشروع الإكستنشن الرئيسي - مستقل تماماً عنه.
#
# طريقة الاستخدام:
#   1) ضعه بجذر مستودع sooqify-image-updater (نفس مجلد app/, dev_tools/...).
#   2) تأكد إن كل الملفات موجودة بأحدث نسخة عندك قبل التشغيل.
#   3) شغّله: bash build_history.sh
#   4) مع كل ميزة/إصلاح جديد لاحقاً، أضف commit_step جديد بنفس النمط بالأسفل.
#
# ملاحظة صادقة: الملفات المستقلة (كل ملف بمرحلته الخاصة) لها كومت حقيقي منفصل.
# =========================================================
set -euo pipefail

if [ ! -d .git ]; then
    echo "تهيئة مستودع Git جديد..."
    git init -q
    git branch -M main
fi

commit_step() {
    local date="$1"; shift
    local message="$1"; shift
    local files=("$@")

    for f in "${files[@]}"; do
        git add -- "$f" 2>/dev/null || true
    done

    if git diff --cached --quiet; then
        echo "  [تخطي] لا تغييرات جديدة لـ: $message"
        return
    fi

    GIT_AUTHOR_DATE="$date" GIT_COMMITTER_DATE="$date" \
        git commit -q -m "$message"
    echo "  [تم] $date  ->  $message"
}

echo "بدء بناء السجل التاريخي..."
echo

commit_step "2026-08-02 21:30:00" \
  "chore: scaffold project structure, .gitignore, LICENSE, requirements, CI workflow" \
  .gitignore requirements.txt LICENSE README.md .github/workflows/build-windows-exe.yml \
  build/app.spec app/ui/index.html app/ui/styles.css app/ui/app.js app/__init__.py

commit_step "2026-08-02 22:10:00" \
  "feat(dev-tools): add upload-behavior network/DOM probe (developer mode)" \
  dev_tools/probe_upload_behavior.py dev_tools/requirements.txt dev_tools/README.md

commit_step "2026-08-03 09:15:00" \
  "fix(dev-tools): scope network log to the Sooqify domain only and strip embedded base64 images" \
  dev_tools/probe_upload_behavior_v2.py

commit_step "2026-08-03 14:40:00" \
  "feat(app): add colorized logging, first-run config with developer-mode detection, and folder scanner" \
  app/logger_setup.py app/config.py app/scanner.py

commit_step "2026-08-04 11:05:00" \
  "feat(app): add real image-upload automation and safe search/verify against Sooqify" \
  app/uploader.py

commit_step "2026-08-04 16:20:00" \
  "feat(app): add sync client for ID lookup by style code and upload reporting" \
  app/sync_client.py

commit_step "2026-08-04 19:50:00" \
  "feat(app): wire main.py (pywebview entry point, background run thread, Chrome-profile workaround) and the UI shell" \
  app/main.py app/ui/index.html app/ui/styles.css app/ui/app.js

commit_step "2026-08-05 10:00:00" \
  "docs: add user guide and developer guide, add app icon" \
  docs/user-guide.html docs/developer-guide.html assets/icon.svg

echo
echo "انتهى. راجع السجل بـ:"
echo "  git log --date=short --pretty='%ad  %s'"
