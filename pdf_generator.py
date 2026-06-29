"""
pdf_generator.py
Exact TN Board question paper format.
Supports: Question Paper + Answer Key generation
Tamil font: place NotoSansTamil-Regular.ttf or Latha.ttf in project folder.
"""

import os
from datetime import datetime

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                     Table, TableStyle, HRFlowable)
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas as pdfcanvas
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False

from config import EXAM_FOOTER

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

TAMIL_CANDIDATES = [
    ("/usr/share/fonts/truetype/freefont/FreeSans.ttf",           "FreeSans"),
    ("/usr/share/fonts/truetype/lohit-tamil/Lohit-Tamil.ttf",     "Lohit-Tamil"),
    ("/usr/share/fonts/truetype/noto/NotoSansTamil-Regular.ttf",  "NotoSansTamil"),
    ("/usr/share/fonts/opentype/noto/NotoSansTamil-Regular.ttf",  "NotoSansTamil"),
    (os.path.join(BASE_DIR, "NotoSansTamil-Regular.ttf"),         "NotoSansTamil"),
    (os.path.join(BASE_DIR, "Latha.ttf"),                         "Latha"),
    (os.path.join(BASE_DIR, "FreeSans.ttf"),                      "FreeSans"),
    ("C:/Windows/Fonts/Latha.ttf",                                "Latha"),
    ("C:/Windows/Fonts/latha.ttf",                                "Latha"),
]

_FONT_NAME = None

def _get_font():
    global _FONT_NAME
    if _FONT_NAME:
        return _FONT_NAME
    if not REPORTLAB_OK:
        _FONT_NAME = "Helvetica"
        return _FONT_NAME
    for path, name in TAMIL_CANDIDATES:
        if os.path.exists(path) and os.path.getsize(path) > 5000:
            try:
                pdfmetrics.registerFont(TTFont(name, path))
                _FONT_NAME = name
                print(f"[PDF] Tamil font: {name}  ({path})")
                return _FONT_NAME
            except Exception as e:
                print(f"[PDF] Font load failed ({path}): {e}")
    print("[PDF] No Tamil font — using Helvetica")
    _FONT_NAME = "Helvetica"
    return _FONT_NAME


# ── Watermark canvas ─────────────────────────────────────────────────

class _WMCanvas(pdfcanvas.Canvas):
    def __init__(self, filename, wm_text="EduPulse-JB", **kw):
        super().__init__(filename, **kw)
        self._pages   = []
        self._wm_text = wm_text

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        for state in self._pages:
            self.__dict__.update(state)
            self._draw_wm()
            super().showPage()
        super().save()

    def _draw_wm(self):
        self.saveState()
        self.setFont("Helvetica", 7)
        self.setFillColorRGB(0.78, 0.78, 0.78)
        w, h = A4
        self.drawRightString(w - 1.5*cm, 0.7*cm, self._wm_text)
        self.restoreState()


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


# ── Core builder (shared by question paper + answer key) ─────────────

def _build_pdf(output_path, story, wm_text="EduPulse-JB"):
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=1.9*cm, bottomMargin=1.9*cm)

    class _Canvas(_WMCanvas):
        def __init__(self, filename, **kw):
            super().__init__(filename, wm_text=wm_text, **kw)

    doc.build(story, canvasmaker=_Canvas)


def _make_story(fn, H, class_, subject, lesson, groups, part_d_qs,
                pairs, total, school_name, test_name,
                is_answer_key=False, start_number=1):
    """Build the ReportLab story list for one paper or answer key."""

    def S(name, size, align=TA_LEFT, color=None, sb=0, sa=4, li=0):
        return ParagraphStyle(
            name, fontName=fn, fontSize=size,
            leading=round(size * 1.32, 1),
            alignment=align,
            textColor=colors.HexColor(color) if color else colors.black,
            spaceBefore=sb, spaceAfter=sa,
            leftIndent=li)

    story = []

    # ── Header ───────────────────────────────────────────────────────
    if school_name or test_name:
        top = school_name if school_name else test_name
        story.append(Paragraph(top, S("top", 16, align=TA_CENTER, sb=0, sa=2)))
    if school_name and test_name:
        story.append(Paragraph(test_name, S("tn", 12, align=TA_CENTER, sb=0, sa=4)))

    story.append(Paragraph(
        f"{class_} – ஆம் வகுப்பு          {subject}",
        S("cs", 11, align=TA_CENTER, sb=0, sa=2)))

    if is_answer_key:
        story.append(Paragraph(
            f"[ {H['answer_key']} ]",
            S("ak", 12, align=TA_CENTER, sb=0, sa=4,
               color="#c0392b")))

    hdr_data = [[
        Paragraph(H["duration"],            S("hl", 9, align=TA_LEFT)),
        Paragraph(lesson,                   S("hc", 9, align=TA_CENTER)),
        Paragraph(H["total"].format(t=total),S("hr", 9, align=TA_RIGHT)),
    ]]
    ht = Table(hdr_data, colWidths=["33%","34%","33%"])
    ht.setStyle(TableStyle([
        ("FONTNAME",      (0,0),(-1,-1), fn),
        ("FONTSIZE",      (0,0),(-1,-1), 9),
        ("TOPPADDING",    (0,0),(-1,-1), 1),
        ("BOTTOMPADDING", (0,0),(-1,-1), 3),
    ]))
    story.append(ht)
    story.append(HRFlowable(width="100%", thickness=1, color=colors.black))
    story.append(Spacer(1, 6))

    # ── Styles ───────────────────────────────────────────────────────
    sec_num  = 0
    global_n = start_number

    q_style  = S("q",  10, sb=1, sa=4, li=12)
    opt_s    = S("opt",10, sb=0, sa=5, li=24)
    or_s     = S("or", 10, align=TA_CENTER, sb=2, sa=2)
    sub_s    = S("sub", 9, sb=0, sa=2, li=12, color="#333333")
    ans_s    = S("ans", 9, sb=0, sa=6, li=24, color="#1a5276")

    def _sec_heading(main, sub, marks_str):
        data = [[
            Paragraph(f"{ROMAN[sec_num]}   {main}",
                      S(f"sh{sec_num}", 10, sb=8, sa=1)),
            Paragraph(marks_str,
                      S(f"sr{sec_num}", 10, align=TA_RIGHT, sb=8, sa=1)),
        ]]
        t = Table(data, colWidths=["80%","20%"])
        t.setStyle(TableStyle([
            ("FONTNAME",      (0,0),(-1,-1), fn),
            ("FONTSIZE",      (0,0),(-1,-1), 10),
            ("TOPPADDING",    (0,0),(-1,-1), 2),
            ("BOTTOMPADDING", (0,0),(-1,-1), 2),
        ]))
        story.append(t)
        if sub:
            story.append(Paragraph(sub, sub_s))

    # ── Section I ────────────────────────────────────────────────────
    if 1 in groups and groups[1]:
        qs = groups[1]; n1 = len(qs); sec_num = 1
        _sec_heading(H["sec1_main"], H["sec1_sub"], f"{n1}X1={n1}")
        for q in qs:
            story.append(Paragraph(
                f"{global_n}.&nbsp; {q.get('question','')}", q_style))
            opts = q.get("options","")
            if opts:
                opt_list = [o.strip() for o in opts.split("|")]
                labels   = ["(அ)","(ஆ)","(இ)","(ஈ)"]
                line = "  ".join(
                    f"{labels[i]} {opt_list[i]}"
                    for i in range(min(len(labels),len(opt_list))))
                story.append(Paragraph(line, opt_s))
            if is_answer_key:
                ans = q.get("answer","") or q.get("correct_option","")
                if ans:
                    story.append(Paragraph(
                        f"{H['answer_lbl']}: {ans}", ans_s))
            global_n += 1
        story.append(Spacer(1,4))

    # ── Section II ───────────────────────────────────────────────────
    if 2 in groups and groups[2]:
        qs = groups[2]; n2 = len(qs); ans2 = min(n2,7); sec_num = 2
        _sec_heading(H["sec2_main"],
                     H["sec2_sub"].format(q=global_n+ans2-1),
                     f"{ans2}X2={ans2*2}")
        for q in qs:
            story.append(Paragraph(
                f"{global_n}.&nbsp; {q.get('question','')}", q_style))
            if is_answer_key:
                ans = q.get("answer","")
                if ans:
                    story.append(Paragraph(
                        f"{H['answer_lbl']}: {ans}", ans_s))
            global_n += 1
        story.append(Spacer(1,4))

    # ── Section III ──────────────────────────────────────────────────
    if 3 in groups and groups[3]:
        qs = groups[3]; n3 = len(qs); ans3 = min(n3,7); sec_num = 3
        _sec_heading(H["sec3_main"],
                     H["sec3_sub"].format(q=global_n+ans3-1),
                     f"{ans3}X3={ans3*3}")
        for q in qs:
            story.append(Paragraph(
                f"{global_n}.&nbsp; {q.get('question','')}", q_style))
            if is_answer_key:
                ans = q.get("answer","")
                if ans:
                    story.append(Paragraph(
                        f"{H['answer_lbl']}: {ans}", ans_s))
            global_n += 1
        story.append(Spacer(1,4))

    # ── Section IV ───────────────────────────────────────────────────
    if part_d_qs and pairs > 0:
        sec_num = 4
        _sec_heading(H["sec4_main"], H["sec4_sub"], f"{pairs}X5={pairs*5}")
        for i in range(0, len(part_d_qs)-1, 2):
            qa  = part_d_qs[i].get("question","")
            qb  = part_d_qs[i+1].get("question","")
            ans = part_d_qs[i].get("answer","")
            story.append(Paragraph(
                f"{global_n}.&nbsp; {qa}", q_style))
            story.append(Paragraph(H["or"], or_s))
            story.append(Paragraph(
                f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{qb}",
                q_style))
            if is_answer_key and ans:
                story.append(Paragraph(
                    f"{H['answer_lbl']}: {ans}", ans_s))
            story.append(Spacer(1,6))
            global_n += 1

    # ── Footer ───────────────────────────────────────────────────────
    story.append(Spacer(1,16))
    story.append(HRFlowable(
        width="100%", thickness=0.5,
        color=colors.HexColor("#cccccc")))
    story.append(Paragraph(
        EXAM_FOOTER,
        S("ft", 9, align=TA_CENTER, color="#555555", sb=4)))

    return story, global_n  # return next question number


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

    if not REPORTLAB_OK:
        print("[PDF] reportlab not installed.")
        return ""

    fn        = _get_font()
    all_qs    = questions + (part_d or [])
    lang      = _detect_language(all_qs)
    H         = _HEADINGS[lang]
    part_d_qs = part_d if part_d else []
    other_qs  = [q for q in questions if q.get("marks") != 5]
    groups    = {}
    for q in other_qs:
        groups.setdefault(q.get("marks",1),[]).append(q)
    pairs = len(part_d_qs) // 2
    total = (_score(1,len(groups.get(1,[]))) +
             _score(2,len(groups.get(2,[]))) +
             _score(3,len(groups.get(3,[]))) +
             pairs * 5)

    try:
        story, _ = _make_story(
            fn, H, class_, subject, lesson,
            groups, part_d_qs, pairs, total,
            school_name, test_name,
            is_answer_key=False,
            start_number=start_number)
        _build_pdf(output_path, story)
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

    if not REPORTLAB_OK:
        print("[PDF] reportlab not installed.")
        return ""

    fn        = _get_font()
    all_qs    = questions + (part_d or [])
    lang      = _detect_language(all_qs)
    H         = _HEADINGS[lang]
    part_d_qs = part_d if part_d else []
    other_qs  = [q for q in questions if q.get("marks") != 5]
    groups    = {}
    for q in other_qs:
        groups.setdefault(q.get("marks",1),[]).append(q)
    pairs = len(part_d_qs) // 2
    total = (_score(1,len(groups.get(1,[]))) +
             _score(2,len(groups.get(2,[]))) +
             _score(3,len(groups.get(3,[]))) +
             pairs * 5)

    try:
        story, _ = _make_story(
            fn, H, class_, subject, lesson,
            groups, part_d_qs, pairs, total,
            school_name, test_name,
            is_answer_key=True,
            start_number=start_number)
        _build_pdf(output_path, story, wm_text="Answer Key — EduPulse-JB")
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
