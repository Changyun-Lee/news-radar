# CONTRACT: news-radar v1

목표: 음식료·화장품 뉴스(국내 네이버 10분 / 해외 Google News RSS 1시간)를 GitHub Actions에서 수집,
2단 LLM 판정(OpenRouter) 후 텔레그램 발송. 민감도(recall) 우선, 피드백 버튼 + 주간 기준 증류.

허용: news_radar/**
허용: .github/**
허용: config/**
허용: prompts/**
허용: data/**
허용: README.md
읽기 참조: ..\텔레그램 자동화\news_dart_monitor\** (모듈 이식 원본, 수정 금지)
금지: 허용 경로 밖 쓰기, .env/키 커밋, CONTRACT.md 수정, 원본 프로젝트 수정

핵심 설계:
1. 수집: naver.py(이식, 프록시 폴백 유지) + google_news.py(신규, RSS search, 섹터 쿼리 세트)
2. 중복: SQLite seen(URL 키) → 1차 LLM 관련성(초저가, 명백히 무관할 때만 탈락)
   → 2차 LLM 점수·요약·issue_key 묶기(국내=기업별, 해외=섹터별 이력 최대 12건)
3. 발송: 중요도 ⭐(4-5)/●(3)/○(1-2) + 👍/👎 인라인 버튼, KST 23-07시는 무음
4. 피드백: 실행 시작 시 getUpdates 수거 → SQLite → 주 1회 distill이 기준문서 갱신(40줄 캡)
5. 상태: data/monitor.sqlite3 매 실행 후 리포 커밋(pull --rebase+재시도), 30일 프루닝
6. 워크플로 3개: domestic(10분, KST 07-23 파이썬 게이트), overseas(1시간), distill(주 1회)
7. 확장성: source 필드/수집기 인터페이스 유지 — DART 공시 수집기를 추후 무변경 삽입 가능

검증: python -m compileall news_radar
수동 검증(게이트 외): RUN_ONCE 드라이런 2회 연속 → 1회차 수집>0, 2회차 신규 0건, RSS 실응답 파싱

완료 정의:
1. 드라이런 2회 검증 통과 (LLM 키 없이도 구조 동작, 키 있으면 판정까지)
2. 워크플로 YAML 3개 + README(Secrets 등록 절차 포함) 존재
3. 원본 프로젝트 무변경 (git status 및 파일 타임스탬프 기준)
