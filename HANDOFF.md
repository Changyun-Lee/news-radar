완료한 것
- news_radar 패키지 생성: 수집기, SQLite store, OpenRouter 2단 judge, Telegram, feedback, distill, worker.
- config/overseas_queries.txt와 prompts/criteria_ko.md 작성.
- GitHub Actions 3개 작성: domestic.yml, overseas.yml, distill.yml.
- README.md 작성: Secrets, 수동 실행, SEND_TELEGRAM 전환, 기업/쿼리 수정, DART 추가 지점.
- data/monitor.sqlite3 생성: 드라이런 seed 후 seen_items=125, worker_state=2.
- 검증 완료: compileall 통과, RSS 단독 파싱, RUN_ONCE 드라이런 2회, CLI help/invalid 인자 확인.

결정 근거
- 사용자 계약의 표준라이브러리만 사용 조건에 맞춰 urllib, sqlite3, xml.etree만 사용.
- Naver는 원본의 직접 API 우선, k-skill-proxy 폴백 구조 유지.
- source별 initialized 상태를 분리해 국내/해외 첫 실행 seed를 각각 유지.
- MAX_LLM_CALLS_PER_RUN 초과분은 seen 기록 없이 skip 처리.
- OPENROUTER_API_KEY 미설정 시 seen 기록 후 LLM skip 처리.

미해결 쟁점
- OPENROUTER_API_KEY 없이 검증했으므로 실제 2단 LLM 판정 응답은 미검증.
- TELEGRAM_BOT_TOKEN 없이 검증했으므로 실제 sendMessage/getUpdates는 미검증.
- GitHub 원격 저장소와 Secrets 등록 후 Actions push 동작은 미검증.

다음 작업
- Claude Code에서 커밋 필요.
- GitHub Secrets 등록 후 workflow_dispatch dry-run 실행.
- SEND_TELEGRAM=1 전환 전 Telegram 채팅 ID와 봇 권한 확인.
