"""
Core data analysis engine.
Handles: overview, stats, outliers, correlation, insights.
"""

from __future__ import annotations

import io
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler


class DataAnalyzer:
    """Stateful analyzer that keeps the loaded DataFrame in memory."""

    def __init__(self) -> None:
        self.df: Optional[pd.DataFrame] = None
        self.filename: str = ""

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------
    def load_bytes(self, content: bytes, filename: str) -> Dict[str, Any]:
        """Load CSV or Excel from raw bytes."""
        try:
            if filename.lower().endswith((".xlsx", ".xls")):
                self.df = pd.read_excel(io.BytesIO(content))
            else:
                # Try common encodings
                for enc in ("utf-8", "latin-1", "iso-8859-1", "cp1252"):
                    try:
                        self.df = pd.read_csv(io.BytesIO(content), encoding=enc)
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    raise ValueError("Could not decode file. Save as UTF-8 and retry.")

            self.filename = filename
            return {"success": True, "message": f"Loaded {filename}", **self.overview()}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def load_dataframe(self, df: pd.DataFrame, filename: str = "uploaded.csv") -> None:
        self.df = df
        self.filename = filename

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _require_df(self) -> pd.DataFrame:
        if self.df is None or self.df.empty:
            raise ValueError("No data loaded. Upload a file first.")
        return self.df

    def numeric_cols(self) -> List[str]:
        df = self._require_df()
        return df.select_dtypes(include=[np.number]).columns.tolist()

    def categorical_cols(self) -> List[str]:
        df = self._require_df()
        return df.select_dtypes(include=["object", "category", "bool"]).columns.tolist()

    # ------------------------------------------------------------------
    # Overview
    # ------------------------------------------------------------------
    def overview(self) -> Dict[str, Any]:
        df = self._require_df()
        missing = df.isnull().sum()
        return {
            "filename": self.filename,
            "rows": int(len(df)),
            "columns": int(len(df.columns)),
            "numeric_columns": self.numeric_cols(),
            "categorical_columns": self.categorical_cols(),
            "column_info": [
                {
                    "name": col,
                    "dtype": str(df[col].dtype),
                    "non_null": int(df[col].count()),
                    "nulls": int(missing[col]),
                    "null_pct": round(float(missing[col] / len(df) * 100), 2),
                    "unique": int(df[col].nunique()),
                }
                for col in df.columns
            ],
            "missing_total": int(missing.sum()),
            "memory_mb": round(float(df.memory_usage(deep=True).sum() / 1024**2), 2),
            "preview": df.head(20).replace({np.nan: None}).to_dict(orient="records"),
            "columns_list": list(df.columns),
        }

    # ------------------------------------------------------------------
    # Descriptive statistics
    # ------------------------------------------------------------------
    def describe(self) -> Dict[str, Any]:
        df = self._require_df()
        numeric = self.numeric_cols()
        cats = self.categorical_cols()

        result: Dict[str, Any] = {}
        if numeric:
            desc = df[numeric].describe().round(4)
            result["numeric"] = desc.to_dict()
        if cats:
            result["categorical"] = df[cats].describe().to_dict()
        return result

    # ------------------------------------------------------------------
    # Outlier detection
    # ------------------------------------------------------------------
    def outliers_iqr(self, column: str) -> Dict[str, Any]:
        df = self._require_df()
        if column not in df.columns:
            raise ValueError(f"Column '{column}' not found")
        series = df[column].dropna()
        if not pd.api.types.is_numeric_dtype(series):
            raise ValueError(f"Column '{column}' is not numeric")

        q1 = float(series.quantile(0.25))
        q3 = float(series.quantile(0.75))
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        mask = (df[column] < lower) | (df[column] > upper)
        n = int(mask.sum())

        return {
            "method": "IQR",
            "column": column,
            "lower_bound": round(lower, 4),
            "upper_bound": round(upper, 4),
            "outlier_count": n,
            "outlier_pct": round(n / len(df) * 100, 2),
            "outlier_indices": df.index[mask].tolist()[:500],  # cap
            "outlier_rows": df.loc[mask].head(100).replace({np.nan: None}).to_dict(orient="records"),
        }

    def outliers_zscore(self, column: str, threshold: float = 3.0) -> Dict[str, Any]:
        df = self._require_df()
        if column not in df.columns:
            raise ValueError(f"Column '{column}' not found")
        series = df[column].dropna()
        if not pd.api.types.is_numeric_dtype(series):
            raise ValueError(f"Column '{column}' is not numeric")

        z = np.abs(stats.zscore(series))
        mask_series = pd.Series(False, index=df.index)
        mask_series.loc[series.index] = z > threshold
        n = int(mask_series.sum())

        return {
            "method": "Z-Score",
            "column": column,
            "threshold": threshold,
            "outlier_count": n,
            "outlier_pct": round(n / len(df) * 100, 2),
            "outlier_indices": df.index[mask_series].tolist()[:500],
            "outlier_rows": df.loc[mask_series].head(100).replace({np.nan: None}).to_dict(orient="records"),
        }

    def outliers_isolation_forest(
        self, columns: Optional[List[str]] = None, contamination: float = 0.05
    ) -> Dict[str, Any]:
        df = self._require_df()
        numeric = self.numeric_cols()
        if not numeric:
            raise ValueError("No numeric columns available")

        cols = columns or numeric[: min(8, len(numeric))]
        cols = [c for c in cols if c in numeric]
        if len(cols) < 2:
            raise ValueError("Need at least 2 numeric columns")

        sub = df[cols].fillna(df[cols].median())
        scaler = StandardScaler()
        scaled = scaler.fit_transform(sub)
        iso = IsolationForest(contamination=contamination, random_state=42, n_estimators=100)
        preds = iso.fit_predict(scaled)
        mask = preds == -1
        n = int(mask.sum())

        return {
            "method": "Isolation Forest",
            "columns": cols,
            "contamination": contamination,
            "outlier_count": n,
            "outlier_pct": round(n / len(df) * 100, 2),
            "outlier_indices": df.index[mask].tolist()[:500],
            "outlier_rows": df.loc[mask].head(100).replace({np.nan: None}).to_dict(orient="records"),
            "labels": mask.tolist(),  # for frontend scatter coloring
        }

    # ------------------------------------------------------------------
    # Correlation
    # ------------------------------------------------------------------
    def correlation(
        self, columns: Optional[List[str]] = None, method: str = "pearson"
    ) -> Dict[str, Any]:
        df = self._require_df()
        numeric = self.numeric_cols()
        if len(numeric) < 2:
            raise ValueError("Need at least 2 numeric columns")

        cols = columns or numeric
        cols = [c for c in cols if c in numeric]
        if len(cols) < 2:
            raise ValueError("Need at least 2 valid numeric columns")

        corr = df[cols].corr(method=method).round(4)
        matrix = corr.values.tolist()
        labels = list(corr.columns)

        # Ranked pairs
        pairs = []
        for i in range(len(labels)):
            for j in range(i + 1, len(labels)):
                pairs.append(
                    {
                        "feature_a": labels[i],
                        "feature_b": labels[j],
                        "correlation": float(corr.iloc[i, j]),
                    }
                )
        pairs.sort(key=lambda x: abs(x["correlation"]), reverse=True)

        return {
            "method": method,
            "labels": labels,
            "matrix": matrix,
            "pairs": pairs[:30],
        }

    # ------------------------------------------------------------------
    # Rule-based AI Insights (always available, no LLM needed)
    # ------------------------------------------------------------------
    def rule_based_insights(self) -> List[Dict[str, str]]:
        df = self._require_df()
        insights: List[Dict[str, str]] = []
        n_rows, n_cols = df.shape
        numeric = self.numeric_cols()
        cats = self.categorical_cols()

        insights.append(
            {
                "type": "info",
                "title": "Dataset Overview",
                "text": f"Dataset has {n_rows:,} rows and {n_cols} columns "
                f"({len(numeric)} numeric, {len(cats)} categorical).",
            }
        )

        # Missing
        missing = df.isnull().sum()
        missing_pct = (missing / n_rows * 100).round(2)
        high = missing_pct[missing_pct > 20]
        if len(high) > 0:
            cols_str = ", ".join(f"{c} ({v}%)" for c, v in high.items())
            insights.append(
                {
                    "type": "warning",
                    "title": "High Missing Values",
                    "text": f"Columns with >20% missing data: {cols_str}. Consider imputation or dropping.",
                }
            )
        elif missing.sum() > 0:
            insights.append(
                {
                    "type": "info",
                    "title": "Missing Values",
                    "text": f"Total missing cells: {int(missing.sum()):,} "
                    f"({missing.sum() / (n_rows * n_cols) * 100:.2f}% of dataset).",
                }
            )
        else:
            insights.append(
                {
                    "type": "success",
                    "title": "Complete Data",
                    "text": "No missing values detected. Excellent data quality.",
                }
            )

        # Duplicates
        n_dupes = int(df.duplicated().sum())
        if n_dupes > 0:
            insights.append(
                {
                    "type": "warning",
                    "title": "Duplicate Rows",
                    "text": f"Found {n_dupes:,} fully duplicate rows ({n_dupes / n_rows * 100:.1f}%).",
                }
            )

        # Skew & outliers
        for col in numeric[:6]:
            series = df[col].dropna()
            if len(series) < 10:
                continue
            skew = float(series.skew())
            if abs(skew) > 1.5:
                direction = "right" if skew > 0 else "left"
                insights.append(
                    {
                        "type": "info",
                        "title": f"Skewed: {col}",
                        "text": f"{col} is highly {direction}-skewed (skewness={skew:.2f}). "
                        "Consider log-transform or robust statistics.",
                    }
                )
            q1, q3 = series.quantile(0.25), series.quantile(0.75)
            iqr = q3 - q1
            mask = (series < q1 - 1.5 * iqr) | (series > q3 + 1.5 * iqr)
            pct = mask.sum() / len(series) * 100
            if pct > 5:
                insights.append(
                    {
                        "type": "warning",
                        "title": f"Outliers in {col}",
                        "text": f"{col} has {pct:.1f}% outliers (IQR method).",
                    }
                )

        # Categorical
        for col in cats[:5]:
            n_unique = df[col].nunique()
            if n_unique == 1:
                insights.append(
                    {
                        "type": "warning",
                        "title": f"Constant Column: {col}",
                        "text": f"{col} has only one unique value — no information gain.",
                    }
                )
            elif n_unique > n_rows * 0.9:
                insights.append(
                    {
                        "type": "info",
                        "title": f"High Cardinality: {col}",
                        "text": f"{col} has {n_unique} unique values (almost unique). Possible ID column.",
                    }
                )
            else:
                top_pct = df[col].value_counts().iloc[0] / n_rows * 100
                if top_pct > 80:
                    insights.append(
                        {
                            "type": "info",
                            "title": f"Imbalanced: {col}",
                            "text": f"{col} is dominated by one value ({top_pct:.0f}% of rows).",
                        }
                    )

        # Strong correlations
        if len(numeric) >= 2:
            corr = df[numeric].corr()
            high_corr = []
            for i in range(len(corr.columns)):
                for j in range(i + 1, len(corr.columns)):
                    val = corr.iloc[i, j]
                    if abs(val) > 0.8:
                        high_corr.append((corr.columns[i], corr.columns[j], val))
            if high_corr:
                pairs = ", ".join(f"{a} & {b} ({v:.2f})" for a, b, v in high_corr[:5])
                insights.append(
                    {
                        "type": "info",
                        "title": "Strong Correlations",
                        "text": f"Strong linear relationships: {pairs}. Watch for multicollinearity.",
                    }
                )

        insights.append(
            {
                "type": "info",
                "title": "Memory Footprint",
                "text": f"Dataset uses approximately {df.memory_usage(deep=True).sum() / 1024**2:.2f} MB.",
            }
        )
        return insights

    # ------------------------------------------------------------------
    # Chart data helpers (for frontend Plotly)
    # ------------------------------------------------------------------
    def histogram_data(self, column: str, bins: int = 30) -> Dict[str, Any]:
        df = self._require_df()
        series = df[column].dropna()
        counts, edges = np.histogram(series, bins=bins)
        return {
            "column": column,
            "counts": counts.tolist(),
            "bin_edges": edges.tolist(),
            "mean": float(series.mean()),
            "median": float(series.median()),
            "std": float(series.std()),
        }

    def value_counts_data(self, column: str, top_n: int = 15) -> Dict[str, Any]:
        df = self._require_df()
        vc = df[column].value_counts().head(top_n)
        return {
            "column": column,
            "labels": [str(x) for x in vc.index.tolist()],
            "counts": vc.values.tolist(),
        }

    def scatter_data(
        self, x_col: str, y_col: str, color_col: Optional[str] = None, sample: int = 2000
    ) -> Dict[str, Any]:
        df = self._require_df()
        cols = [x_col, y_col]
        if color_col:
            cols.append(color_col)
        sub = df[cols].dropna()
        if len(sub) > sample:
            sub = sub.sample(sample, random_state=42)
        result = {
            "x": sub[x_col].tolist(),
            "y": sub[y_col].tolist(),
            "x_label": x_col,
            "y_label": y_col,
        }
        if color_col:
            result["color"] = sub[color_col].astype(str).tolist()
            result["color_label"] = color_col
        return result

    def get_full_data_sample(self, n: int = 100) -> List[Dict]:
        df = self._require_df()
        return df.head(n).replace({np.nan: None}).to_dict(orient="records")

    def get_column_series(self, column: str) -> List[Any]:
        df = self._require_df()
        return df[column].replace({np.nan: None}).tolist()
