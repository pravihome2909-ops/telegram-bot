import os

# ─────────────────────────────────────────────────────────────────────
#  config.py  —  TN Exam Software
#  Edit this file before running the app.
#  For Railway deployment, set these as environment variables instead.
# ─────────────────────────────────────────────────────────────────────

# ── Telegram Bot ──────────────────────────────────────────────────────
# Get from @BotFather on Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8628752943:AAFE_pk6-dkPvs-pS3MICJBkk9n4vj3JO2M")

# ── Firebase ──────────────────────────────────────────────────────────
# Path to Firebase service account JSON (for local PC use)
FIREBASE_CREDENTIALS_PATH = os.getenv(
    "FIREBASE_CREDENTIALS_PATH", "serviceAccountKey.json"
)

# Your Firebase project ID (Firebase Console → Project Settings → General)
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "tnqp-9220d")

# Firestore collection names — do not change unless you know what you're doing
FIRESTORE_QUESTIONS_COLLECTION       = "questions"
FIRESTORE_PAPERS_COLLECTION          = "generated_papers"
FIRESTORE_APPROVED_USERS_COLLECTION  = "approved_telegram_users"

# ── School Info (printed on every PDF question paper) ─────────────────
SCHOOL_NAME    = os.getenv("SCHOOL_NAME",    "skv")
SCHOOL_ADDRESS = os.getenv("SCHOOL_ADDRESS", "Pappunayakkanpatti, Madurai")
EXAM_FOOTER    = "All the Best!"

# ── App Info ──────────────────────────────────────────────────────────
APP_NAME    = "TN Exam Software"
APP_VERSION = "2.0"
