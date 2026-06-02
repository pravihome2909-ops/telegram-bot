"""
docx_generator.py
Layout : A4, L=2cm R=2cm T=1.9cm B=1.9cm, line-spacing 1.15
Header : Test Name | Class & Lessons | Marks breakdown
Footer : All The Best  +  EduPulse-JB watermark (bottom-right)
Tamil  : Uses FreeSans / Noto / Latha — whichever exists on the system.
         On Railway Linux: apt-get install -y fonts-freefont-ttf
         On Windows PC  : Latha is built-in (C:/Windows/Fonts/Latha.ttf)
"""

import os
import platform
from datetime import datetime

try:
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    DOCX_OK = True
except ImportError:
    DOCX_OK = False

from config import EXAM_FOOTER

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Tamil font detection ──────────────────────────────────────────────
# Priority order — first found wins
_FONT_CANDIDATES = [
    # Linux (Railway) — installed via apt-get install -y fonts-freefont-ttf
    ("/usr/share/fonts/truetype/freefont/FreeSans.ttf",    "FreeSans"),
    ("/usr/share/fonts/truetype/lohit-tamil/Lohit-Tamil.ttf", "Lohit Tamil"),
    ("/usr/share/fonts/truetype/noto/NotoSansTamil-Regular.ttf", "Noto Sans Tamil"),
    # Project folder (place any Tamil .ttf here)
    (os.path.join(BASE_DIR, "NotoSansTamil-Regular.ttf"), "Noto Sans Tamil"),
    (os.path.join(BASE_DIR, "Latha.ttf"),                 "Latha"),
    (os.path.join(BASE_DIR, "FreeSans.ttf"),              "FreeSans"),
    # Windows built-in
    ("C:/Windows/Fonts/latha.ttf",   "Latha"),
    ("C:/Windows/Fonts/Latha.ttf",   "Latha"),
    ("C:/Windows/Fonts/freesans.ttf","FreeSans"),
]

def _detect_tamil_font() -> str:
    for path, name in _FONT_CANDIDATES:
        if os.path.exists(path) and os.path.getsize(path) > 1000:
            print(f"[DOCX] Tamil font: {name}  ({path})")
            return name
    print("[DOCX] No Tamil font found — using Arial (Tamil may show boxes).")
    print("       Run: apt-get install -y fonts-freefont-ttf")
    return "Arial"

TAMIL_FONT = _detect_tamil_font()


# ── XML helpers ───────────────────────────────────────────────────────

def _font(run, name: str, size_pt: float,
           bold=False, color_hex: str = None):
    """Apply font to a run — forces complex-script (Tamil/Indic) font."""
    run.font.name  = name
    run.font.size  = Pt(size_pt)
    run.font.bold  = bold
    if color_hex:
        run.font.color.rgb = RGBColor(
            int(color_hex[0:2], 16),
            int(color_hex[2:4], 16),
            int(color_hex[4:6], 16))
    # Force all script types to use this font
    rPr = run._r.get_or_add_rPr()
    rf  = rPr.find(qn("w:rFonts"))
    if rf is None:
        rf = OxmlElement("w:rFonts")
        rPr.insert(0, rf)
    rf.set(qn("w:ascii"),    name)
    rf.set(qn("w:hAnsi"),    name)
    rf.set(qn("w:cs"),       name)   # ← critical for Tamil
    rf.set(qn("w:eastAsia"), name)


def _spacing(para, before=0, after=4, ls=1.15):
    fmt = para.paragraph_format
    fmt.space_before = Pt(before)
    fmt.space_after  = Pt(after)
    fmt.line_spacing = Pt(11 * ls)


def _hline(para, color="AAAAAA", thick=4):
    pPr  = para._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bot  = OxmlElement("w:bottom")
    bot.set(qn("w:val"),   "single")
    bot.set(qn("w:sz"),    str(thick * 8))
    bot.set(qn("w:space"), "1")
    bot.set(qn("w:color"), color)
    pBdr.append(bot)
    pPr.append(pBdr)


def _no_border_cell(cell):
    tc   = cell._tc
    tcPr = tc.get_or_add_tcPr()
    bdr  = OxmlElement("w:tcBdr")
    for s in ["top","left","bottom","right","insideH","insideV"]:
        e = OxmlElement(f"w:{s}")
        e.set(qn("w:val"),   "none")
        e.set(qn("w:sz"),    "0")
        e.set(qn("w:space"), "0")
        e.set(qn("w:color"), "auto")
        bdr.append(e)
    tcPr.append(bdr)


def _build_footer(section, fn):
    """Footer: All The Best (left)  ···  EduPulse-JB (right)"""
    footer = section.footer
    fp     = footer.paragraphs[0] if footer.paragraphs \
             else footer.add_paragraph()
    fp.clear()
    fp.alignment = WD_ALIGN_PARAGRAPH.LEFT
    _spacing(fp, before=0, after=0)

    # Left text
    r1 = fp.add_run(EXAM_FOOTER)
    _font(r1, fn, 9, color_hex="333333")

    # Tab to right
    fp.add_run("\t")

    # Right watermark
    r2 = fp.add_run("EduPulse-JB")
    _font(r2, "Arial", 8, color_hex="BBBBBB")

    # Tab stop at far right
    pPr  = fp._p.get_or_add_pPr()
    tabs = OxmlElement("w:tabs")
    tab  = OxmlElement("w:tab")
    tab.set(qn("w:val"),    "right")
    tab.set(qn("w:pos"),    "9072")  # 16cm in twips
    tab.set(qn("w:leader"), "none")
    tabs.append(tab)
    pPr.append(tabs)


# ── Main generator ────────────────────────────────────────────────────

def generate_question_paper_docx(
        class_: str, subject: str, lesson: str,
        questions: list, teacher_name: str = "",
        output_path: str = None,
        part_d: list = None,
        test_name: str = "",
        school_name: str = "") -> str:
    """
    Generate Tamil-supported Word question paper.
    Returns file path or "" on failure.
    """
    if not DOCX_OK:
        print("[DOCX] python-docx not installed.")
        return ""

    if output_path is None:
        os.makedirs("generated_papers", exist_ok=True)
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = subject.replace(" ", "_")
        output_path = os.path.join(
            "generated_papers", f"Class{class_}_{safe}_{ts}.docx")

    fn = TAMIL_FONT
    LS = 1.15

    try:
        doc = Document()

        # ── Page margins ──────────────────────────────────────────
        for sec in doc.sections:
            sec.page_width    = Cm(21.0)
            sec.page_height   = Cm(29.7)
            sec.left_margin   = Cm(2.0)
            sec.right_margin  = Cm(2.0)
            sec.top_margin    = Cm(1.9)
            sec.bottom_margin = Cm(1.9)
            _build_footer(sec, fn)

        # ── Separate part_d from other questions ──────────────────
        part_d_qs = part_d if part_d else []
        other_qs  = [q for q in questions if q.get("marks") != 5]

        # ── Compute CORRECT marks ─────────────────────────────────
        # 2-mark: students answer only 7 of 10 → marks = 7×2 = 14
        # 3-mark: students answer only 7 of 10 → marks = 7×3 = 21
        # 5-mark: Either/Or pairs → marks = pairs × 5
        # 1-mark: all attempted
        groups = {}
        for q in other_qs:
            groups.setdefault(q.get("marks", 1), []).append(q)

        actual_pairs = len(part_d_qs) // 2

        def _score(mark, count):
            """Return marks actually scored based on TN board pattern."""
            if mark == 1:
                return count * 1        # all attempted
            elif mark == 2:
                answered = min(count, 7)  # student answers 7
                return answered * 2
            elif mark == 3:
                answered = min(count, 7)  # student answers 7
                return answered * 3
            elif mark == 5:
                return actual_pairs * 5   # Either/Or pairs
            return count * mark

        total_marks = (
            _score(1, len(groups.get(1, []))) +
            _score(2, len(groups.get(2, []))) +
            _score(3, len(groups.get(3, []))) +
            actual_pairs * 5
        )

        # ── Header info ───────────────────────────────────────────
        # Row 1: Test Name (or QUESTION PAPER) centered
        if test_name or school_name:
            top_text = test_name if test_name else "QUESTION PAPER"
            if school_name:
                top_text = f"{school_name}  —  {top_text}"
            tp = doc.add_paragraph()
            tp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _spacing(tp, before=0, after=4, ls=LS)
            r = tp.add_run(top_text.upper())
            _font(r, fn, 12, bold=True, color_hex="1A3A5C")

        # Row 2: Class | Lesson(s) | Total Marks  (3-column table)
        tbl  = doc.add_table(rows=1, cols=3)
        tbl.style = "Table Grid"
        cells = tbl.rows[0].cells

        hdr_vals = [
            f"Class : {class_}",
            f"Lesson(s) : {lesson}",
            f"Total Marks : {total_marks}",
        ]
        hdr_alns = [WD_ALIGN_PARAGRAPH.LEFT,
                    WD_ALIGN_PARAGRAPH.CENTER,
                    WD_ALIGN_PARAGRAPH.RIGHT]

        for cell, txt, aln in zip(cells, hdr_vals, hdr_alns):
            cell.text = ""
            _no_border_cell(cell)
            p = cell.paragraphs[0]
            p.alignment = aln
            _spacing(p, before=2, after=4, ls=LS)
            r = p.add_run(txt)
            _font(r, fn, 10, bold=True)

        # Remove all table borders
        tbl_pr = tbl._tbl.find(qn("w:tblPr"))
        if tbl_pr is None:
            tbl_pr = OxmlElement("w:tblPr")
            tbl._tbl.insert(0, tbl_pr)
        tb = OxmlElement("w:tblBorders")
        for s in ["top","left","bottom","right","insideH","insideV"]:
            e = OxmlElement(f"w:{s}")
            e.set(qn("w:val"),   "none")
            e.set(qn("w:sz"),    "0")
            e.set(qn("w:color"), "auto")
            tb.append(e)
        tbl_pr.append(tb)

        # Row 3: Marks breakdown  20×1=20  |  10×2=14  |  10×3=21  |  7×5=35
        breakdown_parts = []
        if 1 in groups and groups[1]:
            n = len(groups[1])
            breakdown_parts.append(f"{n}×1={n}")
        if 2 in groups and groups[2]:
            n = len(groups[2])
            breakdown_parts.append(f"{n}×2={_score(2,n)}")
        if 3 in groups and groups[3]:
            n = len(groups[3])
            breakdown_parts.append(f"{n}×3={_score(3,n)}")
        if actual_pairs > 0:
            breakdown_parts.append(f"{actual_pairs}×5={actual_pairs*5}")

        if breakdown_parts:
            bp = doc.add_paragraph()
            bp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _spacing(bp, before=2, after=2, ls=LS)
            r = bp.add_run("  |  ".join(breakdown_parts) +
                            f"  =  {total_marks} Marks")
            _font(r, fn, 9, color_hex="444444")

        # Separator
        sep = doc.add_paragraph()
        _spacing(sep, before=2, after=6, ls=LS)
        _hline(sep, color="1A3A5C", thick=2)

        # Title (if no test name was provided)
        if not test_name:
            tp2 = doc.add_paragraph()
            tp2.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _spacing(tp2, before=4, after=10, ls=LS)
            r = tp2.add_run("QUESTION PAPER")
            _font(r, fn, 13, bold=True, color_hex="1A3A5C")

        # ── Sections A / B / C ────────────────────────────────────
        SEC = {
            1: "Section A — Choose the Best Answer",
            2: "Section B — Short Answer Questions",
            3: "Section C — Brief Answer Questions",
            5: "Section D — Long Answer / Essay (Either / Or)",
        }

        num = 1

        for marks in sorted(groups.keys()):
            qs       = groups[marks]
            answered = min(len(qs), 7) if marks in (2, 3) else len(qs)
            lbl      = SEC.get(marks, f"Section — {marks} Mark Questions")
            sec_line = (f"{lbl}  "
                        f"({len(qs)} × {marks}"
                        + (f", Answer any {answered}" if marks in (2,3) and len(qs) > answered else "")
                        + f" = {_score(marks, len(qs))} marks)")

            sh = doc.add_paragraph()
            _spacing(sh, before=10, after=4, ls=LS)
            r  = sh.add_run(sec_line)
            _font(r, fn, 11, bold=True, color_hex="1A3A5C")
            _hline(sh, color="AAAAAA", thick=1)

            for q in qs:
                qp = doc.add_paragraph()
                qp.paragraph_format.left_indent = Cm(0.5)
                _spacing(qp, before=2, after=5, ls=LS)
                _font(qp.add_run(f"{num}.  "), fn, 10, bold=True)
                _font(qp.add_run(q.get("question", "")), fn, 10)
                _font(qp.add_run(f"  [{marks}m]"), fn, 8,
                       color_hex="888888")
                num += 1

        # ── Section D — Either / Or ───────────────────────────────
        if part_d_qs:
            pairs   = len(part_d_qs) // 2
            sec_line = (f"{SEC[5]}  "
                        f"({pairs} × 5 = {pairs*5} marks)")
            sh = doc.add_paragraph()
            _spacing(sh, before=10, after=4, ls=LS)
            r  = sh.add_run(sec_line)
            _font(r, fn, 11, bold=True, color_hex="1A3A5C")
            _hline(sh, color="AAAAAA", thick=1)

            for i in range(0, len(part_d_qs) - 1, 2):
                qa = part_d_qs[i].get("question", "")
                qb = part_d_qs[i+1].get("question", "")

                pa = doc.add_paragraph()
                pa.paragraph_format.left_indent = Cm(0.5)
                _spacing(pa, before=2, after=2, ls=LS)
                _font(pa.add_run(f"{num}a.  "), fn, 10, bold=True)
                _font(pa.add_run(qa), fn, 10)
                _font(pa.add_run("  [5m]"), fn, 8, color_hex="888888")

                por = doc.add_paragraph()
                por.paragraph_format.left_indent = Cm(1.5)
                _spacing(por, before=1, after=1, ls=LS)
                por.alignment = WD_ALIGN_PARAGRAPH.CENTER
                _font(por.add_run("(OR)"), fn, 10,
                       bold=True, color_hex="555555")

                pb = doc.add_paragraph()
                pb.paragraph_format.left_indent = Cm(0.5)
                _spacing(pb, before=2, after=8, ls=LS)
                _font(pb.add_run(f"{num}b.  "), fn, 10, bold=True)
                _font(pb.add_run(qb), fn, 10)
                _font(pb.add_run("  [5m]"), fn, 8, color_hex="888888")

                num += 1

        doc.save(output_path)
        print(f"[DOCX] Saved: {output_path}")
        return output_path

    except Exception as e:
        print(f"[DOCX] Failed: {e}")
        import traceback; traceback.print_exc()
        return ""
