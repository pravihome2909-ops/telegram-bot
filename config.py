import os

# ─────────────────────────────────────────────────────────────────────
#  config.py  —  TN Exam Software
#  Edit this file before running the app.
#  For Railway deployment, set these as environment variables instead.
# ─────────────────────────────────────────────────────────────────────

# ── Telegram Bot ──────────────────────────────────────────────────────
# Get from @BotFather on Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# Your personal Telegram Chat ID — get it from @userinfobot
# Admin receives approval requests and can use /pending /approved /remove
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")

# ── Firebase ──────────────────────────────────────────────────────────
# Path to Firebase service account JSON (for local PC use)
FIREBASE_CREDENTIALS_PATH = os.getenv(
    "FIREBASE_CREDENTIALS_PATH", "serviceAccountKey.json"
)

# Your Firebase project ID (Firebase Console → Project Settings → General)
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "your-firebase-project-id")

# Firestore collection names — do not change unless you know what you're doing
FIRESTORE_QUESTIONS_COLLECTION       = "questions"
FIRESTORE_PAPERS_COLLECTION          = "generated_papers"
FIRESTORE_APPROVED_USERS_COLLECTION  = "approved_telegram_users"

# ── School Info (printed on every PDF question paper) ─────────────────
SCHOOL_NAME    = os.getenv("SCHOOL_NAME",    "Tamil Nadu Government School")
SCHOOL_ADDRESS = os.getenv("SCHOOL_ADDRESS", "Your Town, District")
EXAM_FOOTER    = "All the Best!"

# ── Google Drive ──────────────────────────────────────────────────────
# Folder ID from Google Drive folder URL:
# https://drive.google.com/drive/folders/THIS_PART_IS_THE_ID
# Share this folder with your Firebase service account email.
GDRIVE_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID", "")

# ── App Info ──────────────────────────────────────────────────────────
APP_NAME    = "TN Exam Software"
APP_VERSION = "2.0"
