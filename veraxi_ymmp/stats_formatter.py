"""Formatting for YouTube stats report."""
from __future__ import annotations
import csv
import io
import json
from typing import Any, Dict, List
from .ports import VideoStatsReport


def format_stats(report: VideoStatsReport, format_type: str) -> str:
    """Format the report into string based on the format_type."""
    if format_type == "json":
        return format_json(report)
    elif format_type == "csv":
        return format_csv(report)
    elif format_type == "table":
        return format_table(report)
    else:
        raise ValueError(f"Unknown format type: {format_type}")


def format_json(report: VideoStatsReport) -> str:
    """Format report into JSON."""
    data: Dict[str, Any] = {
        "schema_version": 1,
        "fetched_at": report.fetched_at,
        "start_date": report.start_date,
        "end_date": report.end_date,
        "granularity": report.granularity,
        "metrics": report.metrics,
        "rows": []
    }

    for row in report.rows:
        row_data: Dict[str, Any] = {
            "video_id": row.video_id,
            "date": row.date,
        }
        for metric in report.metrics:
            row_data[metric] = row.metrics.get(metric)
        data["rows"].append(row_data)

    return json.dumps(data, ensure_ascii=False, indent=2)


def format_csv(report: VideoStatsReport) -> str:
    """Format report into CSV string."""
    buf = io.StringIO()
    writer = csv.writer(buf)

    header = ["video_id", "date"] + report.metrics
    writer.writerow(header)

    # Sort rows by video_id, date
    sorted_rows = sorted(report.rows, key=lambda r: (r.video_id, r.date or ""))

    for row in sorted_rows:
        csv_row: List[Any] = [row.video_id, row.date if row.date else ""]
        for m in report.metrics:
            val = row.metrics.get(m)
            csv_row.append(val if val is not None else "")
        writer.writerow(csv_row)

    return buf.getvalue()


def _format_duration(seconds: float) -> str:
    """Format seconds into m:ss."""
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m}:{s:02d}"


def format_table(report: VideoStatsReport) -> str:
    """Format report into a human-readable table."""
    # Determine column widths
    cols = ["video_id", "date"] + report.metrics
    widths = [len(c) for c in cols]

    formatted_rows = []

    sorted_rows = sorted(report.rows, key=lambda r: (r.video_id, r.date or ""))
    for row in sorted_rows:
        f_row = [row.video_id, str(row.date) if row.date else "Total"]

        for i, m in enumerate(report.metrics):
            val = row.metrics.get(m)
            if val is None:
                s_val = "n/a"
            elif m == "averageViewDuration":
                s_val = _format_duration(float(val))
            elif m == "averageViewPercentage":
                s_val = f"{val:.1f}%"
            elif isinstance(val, float) and val.is_integer():
                s_val = str(int(val))
            else:
                s_val = str(val)

            f_row.append(s_val)
            widths[i + 2] = max(widths[i + 2], len(s_val))

        formatted_rows.append(f_row)
        widths[0] = max(widths[0], len(f_row[0]))
        widths[1] = max(widths[1], len(f_row[1]))

    # Build string
    lines = []

    # Header
    h_parts = []
    for i, c in enumerate(cols):
        h_parts.append(c.ljust(widths[i]))
    lines.append(" | ".join(h_parts))

    # Separator
    s_parts = []
    for w in widths:
        s_parts.append("-" * w)
    lines.append("-+-".join(s_parts))

    # Rows
    for f_row in formatted_rows:
        r_parts = []
        for i, v in enumerate(f_row):
            r_parts.append(v.ljust(widths[i]))
        lines.append(" | ".join(r_parts))

    return "\n".join(lines)
