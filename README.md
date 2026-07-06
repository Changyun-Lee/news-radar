# news-radar

음식료·화장품 뉴스 레이더입니다. GitHub Actions가 국내 네이버 뉴스, DART 공시, 해외 Google News RSS, 공개 텔레그램 채널을 수집하고, OpenRouter 판정 뒤 텔레그램으로 보냅니다.

## 1. GitHub 저장소 만들기

1. GitHub에서 새 Public 저장소를 만듭니다.
2. 이 폴더 내용을 저장소에 올립니다.
3. Actions 탭에서 워크플로 실행 권한을 켭니다.

## 2. Secrets 등록

경로: `Settings` → `Secrets and variables` → `Actions` → `New repository secret`

필수 키 5개:

- `KSKILL_PROXY_BASE_URL`: 네이버 뉴스 프록시. 예: `https://k-skill-proxy.nomadamas.org`
- `TELEGRAM_BOT_TOKEN`: 텔레그램 봇 토큰
- `TELEGRAM_CHAT_ID`: 발송 대상 채팅 ID
- `OPENROUTER_API_KEY`: OpenRouter API 키
- `SEND_TELEGRAM`: 처음에는 `0`, 실발송 전환 시 `1`

선택 키:

- `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`: 네이버 공식 검색 API를 직접 쓸 때만 등록
- `API_K_DART`: DART 공시 수집용 OpenDART 인증키. 없으면 DART 수집기는 `[dart:skip]` 로그 후 상태 초기화를 하지 않습니다.
- `STAGE1_MODEL`: 기본 `google/gemini-2.5-flash-lite`
- `STAGE2_MODEL`: 기본 `google/gemini-2.5-flash`
- `MENTOR_SHARED_HOURS`: 사수 공유 뉴스 억제 이력을 stage2에 넣을 조회 시간. 기본 `48`
- `MENTOR_SHARED_LIMIT`: stage2에 넣을 사수 공유 뉴스 제목 수. 기본 `30`

## 3. 수동 실행

GitHub `Actions` 탭에서 아래 워크플로를 선택한 뒤 `Run workflow`를 누릅니다.

- `Domestic news radar`: 국내 네이버 뉴스 실행 뒤 DART 공시도 같은 10분 창에서 실행
- `Overseas news radar`: 해외 Google News RSS
- `Telegram channel news radar`: 공개 텔레그램 채널
- `Distill criteria`: 주간 기준 증류

## 4. Dry-run에서 실발송으로 전환

처음에는 `SEND_TELEGRAM=0`으로 둡니다. 이 상태에서는 텔레그램 API를 호출하지 않고 로그만 남기며, 중복 방지 DB에는 기록됩니다.

실발송 메시지에는 `👍 유용`, `👎 버림`, `🔁 이미 앎` 피드백 버튼이 붙습니다.

실발송 준비가 되면 GitHub Secrets의 `SEND_TELEGRAM` 값을 `1`로 바꿉니다.

## 5. 기업 추가/삭제

`config/companies.txt`를 수정합니다.

형식:

```text
회사명 | 검색별칭1,검색별칭2 | 메모
```

기업당 네이버 쿼리는 첫 번째 별칭 1개만 사용합니다. 줄을 삭제하면 다음 실행부터 수집 대상에서 빠집니다.

## 6. 해외 쿼리 수정

`config/overseas_queries.txt`를 수정합니다.

형식:

```text
stream | Google News 검색식
```

`stream`은 해외 이력 비교 단위입니다.

## 7. 텔레그램 채널 추가/삭제

`config/telegram_channels.txt`를 수정합니다.

형식:

```text
stream | handle | mode
```

- `handle`은 `https://t.me/s/<handle>` 공개 웹 페이지에서 접근 가능한 채널명입니다.
- `mode=llm`은 수집한 텍스트 메시지를 전부 기존 LLM 파이프라인으로 보냅니다.
- `mode=keyword`는 `config/breaking_keywords.txt`와 `config/companies.txt`의 기업명·별칭에 걸린 메시지만 LLM 파이프라인으로 보냅니다.
- `mode=suppress`는 메시지를 발송 후보로 만들지 않고 `tgsuppress` 이력으로 저장합니다. URL 포함 줄이 2개 이상이면 줄 단위로 분해해 stage2 중복 억제에만 사용합니다.
- 채널별 마지막 수집 `message_id`는 `worker_state`의 `tg_high_water:<handle>` 키로 저장됩니다.

## 8. 속보 키워드 관리

`config/breaking_keywords.txt`를 수정합니다.

형식:

```text
키워드
```

한 줄에 하나씩 적고, `#`로 주석을 남길 수 있습니다. 매칭은 대소문자를 구분하지 않으며 하이픈·공백 제거 비교를 병행하므로 `K-뷰티`, `K 뷰티`, `K뷰티`가 같은 키워드로 처리됩니다. `config/companies.txt`의 회사명과 별칭은 실행 시 자동 병합됩니다.

## 9. DART 공시 수집

DART 수집기는 `config/companies.txt`의 감시 기업별 최근 공시를 OpenDART `list.json`에서 조회합니다. 기본 조회 기간은 최근 2일이며 `DART_LOOKBACK_DAYS` 환경변수로 조정할 수 있습니다.

- `API_K_DART` Secret이 필요합니다. 로컬에서는 같은 이름의 환경변수 또는 `DART_API_KEY`를 사용할 수 있습니다.
- DART `corpCode.zip`은 매 실행 받지 않고 `DATA_DIR/dart_corp_codes.json` 캐시에 기업명별 `corp_code`를 저장합니다.
- `corp_code`가 없거나 정확명/별칭 매칭이 안 되는 비상장·외감 법인은 `[dart:skip-nocode]` 로그 후 건너뜁니다.
- 보고서명에서 공백과 `ㆍ`, `·`, `.`를 제거한 뒤 `임원주요주주특정증권등소유상황보고서`가 포함되면 LLM 전 단계에서 제외합니다. `주식등의대량보유상황보고서`는 별도 보고서이므로 유지합니다.
- DART 항목은 감시 기업의 공식 공시라 stage1 관련성 필터를 건너뛰고 stage2 중요도 판정으로 바로 들어갑니다.

## 10. 운영 필터

- 해외 Google News RSS는 `<source url>` 도메인(없으면 link 도메인)이 `.kr`이거나 `config/overseas_source_blocklist.txt`에 suffix 매칭되면 LLM 전에 제외합니다.
- 텔레그램 `mode=keyword` 채널은 키워드 게이트 통과분만 중복 체크와 LLM 판정으로 들어갑니다. 게이트 탈락분은 seen DB에 기록하지 않습니다.
- Telegram 발송은 `MIN_SEND_IMPORTANCE`(기본 `4`) 이상만 허용하며, 낮은 판정은 저장만 하고 `below_send_tier`로 미발송 처리합니다.

