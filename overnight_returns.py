"""
Compute return of each future since the most recent 5pm Central time.
Reads futures tickers from an input CSV and writes returns to stdout or an output CSV.
Optional: email or text the report via --email (use carrier email-to-SMS for text).
"""

import argparse
import html as html_lib
import os
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import pandas as pd
import yfinance as yf
import pytz

CENTRAL = pytz.timezone("America/Chicago")


def get_most_recent_5pm_ct():
    """Return the datetime of the most recent 5pm Central (naive in CT, for comparison with yfinance)."""
    now_ct = pd.Timestamp.now(tz=CENTRAL)
    today_5pm = now_ct.replace(hour=17, minute=0, second=0, microsecond=0)
    if now_ct >= today_5pm:
        return today_5pm
    # Before 5pm today -> use yesterday 5pm
    from datetime import timedelta
    return today_5pm - timedelta(days=1)


def price_at_5pm_ct(ticker: str, ref_time: pd.Timestamp) -> float | None:
    """
    Get the price of the future at or just before the most recent 5pm CT.
    Uses hourly data when available; falls back to daily previous close.
    """
    ref_utc = ref_time.astimezone(pytz.UTC)
    ref_naive = ref_utc.replace(tzinfo=None)

    # Try hourly first (yfinance often gives ~7 days for 1h)
    try:
        hist = yf.Ticker(ticker).history(interval="1h", period="7d", timeout=10)
    except Exception:
        hist = pd.DataFrame()

    if not hist.empty:
        # Normalize to naive UTC for comparison with ref_naive
        if hist.index.tz is not None:
            hist = hist.copy()
            hist.index = hist.index.tz_convert(pytz.UTC).tz_localize(None)
        # Rows at or before ref time
        before = hist[hist.index <= ref_naive]
        if not before.empty:
            return float(before.iloc[-1]["Close"])

    # Fallback: daily data, use the close of the day that contains 5pm CT
    try:
        hist_d = yf.Ticker(ticker).history(period="5d", timeout=10)
    except Exception:
        return None

    if hist_d.empty or len(hist_d) < 2:
        return None
    # Previous close as proxy for "price at last 5pm CT"
    return float(hist_d["Close"].iloc[-2])


def current_price(ticker: str) -> float | None:
    """Latest available price (close or last)."""
    try:
        hist = yf.Ticker(ticker).history(period="5d", timeout=10)
    except Exception:
        return None
    if hist.empty:
        return None
    return float(hist["Close"].iloc[-1])


def ticker_name(ticker: str) -> str:
    """Return short name/description for the ticker from yfinance, or the ticker symbol if unavailable."""
    try:
        info = yf.Ticker(ticker).info
        return (
            info.get("shortName")
            or info.get("longName")
            or info.get("contractSymbol")
            or ticker
        )
    except Exception:
        return ticker


def format_table_aligned(df: pd.DataFrame) -> str:
    """Format DataFrame as a fixed-width table with headers aligned to column values."""
    df_str = df.astype(str).fillna("")
    cols = df_str.columns.tolist()
    # Column widths: at least header length, at least as wide as content
    widths = []
    for c in cols:
        content_max = int(df_str[c].str.len().max()) if len(df_str) else 0
        widths.append(max(len(str(c)), content_max))
    # Right-align: price_5pm_ct, price_current, return_since_5pm_ct
    right_cols = {"price_5pm_ct", "price_current", "return_since_5pm_ct"}
    lines = []
    for row in df_str.itertuples(index=False):
        parts = []
        for j, (c, w) in enumerate(zip(cols, widths)):
            val = str(row[j])
            if c in right_cols:
                parts.append(val.rjust(w))
            else:
                parts.append(val.ljust(w))
        lines.append("  ".join(parts))
    header_parts = [
        str(c).rjust(w) if c in right_cols else str(c).ljust(w)
        for c, w in zip(cols, widths)
    ]
    header = "  ".join(header_parts)
    return "\n".join([header, "  ".join("-" * w for w in widths), *lines])


def read_tickers_from_csv(path: str) -> list[str]:
    """Read ticker symbols from CSV. Supports column 'ticker', 'symbol', or first column."""
    df = pd.read_csv(path)
    if df.empty:
        return []
    for col in ("ticker", "symbol", "Ticker", "Symbol"):
        if col in df.columns:
            return df[col].astype(str).str.strip().dropna().tolist()
    return df.iloc[:, 0].astype(str).str.strip().dropna().tolist()


def dataframe_to_html_email(df: pd.DataFrame, title: str) -> str:
    """Return a full HTML document with a styled table for email. Rows are green if return > 0, red if return < 0."""
    return_col = "return_since_5pm_ct"
    cols = df.columns.tolist()

    def row_bg_style(row) -> str:
        val = row.get(return_col)
        if val is None or pd.isna(val) or val == "":
            return ""
        try:
            s = str(val).replace("%", "").replace(",", "").strip()
            if not s:
                return ""
            n = float(s)
            if n < 0:
                return ' style="background-color: #ffcccc;"'
            if n > 0:
                return ' style="background-color: #ccffcc;"'
        except (ValueError, TypeError):
            pass
        return ""

    th_cells = "".join(f"<th>{html_lib.escape(str(c))}</th>" for c in cols)
    header = f"<tr>{th_cells}</tr>"
    rows_html = [header]
    for _, row in df.iterrows():
        style = row_bg_style(row)
        cells = "".join(
            f"<td>{html_lib.escape(str(row[c]) if pd.notna(row[c]) else '')}</td>"
            for c in cols
        )
        rows_html.append(f"<tr{style}>{cells}</tr>")

    table_html = f'<table border="0">{chr(10).join(rows_html)}</table>'
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
table {{ border-collapse: collapse; font-family: sans-serif; font-size: 14px; }}
th, td {{ border: 1px solid #ccc; padding: 8px 12px; text-align: left; }}
th {{ background-color: #f0f0f0; font-weight: bold; }}
</style>
</head>
<body>
<h2>{title}</h2>
{table_html}
</body>
</html>"""


def send_email(
    to_address: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
    csv_path: str | None = None,
) -> None:
    """Send an email using SMTP. Credentials from env: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD."""
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD") or os.environ.get("SMTP_APP_PASSWORD")

    if not user or not password:
        print(
            "Error: Email requires SMTP_USER and SMTP_PASSWORD (or SMTP_APP_PASSWORD) in the environment.",
            file=sys.stderr,
        )
        print("  Example (Gmail): set SMTP_USER=you@gmail.com and SMTP_APP_PASSWORD=<app password>", file=sys.stderr)
        sys.exit(1)

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_address

    if body_html:
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(body_text, "plain"))
        alt.attach(MIMEText(body_html, "html"))
        msg.attach(alt)
    else:
        msg.attach(MIMEText(body_text, "plain"))

    if csv_path and Path(csv_path).is_file():
        from email.mime.application import MIMEApplication
        with open(csv_path, "rb") as f:
            part = MIMEApplication(f.read(), _subtype="csv")
        part.add_header("Content-Disposition", "attachment", filename=Path(csv_path).name)
        msg.attach(part)

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(user, password)
        server.sendmail(user, [to_address], msg.as_string())


def main():
    parser = argparse.ArgumentParser(
        description="Compute futures returns since the most recent 5pm Central time."
    )
    parser.add_argument(
        "input_csv",
        type=str,
        help="Path to CSV file with futures tickers (column: ticker or symbol, or first column).",
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="Optional output CSV path. If omitted, results are printed to stdout.",
    )
    parser.add_argument(
        "--email",
        type=str,
        metavar="ADDRESS",
        default=None,
        help="Send the report to this email (or use carrier email-to-SMS for text, e.g. 5551234567@vtext.com).",
    )
    args = parser.parse_args()

    input_path = Path(args.input_csv)
    if not input_path.is_file():
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    tickers = read_tickers_from_csv(str(input_path))
    if not tickers:
        print("Error: no tickers found in CSV.", file=sys.stderr)
        sys.exit(1)

    ref_time = get_most_recent_5pm_ct()
    rows = []

    for ticker in tickers:
        p_5pm = price_at_5pm_ct(ticker, ref_time)
        p_now = current_price(ticker)
        if p_5pm is None or p_now is None or p_5pm <= 0:
            ret_pct = None
        else:
            ret_decimal = (p_now - p_5pm) / p_5pm
            ret_pct = f"{round(ret_decimal * 100, 2)}%"
        rows.append({
            "ticker": ticker,
            "name": ticker_name(ticker),
            "price_5pm_ct": round(p_5pm, 2) if p_5pm is not None else None,
            "price_current": round(p_now, 2) if p_now is not None else None,
            "return_since_5pm_ct": ret_pct,
        })

    out = pd.DataFrame(rows)

    if args.output:
        out.to_csv(args.output, index=False)
        print(f"Wrote {len(out)} rows to {args.output}", file=sys.stderr)

    table_str = format_table_aligned(out)

    if not args.output:
        print(table_str)

    if args.email:
        ref_ct = get_most_recent_5pm_ct()
        subject = f"Futures returns since 5pm CT ({ref_ct.strftime('%Y-%m-%d %H:%M')} CT)"
        body_text = f"Futures returns since most recent 5pm Central\n\n{table_str}"
        body_html = dataframe_to_html_email(out, "Futures returns since most recent 5pm Central")
        send_email(args.email, subject, body_text, body_html=body_html, csv_path=args.output)
        print(f"Report sent to {args.email}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
