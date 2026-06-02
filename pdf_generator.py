"""
pdf_generator.py
Layout:  A4, Left=2cm, Right=2cm, Top=1.9cm, Bottom=1.9cm, Line spacing=1.15
Header:  Class, Lesson(s), Marks only — no school/teacher/date
Footer:  All The Best
Watermark: EduPulse-JB (bottom-right, light gray)
Tamil:   Loads NotoSansTamil-Regular.ttf or Latha.ttf from project folder
"""

import os
from datetime import datetime

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm, mm
    from reportlab.lib import colors
    from reportlab.platypus import (SimpleDocTemplate, Paragraph,
                                     Spacer, Table, TableStyle,
                                     HRFlowable)
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
    os.path.join(BASE_DIR, "NotoSansTamil-Regular.ttf"),
    os.path.join(BASE_DIR, "Latha.ttf"),
    os.path.join(BASE_DIR, "tamil.ttf"),
    "C:/Windows/Fonts/latha.ttf",
    "C:/Windows/Fonts/Latha.ttf",
]

_FONT_REGISTERED = False
BODY_FONT        = "Helvetica"


def _register_font():
    global _FONT_REGISTERED, BODY_FONT
    if _FONT_REGISTERED:
        return BODY_FONT
    if not REPORTLAB_OK:
        return "Helvetica"
    for path in TAMIL_CANDIDATES:
        if os.path.exists(path) and os.path.getsize(path) > 5000:
            try:
                pdfmetrics.registerFont(TTFont("TamilFont", path))
                BODY_FONT        = "TamilFont"
                _FONT_REGISTERED = True
                print(f"[PDF] Tamil font loaded: {path}")
                return BODY_FONT
            except Exception as e:
                print(f"[PDF] Font error ({path}): {e}")
    print("[PDF] No Tamil font found — place NotoSansTamil-Regular.ttf "
          "in project folder.")
    _FONT_REGISTERED = True
    return "Helvetica"


# ── Watermark canvas ──────────────────────────────────────────────────

class _WatermarkCanvas(pdfcanvas.Canvas):
    """Draws 'EduPulse-JB' watermark bottom-right on every page."""

    def __init__(self, filename, **kwargs):
        super().__init__(filename, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_watermark()
            super().showPage()
        super().save()

    def _draw_watermark(self):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColorRGB(0.75, 0.75, 0.75)   # light gray
        page_w, page_h = A4
        self.drawRightString(page_w - 1.5*cm, 0.8*cm, "EduPulse-JB")
        self.restoreState()


# ── Main generator ────────────────────────────────────────────────────

def generate_question_paper_pdf(class_: str, subject: str, lesson: str,
                                  questions: list, teacher_name: str = "",
                                  output_path: str = None,
                                  part_d: list = None,
                                  test_name: str = "",
                                  school_name: str = "") -> str:
    if output_path is None:
        os.makedirs("generated_papers", exist_ok=True)
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = subject.replace(" ", "_")
        ext  = ".pdf" if REPORTLAB_OK else ".txt"
        output_path = os.path.join(
            "generated_papers",
            f"Class{class_}_{safe}_{ts}{ext}")

    if not REPORTLAB_OK:
        print("[PDF] reportlab not installed.")
        return _fallback(class_, subject, lesson, questions, output_path)

    font = _register_font()

    # Page margins: Left=2cm Right=2cm Top=1.9cm Bottom=1.9cm
    # (0.75 inch ≈ 1.905 cm)
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=2*cm,   rightMargin=2*cm,
        topMargin=1.9*cm,  bottomMargin=1.9*cm,
    )

    # Line spacing 1.15 = leading ≈ fontSize * 1.15
    def _style(name, size, bold=False, align=TA_LEFT,
               color=None, space_before=0, space_after=4,
               left_indent=0):
        return ParagraphStyle(
            name,
            fontName=font,
            fontSize=size,
            leading=round(size * 1.15 * 1.2, 1),  # 1.15 line + visual padding
            alignment=align,
            textColor=colors.HexColor(color) if color else colors.black,
            spaceBefore=space_before,
            spaceAfter=space_after,
            leftIndent=left_indent,
        )

    story = []

    # ── Compute correct marks (TN board pattern) ─────────────────────
    part_d_qs = part_d if part_d else []
    other_qs  = [q for q in questions if q.get("marks") != 5]
    groups_hdr = {}
    for q in other_qs:
        groups_hdr.setdefault(q.get("marks", 1), []).append(q)
    actual_pairs = len(part_d_qs) // 2

    def _score(mark, count):
        if mark == 1:  return count * 1
        elif mark == 2: return min(count, 7) * 2
        elif mark == 3: return min(count, 7) * 3
        return count * mark

    total_marks = (
        _score(1, len(groups_hdr.get(1, []))) +
        _score(2, len(groups_hdr.get(2, []))) +
        _score(3, len(groups_hdr.get(3, []))) +
        actual_pairs * 5
    )

    # ── Title block: Test Name + School Name ──────────────────────────
    if test_name or school_name:
        top_text = test_name if test_name else "QUESTION PAPER"
        if school_name:
            top_text = f"{school_name}  —  {top_text}"
        story.append(Paragraph(
            top_text.upper(),
            _style("toptitle", 13, align=TA_CENTER,
                   color="#1a3a5c", space_after=4)))

    # ── Header: Class | Lessons | Total Marks ─────────────────────────
    hdr_data = [[
        Paragraph(f"<b>Class : {class_}</b>",
                  _style("h1", 10, color="#000000")),
        Paragraph(f"<b>Lesson(s) : {lesson}</b>",
                  _style("h2", 10, color="#000000",
                          align=TA_CENTER)),
        Paragraph(f"<b>Total Marks : {total_marks}</b>",
                  _style("h3", 10, color="#000000",
                          align=TA_RIGHT)),
    ]]
    hdr_table = Table(hdr_data, colWidths=["30%", "40%", "30%"])
    hdr_table.setStyle(TableStyle([
        ("FONTNAME",      (0, 0), (-1, -1), font),
        ("FONTSIZE",      (0, 0), (-1, -1), 10),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW",     (0, 0), (-1, 0),
         0.8, colors.HexColor("#1a3a5c")),
    ]))
    story.append(hdr_table)

    # Marks breakdown line  20×1=20  |  10×2=14  |  ...
    breakdown = []
    if 1 in groups_hdr and groups_hdr[1]:
        n = len(groups_hdr[1])
        breakdown.append(f"{n}x1={n}")
    if 2 in groups_hdr and groups_hdr[2]:
        n = len(groups_hdr[2])
        breakdown.append(f"{n}x2={_score(2,n)}")
    if 3 in groups_hdr and groups_hdr[3]:
        n = len(groups_hdr[3])
        breakdown.append(f"{n}x3={_score(3,n)}")
    if actual_pairs > 0:
        breakdown.append(f"{actual_pairs}x5={actual_pairs*5}")
    if breakdown:
        story.append(Paragraph(
            "  |  ".join(breakdown) + f"  =  {total_marks} Marks",
            _style("bd", 9, align=TA_CENTER,
                   color="#444444", space_after=6)))

    story.append(Spacer(1, 6))

    # ── Title ─────────────────────────────────────────────────────────
    if not test_name:
        story.append(Paragraph(
            "QUESTION PAPER",
            _style("title", 13, align=TA_CENTER,
                   color="#1a3a5c", space_after=10)))

    # ── Sections ──────────────────────────────────────────────────────
    SECTION_LABELS = {
        1: "Section A  —  Choose the Best Answer",
        2: "Section B  —  Short Answer Questions",
        3: "Section C  —  Brief Answer Questions",
        5: "Section D  —  Long Answer / Essay Questions",
    }

    groups = {}
    for q in questions:
        groups.setdefault(q.get("marks", 1), []).append(q)

    q_style  = _style("q",  10, space_after=5, left_indent=8)
    sec_style = _style("sec", 11, color="#1a3a5c",
                        space_before=10, space_after=4)

    num = 1
    for marks in sorted(groups.keys()):
        qs  = groups[marks]
        lbl = SECTION_LABELS.get(marks,
                                  f"Section — {marks} Mark Questions")
        story.append(Paragraph(
            f"{lbl}  ({len(qs)} x {marks} = {len(qs)*marks} marks)",
            sec_style))
        story.append(HRFlowable(
            width="100%", thickness=0.5,
            color=colors.HexColor("#aaaaaa")))
        story.append(Spacer(1, 4))

        for q in qs:
            m_tag = (f'<font color="#888888" size="8">'
                     f' [{marks}m]</font>')
            story.append(Paragraph(
                f"{num}.&nbsp; {q.get('question', '')} {m_tag}",
                q_style))
            num += 1

    # ── Footer ────────────────────────────────────────────────────────
    story.append(Spacer(1, 18))
    story.append(HRFlowable(
        width="100%", thickness=0.5,
        color=colors.HexColor("#cccccc")))
    story.append(Paragraph(
        EXAM_FOOTER,
        _style("footer", 9, align=TA_CENTER,
               color="#555555", space_before=4)))

    try:
        doc.build(story, canvasmaker=_WatermarkCanvas)
        print(f"[PDF] Generated: {output_path}")
        return output_path
    except Exception as e:
        print(f"[PDF] Build failed: {e}")
        return ""


def _fallback(class_, subject, lesson, questions, output_path):
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"Class: {class_}  Lesson: {lesson}\n{'='*60}\n\n")
            for i, q in enumerate(questions, 1):
                f.write(f"{i}. {q.get('question','')} "
                        f"[{q.get('marks',1)}m]\n\n")
            f.write(f"\n{EXAM_FOOTER}\n\nEduPulse-JB\n")
        return output_path
    except Exception as e:
        print(f"[PDF] Fallback failed: {e}")
        return ""
