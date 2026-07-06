완료한 것
- DART 공시 수집기 news_radar/dart.py 추가: list.json 조회, corp_code JSON 캐시, 보고서 제외 필터, Item 매핑.
- worker COLLECTORS에 source=dart 등록 및 skip_stage1 플래그 추가.
- Settings에 API_K_DART/DART_API_KEY, DART_LOOKBACK_DAYS 로드 추가.
- domestic.yml에 API_K_DART env와 DART 별도 실행 스텝(if: always()) 추가.
- README.md에 DART Secret, 캐시, 제외 규칙, 비상장 스킵 규칙 추가.

결정 근거
- DART는 감시 기업 공식 공시라 stage1 관련성 필터를 생략하고 stage2 판정/중복/시드/발송 로직은 기존 worker를 재사용.
- corpCode.zip은 캐시 미스 기업이 있을 때만 내려받고 data/dart_corp_codes.json에 기업명별 corp_code를 저장.
- 미해결 기업은 빈 corp_code로 캐시에 남겨 반복 실행마다 zip을 받지 않음.
- DART API 키는 환경변수에서만 읽고 로그/설정/코드에 기록하지 않음.

미해결 쟁점
- OpenRouter/Telegram 실발송 검증은 하지 않음.
- 운영 data/는 임시 DATA_DIR 검증 후 git status 변경 없음 확인.

다음 작업
- Claude Code에서 변경 파일 리뷰 후 커밋 필요.
