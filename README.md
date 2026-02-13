# Overnight Futures Returns (since 5pm Central)

This project reads an input CSV of financial futures tickers and outputs each contract’s **return since the most recent 5pm Central time**.

## Setup

```bash
pip install -r requirements.txt
```

## Input CSV

The CSV must list one futures ticker per row. Supported formats:

- A column named **`ticker`** or **`symbol`** (case-insensitive), or
- No header: first column is treated as the ticker.

Example `futures_input.csv`:

```csv
ticker
ES=F
NQ=F
GC=F
CL=F
```

Use the same symbols as on Yahoo Finance. Examples:
- Continuous: `ES=F`, `NQ=F`, `GC=F`, `CL=F`
- Specific contracts: `ESH6`, `NQM6`, `GCJ6` (Yahoo may use slightly different codes; use the symbol that returns data).

## Usage

**Print results to stdout:**

```bash
python overnight_returns.py futures_input.csv
```

**Write results to a CSV:**

```bash
python overnight_returns.py futures_input.csv -o returns.csv
```

**Email or text the report to yourself:**

```bash
python overnight_returns.py futures_input.csv --email you@example.com
```

- **Email:** Use your normal email address. You must set SMTP environment variables (see below).
- **Text (SMS):** Use your carrier’s email-to-SMS address (e.g. `5551234567@vtext.com` for Verizon, `5551234567@tmomail.net` for T-Mobile). Same `--email` flag; the script sends an email to that address and your carrier delivers it as SMS.

You can combine options: `-o returns.csv --email you@example.com` writes the CSV, sends an email with the table in the body, and attaches the CSV.

**Return period (`--period`):**

| Value  | Description |
|--------|--------------|
| `5pm`  | Return since the most recent 5pm Central (default). |
| `wtd`  | Week-to-date (since start of current week, Monday). |
| `mtd`  | Month-to-date (since the 1st of the current month). |

Example: `python overnight_returns.py futures_input.csv --period wtd`

### SMTP setup (for email/text)

The script uses your SMTP server to send mail. Set these environment variables:

| Variable           | Example (Gmail)     | Description        |
|-------------------|---------------------|--------------------|
| `SMTP_HOST`       | `smtp.gmail.com`    | SMTP server (default if unset) |
| `SMTP_PORT`       | `587`               | Port (default 587) |
| `SMTP_USER`       | `you@gmail.com`     | Your email         |
| `SMTP_PASSWORD` or `SMTP_APP_PASSWORD` | *app password* | Password or Gmail app password |

**Gmail:** Use an [App Password](https://support.google.com/accounts/answer/185833), not your normal password. Enable 2FA first, then create the app password.

**PowerShell (one-time):**
```powershell
$env:SMTP_USER = "you@gmail.com"
$env:SMTP_APP_PASSWORD = "your-app-password"
python overnight_returns.py futures_input.csv --email 5551234567@vtext.com
```

## Output

For each ticker you get:

| Column          | Description                                                                 |
|-----------------|-----------------------------------------------------------------------------|
| `ticker`        | Futures symbol                                                              |
| `name`          | Name/description of the contract (from Yahoo Finance)                       |
| `price_start`   | Price at the period start (2 decimal places)                                |
| `price_current` | Latest available price (2 decimal places)                                   |
| `return_pct`    | Return over the period, in percent (e.g. `3.78%`, `-1.25%`)                  |

The **5pm Central** reference is computed in `America/Chicago` (CST/CDT). The script uses hourly data when available to approximate the price at that time; otherwise it uses the previous trading day’s close.

## Notes

- Data is pulled from Yahoo Finance via `yfinance`. Availability and symbols depend on Yahoo.
- If no hourly bar exists at 5pm CT, the script falls back to the previous day’s close.
- Missing or invalid data for a ticker yields `NaN` in the output for that row.
