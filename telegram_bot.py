"""
telegram_bot.py  —  TN Exam Telegram Bot

Teacher conversation flow:
  /start → Class → Subject → Lesson → Marks type → Confirm → PDF sent

Run locally:
    python telegram_bot.py

Deploy to Railway:
    Push this file + requirements.txt + Procfile to GitHub repo.
    Set TELEGRAM_BOT_TOKEN and FIREBASE_CREDENTIALS_JSON as env vars on Railway.

Install deps:
    pip install python-telegram-bot==20.7 firebase-admin reportlab
"""

import os
import logging
import random
from datetime import datetime

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters,
)

from config import TELEGRAM_BOT_TOKEN
from firebase_sync import (
    is_approved_user,
    fetch_questions_from_firestore,
    save_generated_paper,
    get_db,
    FIRESTORE_QUESTIONS_COLLECTION,
)
from pdf_generator import generate_question_paper_pdf

# ── Logging ───────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s — %(levelname)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Conversation states ───────────────────────────────────────────────
(STATE_CLASS, STATE_SUBJECT, STATE_LESSON,
 STATE_MARKS_TYPE, STATE_CUSTOM_MARKS, STATE_CONFIRM) = range(6)

# ── Marks options ─────────────────────────────────────────────────────
MARKS_OPTIONS = {
    "1️⃣  1-Mark Only":  [1],
    "2️⃣  2-Mark Only":  [2],
    "3️⃣  3-Mark Only":  [3],
    "5️⃣  5-Mark Only":  [5],
    "🔀  Mixed (All)":   [1, 2, 3, 5],
    "⚙️  Custom":        "custom",
}


# ── Helpers ───────────────────────────────────────────────────────────

def _kb(options: list, cols: int = 2) -> ReplyKeyboardMarkup:
    rows = [options[i:i+cols] for i in range(0, len(options), cols)]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True,
                                one_time_keyboard=True)


def _access_denied() -> str:
    return (
        "⛔ *Access Denied*\n\n"
        "You are not authorised to use this bot.\n"
        "Please contact your school admin to get approved."
    )


def _get_subjects_for_class(class_: str) -> list:
    """Fetch distinct subjects for a class from Firestore."""
    try:
        db   = get_db()
        if db is None:
            return []
        docs = db.collection(FIRESTORE_QUESTIONS_COLLECTION).stream()
        return sorted({
            d.to_dict().get("subject", "")
            for d in docs
            if str(d.to_dict().get("class", "")) == str(class_)
        })
    except Exception:
        return []


def _get_lessons(class_: str, subject: str) -> list:
    try:
        qs = fetch_questions_from_firestore(class_, subject)
        return sorted({q.get("lesson", "") for q in qs if q.get("lesson")})
    except Exception:
        return []


# ── /start ────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    name    = update.effective_user.full_name

    # Print Chat ID to console so admin can approve the teacher
    print(f"[Bot] /start from {name}  |  Chat ID: {chat_id}")

    if not is_approved_user(chat_id):
        await update.message.reply_text(
            _access_denied()
        )
        return ConversationHandler.END

    context.user_data.clear()
    await update.message.reply_text(
        f"👋 Welcome, *{name}*!\n\n"
        "📝 I will help you generate a question paper step by step.\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📚 *Step 1 of 4*\n"
        "Please enter the *Class* \\(e\\.g\\. 10\\):",
        parse_mode="MarkdownV2",
        reply_markup=ReplyKeyboardRemove(),
    )
    return STATE_CLASS


# ── Step 1 — Class ────────────────────────────────────────────────────

async def get_class(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("⚠️ Please enter a valid class.")
        return STATE_CLASS

    context.user_data["class"] = text
    subjects = _get_subjects_for_class(text)

    if subjects:
        await update.message.reply_text(
            f"✅ Class: *{text}*\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "📖 *Step 2 of 4*\n"
            "Select or type the *Subject*:",
            parse_mode="Markdown",
            reply_markup=_kb(subjects, cols=3),
        )
    else:
        await update.message.reply_text(
            f"✅ Class: *{text}*\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "📖 *Step 2 of 4*\n"
            "Type the *Subject* name:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove(),
        )
    return STATE_SUBJECT


# ── Step 2 — Subject ──────────────────────────────────────────────────

async def get_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("⚠️ Please enter a valid subject.")
        return STATE_SUBJECT

    context.user_data["subject"] = text
    lessons = _get_lessons(context.user_data["class"], text)

    if lessons:
        await update.message.reply_text(
            f"✅ Subject: *{text}*\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "📂 *Step 3 of 4*\n"
            "Select or type the *Lesson*:",
            parse_mode="Markdown",
            reply_markup=_kb(lessons, cols=2),
        )
    else:
        await update.message.reply_text(
            f"✅ Subject: *{text}*\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "📂 *Step 3 of 4*\n"
            "Type the *Lesson* name or number:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove(),
        )
    return STATE_LESSON


# ── Step 3 — Lesson ───────────────────────────────────────────────────

async def get_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("⚠️ Please enter a valid lesson.")
        return STATE_LESSON

    context.user_data["lesson"] = text
    await update.message.reply_text(
        f"✅ Lesson: *{text}*\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🎯 *Step 4 of 4*\n"
        "Choose the *Marks type* for the paper:",
        parse_mode="Markdown",
        reply_markup=_kb(list(MARKS_OPTIONS.keys()), cols=2),
    )
    return STATE_MARKS_TYPE


# ── Step 4 — Marks type ───────────────────────────────────────────────

async def get_marks_type(update: Update,
                          context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    matched = None
    for label, val in MARKS_OPTIONS.items():
        if label == text:
            matched = val
            break

    if matched is None:
        await update.message.reply_text(
            "⚠️ Please choose one of the options:",
            reply_markup=_kb(list(MARKS_OPTIONS.keys()), cols=2))
        return STATE_MARKS_TYPE

    if matched == "custom":
        await update.message.reply_text(
            "⚙️ *Custom Marks*\n\n"
            "Enter mark values separated by commas.\n"
            "Example: `1,2,5`",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove(),
        )
        return STATE_CUSTOM_MARKS

    context.user_data["marks_filter"] = matched
    return await _show_confirm(update, context)


async def get_custom_marks(update: Update,
                            context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        marks = [int(m.strip()) for m in text.split(",") if m.strip()]
        valid = [m for m in marks if m in (1, 2, 3, 5)]
        if not valid:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "⚠️ Invalid. Enter values from 1, 2, 3, 5.\n"
            "Example: `1,3,5`", parse_mode="Markdown")
        return STATE_CUSTOM_MARKS

    context.user_data["marks_filter"] = valid
    return await _show_confirm(update, context)


async def _show_confirm(update: Update,
                         context: ContextTypes.DEFAULT_TYPE):
    ud        = context.user_data
    marks_str = ", ".join(str(m) for m in ud["marks_filter"])
    await update.message.reply_text(
        "━━━━━━━━━━━━━━━━\n"
        "✅ *Review your request:*\n\n"
        f"📚 Class   : *{ud['class']}*\n"
        f"📖 Subject : *{ud['subject']}*\n"
        f"📂 Lesson  : *{ud['lesson']}*\n"
        f"🎯 Marks   : *{marks_str}*\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "Shall I generate the question paper now?",
        parse_mode="Markdown",
        reply_markup=_kb(["✅ Yes, Generate!", "❌ Cancel"], cols=2),
    )
    return STATE_CONFIRM


# ── Step 5 — Generate ─────────────────────────────────────────────────

async def confirm_generate(update: Update,
                            context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if "Cancel" in text:
        await update.message.reply_text(
            "❌ Cancelled. Send /start to begin again.",
            reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    ud           = context.user_data
    class_       = ud["class"]
    subject      = ud["subject"]
    lesson       = ud["lesson"]
    marks_filter = ud["marks_filter"]
    teacher      = update.effective_user.full_name

    await update.message.reply_text(
        "⏳ Fetching questions from cloud and generating PDF...\n"
        "Please wait a moment.",
        reply_markup=ReplyKeyboardRemove(),
    )

    # Fetch from Firestore
    all_qs   = fetch_questions_from_firestore(class_, subject, lesson)
    filtered = [q for q in all_qs if q.get("marks") in marks_filter]

    if not filtered:
        await update.message.reply_text(
            f"⚠️ No questions found for:\n"
            f"Class {class_} → {subject} → {lesson}\n"
            f"Marks: {marks_filter}\n\n"
            "Please ask your admin to upload questions.\n"
            "Send /start to try again."
        )
        return ConversationHandler.END

    random.shuffle(filtered)

    # Generate PDF
    pdf_path = generate_question_paper_pdf(
        class_, subject, lesson, filtered,
        teacher_name=teacher,
    )

    if not pdf_path or not os.path.exists(pdf_path):
        await update.message.reply_text(
            "❌ PDF generation failed. Please contact your admin.")
        return ConversationHandler.END

    # Save paper record to Firestore
    save_generated_paper(
        class_, subject, lesson, teacher,
        [{"question": q["question"], "marks": q["marks"]}
         for q in filtered],
    )

    # Send PDF via Telegram
    total_marks = sum(q.get("marks", 1) for q in filtered)
    caption = (
        f"📄 *Question Paper Generated*\n\n"
        f"📚 Class    : {class_}\n"
        f"📖 Subject  : {subject}\n"
        f"📂 Lesson   : {lesson}\n"
        f"📊 Questions: {len(filtered)}  |  Total: {total_marks} marks\n"
        f"👩‍🏫 Teacher  : {teacher}\n"
        f"🕐 Time     : {datetime.now().strftime('%d-%m-%Y %I:%M %p')}"
    )

    with open(pdf_path, "rb") as pdf_file:
        await update.message.reply_document(
            document=pdf_file,
            filename=os.path.basename(pdf_path),
            caption=caption,
            parse_mode="Markdown",
        )

    await update.message.reply_text(
        "✅ Paper sent! Send /start to generate another.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


# ── /cancel ───────────────────────────────────────────────────────────

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ Cancelled. Send /start to begin again.",
        reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# ── /help ─────────────────────────────────────────────────────────────

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    print(f"[Bot] /help from {update.effective_user.full_name}  |  Chat ID: {chat_id}")

    if not is_approved_user(chat_id):
        await update.message.reply_text(
            _access_denied(), parse_mode="Markdown")
        return

    await update.message.reply_text(
        "📖 *TN Exam Bot — Help*\n\n"
        "Commands:\n"
        "  /start  — Generate a question paper\n"
        "  /cancel — Cancel current operation\n"
        "  /help   — Show this message\n\n"
        "Steps:\n"
        "  1️⃣  Enter Class\n"
        "  2️⃣  Select Subject\n"
        "  3️⃣  Select Lesson\n"
        "  4️⃣  Choose Marks type\n"
        "  5️⃣  Confirm → PDF sent to you!",
        parse_mode="Markdown",
    )


# ── Main ──────────────────────────────────────────────────────────────

def main():
    if TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌  ERROR: Set your TELEGRAM_BOT_TOKEN in config.py "
              "or as an environment variable before running!")
        return

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            STATE_CLASS:        [MessageHandler(filters.TEXT & ~filters.COMMAND, get_class)],
            STATE_SUBJECT:      [MessageHandler(filters.TEXT & ~filters.COMMAND, get_subject)],
            STATE_LESSON:       [MessageHandler(filters.TEXT & ~filters.COMMAND, get_lesson)],
            STATE_MARKS_TYPE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, get_marks_type)],
            STATE_CUSTOM_MARKS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_custom_marks)],
            STATE_CONFIRM:      [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_generate)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("help", help_cmd))

    print("🤖 TN Exam Bot is running...")
    print("   Press Ctrl+C to stop.\n")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
