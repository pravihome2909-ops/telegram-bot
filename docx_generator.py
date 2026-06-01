"""
docx_generator.py
Layout:  A4, Left=2cm, Right=2cm, Top=1.9cm, Bottom=1.9cm, Line spacing=1.15
Header:  Class, Lesson(s), Marks only
Footer:  All The Best  +  watermark EduPulse-JB (bottom-right)
Tamil:   Uses Latha font (Windows built-in) or NotoSansTamil-Regular.ttf
"""

import os
from datetime import datetime

try:
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.section import WD_ORIENT
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    import lxml.etree as etree
    DOCX_OK = True
except ImportError:
    DOCX_OK = False

from config import EXAM_FOOTER

BASE_DIR        = os.path.dirname(os.path.abspath(__file__))

# Tamil font — Latha is built into Windows.
# On Linux (Railway): set to "Noto Sans Tamil" and install fonts-lohit-taml
TAMIL_FONT = "Latha" if platform.system() == "Windows" else "Lohit Tamil"

SECTION_TITLES = {
    1: "Section A — Choose the Best Answer",
    2: "Section B — Short Answer Questions",
    3: "Section C — Brief Answer Questions",
    5: "Section D — Long Answer / Essay Questions",
}


# ── XML helpers ───────────────────────────────────────────────────────

def _set_run_font(run, font_name: str, size_pt: float,
                   bold=False, italic=False,
                   color_hex: str = None):
    run.font.name  = font_name
    run.font.size  = Pt(size_pt)
    run.font.bold  = bold
    run.font.italic = italic
    if color_hex:
        r = int(color_hex[0:2], 16)
        g = int(color_hex[2:4], 16)
        b = int(color_hex[4:6], 16)
        run.font.color.rgb = RGBColor(r, g, b)
    # Force complex script font (required for Tamil/Indic)
    rPr = run._r.get_or_add_rPr()
    for tag in ["w:rFonts"]:
        existing = rPr.find(qn(tag))
        if existing is None:
            existing = OxmlElement(tag)
            rPr.insert(0, existing)
        existing.set(qn("w:ascii"),       font_name)
        existing.set(qn("w:hAnsi"),       font_name)
        existing.set(qn("w:cs"),          font_name)
        existing.set(qn("w:eastAsia"),    font_name)


def _para_spacing(para, before_pt=0, after_pt=4, line_spacing=1.15):
    """Set paragraph spacing and line spacing."""
    fmt = para.paragraph_format
    fmt.space_before       = Pt(before_pt)
    fmt.space_after        = Pt(after_pt)
    fmt.line_spacing       = Pt(12 * line_spacing)  # 12pt base * 1.15


def _add_horizontal_border(para, color_hex="AAAAAA", size_pt=4):
    """Add a bottom border to a paragraph (acts as horizontal rule)."""
    pPr  = para._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bot  = OxmlElement("w:bottom")
    bot.set(qn("w:val"),   "single")
    bot.set(qn("w:sz"),    str(int(size_pt * 8)))
    bot.set(qn("w:space"), "1")
    bot.set(qn("w:color"), color_hex)
    pBdr.append(bot)
    pPr.append(pBdr)


def _set_cell_no_border(cell):
    """Remove all borders from a table cell."""
    tc   = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBdr = OxmlElement("w:tcBdr")
    for side in ["top","left","bottom","right","insideH","insideV"]:
        e = OxmlElement(f"w:{side}")
        e.set(qn("w:val"),   "none")
        e.set(qn("w:sz"),    "0")
        e.set(qn("w:space"), "0")
        e.set(qn("w:color"), "auto")
        tcBdr.append(e)
    tcPr.append(tcBdr)


def _add_watermark_to_section(section):
    """
    Add 'EduPulse-JB' as a text watermark in the footer (bottom-right).
    Uses a footer paragraph aligned right with light gray color.
    """
    footer     = section.footer
    footer_para = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    footer_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _para_spacing(footer_para, before_pt=0, after_pt=0)

    # "All The Best" on left, "EduPulse-JB" on right using tab stop
    footer_para.clear()

    # Left: All The Best
    run_l = footer_para.add_run(EXAM_FOOTER + "   ")
    _set_run_font(run_l, TAMIL_FONT, 9, color_hex="333333")

    # Tab
    footer_para.add_run("\t")

    # Right: EduPulse-JB watermark
    run_r = footer_para.add_run("EduPulse-JB")
    _set_run_font(run_r, "Helvetica", 8, color_hex="BBBBBB")

    # Add a tab stop at right margin
    pPr  = footer_para._p.get_or_add_pPr()
    tabs = OxmlElement("w:tabs")
    tab  = OxmlElement("w:tab")
    tab.set(qn("w:val"),    "right")
    tab.set(qn("w:pos"),    "9016")   # ~16cm ≈ right margin
    tab.set(qn("w:leader"), "none")
    tabs.append(tab)
    pPr.append(tabs)


# ── Main generator ────────────────────────────────────────────────────

def generate_question_paper_docx(class_: str, subject: str, lesson: str,
                                   questions: list, teacher_name: str = "",
                                   output_path: str = None,
                                   part_d: list = None) -> str:
    if not DOCX_OK:
        print("[DOCX] python-docx not installed — run: pip install python-docx")
        return ""

    if output_path is None:
        os.makedirs("generated_papers", exist_ok=True)
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = subject.replace(" ", "_")
        output_path = os.path.join(
            "generated_papers",
            f"Class{class_}_{safe}_{ts}.docx")

    try:
        doc = Document()
        fn  = TAMIL_FONT

        # ── Page setup: A4, margins in cm ──────────────────────────
        # Left=2cm, Right=2cm, Top=1.9cm(~0.75in), Bottom=1.9cm
        for sec in doc.sections:
            from docx.shared import Cm as _Cm
            sec.page_width    = Cm(21.0)
            sec.page_height   = Cm(29.7)
            sec.left_margin   = Cm(-2.0)
            sec.right_margin  = Cm(-2.0)
            sec.top_margin    = Cm(1.9)
            sec.bottom_margin = Cm(1.9)
            _add_watermark_to_section(sec)

        LS = 1.15   # line spacing multiplier

        # ── Header table: Class | Lesson(s) | Total Marks ──────────
        total_marks = sum(q.get("marks", 1) for q in questions)

        hdr_table = doc.add_table(rows=1, cols=3)
        hdr_table.style = "Table Grid"
        cells = hdr_table.rows[0].cells

        hdr_data = [
            f"Class : {class_}",
            f"Lesson(s) : {lesson}",
            f"Total Marks : {total_marks}",
        ]
        aligns = [WD_ALIGN_PARAGRAPH.LEFT,
                  WD_ALIGN_PARAGRAPH.CENTER,
                  WD_ALIGN_PARAGRAPH.RIGHT]

        for i, (cell, txt, aln) in enumerate(
                zip(cells, hdr_data, aligns)):
            cell.text = ""
            _set_cell_no_border(cell)
            para = cell.paragraphs[0]
            para.alignment = aln
            _para_spacing(para, before_pt=2, after_pt=4,
                           line_spacing=LS)
            run = para.add_run(txt)
            _set_run_font(run, fn, 10, bold=True)

        # Border under header row
        tbl  = hdr_table._tbl
        tblPr = tbl.find(qn("w:tblPr"))
        if tblPr is None:
            tblPr = OxmlElement("w:tblPr")
            tbl.insert(0, tblPr)
        tblBdr = OxmlElement("w:tblBorders")
        for side in ["top","left","bottom","right",
                     "insideH","insideV"]:
            e = OxmlElement(f"w:{side}")
            e.set(qn("w:val"),   "none")
            e.set(qn("w:sz"),    "0")
            e.set(qn("w:color"), "auto")
            tblBdr.append(e)
        tblPr.append(tblBdr)

        # Separator line
        sep = doc.add_paragraph()
        _para_spacing(sep, before_pt=2, after_pt=6, line_spacing=LS)
        _add_horizontal_border(sep, color_hex="1A3A5C", size_pt=2)

        # ── Title ─────────────────────────────────────────────────
        title_para = doc.add_paragraph()
        title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _para_spacing(title_para, before_pt=4, after_pt=10,
                       line_spacing=LS)
        run = title_para.add_run("QUESTION PAPER")
        _set_run_font(run, fn, 13, bold=True, color_hex="1A3A5C")

        # ── Sections ──────────────────────────────────────────────
        groups = {}
        for q in questions:
            groups.setdefault(q.get("marks", 1), []).append(q)

        num = 1
        for marks in sorted(groups.keys()):
            qs  = groups[marks]
            lbl = SECTION_TITLES.get(
                marks, f"Section — {marks} Mark Questions")

            # Section heading
            sec_para = doc.add_paragraph()
            _para_spacing(sec_para, before_pt=10, after_pt=4,
                           line_spacing=LS)
            run = sec_para.add_run(
                f"{lbl}  ({len(qs)} x {marks} = {len(qs)*marks} marks)")
            _set_run_font(run, fn, 11, bold=True, color_hex="1A3A5C")
            _add_horizontal_border(sec_para,
                                    color_hex="AAAAAA", size_pt=1)

            # Questions
            for q in qs:
                q_text = q.get("question", "")
                m_lbl  = f"  [{marks}m]"

                q_para = doc.add_paragraph()
                q_para.paragraph_format.left_indent = Cm(0.5)
                _para_spacing(q_para, before_pt=2, after_pt=5,
                               line_spacing=LS)

                run_num = q_para.add_run(f"{num}.  ")
                _set_run_font(run_num, fn, 10, bold=True)

                run_q = q_para.add_run(q_text)
                _set_run_font(run_q, fn, 10)

                run_m = q_para.add_run(m_lbl)
                _set_run_font(run_m, fn, 8,
                               color_hex="888888")

                num += 1

        doc.save(output_path)
        print(f"[DOCX] Generated: {output_path}")
        return output_path

    except Exception as e:
        print(f"[DOCX] Generation failed: {e}")
        import traceback; traceback.print_exc()
        return ""
