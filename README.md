# DC 갤러리 티켓 알림 봇 (Interpark)

디시인사이드 갤러리를 주기적으로 감시하다가 **취소 / 취켓팅 / 양도 / 풀림** 같은 키워드가 담긴
새 글이 올라오면 **디스코드 웹훅 또는 텔레그램**으로 즉시 알림을 보내는 봇입니다.
알림에는 ① 글 제목 ② 게시글 다이렉트 링크 ③ 인터파크 예매창 링크 ④ 본문에서 추출한 좌석 요약이 담깁니다.

> ⚠️ 인터파크 좌석 자동 선택/자동 결제는 지원하지 않습니다(그리고 하지 않아야 합니다).
> 이 봇은 **"빨리 알아채고 손가락으로 직접 잡는"** 것까지만 도와줍니다.

---

## 1. 동작 방식

```
 ┌────────────┐   ①리스트 조회    ┌──────────────┐
 │ MonitorBot │ ───────────────▶ │  DcinsideScraper │  PC 실패 시 모바일(m.dcinside)로 폴백
 └─────┬──────┘                  └──────┬───────┘
       │ ②새 글만 추림(글번호 캐시)         │
       │◀───────────────  StateStore ────┘  state/last_seen.json
       │ ③제목 + 본문 키워드 매칭 (KeywordMatcher)
       │ ④좌석 정보 정규식 추출 (seatinfo)
       ▼
 ┌────────────────────────────┐
 │ Discord Webhook / Telegram │  제목 · 글 링크 · 예매 링크 · 좌석 요약
 └────────────────────────────┘
       │
       └─ ⑤랜덤 3~7초 대기 후 반복 (while True)
```

### 파일 구조

| 파일 | 역할 |
| --- | --- |
| `main.py` | CLI 진입점 (`--once`, `--dry-run`, `--test-notify`) |
| `dcbot/config.py` | `.env` 로딩 및 설정 검증 |
| `dcbot/http_client.py` | UA 로테이션 · Referer · 지수 백오프 등 **차단 회피 HTTP 계층** |
| `dcbot/scraper.py` | 리스트/본문 파싱 (PC → 모바일 폴백) |
| `dcbot/matcher.py` | 키워드 매칭 (공백 끼워넣기 회피 대응) |
| `dcbot/seatinfo.py` | 구역/열/번호/층/매수/가격 정규식 추출 |
| `dcbot/state.py` | 마지막 글 번호 + 알림 이력 캐시(원자적 저장) |
| `dcbot/notifier.py` | Discord / Telegram / Console 알림 |
| `dcbot/bot.py` | 무한 루프 · 예외 복구 · 종료 시그널 처리 |
| `dcbot/health.py` | Cloud Run 용 헬스체크 서버(`PORT` 있을 때만) |

---

## 2. 설치 (macOS 로컬)

```bash
# 1) 소스 받기
git clone <이 저장소 주소>
cd Interpark

# 2) 가상환경 (파이썬 3.9 이상, 3.11 권장)
python3 -m venv .venv
source .venv/bin/activate

# 3) 의존성 설치
pip install -r requirements.txt

# 4) 설정 파일 준비
cp .env.example .env
open -e .env      # 또는 vi .env
```

### 2-1. 디스코드 웹훅 발급 (권장, 1분)

1. 디스코드 앱에서 알림 받을 **서버 → 채널 → 톱니바퀴(채널 편집)** 클릭
2. **연동(Integrations) → 웹후크(Webhooks) → 새 웹후크** 생성
3. **웹후크 URL 복사** → `.env` 의 `DISCORD_WEBHOOK_URL=` 에 붙여넣기
4. 스마트폰에 디스코드 앱을 설치하고 해당 채널의 알림을 **"모든 메시지"** 로 설정

### 2-2. 텔레그램 봇 (선택)

1. 텔레그램에서 [@BotFather](https://t.me/BotFather) → `/newbot` → 토큰 발급 → `TELEGRAM_BOT_TOKEN`
2. 만든 봇과 대화방을 열고 아무 메시지나 전송 (봇은 먼저 말을 걸 수 없습니다)
3. [@userinfobot](https://t.me/userinfobot) 에게 `/start` → 내 `id` 확인 → `TELEGRAM_CHAT_ID`

> 두 채널을 모두 설정하면 **동시에** 알림이 갑니다.

### 2-3. 인터파크 예매 링크 지정

예매하려는 공연 페이지 URL 이 `https://tickets.interpark.com/goods/24012345` 라면:

```dotenv
INTERPARK_GOODS_CODE=24012345
```

상품 코드를 모르거나 다른 링크(예: 모바일 예매창)를 쓰고 싶다면 전체 URL 을 직접:

```dotenv
INTERPARK_BOOKING_URL=https://tickets.interpark.com/goods/24012345
```

---

## 3. 실행

```bash
# 알림 채널 연결 테스트 (샘플 알림 1건 발송)
python main.py --test-notify

# 실제 알림 없이 콘솔로만 확인 (파싱이 잘 되는지 점검)
python main.py --once --dry-run

# 본 실행 (무한 루프)
python main.py
```

종료는 `Ctrl + C`. 진행 중인 사이클을 마무리하고 상태를 저장한 뒤 안전하게 종료합니다.

**최초 실행 시에는 알림이 오지 않습니다.** 이미 올라와 있던 과거 글로 알림 폭탄을 맞지 않도록
현재 최신 글 번호를 "기준점"으로만 저장하고, 그 **이후에 올라온 글부터** 감시합니다.
(과거 글도 받고 싶다면 `.env` 에서 `NOTIFY_ON_FIRST_RUN=true`)

### macOS 에서 24시간 돌리기

```bash
# 터미널을 닫아도 계속 돌게 하려면
nohup python main.py >> bot.log 2>&1 &
tail -f bot.log        # 로그 확인
pkill -f "python main.py"   # 종료
```
> 맥북 뚜껑을 닫으면 잠들기 때문에, **시스템 설정 → 배터리 → "디스플레이가 꺼져도 자동으로 잠자지 않음"** 을 켜거나
> `caffeinate -is python main.py` 로 실행하세요. 진짜 24시간이 필요하면 아래 Docker/클라우드 배포를 권장합니다.

---

## 4. 주요 설정 (`.env`)

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `GALLERY_ID` | `vaundy0606` | 갤러리 URL 의 `?id=` 값 |
| `GALLERY_TYPE` | `mgallery` | `board`(정식) / `mgallery`(마이너) / `mini`(미니) |
| `KEYWORDS` | `취소,취켓팅,양도,풀림` | 쉼표로 구분. 자유롭게 추가 |
| `EXCLUDE_KEYWORDS` | (없음) | 이 단어가 있으면 알림 제외 (예: `구합니다,삽니다`) |
| `LIST_PAGES` | `1` | 사이클마다 확인할 리스트 페이지 수 |
| `POLL_MIN_SECONDS` / `POLL_MAX_SECONDS` | `3` / `7` | 사이클 간 **무작위** 대기 시간 |
| `FETCH_BODY` | `true` | 본문까지 검사(끄면 제목만 검사 → 요청 수 감소) |
| `MAX_BODY_FETCH_PER_CYCLE` | `5` | 한 사이클의 본문 조회 상한 |
| `NOTIFY_ON_FIRST_RUN` | `false` | 최초 실행 시 기존 글도 알릴지 |
| `STATE_FILE` | `state/last_seen.json` | 글 번호 캐시 경로 |
| `DRY_RUN` | `false` | `true` 면 실제 발송 없이 콘솔 출력 |

### 키워드 확장 예시

```dotenv
KEYWORDS=취소,취켓팅,양도,풀림,자리있,연석,정가양도,1층,플로어
EXCLUDE_KEYWORDS=구해요,구합니다,삽니다,사요
```

---

## 5. IP 차단 방지 설계 (중요)

디시인사이드는 짧은 간격의 반복 요청에 민감합니다. 이 봇에는 다음 방어 로직이 들어 있습니다.

- **브라우저 유사 헤더**: `User-Agent`, `Referer`, `Accept-Language: ko-KR`, `Sec-Fetch-*` 등 부착
- **User-Agent 로테이션**: 실패가 감지되면 UA를 바꾸고 세션 쿠키를 초기화
- **무작위 대기**: 사이클 간 3~7초 랜덤 + 요청 간 최소 간격(지터 포함)
- **지수 백오프**: 403/429/5xx·타임아웃 시 2s → 4s → 8s… 최대 `MAX_BACKOFF_SECONDS`
- **차단 페이지 감지**: HTTP 200 이어도 "비정상적인 접근" 등의 안내 페이지면 차단으로 간주
- **모바일 폴백**: PC 리스트가 막히면 `m.dcinside.com` 으로 자동 전환
- **본문 조회 상한**: 새 글이 쏟아져도 한 사이클에 최대 N건만 본문 조회(나머지는 다음 사이클)
- **세션 재사용**: `requests.Session` 으로 커넥션/쿠키 유지

> 💡 `POLL_MIN_SECONDS` 를 1초 미만으로 낮추지 마세요. 차단되면 알림 자체가 멈춥니다.
> 티켓팅 당일처럼 급할 때는 `3~5`, 평상시에는 `10~20` 정도를 권장합니다.

---

## 6. Docker 로 실행

```bash
# 빌드 & 실행 (.env 필요)
docker compose up -d --build

# 로그 확인
docker compose logs -f

# 중지
docker compose down
```

`./state` 디렉터리를 볼륨으로 물려두었기 때문에 컨테이너를 재시작해도 마지막 글 번호가 유지됩니다.

단독 도커 실행:

```bash
docker build -t dc-monitor .
docker run -d --name dc-monitor --restart unless-stopped \
  --env-file .env -v "$(pwd)/state:/app/state" dc-monitor
```

---

## 7. Google Cloud Run 배포

> Cloud Run **서비스**는 기본적으로 요청이 없으면 CPU가 멈춥니다. 무한 루프 봇을 돌리려면
> **최소 인스턴스 1 + CPU 상시 할당** 옵션이 필요합니다. (`PORT` 가 주입되면 봇이 자동으로
> 헬스체크용 HTTP 서버를 열어 Cloud Run 의 포트 리스닝 요구사항을 충족합니다.)

```bash
PROJECT_ID=your-project
REGION=asia-northeast3

# 1) 이미지 빌드 & 푸시
gcloud builds submit --tag gcr.io/$PROJECT_ID/dc-monitor

# 2) 시크릿 등록 (웹훅 URL 은 Secret Manager 권장)
echo -n "https://discord.com/api/webhooks/..." | \
  gcloud secrets create discord-webhook --data-file=-

# 3) 배포
gcloud run deploy dc-monitor \
  --image gcr.io/$PROJECT_ID/dc-monitor \
  --region $REGION \
  --min-instances 1 --max-instances 1 \
  --no-cpu-throttling \
  --memory 512Mi \
  --allow-unauthenticated \
  --set-env-vars "GALLERY_ID=vaundy0606,GALLERY_TYPE=mgallery,INTERPARK_GOODS_CODE=24012345" \
  --set-secrets "DISCORD_WEBHOOK_URL=discord-webhook:latest"
```

**상태 파일 주의**: Cloud Run 의 파일 시스템은 휘발성이라 인스턴스가 재시작되면
`state/last_seen.json` 이 사라집니다. 이때 봇은 다시 "기준점 잡기"부터 시작하므로
**과거 글 알림 폭탄은 발생하지 않지만**, 재시작 직전 몇 초 사이의 글은 놓칠 수 있습니다.
완전한 보존이 필요하면 Cloud Storage FUSE 볼륨을 `/app/state` 에 마운트하세요.

> 비용/단순함만 놓고 보면 **GCE e2-micro(무료 등급) + `docker compose up -d`** 또는
> 집에 있는 라즈베리파이가 이런 상시 구동 봇에는 더 잘 맞습니다.

---

## 8. 테스트

```bash
python -m unittest discover -s tests -v
# 또는
pip install pytest && pytest -q
```

네트워크 없이 도는 단위 테스트 35건이 포함되어 있습니다
(리스트/본문 파싱, 공지·광고 제외, 키워드 매칭, 좌석 정규식, 상태 캐시, 중복 알림 방지, 알림 payload).

---

## 9. 트러블슈팅

| 증상 | 원인 / 해결 |
| --- | --- |
| `설정 오류: 알림 채널이 없습니다` | `.env` 에 `DISCORD_WEBHOOK_URL` 또는 텔레그램 토큰/챗ID 를 채우세요 |
| `리스트에서 글을 가져오지 못했습니다` | 갤러리 ID/타입 확인. 마이너 갤러리는 `GALLERY_TYPE=mgallery` |
| `요청에 반복 실패했습니다` 반복 | 차단 가능성. `POLL_MIN/MAX_SECONDS` 를 늘리고 10~30분 쉬었다 재시작 |
| 알림이 안 옴 | `python main.py --test-notify` 로 채널부터 점검 |
| 같은 글 알림이 또 옴 | `state/last_seen.json` 이 지워졌는지 확인(도커라면 볼륨 마운트 확인) |
| 좌석 요약이 비어 있음 | 본문에 구역/열/번호/층 표기가 없으면 요약을 생략합니다(정상) |
| 처음 실행했는데 조용함 | 정상입니다. 기준점만 잡고 **그 이후 글**부터 알립니다 |

---

## 10. 주의사항

- 이 도구는 **개인적인 알림 용도**입니다. 짧은 주기의 과도한 요청은 대상 사이트에 부담을 주고
  IP 차단으로 이어집니다. 기본값보다 공격적으로 설정하지 마세요.
- 디시인사이드의 HTML 구조가 바뀌면 파서 수정이 필요합니다(`dcbot/scraper.py`).
- 티켓 양도 거래 시 사기 위험이 있으니 안전결제를 이용하세요.
