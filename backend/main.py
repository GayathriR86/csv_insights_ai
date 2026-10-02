"""
CSV Data Analyzer - FastAPI Backend
====================================
Endpoints for upload, analysis, LLM Q&A, and report generation.
"""

from __future__ import annotations

import traceback
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from analyzer import DataAnalyzer
from llm import ask_llm, generate_llm_insights
from report import generate_markdown_report, generate_pdf_report

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = FastAPI(
    title="CSV Data Analyzer API",
    description="Upload CSV → Analyze → Charts data → Outliers → Correlation → LLM Insights → Reports",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session (single-user demo). For multi-user use Redis / DB.
analyzer = DataAnalyzer()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class AskRequest(BaseModel):
    question: str
    api_key: str
    base_url: Optional[str] = None
    model: str = "gpt-4o-mini"


class LLMInsightsRequest(BaseModel):
    api_key: str
    base_url: Optional[str] = None
    model: str = "gpt-4o-mini"


class OutlierRequest(BaseModel):
    column: Optional[str] = None
    columns: Optional[List[str]] = None
    method: str = "iqr"  # iqr | zscore | isolation
    threshold: float = 3.0
    contamination: float = 0.05


class CorrelationRequest(BaseModel):
    columns: Optional[List[str]] = None
    method: str = "pearson"


class ChartRequest(BaseModel):
    chart_type: str  # histogram | bar | scatter | box
    column: Optional[str] = None
    x_col: Optional[str] = None
    y_col: Optional[str] = None
    color_col: Optional[str] = None
    bins: int = 30
    top_n: int = 15


class ReportRequest(BaseModel):
    format: str = "pdf"  # pdf | markdown
    include_llm: bool = False
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: str = "gpt-4o-mini"


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"status": "ok", "data_loaded": analyzer.df is not None}


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------
@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty file")
    result = analyzer.load_bytes(content, file.filename or "upload.csv")
    if not result.get("success"):
        raise HTTPException(400, result.get("message", "Failed to load file"))
    return result


# ---------------------------------------------------------------------------
# Overview & Describe
# ---------------------------------------------------------------------------
@app.get("/api/overview")
def get_overview():
    try:
        return analyzer.overview()
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/describe")
def get_describe():
    try:
        return analyzer.describe()
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/insights")
def get_rule_insights():
    try:
        return {"insights": analyzer.rule_based_insights()}
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---------------------------------------------------------------------------
# Outliers
# ---------------------------------------------------------------------------
@app.post("/api/outliers")
def get_outliers(req: OutlierRequest):
    try:
        method = req.method.lower()
        if method == "iqr":
            if not req.column:
                raise HTTPException(400, "column is required for IQR")
            return analyzer.outliers_iqr(req.column)
        elif method == "zscore":
            if not req.column:
                raise HTTPException(400, "column is required for Z-Score")
            return analyzer.outliers_zscore(req.column, req.threshold)
        elif method == "isolation":
            return analyzer.outliers_isolation_forest(req.columns, req.contamination)
        else:
            raise HTTPException(400, f"Unknown method: {req.method}")
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


# ---------------------------------------------------------------------------
# Correlation
# ---------------------------------------------------------------------------
@app.post("/api/correlation")
def get_correlation(req: CorrelationRequest):
    try:
        return analyzer.correlation(req.columns, req.method)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---------------------------------------------------------------------------
# Chart data (frontend builds Plotly charts)
# ---------------------------------------------------------------------------
@app.post("/api/chart-data")
def get_chart_data(req: ChartRequest):
    try:
        t = req.chart_type.lower()
        if t == "histogram":
            if not req.column:
                raise HTTPException(400, "column required")
            return analyzer.histogram_data(req.column, req.bins)
        elif t == "bar":
            if not req.column:
                raise HTTPException(400, "column required")
            return analyzer.value_counts_data(req.column, req.top_n)
        elif t == "scatter":
            if not req.x_col or not req.y_col:
                raise HTTPException(400, "x_col and y_col required")
            return analyzer.scatter_data(req.x_col, req.y_col, req.color_col)
        elif t == "series":
            if not req.column:
                raise HTTPException(400, "column required")
            return {"column": req.column, "values": analyzer.get_column_series(req.column)}
        else:
            raise HTTPException(400, f"Unknown chart_type: {req.chart_type}")
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---------------------------------------------------------------------------
# LLM - Ask Your Data
# ---------------------------------------------------------------------------
@app.post("/api/ask")
def ask_data(req: AskRequest):
    try:
        if analyzer.df is None:
            raise HTTPException(400, "No data loaded")
        result = ask_llm(
            analyzer,
            req.question,
            api_key=req.api_key,
            base_url=req.base_url,
            model=req.model,
        )
        return result
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/llm-insights")
def llm_insights(req: LLMInsightsRequest):
    try:
        if analyzer.df is None:
            raise HTTPException(400, "No data loaded")
        result = generate_llm_insights(
            analyzer,
            api_key=req.api_key,
            base_url=req.base_url,
            model=req.model,
        )
        return result
    except Exception as e:
        raise HTTPException(500, str(e))


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
@app.post("/api/report")
def create_report(req: ReportRequest):
    try:
        if analyzer.df is None:
            raise HTTPException(400, "No data loaded")

        llm_text = None
        if req.include_llm and req.api_key:
            llm_res = generate_llm_insights(
                analyzer, req.api_key, req.base_url, req.model
            )
            if llm_res.get("success"):
                llm_text = llm_res["answer"]

        if req.format.lower() == "pdf":
            pdf_bytes = generate_pdf_report(analyzer, llm_insights=llm_text)
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": "attachment; filename=data_analysis_report.pdf"
                },
            )
        else:
            md = generate_markdown_report(analyzer, llm_insights=llm_text)
            return Response(
                content=md.encode("utf-8"),
                media_type="text/markdown",
                headers={
                    "Content-Disposition": "attachment; filename=data_analysis_report.md"
                },
            )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, str(e))


# ---------------------------------------------------------------------------
# Sample data endpoint (optional demo)
# ---------------------------------------------------------------------------
@app.get("/api/sample-preview")
def sample_preview(n: int = 20):
    try:
        return {"rows": analyzer.get_full_data_sample(n)}
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---------------------------------------------------------------------------
# Serve frontend (optional)
# ---------------------------------------------------------------------------
from pathlib import Path
from fastapi.staticfiles import StaticFiles

_frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if _frontend_dir.is_dir():
    app.mount("/app", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
