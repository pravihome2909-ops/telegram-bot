"""
telegram_bot.py  —  TN Exam Telegram Bot
Flow:
  /start → Class → Subject → Lessons (multi) → 
  How many 1-mark? → How many 2-mark? → 
  How many 3-mark? → How many 5-mark? → Confirm → PDF + DOCX sent
"""

import os
import logging
import random
from datetime import datetime

from telegram import (Update, ReplyKeyboardMarkup, ReplyKeyboardRemove,
                      InlineKeyboardMarkup, InlineKeyboardButton)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters,
    CallbackQueryHandler,
)

from config import TELEGRAM_BOT_TOKEN, ADMIN_CHAT_ID
from firebase_sync import (
    is_approved_user,
    fetch_questions_from_firestore,
    save_generated_paper,
    get_db,
    FIRESTORE_QUESTIONS_COLLECTION,
)
from pdf_generator  import (generate_question_paper_pdf,
                             generate_answer_key_pdf,
                             get_next_question_number,
                             save_next_question_number)
from docx_generator import (generate_question_paper_docx,
                              generate_answer_key_docx)

logging.basicConfig(
    format="%(asctime)s — %(levelname)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Conversation states ───────────────────────────────────────────────
(STATE_TEST_NAME, STATE_SCHOOL_NAME,
 STATE_CLASS, STATE_SUBJECT, STATE_LESSON,
 STATE_Q1, STATE_Q2, STATE_Q3, STATE_Q5,
 STATE_CONFIRM) = range(10)

# Lesson keyboard constants
SELECTED_PREFIX = "✅ "
DONE_LESSON     = "Done ✔ Confirm Lessons"
ALL_LESSONS     = "Select All Lessons"

# Quick-count buttons shown when asking "how many?"
COUNT_BUTTONS = ["0", "5", "10", "15", "20", "Custom"]


# ── Helpers ───────────────────────────────────────────────────────────

def _kb(options: list, cols: int = 2,
        one_time: bool = False) -> ReplyKeyboardMarkup:
    rows = [options[i:i+cols] for i in range(0, len(options), cols)]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True,
                                one_time_keyboard=one_time)


def _access_denied() -> str:
    return (
        "⛔ Access Denied\n\n"
        "You are not authorised to use this bot.\n"
        "Contact your school admin to get approved."
    )


def _get_subjects(class_: str) -> list:
    try:
        db = get_db()
        if db is None:
            return []
        docs = db.collection(FIRESTORE_QUESTIONS_COLLECTION).stream()
        return sorted({
            d.to_dict().get("subject", "")
            for d in docs
            if str(d.to_dict().get("class", "")) == str(class_)
        })
    except Exception as e:
        logger.error(f"_get_subjects error: {e}")
        return []


def _get_lessons(class_: str, subject: str) -> list:
    try:
        qs = fetch_questions_from_firestore(class_, subject)
        return sorted({q.get("lesson", "") for q in qs if q.get("lesson")})
    except Exception as e:
        logger.error(f"_get_lessons error: {e}")
        return []


def _get_available_count(questions: list, marks: int) -> int:
    return len([q for q in questions if q.get("marks") == marks])


def _lesson_keyboard(all_lessons: list,
                     selected: list) -> ReplyKeyboardMarkup:
    rows = []
    for i in range(0, len(all_lessons), 2):
        row = []
        for les in all_lessons[i:i+2]:
            row.append((SELECTED_PREFIX + les)
                       if les in selected else les)
        rows.append(row)
    rows.append([ALL_LESSONS, DONE_LESSON])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True,
                                one_time_keyboard=False)


def _count_keyboard() -> ReplyKeyboardMarkup:
    return _kb(COUNT_BUTTONS, cols=3, one_time=True)


# ── Admin approval helpers ────────────────────────────────────────────

async def _notify_admin_for_approval(update: Update,
                                      context: ContextTypes.DEFAULT_TYPE):
    """Send approval request to admin with Approve/Reject inline buttons."""
    if not ADMIN_CHAT_ID:
        return   # admin chat ID not configured

    user      = update.effective_user
    chat_id   = str(update.effective_chat.id)
    full_name = user.full_name
    username  = f"@{user.username}" if user.username else "no username"

    # Check if already pending (don't spam admin)
    try:
        db  = get_db()
        if db:
            pending = (db.collection("approval_requests")
                         .document(chat_id).get())
            if pending.exists:
                return   # already sent request before
            # Save pending request
            db.collection("approval_requests").document(chat_id).set({
                "chat_id":   chat_id,
                "name":      full_name,
                "username":  username,
                "status":    "pending",
            })
    except Exception as e:
        logger.error(f"Approval request save error: {e}")

    # Build inline keyboard
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "✅ Approve",
            callback_data=f"approve:{chat_id}:{full_name}"),
        InlineKeyboardButton(
            "❌ Reject",
            callback_data=f"reject:{chat_id}:{full_name}"),
    ]])

    msg = (
        "🔔 New Teacher Access Request\n\n"
        f"👤 Name     : {full_name}\n"
        f"🆔 Username : {username}\n"
        f"📱 Chat ID  : {chat_id}\n\n"
        "Tap Approve or Reject below:"
    )

    try:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=msg,
            reply_markup=keyboard,
        )
        logger.info(f"Approval request sent to admin for {full_name} ({chat_id})")
    except Exception as e:
        logger.error(f"Could not notify admin: {e}")


async def handle_approval_callback(update: Update,
                                    context: ContextTypes.DEFAULT_TYPE):
    """Handle admin tapping Approve or Reject button."""
    query = update.callback_query
    await query.answer()

    data        = query.data          # "approve:CHAT_ID:NAME" or "reject:..."
    parts       = data.split(":", 2)
    action      = parts[0]            # approve / reject
    teacher_id  = parts[1]            # teacher's chat ID
    teacher_name = parts[2] if len(parts) > 2 else "Teacher"

    if action == "approve":
        # Add to approved users in Firestore
        try:
            fn = None
            try:
                from firebase_sync import add_approved_telegram_user
                fn = add_approved_telegram_user
            except Exception:
                pass

            if fn:
                fn(teacher_id, teacher_name)

            # Update request status
            db = get_db()
            if db:
                db.collection("approval_requests").document(teacher_id).update(
                    {"status": "approved"})

        except Exception as e:
            logger.error(f"Approve error: {e}")
            await query.edit_message_text(
                query.message.text + "\n\n❌ Error: " + str(e))
            return

        # Update admin message
        await query.edit_message_text(
            query.message.text +
            f"\n\n✅ Approved by {update.effective_user.first_name}!")

        # Notify teacher
        try:
            await context.bot.send_message(
                chat_id=teacher_id,
                text=(
                    "✅ Your access has been approved!\n\n"
                    "Send /start to generate question papers."
                ),
            )
        except Exception as e:
            logger.error(f"Could not notify teacher: {e}")

    elif action == "reject":
        # Update request status
        try:
            db = get_db()
            if db:
                db.collection("approval_requests").document(teacher_id).update(
                    {"status": "rejected"})
        except Exception as e:
            logger.error(f"Reject update error: {e}")

        # Update admin message
        await query.edit_message_text(
            query.message.text +
            f"\n\n❌ Rejected by {update.effective_user.first_name}.")

        # Notify teacher
        try:
            await context.bot.send_message(
                chat_id=teacher_id,
                text=(
                    "❌ Your access request was not approved.\n"
                    "Please contact your school admin."
                ),
            )
        except Exception as e:
            logger.error(f"Could not notify teacher rejection: {e}")


async def cmd_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /pending — Admin command to list all pending approval requests.
    Only works for ADMIN_CHAT_ID.
    """
    chat_id = str(update.effective_chat.id)
    if ADMIN_CHAT_ID and chat_id != str(ADMIN_CHAT_ID):
        await update.message.reply_text("⛔ Admin only command.")
        return

    try:
        db = get_db()
        if db is None:
            await update.message.reply_text("Firebase not connected.")
            return

        docs = (db.collection("approval_requests")
                  .where("status", "==", "pending")
                  .stream())
        pending = [d.to_dict() for d in docs]
    except Exception as e:
        await update.message.reply_text("Error: " + str(e))
        return

    if not pending:
        await update.message.reply_text(
            "✅ No pending approval requests.")
        return

    for req in pending:
        tid   = req.get("chat_id",  "")
        tname = req.get("name",     "Unknown")
        tusr  = req.get("username", "")
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "✅ Approve",
                callback_data=f"approve:{tid}:{tname}"),
            InlineKeyboardButton(
                "❌ Reject",
                callback_data=f"reject:{tid}:{tname}"),
        ]])
        await update.message.reply_text(
            f"👤 {tname}  ({tusr})\nChat ID: {tid}",
            reply_markup=keyboard,
        )


async def cmd_approved_list(update: Update,
                             context: ContextTypes.DEFAULT_TYPE):
    """
    /approved — Admin command to list all approved teachers.
    """
    chat_id = str(update.effective_chat.id)
    if ADMIN_CHAT_ID and chat_id != str(ADMIN_CHAT_ID):
        await update.message.reply_text("⛔ Admin only command.")
        return

    try:
        from firebase_sync import get_approved_telegram_users
        users = get_approved_telegram_users()
    except Exception as e:
        await update.message.reply_text("Error: " + str(e))
        return

    if not users:
        await update.message.reply_text("No approved teachers yet.")
        return

    lines = ["✅ Approved Teachers:\n"]
    for i, u in enumerate(users, 1):
        lines.append(
            f"{i}. {u.get('name','')}  |  "
            f"ID: {u.get('chat_id','')}")

    await update.message.reply_text("\n".join(lines))


async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /remove CHAT_ID — Admin removes a teacher's access.
    """
    chat_id = str(update.effective_chat.id)
    if ADMIN_CHAT_ID and chat_id != str(ADMIN_CHAT_ID):
        await update.message.reply_text("⛔ Admin only command.")
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: /remove CHAT_ID\nExample: /remove 123456789")
        return

    target_id = args[0].strip()
    try:
        from firebase_sync import remove_approved_telegram_user
        ok = remove_approved_telegram_user(target_id)
        if ok:
            await update.message.reply_text(
                f"✅ Removed teacher {target_id} from approved list.")
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text="❌ Your bot access has been removed by admin.")
            except Exception:
                pass
        else:
            await update.message.reply_text(
                f"❌ Could not remove {target_id}.")
    except Exception as e:
        await update.message.reply_text("Error: " + str(e))


# ── /start ────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    name    = update.effective_user.full_name
    logger.info(f"/start  {name}  {chat_id}")

    if not is_approved_user(chat_id):
        # Notify admin with Approve/Reject buttons
        await _notify_admin_for_approval(update, context)
        await update.message.reply_text(
            "⏳ Your access request has been sent to the admin.\n\n"
            "You will be notified once approved.\n"
            "Send /start again after approval.",
        )
        return ConversationHandler.END

    context.user_data.clear()
    await update.message.reply_text(
        f"👋 Welcome, {name}!\n\n"
        "📝 Let's generate a question paper step by step.\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📋 Step 1 of 8\n"
        "Enter the Test Name\n"
        "(e.g. Unit Test 1, Mid Term, Quarterly)\n"
        "Or type  skip  to leave blank:",
        reply_markup=ReplyKeyboardRemove(),
    )
    return STATE_TEST_NAME


# ── Step 1 — Test Name ───────────────────────────────────────────────

async def get_test_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    context.user_data["test_name"] = "" if text.lower() == "skip" else text

    await update.message.reply_text(
        f"✅ Test: {context.user_data['test_name'] or '(none)'}\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🏫 Step 2 of 8\n"
        "Enter the School Name\n"
        "Or type  skip  to leave blank:",
        reply_markup=ReplyKeyboardRemove(),
    )
    return STATE_SCHOOL_NAME


# ── Step 2 — School Name ──────────────────────────────────────────────

async def get_school_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    context.user_data["school_name"] = "" if text.lower() == "skip" else text

    await update.message.reply_text(
        f"✅ School: {context.user_data['school_name'] or '(none)'}\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📚 Step 3 of 8\n"
        "Enter the Class (e.g. 10):",
        reply_markup=ReplyKeyboardRemove(),
    )
    return STATE_CLASS


# ── Step 3 — Class ────────────────────────────────────────────────────

async def get_class(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("Please enter a valid class.")
        return STATE_CLASS

    context.user_data["class"] = text
    subjects = _get_subjects(text)
    logger.info(f"Class={text!r}  subjects={subjects}")

    if subjects:
        await update.message.reply_text(
            f"✅ Class: {text}\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "📖 Step 2 of 6\n"
            "Select the Subject:",
            reply_markup=_kb(subjects, cols=3, one_time=True),
        )
    else:
        await update.message.reply_text(
            f"✅ Class: {text}\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "📖 Step 2 of 6\n"
            "Type the Subject name:",
            reply_markup=ReplyKeyboardRemove(),
        )
    return STATE_SUBJECT


# ── Step 2 — Subject ──────────────────────────────────────────────────

async def get_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("Please enter a valid subject.")
        return STATE_SUBJECT

    context.user_data["subject"]          = text
    context.user_data["selected_lessons"] = []

    lessons = _get_lessons(context.user_data["class"], text)
    context.user_data["all_lessons"] = lessons
    logger.info(f"Subject={text!r}  lessons={lessons}")

    if not lessons:
        await update.message.reply_text(
            f"✅ Subject: {text}\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "📂 Step 3 of 6\n"
            "Type the Lesson name:",
            reply_markup=ReplyKeyboardRemove(),
        )
        return STATE_LESSON

    kb = _lesson_keyboard(lessons, [])
    await update.message.reply_text(
        f"✅ Subject: {text}\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📂 Step 3 of 6 — Select Lessons\n\n"
        "Tap lessons to select (✅ = selected).\n"
        "You can select multiple lessons.\n"
        f"Tap  '{ALL_LESSONS}'  to select all.\n"
        f"Tap  '{DONE_LESSON}'  when done.",
        reply_markup=kb,
    )
    return STATE_LESSON


# ── Step 3 — Lesson multi-select ─────────────────────────────────────

async def get_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text     = update.message.text.strip()
    all_les  = context.user_data.get("all_lessons", [])
    selected = context.user_data.get("selected_lessons", [])

    # ── Manual entry (no lessons from cloud) ──
    if not all_les:
        context.user_data["selected_lessons"] = [text]
        context.user_data["lesson_display"]   = text
        return await _ask_q1(update, context)

    # ── Select All ──
    if text == ALL_LESSONS:
        context.user_data["selected_lessons"] = list(all_les)
        kb = _lesson_keyboard(all_les, all_les)
        await update.message.reply_text(
            f"✅ All {len(all_les)} lessons selected!\n"
            f"Tap  '{DONE_LESSON}'  to continue.",
            reply_markup=kb,
        )
        return STATE_LESSON

    # ── Done ──
    if text == DONE_LESSON:
        if not selected:
            kb = _lesson_keyboard(all_les, selected)
            await update.message.reply_text(
                "⚠️ Please select at least one lesson first.",
                reply_markup=kb,
            )
            return STATE_LESSON
        context.user_data["lesson_display"] = ", ".join(selected)
        # Pre-fetch questions NOW in background while teacher reads next screen
        import asyncio
        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, lambda: _prefetch_and_store(context))
        return await _ask_q1(update, context)

    # ── Toggle lesson ──
    clean = text.replace(SELECTED_PREFIX, "").strip()
    if clean in all_les:
        if clean in selected:
            selected.remove(clean)
        else:
            selected.append(clean)
        context.user_data["selected_lessons"] = selected
        kb = _lesson_keyboard(all_les, selected)
        n  = len(selected)
        await update.message.reply_text(
            f"{'✅' if n else '⬜'} {n} lesson(s) selected.\n"
            f"Tap more or tap  '{DONE_LESSON}'.",
            reply_markup=kb,
        )
        return STATE_LESSON

    kb = _lesson_keyboard(all_les, selected)
    await update.message.reply_text(
        "Please tap a lesson from the keyboard.", reply_markup=kb)
    return STATE_LESSON


# ── Fetch all questions for selected lessons ──────────────────────────

def _prefetch_and_store(context):
    """Background pre-fetch — runs while teacher is reading the marks screen."""
    if context.user_data.get("all_fetched"):
        return   # already fetched
    try:
        qs = _fetch_all(context)
        context.user_data["all_fetched"] = qs
        logger.info(f"Pre-fetch complete: {len(qs)} questions cached")
    except Exception as e:
        logger.error(f"Pre-fetch error: {e}")


def _fetch_all(context) -> list:
    """
    Fetch questions in ONE Firestore call (fetch entire subject),
    then filter locally by selected lessons.
    Much faster than one call per lesson.
    """
    cls      = context.user_data["class"]
    subj     = context.user_data["subject"]
    lessons  = set(context.user_data.get("selected_lessons", []))

    # Single Firestore call — no lesson filter (fetch all for subject)
    all_qs = fetch_questions_from_firestore(cls, subj)

    # Filter locally by selected lessons
    if lessons:
        all_qs = [q for q in all_qs
                  if q.get("lesson", "") in lessons]

    logger.info(f"Fetched {len(all_qs)} questions in 1 Firestore call "
                f"(lessons: {lessons})")
    return all_qs


# ── Step 4 — How many 1-mark? ─────────────────────────────────────────

async def _ask_q1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Use pre-fetched data if available, otherwise fetch now
    all_qs = context.user_data.get("all_fetched") or _fetch_all(context)
    context.user_data["all_fetched"] = all_qs

    # Load cross-session used questions (Feature 3)
    if not context.user_data.get("used_question_ids"):
        cls  = context.user_data.get("class","")
        subj = context.user_data.get("subject","")
        chat = str(update.effective_chat.id)
        prev_used = _load_used_questions(chat, cls, subj)
        context.user_data["used_question_ids"] = prev_used
        if prev_used:
            logger.info(f"Loaded {len(prev_used)} previously used questions")
    avail   = _get_available_count(all_qs, 1)
    display = context.user_data.get("lesson_display", "")
    logger.info(f"Lessons={display}  total_q={len(all_qs)}  1m_avail={avail}")

    context.user_data["q1"] = 0  # default

    if avail == 0:
        # Skip — no 1-mark questions available
        context.user_data["q1"] = 0
        return await _ask_q2(update, context)

    await update.message.reply_text(
        f"✅ Lessons: {display}\n\n"
        "━━━━━━━━━━━━━━━━\n"
        f"Step 4 of 6\n\n"
        f"1️⃣  How many 1-Mark questions?\n"
        f"Available: {avail}",
        reply_markup=_count_keyboard(),
    )
    return STATE_Q1


async def get_q1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text   = update.message.text.strip()
    all_qs = context.user_data.get("all_fetched", [])
    avail  = _get_available_count(all_qs, 1)
    n      = _parse_count(text, avail)

    if n is None:
        await update.message.reply_text(
            f"⚠️ Enter a number between 0 and {avail}.",
            reply_markup=_count_keyboard())
        return STATE_Q1

    context.user_data["q1"] = n
    return await _ask_q2(update, context)


# ── Step 5 — How many 2-mark? ─────────────────────────────────────────

async def _ask_q2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    all_qs = context.user_data.get("all_fetched", _fetch_all(context))
    avail  = _get_available_count(all_qs, 2)

    if avail == 0:
        context.user_data["q2"] = 0
        return await _ask_q3(update, context)

    await update.message.reply_text(
        "━━━━━━━━━━━━━━━━\n"
        f"Step 5 of 6\n\n"
        f"2️⃣  How many 2-Mark questions?\n"
        f"Available: {avail}",
        reply_markup=_count_keyboard(),
    )
    return STATE_Q2


async def get_q2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text   = update.message.text.strip()
    all_qs = context.user_data.get("all_fetched", [])
    avail  = _get_available_count(all_qs, 2)
    n      = _parse_count(text, avail)

    if n is None:
        await update.message.reply_text(
            f"⚠️ Enter a number between 0 and {avail}.",
            reply_markup=_count_keyboard())
        return STATE_Q2

    context.user_data["q2"] = n
    return await _ask_q3(update, context)


# ── Step 5 — How many 3-mark? ─────────────────────────────────────────

async def _ask_q3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    all_qs = context.user_data.get("all_fetched", _fetch_all(context))
    avail  = _get_available_count(all_qs, 3)

    if avail == 0:
        context.user_data["q3"] = 0
        return await _ask_q5(update, context)

    await update.message.reply_text(
        "━━━━━━━━━━━━━━━━\n"
        f"Step 5 of 6\n\n"
        f"3️⃣  How many 3-Mark questions?\n"
        f"Available: {avail}",
        reply_markup=_count_keyboard(),
    )
    return STATE_Q3


async def get_q3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text   = update.message.text.strip()
    all_qs = context.user_data.get("all_fetched", [])
    avail  = _get_available_count(all_qs, 3)
    n      = _parse_count(text, avail)

    if n is None:
        await update.message.reply_text(
            f"⚠️ Enter a number between 0 and {avail}.",
            reply_markup=_count_keyboard())
        return STATE_Q3

    context.user_data["q3"] = n
    return await _ask_q5(update, context)


# ── Step 6 — How many 5-mark? ─────────────────────────────────────────

async def _ask_q5(update: Update, context: ContextTypes.DEFAULT_TYPE):
    all_qs = context.user_data.get("all_fetched", _fetch_all(context))
    avail  = _get_available_count(all_qs, 5)

    if avail == 0:
        context.user_data["q5"] = 0
        return await _show_confirm(update, context)

    await update.message.reply_text(
        "━━━━━━━━━━━━━━━━\n"
        f"Step 6 of 6\n\n"
        f"5️⃣  How many 5-Mark questions?\n"
        f"Available: {avail}",
        reply_markup=_count_keyboard(),
    )
    return STATE_Q5


async def get_q5(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text   = update.message.text.strip()
    all_qs = context.user_data.get("all_fetched", [])
    avail  = _get_available_count(all_qs, 5)
    n      = _parse_count(text, avail)

    if n is None:
        await update.message.reply_text(
            f"⚠️ Enter a number between 0 and {avail}.",
            reply_markup=_count_keyboard())
        return STATE_Q5

    context.user_data["q5"] = n
    return await _show_confirm(update, context)


# ── Confirm ───────────────────────────────────────────────────────────

def _parse_count(text: str, available: int):
    """
    Parse count input. Returns int or None if invalid.
    Accepts numeric strings. 'Custom' triggers free input.
    """
    if text == "Custom":
        return None   # prompt again
    try:
        n = int(text)
        if 0 <= n <= available:
            return n
        return None
    except ValueError:
        return None


async def _show_confirm(update: Update,
                         context: ContextTypes.DEFAULT_TYPE):
    ud      = context.user_data
    q1      = ud.get("q1", 0)
    q2      = ud.get("q2", 0)
    q3      = ud.get("q3", 0)
    q5      = ud.get("q5", 0)
    display = ud.get("lesson_display", "")

    if q1 + q2 + q3 + q5 == 0:
        await update.message.reply_text(
            "⚠️ You selected 0 questions for all marks.\n"
            "Please enter at least 1 question.\n"
            "Send /start to begin again.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationHandler.END

    total = q1*1 + q2*2 + q3*3 + q5*5

    # Correct marks using TN board pattern
    m1_score = q1 * 1
    m2_score = min(q2, 7) * 2
    m3_score = min(q3, 7) * 3
    m5_score = q5 * 5
    total    = m1_score + m2_score + m3_score + m5_score

    test_nm   = ud.get("test_name",   "")
    school_nm = ud.get("school_name", "")
    hdr_line  = ""
    if test_nm or school_nm:
        hdr_line = (f"📋 Test    : {test_nm or '—'}\n"
                    f"🏫 School  : {school_nm or '—'}\n")

    await update.message.reply_text(
        "━━━━━━━━━━━━━━━━\n"
        "📝 Review your paper:\n\n"
        + hdr_line +
        f"📚 Class    : {ud['class']}\n"
        f"📖 Subject  : {ud['subject']}\n"
        f"📂 Lessons  : {display}\n\n"
        f"1️⃣  1-Mark   : {q1} Qs  × 1  = {m1_score} marks\n"
        f"2️⃣  2-Mark   : {q2} Qs  (ans 7) × 2  = {m2_score} marks\n"
        f"3️⃣  3-Mark   : {q3} Qs  (ans 7) × 3  = {m3_score} marks\n"
        f"5️⃣  5-Mark   : {q5} pairs × 5  = {m5_score} marks\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📊 Total     : {total} marks\n\n"
        "You will receive both PDF and Word files.\n"
        "Generate now?",
        reply_markup=_kb(["✅ Yes, Generate!", "❌ Cancel"],
                          cols=2, one_time=True),
    )
    return STATE_CONFIRM


# ── Generate & Send ───────────────────────────────────────────────────

async def confirm_generate(update: Update,
                            context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if "Cancel" in text:
        await update.message.reply_text(
            "❌ Cancelled. Send /start to begin again.",
            reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    ud      = context.user_data
    class_  = ud["class"]
    subject = ud["subject"]
    display = ud.get("lesson_display", "")
    q1      = ud.get("q1", 0)
    q2      = ud.get("q2", 0)
    q3      = ud.get("q3", 0)
    q5      = ud.get("q5", 0)
    teacher = update.effective_user.full_name
    chat_id = str(update.effective_chat.id)

    # ── Numbering continuity (Feature 2) ──
    start_number = get_next_question_number(chat_id, class_, subject)
    if start_number > 1:
        await update.message.reply_text(
            f"ℹ️ Continuing from Question No. {start_number}\n"
            f"(Previous papers: {start_number-1} questions used)\n"
            f"Send /reset_numbers to restart from Q.1",
            reply_markup=ReplyKeyboardRemove(),
        )

    await update.message.reply_text(
        "⏳ Generating PDF and Word files...\nPlease wait.",
        reply_markup=ReplyKeyboardRemove(),
    )

    all_qs = ud.get("all_fetched", [])

    # ── Smart unique random picking (mirrors exam_engine.py logic) ──
    # Tracks questions used in this session to avoid repeats
    used_ids = ud.setdefault("used_question_ids", set())

    def _safe_sample(population: list, k: int) -> list:
        """
        Exact copy of exam_engine safe_sample logic:
        - Never repeats a question within this session
        - Falls back to full pool if not enough unused questions
        - Uses random.sample() — no in-place mutation
        """
        if k <= 0:
            return []

        # Prefer questions not yet used this session
        unused = [q for q in population
                  if q.get("question", "") not in used_ids]

        if len(unused) >= k:
            picked = random.sample(unused, k)
        elif len(population) >= k:
            # Not enough unused — use full pool but still randomise
            logger.info(f"Not enough unused questions (need {k}, "
                        f"unused={len(unused)}, total={len(population)}) "
                        f"— using full pool")
            picked = random.sample(population, k)
        else:
            # Fewer available than requested — take all
            logger.info(f"Fewer questions than requested "
                        f"(need {k}, have {len(population)}) — taking all")
            picked = random.sample(population, len(population))

        # Record used question texts in session
        for q in picked:
            used_ids.add(q.get("question", ""))

        return picked

    def _pick_by_marks(mark: int, count: int) -> list:
        pool = [q for q in all_qs if q.get("marks") == mark]
        return _safe_sample(pool, count)

    def _pick_either_or(count: int) -> list:
        """
        5-mark Either/Or pairs — mirrors exam_engine Part D logic:
        fetch double the count to form pairs (Qa OR Qb).
        Returns flat list; pdf/docx generators pair them up.
        """
        pool = [q for q in all_qs if q.get("marks") == 5]
        # Need count*2 questions for count pairs
        return _safe_sample(pool, count * 2)

    part_a = _pick_by_marks(1, q1)   # 1-mark: exact count
    part_b = _pick_by_marks(2, q2)   # 2-mark: exact count
    part_c = _pick_by_marks(3, q3)   # 3-mark: exact count
    part_d = _pick_either_or(q5)     # 5-mark: double for Either/Or pairs

    logger.info(f"Picked: 1M={len(part_a)} 2M={len(part_b)} "
                f"3M={len(part_c)} 5M_pool={len(part_d)} pairs={len(part_d)//2}")

    # Combine for generators (part_d passed separately for Either/Or layout)
    final = part_a + part_b + part_c + part_d

    if not final:
        await update.message.reply_text(
            "⚠️ No questions available. "
            "Ask admin to sync questions to Firebase.\n"
            "Send /start to retry.")
        return ConversationHandler.END

    actual_q5_pairs = len(part_d) // 2

    # TN board pattern: 2-mark → students answer 7 only, 3-mark → students answer 7 only
    def _scored(mark, count):
        if mark == 1:  return count * 1
        elif mark == 2: return min(count, 7) * 2
        elif mark == 3: return min(count, 7) * 3
        elif mark == 5: return actual_q5_pairs * 5
        return count * mark

    total_marks = (_scored(1, len(part_a)) + _scored(2, len(part_b)) +
                   _scored(3, len(part_c)) + actual_q5_pairs * 5)

    test_name   = ud.get("test_name",   "")
    school_name = ud.get("school_name", "")

    # ── Generate PDF + DOCX in parallel (2x faster) ──
    import asyncio
    import concurrent.futures

    loop = asyncio.get_event_loop()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)

    pdf_future  = loop.run_in_executor(
        executor,
        lambda: generate_question_paper_pdf(
            class_, subject, display, final,
            teacher_name=teacher, part_d=part_d,
            test_name=test_name, school_name=school_name))

    docx_future = loop.run_in_executor(
        executor,
        lambda: generate_question_paper_docx(
            class_, subject, display, final,
            teacher_name=teacher, part_d=part_d,
            test_name=test_name, school_name=school_name))

    # Wait for both to finish simultaneously
    pdf_path, docx_path = await asyncio.gather(pdf_future, docx_future)

    # ── Save to Firestore ──
    save_generated_paper(
        class_, subject, display, teacher,
        [{"question": q["question"], "marks": q["marks"]}
         for q in final],
    )

    # ── Log usage to Excel + Drive ──
    # log_paper_generation(
    #     teacher_name = teacher,
    #     chat_id      = str(update.effective_chat.id),
    #     class_       = class_,
    #     subject      = subject,
    #     lessons      = display,
    #     q1           = len(part_a),
    #     q2           = len(part_b),
    #     q3           = len(part_c),
    #     q5_pairs     = actual_q5_pairs,
    #     total_marks  = total_marks,
    # )

    actual_pairs_display = actual_q5_pairs if actual_q5_pairs > 0 else 0
    total_q_display = len(part_a) + len(part_b) + len(part_c) + actual_pairs_display

    caption = (
        f"📄 Question Paper\n\n"
        f"Class    : {class_}\n"
        f"Subject  : {subject}\n"
        f"Lessons  : {display}\n"
        f"1M = {len(part_a)} Qs  |  "
        f"2M = {len(part_b)} Qs  |  "
        f"3M = {len(part_c)} Qs  |  "
        f"5M = {actual_pairs_display} pairs\n"
        f"Total    : {total_q_display} questions  |  {total_marks} marks\n"
        f"Time     : {datetime.now().strftime('%d-%m-%Y %I:%M %p')}"
    )

    # ── Send PDF ──
    if pdf_path and os.path.exists(pdf_path):
        with open(pdf_path, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=os.path.basename(pdf_path),
                caption=caption + "\n\n📕 PDF Version",
            )
    else:
        await update.message.reply_text("⚠️ PDF generation failed.")

    # ── Send DOCX ──
    if docx_path and os.path.exists(docx_path):
        with open(docx_path, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=os.path.basename(docx_path),
                caption="📘 Word (.docx) Version — Edit as needed",
            )
    else:
        await update.message.reply_text("⚠️ Word file generation failed.")

    await update.message.reply_text(
        "✅ Done! Both files sent successfully.\n"
        "Send /start to generate another paper.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


# ── Cross-session deduplication helpers ──────────────────────────────

def _save_used_questions(chat_id: str, class_: str,
                          subject: str, used_ids: set):
    """Save used question texts to Firestore for cross-session dedup."""
    if not used_ids:
        return
    try:
        db = get_db()
        if db is None:
            return
        key = f"{chat_id}_{class_}_{subject.replace(' ','_')}"
        doc_ref = db.collection("used_questions").document(key)
        existing = doc_ref.get()
        prev = set(existing.to_dict().get("questions", []))                if existing.exists else set()
        combined = list(prev | used_ids)[:500]  # cap at 500
        doc_ref.set({"questions": combined}, merge=True)
    except Exception as e:
        logger.error(f"Save used questions error: {e}")


def _load_used_questions(chat_id: str, class_: str,
                          subject: str) -> set:
    """Load previously used question texts from Firestore."""
    try:
        db = get_db()
        if db is None:
            return set()
        key = f"{chat_id}_{class_}_{subject.replace(' ','_')}"
        doc = db.collection("used_questions").document(key).get()
        if doc.exists:
            return set(doc.to_dict().get("questions", []))
        return set()
    except Exception:
        return set()


# ── /cancel & /help ───────────────────────────────────────────────────

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ Cancelled. Send /start to begin again.",
        reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_approved_user(str(update.effective_chat.id)):
        await update.message.reply_text(_access_denied())
        return
    await update.message.reply_text(
        "📖 TN Exam Bot — Help\n\n"
        "Commands:\n"
        "  /start  — Generate a question paper\n"
        "  /cancel — Cancel current operation\n"
        "  /help   — Show this message\n\n"
        "Steps:\n"
        "  1. Enter Class\n"
        "  2. Select Subject\n"
        "  3. Select one or more Lessons\n"
        "  4. How many 1-mark questions?\n"
        "  5. How many 2-mark questions?\n"
        "  6. How many 3-mark questions?\n"
        "  7. How many 5-mark questions?\n"
        "  8. Confirm → PDF + Word sent!\n\n"
        "Tip: If no questions available for a mark,\n"
        "that step is skipped automatically."
    )


# ── Main ──────────────────────────────────────────────────────────────

async def cmd_reset_numbers(update: Update,
                             context: ContextTypes.DEFAULT_TYPE):
    """/reset_numbers — Reset question numbering to 1 for current class+subject."""
    chat_id = str(update.effective_chat.id)
    if not is_approved_user(chat_id):
        await update.message.reply_text(_access_denied())
        return
    # Ask which class+subject to reset
    await update.message.reply_text(
        "🔄 Reset Question Numbering\n\n"
        "Reply with:  CLASS SUBJECT\n"
        "Example:  10 Science\n\n"
        "Or send  ALL  to reset everything.",
    )
    context.user_data["awaiting_reset"] = True


async def cmd_status(update: Update,
                     context: ContextTypes.DEFAULT_TYPE):
    """/status — Show available question counts for teacher's class+subject."""
    chat_id = str(update.effective_chat.id)
    if not is_approved_user(chat_id):
        await update.message.reply_text(_access_denied())
        return

    await update.message.reply_text(
        "📊 Status Check\n\n"
        "Send me:  CLASS SUBJECT\n"
        "Example:  10 Science\n\n"
        "I'll show how many questions are available.",
    )
    context.user_data["awaiting_status"] = True


async def handle_text_commands(update: Update,
                                context: ContextTypes.DEFAULT_TYPE):
    """Handle free-text replies for /status and /reset_numbers."""
    text    = update.message.text.strip()
    chat_id = str(update.effective_chat.id)

    if context.user_data.get("awaiting_status"):
        context.user_data.pop("awaiting_status")
        parts = text.split(None, 1)
        if len(parts) < 2:
            await update.message.reply_text(
                "Format: CLASS SUBJECT\nExample: 10 Science")
            return
        cls, subj = parts[0], parts[1]
        all_qs = fetch_questions_from_firestore(cls, subj)
        used   = _load_used_questions(chat_id, cls, subj)
        c1 = len([q for q in all_qs if q.get("marks")==1])
        c2 = len([q for q in all_qs if q.get("marks")==2])
        c3 = len([q for q in all_qs if q.get("marks")==3])
        c5 = len([q for q in all_qs if q.get("marks")==5])
        u1 = len([q for q in all_qs if q.get("marks")==1
                  and q.get("question","") in used])
        u2 = len([q for q in all_qs if q.get("marks")==2
                  and q.get("question","") in used])
        u3 = len([q for q in all_qs if q.get("marks")==3
                  and q.get("question","") in used])
        u5 = len([q for q in all_qs if q.get("marks")==5
                  and q.get("question","") in used])
        next_num = get_next_question_number(chat_id, cls, subj)
        await update.message.reply_text(
            f"📊 Class {cls} — {subj}\n\n"
            f"1-Mark : {c1} total  |  {c1-u1} unused  |  {u1} used\n"
            f"2-Mark : {c2} total  |  {c2-u2} unused  |  {u2} used\n"
            f"3-Mark : {c3} total  |  {c3-u3} unused  |  {u3} used\n"
            f"5-Mark : {c5} total  |  {c5-u5} unused  |  {u5} used\n\n"
            f"Next question number: {next_num}"
        )
        return

    if context.user_data.get("awaiting_reset"):
        context.user_data.pop("awaiting_reset")
        chat_id_str = str(update.effective_chat.id)
        if text.upper() == "ALL":
            try:
                db = get_db()
                if db:
                    docs = (db.collection("teacher_paper_history")
                              .where("__name__", ">=", chat_id_str)
                              .stream())
                    for d in docs:
                        d.reference.delete()
                    docs2 = (db.collection("used_questions")
                               .where("__name__", ">=", chat_id_str)
                               .stream())
                    for d in docs2:
                        d.reference.delete()
            except Exception as e:
                logger.error(f"Reset all error: {e}")
            await update.message.reply_text(
                "✅ All question numbering reset to Q.1\n"
                "All used question history cleared.")
        else:
            parts = text.split(None, 1)
            if len(parts) < 2:
                await update.message.reply_text(
                    "Format: CLASS SUBJECT or ALL")
                return
            cls, subj = parts[0], parts[1]
            save_next_question_number(chat_id_str, cls, subj, 1)
            try:
                db = get_db()
                if db:
                    key = f"{chat_id_str}_{cls}_{subj.replace(' ','_')}"
                    db.collection("used_questions").document(key).delete()
            except Exception:
                pass
            await update.message.reply_text(
                f"✅ Reset Class {cls} — {subj}\n"
                "Numbering starts from Q.1 next time.\n"
                "All used question history cleared.")
        return


def main():
    if TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("ERROR: Set TELEGRAM_BOT_TOKEN!")
        return

    logger.info("Starting TN Exam Bot...")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            STATE_TEST_NAME:   [MessageHandler(filters.TEXT & ~filters.COMMAND, get_test_name)],
            STATE_SCHOOL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_school_name)],
            STATE_CLASS:       [MessageHandler(filters.TEXT & ~filters.COMMAND, get_class)],
            STATE_SUBJECT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, get_subject)],
            STATE_LESSON:   [MessageHandler(filters.TEXT & ~filters.COMMAND, get_lesson)],
            STATE_Q1:       [MessageHandler(filters.TEXT & ~filters.COMMAND, get_q1)],
            STATE_Q2:       [MessageHandler(filters.TEXT & ~filters.COMMAND, get_q2)],
            STATE_Q3:       [MessageHandler(filters.TEXT & ~filters.COMMAND, get_q3)],
            STATE_Q5:       [MessageHandler(filters.TEXT & ~filters.COMMAND, get_q5)],
            STATE_CONFIRM:  [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_generate)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("help",          help_cmd))
    app.add_handler(CommandHandler("pending",        cmd_pending))
    app.add_handler(CommandHandler("approved",       cmd_approved_list))
    app.add_handler(CommandHandler("remove",         cmd_remove))
    app.add_handler(CommandHandler("reset_numbers",  cmd_reset_numbers))
    app.add_handler(CommandHandler("status",         cmd_status))
    app.add_handler(CallbackQueryHandler(handle_approval_callback,
                                          pattern="^(approve|reject):"))
    # Handle free-text replies for /status and /reset_numbers
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_text_commands))

    print("TN Exam Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
