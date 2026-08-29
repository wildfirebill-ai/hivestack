"""Data & analytics — CSV/JSON profiling, log normalization, anomaly detection
(z-score / IQR, plus Isolation Forest when scikit-learn is available). All CPU,
fully offline."""

from __future__ import annotations

import csv
import io
import json
import re
import statistics
from typing import Any

import numpy as np


# ------------------------------------------------------------------ analysis
def analyze(content: str, name: str = "data") -> dict:
    text = content.strip()
    if not text:
        return {"error": "empty input"}
    # JSON detection (array of records)
    if text.startswith("["):
        try:
            records = json.loads(text)
            return _profile_records(records, name)
        except json.JSONDecodeError:
            pass
    if text.startswith("{"):
        try:
            obj = json.loads(text)
            records = obj if isinstance(obj, list) else [obj]
            return _profile_records(records, name)
        except json.JSONDecodeError:
            pass
    # CSV
    try:
        rows = list(csv.reader(io.StringIO(text)))
    except Exception as exc:  # noqa: BLE001
        return {"error": f"could not parse input: {exc}"}
    if not rows:
        return {"error": "no rows"}
    header = rows[0]
    body = rows[1:]
    cols = [{ "name": header[i] if i < len(header) else f"col{i}",
              "type": "numeric", "mean": None, "min": None, "max": None, "top": [] }
            for i in range(max(1, len(header)))]
    for i in range(len(cols)):
        raw = [r[i] for r in body if i < len(r)]
        nums = [float(x) for x in raw if _isnum(x)]
        if nums:
            cols[i]["mean"] = round(statistics.mean(nums), 3)
            cols[i]["min"] = min(nums)
            cols[i]["max"] = max(nums)
        elif raw:
            from collections import Counter

            top = Counter(raw).most_common(3)
            cols[i]["type"] = "categorical"
            cols[i]["top"] = [{"value": k, "count": v} for k, v in top]
    return {
        "name": name,
        "rows": len(body),
        "columns": len(cols),
        "header": header,
        "col_stats": cols,
        "insights": [
            f"{len(body)} rows x {len(cols)} columns",
        ],
    }


def _isnum(x: str) -> bool:
    try:
        float(x)
        return True
    except (TypeError, ValueError):
        return False


def _profile_records(records: list[dict], name: str) -> dict:
    if not records:
        return {"error": "empty records"}
    keys = list(records[0].keys())
    col_stats = []
    for k in keys:
        vals = [r.get(k) for r in records]
        nums = [v for v in vals if isinstance(v, (int, float))]
        if nums:
            col_stats.append({"name": k, "type": "numeric", "mean": round(statistics.mean(nums), 3),
                              "min": min(nums), "max": max(nums)})
        else:
            from collections import Counter

            c = Counter(str(v) for v in vals if v is not None).most_common(3)
            col_stats.append({"name": k, "type": "categorical", "top": [{"value": a, "count": b} for a, b in c]})
    missing = sum(1 for r in records for v in r.values() if v is None or v == "")
    return {"name": name, "rows": len(records), "columns": len(keys), "header": keys,
            "col_stats": col_stats, "insights": [f"{len(records)} records, {missing} missing values"]}


# ------------------------------------------------------------------ log normalization
_ACCESS_RE = re.compile(
    r'^([\d\.\-]+) \S+ \S+ \[([^\]]+)\] "([A-Z]+) (\S+) ([^\"]*)" (\d{3}) (\d+)'
)


def normalize_logs(lines: list[str]) -> dict:
    records: list[dict] = []
    key_counts: dict[str, int] = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        rec: dict[str, Any] = {"source_line": line[:200]}
        if line.startswith("{") or line.startswith("["):
            try:
                rec["json"] = json.loads(line)
            except json.JSONDecodeError:
                pass
        m = _ACCESS_RE.match(line)
        if m:
            rec["access"] = {
                "ip": m.group(1), "ts": m.group(2), "method": m.group(3),
                "path": m.group(4), "status": int(m.group(6)), "bytes": int(m.group(7)),
            }
        # key=value pairs
        kv = dict(re.findall(r"(\w+)=([^\s,]+)", line))
        if kv and len(kv) >= 2:
            rec["kv"] = kv
        for k in rec:
            key_counts[k] = key_counts.get(k, 0) + 1
        records.append(rec)
    return {"records": len(records), "features": sorted(key_counts.items(), key=lambda x: -x[1]),
            "sample": records[:5]}


# ------------------------------------------------------------------ anomaly detection
def detect_zscore(points: list[float], threshold: float = 3.0) -> list[int]:
    arr = np.asarray(points, dtype=np.float64)
    if arr.size < 3 or np.std(arr) == 0:
        return []
    z = np.abs((arr - np.mean(arr)) / np.std(arr))
    return [int(i) for i, v in enumerate(z) if v > threshold]


def detect_iqr(points: list[float]) -> list[int]:
    q1, q3 = np.percentile(points, [25, 75])
    iqr = q3 - q1
    if iqr == 0:
        return []
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    return [i for i, v in enumerate(points) if v < lo or v > hi]


def anomalies(series: dict[str, list[float]], method: str = "hybrid") -> dict:
    out: dict[str, dict] = {}
    for name, points in series.items():
        pts = [float(p) for p in points]
        flagged: set[int] = set()
        detect = "zscore"
        if method == "isolation":
            try:
                from sklearn.ensemble import IsolationForest

                X = np.asarray(pts, dtype=np.float64).reshape(-1, 1)
                preds = IsolationForest(contamination=0.05, random_state=0).fit_predict(X)
                flagged = {int(i) for i, p in enumerate(preds) if int(p) == -1}
                detect = "isolation_forest"
            except Exception:  # noqa: BLE001
                flagged = set(detect_zscore(pts))
                detect = "zscore(fallback)"
        else:
            flagged |= set(detect_zscore(pts))
            if method in ("iqr", "hybrid"):
                flagged |= set(detect_iqr(pts))
            detect = "hybrid" if method == "hybrid" else method
        out[name] = {"n": len(pts), "method": detect, "anomalies": sorted(flagged)[:200]}
    return out