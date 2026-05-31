"""
pdf_generator.py  —  Generate question paper PDF using reportlab.
Falls back to plain .txt if reportlab is not installed.
"""

import os
from datetime import datetime

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import (SimpleDocTemplate, Paragraph,
                                     Spacer, Table, TableStyle,
                                     HRFlowable)
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False

from config import SCHOOL_NAME, SCHOOL_ADDRESS, EXAM_FOOTER


def generate_question_paper_pdf(class_: str, subject: str, lesson: str,
                                  questions: list, teacher_name: str = "",
                                  output_path: str = None) -> str:
    """
    Generate a formatted A4 question paper PDF.

    questions: list of dicts — each must have:
        question (str), marks (int), lesson (str)

    Returns path to the generated file, or "" on failure.
    """
    if output_path is None:
        os.makedirs("generated_papers", exist_ok=True)
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = subject.replace(" ", "_")
        ext  = ".pdf" if REPORTLAB_OK else ".txt"
        output_path = os.path.join(
            "generated_papers",
            f"Class{class_}_{safe}_Lesson{lesson}_{ts}{ext}"
        )

    if not REPORTLAB_OK:
        print("[PDF] reportlab not installed — generating plain text instead.")
        print("      Run: pip install reportlab")
        return _plain_text_fallback(class_, subject, lesson,
                                     questions, output_path)

    try:
        doc    = SimpleDocTemplate(
            output_path, pagesize=A4,
            topMargin=1.5*cm, bottomMargin=1.5*cm,
            leftMargin=2*cm,  rightMargin=2*cm
        )
        styles = getSampleStyleSheet()
        story  = []

        # ── School header ──
        school_style = ParagraphStyle(
            "school", fontSize=14, fontName="Helvetica-Bold",
            alignment=TA_CENTER, spaceAfter=2)
        addr_style = ParagraphStyle(
            "addr", fontSize=9, fontName="Helvetica",
            alignment=TA_CENTER, spaceAfter=4)

        story.append(Paragraph(SCHOOL_NAME.upper(), school_style))
        story.append(Paragraph(SCHOOL_ADDRESS, addr_style))
        story.append(HRFlowable(
            width="100%", thickness=2,
            color=colors.HexColor("#1a3a5c")))
        story.append(Spacer(1, 8))

        # ── Exam info table ──
        total_marks = sum(q.get("marks", 1) for q in questions)
        now         = datetime.now().strftime("%d-%m-%Y %I:%M %p")
        info_data   = [
            [f"Class   : {class_}",
             f"Subject : {subject}",
             f"Date    : {now}"],
            [f"Lesson  : {lesson}",
             f"Teacher : {teacher_name}",
             f"Total   : {total_marks} Marks"],
        ]
        info_table = Table(info_data, colWidths=[5.5*cm, 7*cm, 5.5*cm])
        info_table.setStyle(TableStyle([
            ("FONTNAME",      (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE",      (0, 0), (-1, -1), 9),
            ("TEXTCOLOR",     (0, 0), (-1, -1), colors.HexColor("#333333")),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(info_table)
        story.append(Spacer(1, 6))
        story.append(HRFlowable(
            width="100%", thickness=1,
            color=colors.HexColor("#cccccc")))
        story.append(Spacer(1, 10))

        # ── Title ──
        title_style = ParagraphStyle(
            "title", fontSize=13, fontName="Helvetica-Bold",
            alignment=TA_CENTER, spaceAfter=12,
            textColor=colors.HexColor("#1a3a5c"))
        story.append(Paragraph("QUESTION PAPER", title_style))

        # ── Group questions by marks ──
        groups = {}
        for q in questions:
            groups.setdefault(q.get("marks", 1), []).append(q)

        section_titles = {
            1: "Section A  —  Choose the Best Answer",
            2: "Section B  —  Short Answer",
            3: "Section C  —  Brief Answer",
            5: "Section D  —  Long Answer / Essay",
        }

        q_style = ParagraphStyle(
            "q", fontSize=10, fontName="Helvetica",
            leading=14, spaceAfter=6, leftIndent=10)
        sec_style = ParagraphStyle(
            "sec", fontSize=11, fontName="Helvetica-Bold",
            textColor=colors.HexColor("#1a3a5c"),
            spaceBefore=10, spaceAfter=6)

        global_num = 1
        for marks in sorted(groups.keys()):
            qs       = groups[marks]
            sec_title = section_titles.get(
                marks, f"Section  —  {marks} Mark Questions")
            story.append(Paragraph(
                f"{sec_title}  "
                f"({len(qs)} × {marks} = {len(qs)*marks} marks)",
                sec_style))
            story.append(HRFlowable(
                width="100%", thickness=0.5,
                color=colors.HexColor("#aaaaaa")))
            story.append(Spacer(1, 4))

            for q in qs:
                m_label = (f"<font color='#888888' size='8'>"
                           f"[{marks} mark{'s' if marks > 1 else ''}]</font>")
                story.append(Paragraph(
                    f"{global_num}.&nbsp;&nbsp;{q.get('question', '')}  {m_label}",
                    q_style))
                story.append(Spacer(1, 4))
                global_num += 1

        # ── Footer ──
        story.append(Spacer(1, 20))
        story.append(HRFlowable(
            width="100%", thickness=1,
            color=colors.HexColor("#cccccc")))
        footer_style = ParagraphStyle(
            "footer", fontSize=9,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#666666"),
            spaceBefore=6)
        story.append(Paragraph(EXAM_FOOTER, footer_style))
        story.append(Paragraph(
            f"Generated on {now}  |  {SCHOOL_NAME}",
            footer_style))

        doc.build(story)
        print(f"[PDF] Generated: {output_path}")
        return output_path

    except Exception as e:
        print(f"[PDF] Generation failed: {e}")
        return ""


def _plain_text_fallback(class_, subject, lesson,
                          questions, output_path):
    """Plain .txt fallback when reportlab is unavailable."""
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"{SCHOOL_NAME}\n{'='*60}\n")
            f.write(f"Class: {class_}  Subject: {subject}  Lesson: {lesson}\n")
            f.write(f"{'='*60}\n\n")
            for i, q in enumerate(questions, 1):
                f.write(f"{i}. {q.get('question','')}  "
                        f"[{q.get('marks',1)} mark]\n\n")
            f.write(f"\n{EXAM_FOOTER}\n")
        return output_path
    except Exception as e:
        print(f"[PDF] Fallback write failed: {e}")
        return ""
