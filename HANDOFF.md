완료한 것
- tgchannel high-water 저장을 수집 직후에서 worker 처리 후 finalize 훅으로 이동.
- CollectionResult에 candidate_marks/item_marks를 추가해 채널별 후보 마크와 URL별 message_id를 전달.
- worker COLLECTORS를 collect/finalize 레지스트리로 변경하고, add_seen 미완료 URL을 finalize에 전달.
- budget_skip/circuit_skip/judge 오류/Telegram 발송 오류/Stage2Failure 항목은 미소비로 남겨 다음 실행 재수집 대상이 되게 함.
- 채널별 high-water가 없는 첫 수집 항목은 Item.seed=True로 표시해 source 초기화 여부와 무관하게 seed 처리.
- tgchannel 키워드 게이트를 600자 description 절단 전 message.text 원문 전체 기준으로 적용.
- tgchannel high-water 상태와 키워드 게이트 로직을 tgchannel_state.py/tgchannel_keywords.py로 분리.

결정 근거
- naver/google과 같은 “미처리=unseen=재시도” 의미론을 유지하려면 상태 커밋은 처리 루프 이후여야 함.
- 게이트 탈락분은 candidate mark에는 포함하고 item_marks에는 포함하지 않아 high-water 전진과 LLM 비용 차단을 동시에 만족.
- 미소비 항목이 있으면 채널 마크를 최소 미소비 message_id - 1로 저장해 해당 항목부터 재시도.
- 채널별 seed 플래그는 나중에 새 채널을 추가해도 과거분 LLM/발송 폭탄을 막음.

미해결 쟁점
- 실제 LLM/Telegram 발송은 OPENROUTER_API_KEY/TELEGRAM_BOT_TOKEN 없이 검증하지 않음.
- 영구 테스트 파일은 추가하지 않고 요구된 python -c/worker 검증으로 확인.

다음 작업
- Claude Code에서 변경 파일 리뷰 후 커밋 필요.
