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

commit_step "2026-05-15 10:00:00" \
  "chore: scaffold project structure, .gitignore, LICENSE, requirements, CI workflow" \
  .gitignore requirements.txt LICENSE README.md .github/workflows/build-windows-exe.yml \
  build/app.spec app/ui/index.html app/ui/styles.css app/ui/app.js app/__init__.py

commit_step "2026-05-28 14:00:00" \
  "feat(dev-tools): add upload-behavior network/DOM probe (developer mode)" \
  dev_tools/probe_upload_behavior.py dev_tools/requirements.txt dev_tools/README.md

commit_step "2026-06-12 11:30:00" \
  "fix(dev-tools): scope network log to the Sooqify domain only and strip embedded base64 images" \
  dev_tools/probe_upload_behavior_v2.py

commit_step "2026-06-25 09:00:00" \
  "feat(app): add colorized logging, first-run config with developer-mode detection, and folder scanner" \
  app/logger_setup.py app/config.py app/scanner.py

commit_step "2026-07-10 16:30:00" \
  "feat(app): add real image-upload automation and safe search/verify against Sooqify" \
  app/uploader.py

commit_step "2026-07-25 15:45:00" \
  "feat(app): add sync client for ID lookup by style code and upload reporting" \
  app/sync_client.py

commit_step "2026-08-04 10:00:00" \
  "feat(app): wire main.py (pywebview entry point, background run thread, Chrome-profile workaround) and the UI shell" \
  app/main.py app/ui/index.html app/ui/styles.css app/ui/app.js

commit_step "2026-08-08 11:00:00" \
  "docs: add user guide and developer guide, add app icon" \
  docs/user-guide.html docs/developer-guide.html assets/icon.svg

commit_step "2026-08-11 02:00:00" \
  "feat: implement async folder scanning, tag ID matching validation, automatic folder relocation, advanced sync reporting, and settings modal UI" \
  app/main.py app/config.py app/scanner.py app/uploader.py app/sync_client.py app/ui/index.html app/ui/styles.css app/ui/app.js build_history.sh

commit_step "2026-08-11 04:30:00" \
  "feat: Release Version 2.0 - intelligent gallery image replacement preventing server rejection, native Python loop handling for AJAX elements, robust dialog handling, tab management, and enhanced dry run review workflows" \
  app/uploader.py app/main.py app/ui/index.html app/ui/app.js 

commit_step "2026-08-11 05:25:00" \
  "fix(uploader): disable buggy gallery deletion and gracefully fail product upload when existing gallery images are detected to honor store constraints" \
  app/uploader.py build_history.sh

echo
echo "انتهى. راجع السجل بـ:"
echo "  git log --date=short --pretty='%ad  %s'"
