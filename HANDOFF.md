완료한 것
- 공개 텔레그램 채널 수집기 news_radar/telegram_channels.py 신규 추가.
- COLLECTORS에 source=tgchannel 등록, worker_state 고수위 키 tg_high_water:<handle> 저장 연결.
- config/telegram_channels.txt와 config/breaking_keywords.txt 신규 추가.
- keyword 모드는 breaking_keywords와 companies.txt 기업명·별칭을 병합해 LLM 전 게이트 적용.
- .github/workflows/tgchannel.yml 신규 추가, 5분 cron과 news-radar-state concurrency 설정.
- README에 텔레그램 채널 추가법, 키워드 관리법, 운영 필터 설명 추가.

결정 근거
- t.me/s/<handle> HTML은 표준 HTMLParser로 파싱해 외부 의존성을 추가하지 않음.
- 첫 실행은 최신 1페이지만 수집하고, 이후 실행은 before 페이지네이션으로 고수위 초과분만 수집.
- 게이트 탈락분은 Item으로 반환하지 않아 seen_items와 LLM 판정에 들어가지 않음.
- 운영 data/monitor.sqlite3 보호를 위해 DATA_DIR은 data/_tmp_tgchannel_verify_* 임시 폴더로만 실행 후 삭제.

미해결 쟁점
- 로컬 검증은 OPENROUTER_API_KEY와 TELEGRAM_BOT_TOKEN을 빈 값으로 고정해 실제 LLM/Telegram 발송은 수행하지 않음.
- GitHub Actions 실제 secrets 값과 원격 push 권한은 로컬에서 확인하지 않음.

다음 작업
- Claude Code에서 변경 파일 리뷰 후 커밋 필요.
