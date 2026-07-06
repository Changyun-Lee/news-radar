완료한 것
- `config/telegram_channels.txt`에 `kyobo-shared | kyobofnbcosmetic | suppress` 추가.
- `mode=suppress` 파서 허용 및 tgchannel 수집/페이지네이션/high-water/finalize 흐름 재사용.
- suppress 메시지를 URL 포함 줄 2개 이상이면 URL 줄 단위 제목으로 분해, 아니면 첫 줄 120자로 저장.
- suppress 레코드를 `seen_items` dedupe 후 `judgments`에 `source=tgsuppress`, `decision=mentor_shared`, `sent=0`으로 기록.
- `MENTOR_SHARED_HOURS` 기본 48, `MENTOR_SHARED_LIMIT` 기본 30 추가 및 Actions env 연결.
- worker 시작 시 최근 사수 공유 제목을 1회 조회해 모든 source stage2 payload에 `mentor_shared_recent`로 주입.
- README에 suppress 모드와 새 env 2개 설명 추가.

결정 근거
- suppress 채널은 `CollectionResult.items`에 넣지 않아 judge/send 경로에 진입하지 않음.
- dedupe_key는 제목 casefold 후 공백/하이픈 제거 문자열의 sha256으로 저장해 수정/재게시 중복을 차단.
- 기존 `judgments`/30일 prune/stream 스코프를 재사용해 별도 테이블 없이 억제 이력을 격리.
- high-water는 suppress 레코드 저장 뒤 기존 finalize가 전진시키도록 candidate mark만 넘김.

미해결 쟁점
- 운영 OpenRouter/Telegram 실발송은 수행하지 않음.
- 1회차 검증 중 beautylog 공개 페이지가 1회 타임아웃됐고 2회차에는 정상 fetch됨.

다음 작업
- Claude Code에서 변경 파일 리뷰 후 커밋 필요.
