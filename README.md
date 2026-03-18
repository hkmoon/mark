# Minervini System

Mark Minervini style scan and single-ticker backtest skeleton.

## Files

- `minervini_system/config.py`: scan and backtest parameters
- `minervini_system/data.py`: OHLCV download helpers
- `minervini_system/indicators.py`: moving averages and range metrics
- `minervini_system/scanner.py`: trend template, VCP proxy, breakout detection
- `minervini_system/signals.py`: entry and exit signal frame builder
- `minervini_system/backtest.py`: single-ticker backtest engine
- `run_scan.py`: sample scanner entrypoint
- `run_backtest.py`: sample backtest entrypoint

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

```powershell
python run_scan.py
python run_backtest.py
```

## GitHub Actions Cloud Run

This repository includes a scheduled GitHub Actions workflow at
`.github/workflows/daily-market-scan.yml`.

- It runs on weekdays at `21:20 UTC`, which is after the U.S. market close year-round.
- It generates `scan_results.csv` and `scan_report.md`.
- It uploads both files as workflow artifacts.
- It also writes the markdown report into the GitHub Actions job summary.

Manual local equivalent:

```powershell
python run_cloud_scan.py
```

### GitHub setup

1. Create a GitHub repository for this project.
2. Push this code to the default branch.
3. Enable GitHub Actions for the repository.
4. Optionally use `workflow_dispatch` to test it immediately.

### Receiving the result

- Open the workflow run and read the job summary for a quick report.
- Download the `daily-market-scan` artifact to get the CSV and markdown report.
- The workflow can email the report to `hkmoon@me.com` once SMTP secrets are configured.

### Email setup

Add these repository secrets in GitHub:

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `EMAIL_FROM`

After those are set, each scheduled run will email:

- message body: `scan_report.md`
- attachments: `scan_report.md`, `scan_results.csv`
- recipient: `hkmoon@me.com`

For example, if you use Gmail SMTP, `EMAIL_FROM` is usually the Gmail address and `SMTP_PASSWORD` is an app password.

## Notes

- This is intentionally a simplified SEPA approximation.
- VCP detection is heuristic, not a full structural pattern recognizer.
- The backtest currently supports one ticker at a time.
- Good next steps are RS percentile ranking, market regime filters, and a multi-ticker portfolio engine.
