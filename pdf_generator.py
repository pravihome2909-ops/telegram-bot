"""
pdf_generator.py
Exact TN Board question paper format.
Supports: Question Paper + Answer Key generation
Uses WeasyPrint for proper Tamil character shaping via Pango/HarfBuzz.
"""

import os
import html as html_mod
from datetime import datetime

try:
    from weasyprint import HTML, CSS
    WEASYPRINT_OK = True
except ImportError:
    WEASYPRINT_OK = False

from config import EXAM_FOOTER

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Tamil font discovery ──────────────────────────────────────────────
# WeasyPrint uses CSS @font-face; we locate a font file and embed it.

TAMIL_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/noto/NotoSansTamil-Regular.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansTamil-Regular.ttf",
    "/usr/share/fonts/truetype/lohit-tamil/Lohit-Tamil.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    os.path.join(BASE_DIR, "NotoSansTamil-Regular.ttf"),
    os.path.join(BASE_DIR, "Latha.ttf"),
    os.path.join(BASE_DIR, "FreeSans.ttf"),
    "C:/Windows/Fonts/Latha.ttf",
    "C:/Windows/Fonts/latha.ttf",
]

_TAMIL_FONT_PATH = None

def _get_tamil_font_path() -> str:
    """Return the first available Tamil font file path, or empty string."""
    global _TAMIL_FONT_PATH
    if _TAMIL_FONT_PATH is not None:
        return _TAMIL_FONT_PATH
    for path in TAMIL_FONT_CANDIDATES:
        if os.path.exists(path) and os.path.getsize(path) > 5000:
            _TAMIL_FONT_PATH = path
            print(f"[PDF] Tamil font: {path}")
            return _TAMIL_FONT_PATH
    print("[PDF] No Tamil font found — system fonts will be used")
    _TAMIL_FONT_PATH = ""
    return _TAMIL_FONT_PATH


# ── Language detection ────────────────────────────────────────────────

def _is_tamil(text: str) -> bool:
    return any('\u0B80' <= ch <= '\u0BFF' for ch in text)

def _detect_language(questions: list) -> str:
    for q in questions:
        text = q.get("question", "")
        if text.strip():
            return "ta" if _is_tamil(text) else "en"
    return "en"


_HEADINGS = {
    "ta": {
        "sec1_main": "அனைத்து வினாக்களுக்கும் விடையளிக்கவும்.",
        "sec1_sub":  "",
        "sec2_main": "எவையேனும் 7 வினாக்களுக்கு விடையளிக்கவும்.",
        "sec2_sub":  "வினா எண். {q} க்கு கட்டாயம் விடையளிக்கவும்.",
        "sec3_main": "எவையேனும் 7 வினாக்களுக்கு விடையளிக்கவும்.",
        "sec3_sub":  "வினா எண். {q} க்கு கட்டாயம் விடையளிக்கவும்.",
        "sec4_main": "அனைத்து வினாக்களுக்கும் விடையளிக்கவும்.",
        "sec4_sub":  "",
        "or":        "(அல்லது)",
        "duration":  "நேரம் : 3.00 மணி",
        "total":     "மதிப்பெண்கள் : {t}",
        "answer_key":"விடை குறிப்பு",
        "answer_lbl":"விடை",
    },
    "en": {
        "sec1_main": "Answer all questions.",
        "sec1_sub":  "",
        "sec2_main": "Answer any 7 questions.",
        "sec2_sub":  "Question No. {q} is compulsory.",
        "sec3_main": "Answer any 7 questions.",
        "sec3_sub":  "Question No. {q} is compulsory.",
        "sec4_main": "Answer all questions.",
        "sec4_sub":  "",
        "or":        "(OR)",
        "duration":  "Time : 3.00 Hours",
        "total":     "Total Marks : {t}",
        "answer_key":"ANSWER KEY",
        "answer_lbl":"Ans",
    },
}

def _score(mark, count):
    if mark == 1:  return count
    if mark == 2:  return min(count, 7) * 2
    if mark == 3:  return min(count, 7) * 3
    return count * mark

ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV"}

def _e(text) -> str:
    """HTML-escape a string."""
    return html_mod.escape(str(text))


# ── CSS stylesheet ────────────────────────────────────────────────────

def _build_css(font_path: str) -> str:
    font_face = ""
    if font_path:
        font_face = f"""
@font-face {{
    font-family: 'TamilFont';
    src: url('{font_path}');
}}"""

    return f"""
{font_face}

@page {{
    size: A4;
    margin: 1.9cm 2cm;
    @bottom-right {{
        content: "EduPulse-JB";
        font-size: 7pt;
        color: #c8c8c8;
    }}
}}

* {{
    box-sizing: border-box;
}}

body {{
    font-family: 'TamilFont', 'Noto Sans Tamil', 'Lohit Tamil', FreeSans, Arial, sans-serif;
    font-size: 10pt;
    line-height: 1.35;
    color: #000;
    margin: 0;
    padding: 0;
}}

.header-top {{
    text-align: center;
    font-size: 16pt;
    font-weight: bold;
    margin: 0 0 4pt 0;
}}

.header-sub {{
    text-align: center;
    font-size: 12pt;
    margin: 0 0 6pt 0;
}}

.header-class {{
    text-align: center;
    font-size: 11pt;
    margin: 0 0 4pt 0;
}}

.answer-key-label {{
    text-align: center;
    font-size: 12pt;
    font-weight: bold;
    color: #c0392b;
    margin: 0 0 6pt 0;
}}

.header-row {{
    display: table;
    width: 100%;
    margin-bottom: 4pt;
}}

.header-row-left,
.header-row-center,
.header-row-right {{
    display: table-cell;
    font-size: 9pt;
    vertical-align: middle;
}}

.header-row-left   {{ text-align: left; width: 33%; }}
.header-row-center {{ text-align: center; width: 34%; }}
.header-row-right  {{ text-align: right; width: 33%; }}

hr.thick {{
    border: none;
    border-top: 1pt solid #000;
    margin: 2pt 0 6pt 0;
}}

hr.thin {{
    border: none;
    border-top: 0.5pt solid #ccc;
    margin: 12pt 0 4pt 0;
}}

.section-row {{
    display: table;
    width: 100%;
    margin-top: 10pt;
    margin-bottom: 2pt;
}}

.section-title {{
    display: table-cell;
    font-size: 10pt;
    font-weight: bold;
    width: 80%;
}}

.section-marks {{
    display: table-cell;
    font-size: 10pt;
    font-weight: bold;
    text-align: right;
    width: 20%;
}}

.section-sub {{
    font-size: 9pt;
    color: #333;
    margin: 0 0 4pt 12pt;
}}

.question {{
    margin: 2pt 0 4pt 12pt;
    font-size: 10pt;
}}

.options {{
    margin: 0 0 5pt 24pt;
    font-size: 10pt;
}}

.or-line {{
    text-align: center;
    font-size: 10pt;
    margin: 3pt 0;
}}

.answer {{
    margin: 0 0 6pt 24pt;
    font-size: 9pt;
    color: #1a5276;
}}

.footer-text {{
    text-align: center;
    font-size: 9pt;
    color: #555;
    margin-top: 4pt;
}}

.wm-answer-key @page {{
    @bottom-right {{
        content: "Answer Key — EduPulse-JB";
    }}
}}
"""


# ── HTML builder ──────────────────────────────────────────────────────

def _build_html(H, class_, subject, lesson, groups, part_d_qs,
                pairs, total, school_name, test_name,
                is_answer_key=False, start_number=1):
    """Build the full HTML document for one paper or answer key."""

    parts = []
    parts.append('<!DOCTYPE html><html lang="ta"><head>')
    parts.append('<meta charset="UTF-8">')
    parts.append('</head><body>')

    # ── Header ───────────────────────────────────────────────────────
    if school_name or test_name:
        top = school_name if school_name else test_name
        parts.append(f'<div class="header-top">{_e(top)}</div>')
    if school_name and test_name:
        parts.append(f'<div class="header-sub">{_e(test_name)}</div>')

    parts.append(
        f'<div class="header-class">'
        f'{_e(class_)} – ஆம் வகுப்பு &nbsp;&nbsp;&nbsp;&nbsp;&nbsp; {_e(subject)}'
        f'</div>')

    if is_answer_key:
        parts.append(
            f'<div class="answer-key-label">[ {_e(H["answer_key"])} ]</div>')

    parts.append('<div class="header-row">')
    parts.append(f'<div class="header-row-left">{_e(H["duration"])}</div>')
    parts.append(f'<div class="header-row-center">{_e(lesson)}</div>')
    parts.append(f'<div class="header-row-right">{_e(H["total"].format(t=total))}</div>')
    parts.append('</div>')
    parts.append('<hr class="thick">')

    global_n = start_number

    def _sec_heading(roman, main, sub, marks_str):
        parts.append('<div class="section-row">')
        parts.append(f'<div class="section-title">{roman}&nbsp;&nbsp;&nbsp;{_e(main)}</div>')
        parts.append(f'<div class="section-marks">{_e(marks_str)}</div>')
        parts.append('</div>')
        if sub:
            parts.append(f'<div class="section-sub">{_e(sub)}</div>')

    # ── Section I ────────────────────────────────────────────────────
    if 1 in groups and groups[1]:
        qs = groups[1]
        n1 = len(qs)
        _sec_heading(ROMAN[1], H["sec1_main"], H["sec1_sub"], f"{n1}X1={n1}")
        for q in qs:
            parts.append(
                f'<div class="question">{global_n}.&nbsp; {_e(q.get("question",""))}</div>')
            opts = q.get("options", "")
            if opts:
                opt_list = [o.strip() for o in opts.split("|")]
                labels   = ["(அ)", "(ஆ)", "(இ)", "(ஈ)"]
                line = "&nbsp;&nbsp;".join(
                    f"{labels[i]} {_e(opt_list[i])}"
                    for i in range(min(len(labels), len(opt_list))))
                parts.append(f'<div class="options">{line}</div>')
            if is_answer_key:
                ans = q.get("answer", "") or q.get("correct_option", "")
                if ans:
                    parts.append(
                        f'<div class="answer">{_e(H["answer_lbl"])}: {_e(ans)}</div>')
            global_n += 1

    # ── Section II ───────────────────────────────────────────────────
    if 2 in groups and groups[2]:
        qs   = groups[2]
        n2   = len(qs)
        ans2 = min(n2, 7)
        _sec_heading(ROMAN[2], H["sec2_main"],
                     H["sec2_sub"].format(q=global_n + ans2 - 1),
                     f"{ans2}X2={ans2*2}")
        for q in qs:
            parts.append(
                f'<div class="question">{global_n}.&nbsp; {_e(q.get("question",""))}</div>')
            if is_answer_key:
                ans = q.get("answer", "")
                if ans:
                    parts.append(
                        f'<div class="answer">{_e(H["answer_lbl"])}: {_e(ans)}</div>')
            global_n += 1

    # ── Section III ──────────────────────────────────────────────────
    if 3 in groups and groups[3]:
        qs   = groups[3]
        n3   = len(qs)
        ans3 = min(n3, 7)
        _sec_heading(ROMAN[3], H["sec3_main"],
                     H["sec3_sub"].format(q=global_n + ans3 - 1),
                     f"{ans3}X3={ans3*3}")
        for q in qs:
            parts.append(
                f'<div class="question">{global_n}.&nbsp; {_e(q.get("question",""))}</div>')
            if is_answer_key:
                ans = q.get("answer", "")
                if ans:
                    parts.append(
                        f'<div class="answer">{_e(H["answer_lbl"])}: {_e(ans)}</div>')
            global_n += 1

    # ── Section IV ───────────────────────────────────────────────────
    if part_d_qs and pairs > 0:
        _sec_heading(ROMAN[4], H["sec4_main"], H["sec4_sub"],
                     f"{pairs}X5={pairs*5}")
        for i in range(0, len(part_d_qs) - 1, 2):
            qa  = part_d_qs[i].get("question", "")
            qb  = part_d_qs[i + 1].get("question", "")
            ans = part_d_qs[i].get("answer", "")
            parts.append(
                f'<div class="question">{global_n}.&nbsp; {_e(qa)}</div>')
            parts.append(f'<div class="or-line">{_e(H["or"])}</div>')
            parts.append(
                f'<div class="question">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{_e(qb)}</div>')
            if is_answer_key and ans:
                parts.append(
                    f'<div class="answer">{_e(H["answer_lbl"])}: {_e(ans)}</div>')
            global_n += 1

    # ── Footer ───────────────────────────────────────────────────────
    parts.append('<hr class="thin">')
    parts.append(f'<div class="footer-text">{_e(EXAM_FOOTER)}</div>')

    parts.append('</body></html>')
    return "".join(parts), global_n


# ── Core PDF writer ───────────────────────────────────────────────────

def _write_pdf(html_content: str, css_content: str, output_path: str,
               wm_text: str = "EduPulse-JB"):
    """Render HTML+CSS to a PDF file using WeasyPrint."""
    # Patch watermark text into the CSS @page rule
    css_with_wm = css_content.replace(
        '"EduPulse-JB"', f'"{wm_text}"', 1)
    HTML(string=html_content).write_pdf(
        output_path,
        stylesheets=[CSS(string=css_with_wm)])


# ── Public: Question Paper PDF ────────────────────────────────────────

def generate_question_paper_pdf(
        class_: str, subject: str, lesson: str,
        questions: list, teacher_name: str = "",
        output_path: str = None,
        part_d: list = None,
        test_name: str = "",
        school_name: str = "",
        start_number: int = 1) -> str:
    """Generate question paper PDF. Returns file path or ''."""

    if output_path is None:
        os.makedirs("generated_papers", exist_ok=True)
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = subject.replace(" ", "_")
        output_path = os.path.join(
            "generated_papers", f"Class{class_}_{safe}_{ts}.pdf")

    if not WEASYPRINT_OK:
        print("[PDF] weasyprint not installed.")
        return ""

    all_qs    = questions + (part_d or [])
    lang      = _detect_language(all_qs)
    H         = _HEADINGS[lang]
    part_d_qs = part_d if part_d else []
    other_qs  = [q for q in questions if q.get("marks") != 5]
    groups    = {}
    for q in other_qs:
        groups.setdefault(q.get("marks", 1), []).append(q)
    pairs = len(part_d_qs) // 2
    total = (_score(1, len(groups.get(1, []))) +
             _score(2, len(groups.get(2, []))) +
             _score(3, len(groups.get(3, []))) +
             pairs * 5)

    try:
        font_path  = _get_tamil_font_path()
        css        = _build_css(font_path)
        html, _    = _build_html(
            H, class_, subject, lesson,
            groups, part_d_qs, pairs, total,
            school_name, test_name,
            is_answer_key=False,
            start_number=start_number)
        _write_pdf(html, css, output_path, wm_text="EduPulse-JB")
        print(f"[PDF] Question paper: {output_path}")
        return output_path
    except Exception as e:
        print(f"[PDF] Failed: {e}")
        import traceback; traceback.print_exc()
        return ""


# ── Public: Answer Key PDF ────────────────────────────────────────────

def generate_answer_key_pdf(
        class_: str, subject: str, lesson: str,
        questions: list, teacher_name: str = "",
        output_path: str = None,
        part_d: list = None,
        test_name: str = "",
        school_name: str = "",
        start_number: int = 1) -> str:
    """Generate answer key PDF. Returns file path or ''."""

    if output_path is None:
        os.makedirs("generated_papers", exist_ok=True)
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = subject.replace(" ", "_")
        output_path = os.path.join(
            "generated_papers",
            f"Class{class_}_{safe}_{ts}_ANSWER_KEY.pdf")

    if not WEASYPRINT_OK:
        print("[PDF] weasyprint not installed.")
        return ""

    all_qs    = questions + (part_d or [])
    lang      = _detect_language(all_qs)
    H         = _HEADINGS[lang]
    part_d_qs = part_d if part_d else []
    other_qs  = [q for q in questions if q.get("marks") != 5]
    groups    = {}
    for q in other_qs:
        groups.setdefault(q.get("marks", 1), []).append(q)
    pairs = len(part_d_qs) // 2
    total = (_score(1, len(groups.get(1, []))) +
             _score(2, len(groups.get(2, []))) +
             _score(3, len(groups.get(3, []))) +
             pairs * 5)

    try:
        font_path  = _get_tamil_font_path()
        css        = _build_css(font_path)
        html, _    = _build_html(
            H, class_, subject, lesson,
            groups, part_d_qs, pairs, total,
            school_name, test_name,
            is_answer_key=True,
            start_number=start_number)
        _write_pdf(html, css, output_path,
                   wm_text="Answer Key — EduPulse-JB")
        print(f"[PDF] Answer key: {output_path}")
        return output_path
    except Exception as e:
        print(f"[PDF] Answer key failed: {e}")
        import traceback; traceback.print_exc()
        return ""


# ── Public: Get next question number from history ─────────────────────

def get_next_question_number(chat_id: str, class_: str,
                              subject: str) -> int:
    """
    Returns next question number for numbering continuity.
    Reads from Firestore teacher history.
    """
    try:
        from firebase_sync import get_db
        db = get_db()
        if db is None:
            return 1
        doc = (db.collection("teacher_paper_history")
                 .document(f"{chat_id}_{class_}_{subject.replace(' ','_')}")
                 .get())
        if doc.exists:
            return doc.to_dict().get("next_q_number", 1)
        return 1
    except Exception:
        return 1


def save_next_question_number(chat_id: str, class_: str,
                               subject: str, next_num: int):
    """Save next question number for this teacher+class+subject."""
    try:
        from firebase_sync import get_db
        db = get_db()
        if db is None:
            return
        db.collection("teacher_paper_history").document(
            f"{chat_id}_{class_}_{subject.replace(' ','_')}"
        ).set({"next_q_number": next_num}, merge=True)
    except Exception as e:
        print(f"[PDF] Save next q number error: {e}")
