"""
PDF / CSV 報告輸出。
PDF 使用 ReportLab，會自動尋找系統中文字型；CSV 為 UTF-8 with BOM 供 Excel。
"""
from __future__ import annotations

import csv
import io
import time
from pathlib import Path
from typing import Dict, List, Optional

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image,
    )
    REPORTLAB_OK = True
except Exception:  # pragma: no cover
    REPORTLAB_OK = False


_CJK_FONT_CANDIDATES = [
    (r"C:\Windows\Fonts\msjh.ttc", "MSJH"),
    (r"C:\Windows\Fonts\msjhbd.ttc", "MSJHBD"),
    (r"C:\Windows\Fonts\msyh.ttc", "MSYH"),
    (r"C:\Windows\Fonts\simsun.ttc", "SimSun"),
    (r"C:\Windows\Fonts\mingliu.ttc", "MingLiU"),
    ("/System/Library/Fonts/STHeiti Medium.ttc", "STHeiti"),
    ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", "WQYMicroHei"),
]


def _register_cjk_font() -> str:
    if not REPORTLAB_OK:
        return "Helvetica"
    for path, name in _CJK_FONT_CANDIDATES:
        if Path(path).exists():
            try:
                pdfmetrics.registerFont(TTFont(name, path))
                return name
            except Exception:
                continue
    return "Helvetica"


def generate_pdf_report(
    user_name: str,
    age: int,
    exercise: str,
    score: float,
    joint_scores: Dict[str, Dict[str, float]],
    messages: List[str],
    rep_count: Optional[int] = None,
    neural_scores: Optional[Dict[str, float]] = None,
    overlay_png: Optional[bytes] = None,
) -> bytes:
    """產生 PDF 報告位元組。若 ReportLab 未安裝，回傳簡易純文字 bytes。"""
    if not REPORTLAB_OK:
        return _fallback_text_report(
            user_name, age, exercise, score, joint_scores, messages, rep_count
        )

    font_name = _register_cjk_font()
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"],
                        fontName=font_name, fontSize=18, spaceAfter=8)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"],
                        fontName=font_name, fontSize=13, spaceBefore=6, spaceAfter=6)
    body = ParagraphStyle("body", parent=styles["Normal"],
                          fontName=font_name, fontSize=10, leading=14)
    small = ParagraphStyle("sm", parent=body, fontSize=9, textColor=colors.grey)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
    )
    elems: list = []

    elems.append(Paragraph("智慧居家復健 — 單次評估報告", h1))
    elems.append(Paragraph(time.strftime("報告時間：%Y-%m-%d %H:%M"), small))
    elems.append(Spacer(1, 10))

    # 基本資訊
    info_rows = [
        ["使用者", user_name, "年齡", str(age)],
        ["動作", exercise, "整體分數", f"{score:.1f} / 100"],
    ]
    if rep_count is not None:
        info_rows.append(["偵測次數", str(rep_count), "", ""])
    if neural_scores:
        for k, v in neural_scores.items():
            info_rows.append([f"{k} 分數", f"{v:.1f}", "", ""])

    t = Table(info_rows, colWidths=[3 * cm, 5 * cm, 3 * cm, 5 * cm])
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), font_name, 10),
        ("BACKGROUND", (0, 0), (0, -1), colors.lightgrey),
        ("BACKGROUND", (2, 0), (2, -1), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elems.append(t)
    elems.append(Spacer(1, 14))

    # 視覺化影像
    if overlay_png:
        try:
            img = Image(io.BytesIO(overlay_png), width=14 * cm, height=10 * cm, kind="proportional")
            elems.append(Paragraph("關節偏差視覺化", h2))
            elems.append(img)
            elems.append(Spacer(1, 12))
        except Exception:
            pass

    # 建議
    elems.append(Paragraph("個人化建議", h2))
    if messages:
        for m in messages:
            elems.append(Paragraph("• " + m, body))
    else:
        elems.append(Paragraph("各關節皆在可接受範圍內，請繼續保持。", body))
    elems.append(Spacer(1, 12))

    # 關節詳細
    elems.append(Paragraph("關節偏差統計", h2))
    rows = [["關節", "平均偏差 (°)", "最大偏差 (°)", "取樣點"]]
    for k, v in joint_scores.items():
        rows.append([k, f"{v['mean_dev']:.1f}", f"{v['max_dev']:.1f}", str(v.get("samples", "-"))])
    jt = Table(rows, colWidths=[4 * cm, 4 * cm, 4 * cm, 4 * cm])
    jt.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), font_name, 10),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
    ]))
    elems.append(jt)

    elems.append(Spacer(1, 18))
    elems.append(Paragraph(
        "※ 本報告由 AI 系統輔助生成，僅供參考。若有疼痛或異常請諮詢專業醫療人員。",
        small,
    ))

    doc.build(elems)
    return buf.getvalue()


def _fallback_text_report(user_name, age, exercise, score, joint_scores, messages, rep_count):
    lines = [
        "智慧居家復健 - 單次評估報告",
        time.strftime("報告時間：%Y-%m-%d %H:%M"),
        "",
        f"使用者：{user_name}",
        f"年齡：{age}",
        f"動作：{exercise}",
        f"整體分數：{score:.1f} / 100",
    ]
    if rep_count is not None:
        lines.append(f"偵測次數：{rep_count}")
    lines += ["", "個人化建議："]
    lines += [f"  - {m}" for m in messages] or ["  - 動作品質良好。"]
    lines += ["", "關節偏差統計："]
    for k, v in joint_scores.items():
        lines.append(f"  {k}: 平均 {v['mean_dev']:.1f}°, 最大 {v['max_dev']:.1f}°")
    return ("\n".join(lines)).encode("utf-8")


def generate_history_csv(sessions: List[Dict]) -> bytes:
    """將訓練紀錄輸出為 CSV（UTF-8 with BOM，支援 Excel 開啟）。"""
    buf = io.StringIO()
    buf.write("﻿")  # BOM
    writer = csv.writer(buf)
    writer.writerow(["時間", "動作", "分數", "偵測次數", "各關節平均偏差"])
    for s in sessions:
        ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(s["ts"]))
        joints = s.get("joints", {}) or {}
        joint_summary = " | ".join(
            f"{k}:{v['mean_dev']:.1f}°" for k, v in joints.items()
        )
        writer.writerow([
            ts,
            s.get("exercise", ""),
            f"{s.get('score', 0):.1f}",
            s.get("rep_count", "-"),
            joint_summary,
        ])
    return buf.getvalue().encode("utf-8")
