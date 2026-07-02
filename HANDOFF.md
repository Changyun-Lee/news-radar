완료한 것
- FIX-1: Telegram 발송 예외를 항목 단위로 처리하고 실패 시 judgment/seen/sent를 남기지 않도록 수정.
- FIX-1: feedback 수집 실패를 비치명화하고 judge 네트워크 오류 처리를 RuntimeError/OSError 경로로 통합.
- FIX-2: 연속 judge 오류 3회 시 실행 내 LLM 서킷브레이커를 열고 남은 항목을 unseen으로 스킵.
- FIX-3: initialized 타임스탬프 재기록 방지, 수집 시도 완료 시만 초기화, prune 일 1회 가드 적용.
- FIX-4: distill 기준문서 펜스 제거, 최소 라인/해외/국내 헤더 검증, 실패 시 기존 파일 유지.
- FIX-5/6: stage2 send 필드 제거, keep=false 미발송 반영, stage1에도 criteria_ko.md 주입.
- FIX-7: 3개 workflow에 always 커밋 단계, data 디렉터리 가드, rebase abort/retry/DB 충돌 복구 추가.
- FIX-8: worker 수집 디스패치를 COLLECTORS 레지스트리로 중앙화하고 수집기 예외 처리를 모듈 내부로 이동.
- 공용화: OpenRouter 호출/오류 처리, JSON shape helpers, fenced text 추출, clean_text/pubDate 파서 분리.

결정 근거
- OPENROUTER_API_KEY 없음 경로는 기존처럼 seen/judgment 기록을 유지.
- CallLimitReached는 예산 소진으로 보고 unseen 재시도 정책을 유지.
- rebase 중 DB 충돌은 재적용 중인 로컬 상태 커밋 쪽 파일을 유지하도록 --theirs 경로를 사용.
- setup-python 제거 후 workflow 실행 명령은 runner 기본 python3로 변경.

미해결 쟁점
- 검증 중 라이브 RSS/뉴스 신규 8건이 data/monitor.sqlite3에 기록되어 로컬 git status -- data는 M 상태.
- OPENROUTER_API_KEY/TELEGRAM_BOT_TOKEN 없이 검증하여 실제 LLM 응답과 실제 Telegram 발송은 미검증.

다음 작업
- Claude Code에서 커밋 필요.
- GitHub Secrets 환경에서 workflow_dispatch 실행 확인 필요.
