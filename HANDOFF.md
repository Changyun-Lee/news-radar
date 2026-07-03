완료한 것
- 해외 Google News RSS item의 source url/link 도메인 기반 한국 언론사 차단 추가.
- config/overseas_source_blocklist.txt 신규 작성(.kr 중복 도메인 제외).
- 해외 스트림 로그에 skipped_kr 카운트 추가.
- MIN_SEND_IMPORTANCE env 설정(기본 4)과 should_send below_send_tier 문턱 추가.
- domestic/overseas GitHub Actions env에 MIN_SEND_IMPORTANCE 기본값 연결.
- README에 해외 출처 차단과 단독 발송급 문턱 설명 추가.

결정 근거
- source 태그 url을 우선 사용하고 없으면 link 도메인으로 폴백해 LLM 전에 중복 해외 노출을 제거.
- 블록리스트는 suffix 매칭으로 english.chosun.com 같은 하위 도메인을 상위 도메인 항목으로 차단.
- keep=false와 중복 억제 사유를 먼저 유지한 뒤 importance 문턱을 적용.
- 운영 data/monitor.sqlite3 보호를 위해 검증은 DATA_DIR 임시 경로로만 실행.

미해결 쟁점
- 실제 GitHub Secrets의 MIN_SEND_IMPORTANCE 값은 로컬에서 확인하지 않음.
- OPENROUTER_API_KEY 없이 RUN_ONCE 검증해 실제 LLM/Telegram 발송은 수행하지 않음.

다음 작업
- Claude Code에서 커밋 필요.
- GitHub Actions 환경에서 MIN_SEND_IMPORTANCE Secret 조정 여부 확인 필요.
