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
- `run_cloud_scan.py`: multi-market cloud scan entrypoint for GitHub Actions
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
- It also generates `scan_report.html` for web-friendly delivery.
- It stores daily market activity history in `report_history/scan_history.csv`.
- It uploads both files as workflow artifacts.
- It also writes the markdown report into the GitHub Actions job summary.
- It deploys the latest HTML report to GitHub Pages.

Manual local equivalent:

```powershell
python run_cloud_scan.py
```

### GitHub setup

1. Create a GitHub repository for this project.
2. Push this code to the default branch.
3. Enable GitHub Actions for the repository.
4. In repository settings, enable GitHub Pages with `GitHub Actions` as the source.
5. Optionally use `workflow_dispatch` to test it immediately.

### Receiving the result

- Open the workflow run and read the job summary for a quick report.
- Download the `daily-market-scan` artifact to get the CSV and markdown report.
- Open the GitHub Pages site to view the latest public HTML report.
- The workflow can send the report to Telegram once bot secrets are configured.

### Telegram setup

Add these repository secrets in GitHub:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

After those are set, each scheduled run will send a Telegram message with the latest report text:

- message body: `scan_report.md` content (truncated to fit Telegram limits if needed)
- recipient: the configured Telegram chat ID

## Notes

- This is intentionally a simplified SEPA approximation.
- VCP detection is heuristic, not a full structural pattern recognizer.
- The backtest currently supports one ticker at a time.
- The default scan universe includes both U.S. and South Korea tickers.
- The scan now applies a market regime check, RS percentile ranking, and a Minervini-style watchlist filter.
- South Korea is intentionally narrowed to a Korea AI and semiconductor leader group in the runner scripts.
- The U.S. universe is intentionally narrowed to an AI and semiconductor leader group in the runner scripts.
- Good next steps are RS percentile ranking, market regime filters, and a multi-ticker portfolio engine.

## iOS App Store Review 통과 체크리스트 (이 프로젝트를 앱으로 배포할 경우)

현재 저장소는 파이썬 스캐너/백테스트 도구이므로 그대로는 iOS 앱 심사 대상이 아닙니다.  
다만 이 기능을 iOS 앱으로 래핑해 App Store에 제출한다면 아래 항목을 우선 점검하세요.

### 1) 메타데이터/정책

- 앱 설명, 스크린샷, 기능이 실제 앱 동작과 일치해야 합니다.
- 금융 데이터의 출처와 지연 여부를 앱 내에 명시하세요.
- 투자 권유로 오해되지 않도록 `교육/정보 제공 목적` 고지를 넣으세요.
- 개인정보 처리방침(Privacy Policy) URL을 App Store Connect와 앱 내부에서 모두 제공하세요.
- 연락 가능한 지원 URL, 문의 메일, 데모 계정(로그인 필요 시)을 준비하세요.

### 2) 로그인/계정

- 소셜 로그인(구글/페이스북 등)을 제공하면 `Sign in with Apple` 제공 여부를 확인하세요.
- 앱에서 계정을 만들 수 있으면 앱 내 `계정 삭제` 기능도 제공해야 합니다.
- 비회원 사용이 가능한 기능은 로그인 강제를 피하세요.

### 3) 결제/수익화

- 디지털 콘텐츠/구독은 In-App Purchase(IAP)를 사용해야 합니다.
- 외부 결제 링크, 결제 유도 문구, 외부에서 더 저렴하다는 표현을 피하세요.
- 무료 체험, 자동 갱신, 해지 방법, 약관 링크를 결제 화면에 명확히 표기하세요.

### 4) 개인정보/권한

- ATT, 트래킹, 광고 SDK 사용 시 목적 설명과 권한 흐름을 정확히 구현하세요.
- 카메라/사진/푸시 등 권한은 실제로 필요한 시점에만 요청하세요.
- 수집 데이터와 목적이 App Privacy(영양성분표)와 1:1로 일치해야 합니다.

### 5) 앱 품질/기능

- 크래시, 빈 화면, 끊긴 링크, `미구현` 버튼이 없어야 합니다.
- 오프라인/네트워크 실패 시 사용자 친화적인 에러 메시지를 보여주세요.
- iPhone 다양한 해상도에서 레이아웃 깨짐이 없는지 확인하세요.
- 테스트 계정, 서버가 심사 기간 동안 항상 동작하도록 유지하세요.

### 6) 금융 앱 추가 권장

- 백테스트 결과는 과거 데이터 기반이며 미래 수익을 보장하지 않는다는 면책 문구를 표시하세요.
- 실시간 시세로 오인할 수 있는 UI(틱 단위 갱신처럼 보이는 표현)를 주의하세요.
- 국가별 규제(투자자문/중개 해당 여부)를 사전에 법률 검토하세요.
