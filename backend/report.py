"""
Professional PDF report generation using fpdf2.
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any, Dict, List, Optional

from fpdf import FPDF

from analyzer import DataAnalyzer


class PDFReport(FPDF):
    """Custom PDF with header/footer."""

    def __init__(self, title: str = "CSV Data Analysis Report"):
        super().__init__()
        self.report_title = title
        self.set_auto_page_break(auto=True, margin=18)

    def header(self):
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(60, 60, 100)
        self.cell(0, 8, self.report_title, align="L")
        self.set_font("Helvetica", "", 9)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, datetime.now().strftime("%Y-%m-%d %H:%M"), align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(100, 100, 180)
        self.set_line_width(0.4)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(6)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def section_title(self, text: str):
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(40, 40, 90)
        self.cell(0, 9, text, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(80, 80, 160)
        self.set_line_width(0.3)
        self.line(10, self.get_y(), 80, self.get_y())
        self.ln(4)

    def body_text(self, text: str):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 5.5, text)
        self.ln(2)

    def bullet(self, text: str):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(30, 30, 30)
        self.cell(6, 5.5, "-")
        self.multi_cell(0, 5.5, text)

    def kv(self, key: str, value: str):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(50, 50, 50)
        self.cell(55, 6, key)
        self.set_font("Helvetica", "", 10)
        self.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")


def generate_pdf_report(
    analyzer: DataAnalyzer,
    llm_insights: Optional[str] = None,
    include_preview: bool = True,
) -> bytes:
    """
    Build a complete PDF report and return raw bytes.
    """
    overview = analyzer.overview()
    describe = analyzer.describe()
    insights = analyzer.rule_based_insights()

    pdf = PDFReport(title="CSV Data Analysis Report")
    pdf.alias_nb_pages()
    pdf.add_page()

    # ---- Title ----
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(50, 50, 120)
    pdf.cell(0, 12, "CSV Data Analysis Report", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 7, f"File: {overview['filename']}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.cell(
        0,
        7,
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        new_x="LMARGIN",
        new_y="NEXT",
        align="C",
    )
    pdf.ln(6)

    # ---- 1. Overview ----
    pdf.section_title("1. Dataset Overview")
    pdf.kv("Rows", f"{overview['rows']:,}")
    pdf.kv("Columns", str(overview["columns"]))
    pdf.kv("Numeric columns", str(len(overview["numeric_columns"])))
    pdf.kv("Categorical columns", str(len(overview["categorical_columns"])))
    pdf.kv("Missing cells", f"{overview['missing_total']:,}")
    pdf.kv("Memory", f"{overview['memory_mb']} MB")
    pdf.ln(3)

    # ---- 2. Column Information ----
    pdf.section_title("2. Column Information")
    # Simple table header
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(230, 230, 245)
    col_w = [45, 28, 22, 22, 22, 22]
    headers = ["Column", "Type", "Non-Null", "Nulls", "Null %", "Unique"]
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 6, h, border=1, fill=True, align="C")
    pdf.ln()
    pdf.set_font("Helvetica", "", 7)
    for col in overview["column_info"]:
        vals = [
            str(col["name"])[:22],
            str(col["dtype"])[:12],
            str(col["non_null"]),
            str(col["nulls"]),
            str(col["null_pct"]),
            str(col["unique"]),
        ]
        for i, v in enumerate(vals):
            pdf.cell(col_w[i], 5.5, v, border=1, align="C")
        pdf.ln()
    pdf.ln(4)

    # ---- 3. Numeric Summary ----
    if "numeric" in describe:
        pdf.section_title("3. Numeric Summary")
        num_stats = describe["numeric"]
        # keys are stat names, values are dicts col -> value
        stats_order = ["count", "mean", "std", "min", "25%", "50%", "75%", "max"]
        cols = list(next(iter(num_stats.values())).keys()) if num_stats else []
        # Limit columns for page width
        cols = cols[:6]
        if cols:
            pdf.set_font("Helvetica", "B", 7)
            pdf.set_fill_color(230, 230, 245)
            pdf.cell(22, 5.5, "Stat", border=1, fill=True, align="C")
            w = (170 - 22) / len(cols)
            for c in cols:
                pdf.cell(w, 5.5, str(c)[:12], border=1, fill=True, align="C")
            pdf.ln()
            pdf.set_font("Helvetica", "", 7)
            for stat in stats_order:
                if stat not in num_stats:
                    continue
                pdf.cell(22, 5.5, stat, border=1, align="C")
                for c in cols:
                    val = num_stats[stat].get(c, "")
                    try:
                        txt = f"{float(val):.3g}"
                    except Exception:
                        txt = str(val)[:10]
                    pdf.cell(w, 5.5, txt, border=1, align="C")
                pdf.ln()
        pdf.ln(4)

    # ---- 4. Rule-based Insights ----
    pdf.section_title("4. Automated Insights")
    for ins in insights:
        prefix = {"info": "[INFO]", "warning": "[WARN]", "success": "[OK]"}.get(ins["type"], "[•]")
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(40, 40, 80)
        pdf.cell(0, 6, f"{prefix} {ins['title']}", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(40, 40, 40)
        pdf.multi_cell(0, 5, ins["text"])
        pdf.ln(1)

    # ---- 5. LLM Insights (if provided) ----
    if llm_insights:
        pdf.add_page()
        pdf.section_title("5. AI Narrative Insights (LLM)")
        # Strip markdown-ish for plain PDF
        clean = (
            llm_insights.replace("**", "")
            .replace("__", "")
            .replace("### ", "")
            .replace("## ", "")
            .replace("# ", "")
            .replace("`", "")
        )
        pdf.body_text(clean)

    # ---- 6. Correlation Snapshot ----
    try:
        corr = analyzer.correlation()
        if corr["pairs"]:
            if not llm_insights:
                pdf.ln(2)
            else:
                pass
            pdf.section_title("6. Top Correlations")
            for p in corr["pairs"][:12]:
                pdf.bullet(f"{p['feature_a']}  ↔  {p['feature_b']}  :  {p['correlation']:.4f}")
    except Exception:
        pass

    # ---- 7. Data Preview ----
    if include_preview:
        pdf.add_page()
        pdf.section_title("7. Data Preview (first 15 rows)")
        preview = overview["preview"][:15]
        if preview:
            cols = list(preview[0].keys())[:6]  # limit width
            pdf.set_font("Helvetica", "B", 6)
            pdf.set_fill_color(230, 230, 245)
            w = 190 / len(cols)
            for c in cols:
                pdf.cell(w, 5, str(c)[:14], border=1, fill=True, align="C")
            pdf.ln()
            pdf.set_font("Helvetica", "", 6)
            for row in preview:
                for c in cols:
                    val = row.get(c, "")
                    txt = "" if val is None else str(val)[:14]
                    pdf.cell(w, 5, txt, border=1, align="C")
                pdf.ln()

    # ---- Footer note ----
    pdf.ln(8)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(120, 120, 120)
    pdf.multi_cell(
        0,
        4,
        "This report was generated automatically by CSV Data Analyzer. "
        "Always validate critical findings with domain expertise.",
    )

    # Output bytes
    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()


def generate_markdown_report(
    analyzer: DataAnalyzer,
    llm_insights: Optional[str] = None,
) -> str:
    """Generate a Markdown report (for download as .md)."""
    overview = analyzer.overview()
    describe = analyzer.describe()
    insights = analyzer.rule_based_insights()

    lines = [
        "# CSV Data Analysis Report",
        f"**File:** {overview['filename']}  ",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ",
        "",
        "## 1. Dataset Overview",
        f"- **Rows:** {overview['rows']:,}",
        f"- **Columns:** {overview['columns']}",
        f"- **Numeric columns:** {len(overview['numeric_columns'])}",
        f"- **Categorical columns:** {len(overview['categorical_columns'])}",
        f"- **Missing cells:** {overview['missing_total']:,}",
        f"- **Memory:** {overview['memory_mb']} MB",
        "",
        "## 2. Column Information",
        "",
        "| Column | Type | Non-Null | Nulls | Null % | Unique |",
        "|--------|------|----------|-------|--------|--------|",
    ]
    for col in overview["column_info"]:
        lines.append(
            f"| {col['name']} | {col['dtype']} | {col['non_null']} | "
            f"{col['nulls']} | {col['null_pct']} | {col['unique']} |"
        )

    if "numeric" in describe:
        lines.append("")
        lines.append("## 3. Numeric Summary")
        lines.append("")
        lines.append("```")
        # Simple text table
        import pandas as pd

        df = analyzer.df
        lines.append(df[overview["numeric_columns"]].describe().round(4).to_string())
        lines.append("```")

    lines.append("")
    lines.append("## 4. Automated Insights")
    for ins in insights:
        lines.append(f"### {ins['title']}")
        lines.append(ins["text"])
        lines.append("")

    if llm_insights:
        lines.append("## 5. AI Narrative Insights (LLM)")
        lines.append(llm_insights)
        lines.append("")

    try:
        corr = analyzer.correlation()
        lines.append("## 6. Top Correlations")
        for p in corr["pairs"][:15]:
            lines.append(f"- `{p['feature_a']}` ↔ `{p['feature_b']}`: **{p['correlation']:.4f}**")
    except Exception:
        pass

    lines.append("")
    lines.append("---")
    lines.append("*Generated by CSV Data Analyzer*")
    return "\n".join(lines)
