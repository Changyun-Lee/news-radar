# news-radar

음식료·화장품 뉴스 레이더입니다. GitHub Actions가 국내 네이버 뉴스와 해외 Google News RSS를 수집하고, OpenRouter 2단 판정 뒤 텔레그램으로 보냅니다.

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
- `STAGE1_MODEL`: 기본 `google/gemini-2.5-flash-lite`
- `STAGE2_MODEL`: 기본 `google/gemini-2.5-flash`

## 3. 수동 실행

GitHub `Actions` 탭에서 아래 워크플로를 선택한 뒤 `Run workflow`를 누릅니다.

- `Domestic news radar`: 국내 네이버 뉴스
- `Overseas news radar`: 해외 Google News RSS
- `Distill criteria`: 주간 기준 증류

## 4. Dry-run에서 실발송으로 전환

처음에는 `SEND_TELEGRAM=0`으로 둡니다. 이 상태에서는 텔레그램 API를 호출하지 않고 로그만 남기며, 중복 방지 DB에는 기록됩니다.

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

## 7. DART 추후 추가 지점

수집기는 `Item(source, stream, title, description, url, published_at)` 공통 스키마를 사용합니다. DART를 추가할 때는 새 수집기가 같은 `Item`을 반환하게 만들고, `news_radar.worker.collect_source()`에 새 source 분기를 넣으면 됩니다.

