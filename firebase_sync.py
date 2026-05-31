"""
firebase_sync.py  —  Firebase / Firestore integration
Supports:
  - Local PC: reads serviceAccountKey.json from project folder
  - Railway (cloud): reads FIREBASE_CREDENTIALS_JSON environment variable
"""

import os
import json
import threading

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False

from config import (
    FIREBASE_CREDENTIALS_PATH,
    FIRESTORE_QUESTIONS_COLLECTION,
    FIRESTORE_APPROVED_USERS_COLLECTION,
)

_firebase_initialised = False


def init_firebase() -> bool:
    """
    Initialise Firebase Admin SDK.
    Tries environment variable first (Railway), then local JSON file (PC).
    Returns True on success.
    """
    global _firebase_initialised
    if _firebase_initialised:
        return True
    if not FIREBASE_AVAILABLE:
        print("[Firebase] firebase-admin not installed. "
              "Run: pip install firebase-admin")
        return False
    try:
        if not firebase_admin._apps:
            # ── Option 1: Railway environment variable ──
            creds_json = os.environ.get("FIREBASE_CREDENTIALS_JSON")
            if creds_json:
                creds_dict = json.loads(creds_json)
                cred = credentials.Certificate(creds_dict)
                print("[Firebase] Using credentials from environment variable.")

            # ── Option 2: Local file (PC) ──
            elif os.path.exists(FIREBASE_CREDENTIALS_PATH):
                cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
                print(f"[Firebase] Using credentials file: {FIREBASE_CREDENTIALS_PATH}")

            else:
                print("[Firebase] No credentials found.\n"
                      "  • PC:     Place serviceAccountKey.json in project folder.\n"
                      "  • Railway: Set FIREBASE_CREDENTIALS_JSON env variable.")
                return False

            firebase_admin.initialize_app(cred)
        _firebase_initialised = True
        return True
    except Exception as e:
        print(f"[Firebase] Initialisation failed: {e}")
        return False


def get_db():
    """Return Firestore client or None."""
    if not init_firebase():
        return None
    try:
        return firestore.client()
    except Exception as e:
        print(f"[Firebase] Firestore client error: {e}")
        return None


# ─────────────── Question Sync ────────────────────────────────────────

def sync_questions_to_firestore(class_: str, subject: str,
                                 questions: list, on_done=None):
    """
    Upload questions for a class+subject to Firestore (background thread).
    questions: list of dicts with keys: lesson, marks, question, answer
    on_done(success: bool, count: int) called when finished.
    """
    def _run():
        db = get_db()
        if db is None:
            if on_done:
                on_done(False, 0)
            return
        try:
            doc_id    = f"class{class_}_{subject.replace(' ', '_')}"
            col_ref   = db.collection(FIRESTORE_QUESTIONS_COLLECTION)
            doc_ref   = col_ref.document(doc_id)

            # Delete existing questions for this class+subject
            existing = doc_ref.collection("items").stream()
            del_batch = db.batch()
            for doc in existing:
                del_batch.delete(doc.reference)
            del_batch.commit()

            # Upload new questions in batches of 499
            items_ref    = doc_ref.collection("items")
            upload_batch = db.batch()
            count        = 0

            for i, q in enumerate(questions):
                ref = items_ref.document(str(i + 1))
                upload_batch.set(ref, {
                    "class":    class_,
                    "subject":  subject,
                    "lesson":   q.get("lesson", ""),
                    "marks":    q.get("marks", 1),
                    "question": q.get("question", ""),
                    "answer":   q.get("answer", ""),
                })
                count += 1
                if count % 499 == 0:
                    upload_batch.commit()
                    upload_batch = db.batch()

            upload_batch.commit()

            # Metadata document
            doc_ref.set({
                "class":          class_,
                "subject":        subject,
                "question_count": count,
                "last_updated":   firestore.SERVER_TIMESTAMP,
            })

            print(f"[Firebase] Synced {count} questions → {doc_id}")
            if on_done:
                on_done(True, count)

        except Exception as e:
            print(f"[Firebase] Sync error: {e}")
            if on_done:
                on_done(False, 0)

    threading.Thread(target=_run, daemon=True).start()


def fetch_questions_from_firestore(class_: str, subject: str,
                                    lesson: str = None) -> list:
    """
    Fetch questions from Firestore for a class+subject.
    Optionally filter by lesson name.
    Returns list of dicts.
    """
    db = get_db()
    if db is None:
        return []
    try:
        doc_id = f"class{class_}_{subject.replace(' ', '_')}"
        items  = (db.collection(FIRESTORE_QUESTIONS_COLLECTION)
                    .document(doc_id)
                    .collection("items")
                    .stream())
        results = []
        for doc in items:
            data = doc.to_dict()
            if lesson and data.get("lesson", "").lower() != lesson.lower():
                continue
            results.append(data)
        return results
    except Exception as e:
        print(f"[Firebase] Fetch error: {e}")
        return []


def save_generated_paper(class_: str, subject: str, lesson: str,
                          teacher: str, questions: list) -> str:
    """Save a generated paper record to Firestore. Returns doc ID."""
    db = get_db()
    if db is None:
        return ""
    try:
        doc_ref = db.collection("generated_papers").document()
        doc_ref.set({
            "class":        class_,
            "subject":      subject,
            "lesson":       lesson,
            "teacher":      teacher,
            "generated_at": firestore.SERVER_TIMESTAMP,
            "questions":    questions,
        })
        return doc_ref.id
    except Exception as e:
        print(f"[Firebase] Save paper error: {e}")
        return ""


# ─────────────── Approved Telegram Users ──────────────────────────────

def add_approved_telegram_user(chat_id: str, name: str,
                                username: str = "") -> bool:
    db = get_db()
    if db is None:
        return False
    try:
        db.collection(FIRESTORE_APPROVED_USERS_COLLECTION).document(
            str(chat_id)).set({
            "chat_id":  str(chat_id),
            "name":     name,
            "username": username,
            "approved": True,
            "added_at": firestore.SERVER_TIMESTAMP,
        })
        return True
    except Exception as e:
        print(f"[Firebase] Add approved user error: {e}")
        return False


def remove_approved_telegram_user(chat_id: str) -> bool:
    db = get_db()
    if db is None:
        return False
    try:
        db.collection(FIRESTORE_APPROVED_USERS_COLLECTION).document(
            str(chat_id)).delete()
        return True
    except Exception as e:
        print(f"[Firebase] Remove user error: {e}")
        return False


def get_approved_telegram_users() -> list:
    db = get_db()
    if db is None:
        return []
    try:
        docs = db.collection(FIRESTORE_APPROVED_USERS_COLLECTION).stream()
        return [doc.to_dict() for doc in docs]
    except Exception as e:
        print(f"[Firebase] Get users error: {e}")
        return []


def is_approved_user(chat_id: str) -> bool:
    db = get_db()
    if db is None:
        return False
    try:
        doc = (db.collection(FIRESTORE_APPROVED_USERS_COLLECTION)
                 .document(str(chat_id)).get())
        return doc.exists and doc.to_dict().get("approved", False)
    except Exception:
        return False
