---
name: cms-commit
description: Safe commit-and-push checklist for this CMS project. Use whenever the user asks to commit, push, or "commit แล้ว push" here — runs the tests (locally and CI-style from a clean checkout) and blocks secrets, databases, Excel/Word documents and DBA-only SQL from being committed.
---

# Commit / push อย่างปลอดภัย (CMS) -- แบบเดียวกับ travel-commit ของ travel_site

ทำตามลำดับ ถ้าขั้นไหนไม่ผ่าน **หยุด** แล้วบอกผู้ใช้ ห้ามข้ามขั้น

1. **ดูสถานะ**: `git status --short` และ `git branch --show-current`
   - ถ้าอยู่บน `main` ห้าม commit ตรง ให้ถามผู้ใช้ก่อนว่าจะใช้ branch ไหน
2. **ตรวจและรันเทสต์** (mock SQL Server/LDAP ทั้งหมด ไม่เขียนข้อมูลจริง):
   ```bash
   ./venv/Scripts/python.exe manage.py check && ./venv/Scripts/python.exe manage.py test meters 2>&1 | grep -E "^(Ran|OK|FAILED)"
   git diff --check
   ```
   ไม่ `OK` = หยุด แล้วแสดงเทสต์ที่ล้มให้ผู้ใช้ดู
3. **Stage แล้วตรวจไฟล์ต้องห้าม**:
   ```bash
   git add -A && git diff --cached --name-only | grep -E '(^|/)\.env$|\.sqlite3|\.db$|\.(xlsx|xls|docx)$|^sql/|^var/|^staticfiles/|^media/' || echo "CLEAN"
   ```
   ต้องได้ `CLEAN` ; ถ้ามีไฟล์โผล่ ให้ `git restore --staged <ไฟล์>` แล้วบอกผู้ใช้
   - ห้าม commit: `.env` (รหัส SQL Server/LDAP), `db.sqlite3`, เอกสาร Excel/Word, `sql/` (สคริปต์ DBA), `var/`, `staticfiles/`
   - สคริปต์ใน `deploy/` commit ได้ แต่ต้องยังเป็นค่า `CHANGE-ME` ไม่มี URL หรือค่าจริงของเครื่อง
4. **สแกนหารหัสผ่าน/คีย์ในโค้ดที่เปลี่ยน**:
   ```bash
   git diff --cached -U0 | grep -iE '^\+.*(password|passwd|pwd|secret|api[_-]?key|token)\s*[:=]\s*["'\''][^"'\'' ]{6,}' || echo "NO SECRETS"
   git diff --cached -U0 | grep -iE '^\+.*(ngrok|[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3})' || echo "NO HOSTS"
   ```
   ถ้าเจอ ให้แสดงบรรทัดนั้นให้ผู้ใช้ตัดสินก่อน (ห้ามแสดงค่ารหัสผ่านเต็ม)
5. **ถ้าแก้ไฟล์ใน `static/`** รัน `./venv/Scripts/python.exe manage.py collectstatic --noinput` แล้วเตือนผู้ใช้ให้ทำแบบเดียวกันบนเครื่อง Production
6. **Commit**: ข้อความภาษาอังกฤษ บรรทัดแรกสรุปสั้น ตามด้วยรายการสิ่งที่เปลี่ยน และลงท้ายด้วย
   `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
7. **ทดสอบแบบ CI ก่อน push** (จับไฟล์ที่ลืม add / พึ่ง `.env` หรือไฟล์ที่ถูก .gitignore): checkout commit นี้ลงโฟลเดอร์ชั่วคราว ไม่มี `.env` แล้วรันเทสต์ที่นั่น
   ```bash
   P="$(pwd)" && W="$TEMP/cms_ci_wt" && rm -rf "$W" && git worktree add -q --detach "$W" HEAD && \
   (cd "$W" && DJANGO_SECRET_KEY=ci-only-not-secret "$P/venv/Scripts/python.exe" manage.py test meters 2>&1 | grep -E "^(Ran|OK|FAILED)"); \
   git worktree remove --force "$W"
   ```
   ไม่ `OK` = หยุด บอกผู้ใช้ว่าไฟล์ไหนขาด
8. **Push** เฉพาะเมื่อผู้ใช้ขอ push: `git push origin <branch>` ห้าม force push
9. **ผล CI บน GitHub (Ubuntu)**: push แล้ว GitHub Actions (`.github/workflows/tests.yml`) รันเทสต์เองอัตโนมัติ
   - เครื่องนี้ไม่มี `gh` → อ่านผลเองไม่ได้ ให้ลิงก์ผู้ใช้ไปดู: https://github.com/Nowkasin/CMS/actions

## รายงาน
บอกเป็นภาษาไทย: เลข commit, branch, ผลเทสต์ (เครื่องนี้ + แบบ CI), ยืนยันว่าไฟล์ต้องห้ามไม่ได้ขึ้นไป และลิงก์ดูผล CI
