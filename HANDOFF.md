완료한 것
- CHANGE-1: Telegram 인라인 키보드에 `🔁 이미 앎` 버튼과 `fb:k:{row_id}` callback_data 추가.
- CHANGE-1: feedback callback 파서를 추가하고 `k`를 `known` 라벨로 저장하도록 수집 경로 갱신.
- CHANGE-1: distill 기준 갱신 프롬프트에 `known` 라벨 의미와 사용 제한을 명시.
- CHANGE-1: README에 세 피드백 버튼 설명 1줄 추가.
- CHANGE-2: stage2 프롬프트에 검색 키워드/기사 주체 혼동 방지, 명시 사실 한정, 불명확 주체 제목 유지 제약 추가.
- CHANGE-2: `telegram_title_ko`에도 동일 원칙을 적용하도록 stage2 프롬프트에 명시.

결정 근거
- feedback 테이블의 `label`은 TEXT NOT NULL이며 CHECK 제약이 없어 DB 스키마 변경 없이 `known` 저장 가능.
- callback 파싱을 함수로 분리해 실제 수집 경로와 검증 명령이 같은 로직을 사용.
- stage1은 요청 범위상 변경하지 않음.

미해결 쟁점
- OPENROUTER_API_KEY/TELEGRAM_BOT_TOKEN 없이 검증하여 실제 LLM 응답과 실제 Telegram 발송은 미검증.
- 필수 RUN_ONCE 검증으로 `data/monitor.sqlite3`가 갱신됨.

다음 작업
- Claude Code에서 커밋 필요.
- GitHub Secrets 환경에서 실제 stage2 응답과 Telegram callback 수거 확인 필요.
