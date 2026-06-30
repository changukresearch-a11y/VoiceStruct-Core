# Quantinue 작업노트 (WORKLOG)

> 마지막 업데이트: 2026-06-30
> 이 파일 하나만 읽으면 다음 세션에서 바로 이어갈 수 있게 정리한 작업노트.
> (프로젝트 소개·구조는 `README.md`, 설계 배경은 Claude 메모리 `quantinue-*` 참고)

---

## 0. 한 줄 요약

정보분석(공시·뉴스) **단건 코어 완성** + **유니버스 배치(50개) 동작**까지 끝.
다음은 **스케줄러 / 유니버스 2000개 확장 / 백테스트 피드백**.
(실제 매수권한·시장반응은 이 파트 범위 밖 — 별도 Strategist 에이전트 몫)

---

## 1. 빠른 시작 (환경)

```bash
cd quantinue
pip install -r requirements.txt          # 의존성
cp .env.example .env                      # 그리고 .env에 키 채우기
```

`.env` 필수 항목:
```
SEC_USER_AGENT="이름 you@email.com"       # SEC 요구 (키는 불필요, UA만)
OPENAI_API_KEY=sk-...                      # 분석가 LLM (gpt-4o-mini)
LLM_ANALYST_MODEL=openai:gpt-4o-mini
```
- LLM provider = **OpenAI**(사용자 키 보유로 선택). Anthropic 쓰려면
  `ANTHROPIC_API_KEY` + `LLM_ANALYST_MODEL=anthropic:claude-haiku-4-5`,
  그리고 `pip install "pydantic-ai-slim[anthropic]"`.
- SEC·yfinance·Google News RSS는 키 불필요.

---

## 2. 실행 명령어 (다음에 이어서 / 회귀 확인용)

### 공시 (run_skeleton.py)
```bash
# 8-K (이벤트) — Item 라우터 + 하드룰 + LLM
python run_skeleton.py --ticker AAPL --form 8-K  --live --llm --save

# 10-Q/10-K (재무) — XBRL 수치(코드) + LLM 수치해석
python run_skeleton.py --ticker AAPL --form 10-Q --live --llm --save

# Form 4 (내부자거래) — XML 파싱 + 코드 스코어링 (LLM 미사용)
python run_skeleton.py --ticker AAPL --form 4    --live --save

# 배선만 (LLM/네트워크 없이): --live, --llm, --save 빼면 샘플로 동작
python run_skeleton.py --ticker NVDA
```

### 뉴스 (run_news.py)
```bash
# Google News RSS 실수집 + 출처4단계 + 키워드필터 (LLM 없이 사전필터만)
python run_news.py --ticker AAPL --limit 8

# 통과분 LLM 분석까지
python run_news.py --ticker AAPL --limit 4 --llm
```

### 유니버스 배치 (run_universe.py)
```bash
python run_universe.py --seed                        # 시드 50개 적재 (1회)
python run_universe.py --run --limit 5 --save        # 배치(배선+저장, 증분)
python run_universe.py --run --limit 5 --llm --save  # + LLM
```

### DB 빠른 확인
```bash
python -c "from app.storage.db import recent; [print(dict(r)) for r in recent(10)]"
python -c "from app.universe.repository import count; print('companies:', count())"
```
DB 파일: `data/quantinue.sqlite` (gitignore됨)

---

## 3. 완료된 것 ✅ (전부 실데이터 검증)

| 영역 | 내용 |
|---|---|
| 공시 8-K | SEC 수집 → Item 라우터 → 하드룰 → LLM 이벤트해석 |
| 공시 10-Q/K | XBRL companyconcept(코드)로 YoY 수치 → LLM 수치해석 |
| 공시 Form 4 | raw XML 파싱 → 코드 스코어링(매수=호재/매도=악재/베스팅=중립) |
| 뉴스 | Google News RSS 수집 → 출처4단계 + 키워드필터(화이트우선) → LLM(is_confirmed·source_trust) |
| 공통 배관 | NormalizedItem · 최종권한 결정(6단계, 가장 보수적) · SQLite 저장 |
| 유니버스 | companies 테이블 · 시드 50 · 배치 러너 · 증분 처리 |

---

## 4. 주요 결정 / 수정 사항

- **LLM provider = OpenAI gpt-4o-mini** (분석가 티어). `LLMClient`로 추상화.
- **Form별 코드/LLM 비중 차등**: Form4=100% 코드, 10-Q/K=수치는 코드·해석만 LLM,
  8-K=Item 본문만 LLM. (환각 방지의 핵심)
- **Trade Permission 6단계 통일**: BLOCK_ALL > BLOCK_BUY > RISK_REDUCE >
  WATCH_ONLY > TRADE_ELIGIBLE_SMALL_SIZE > TRADE_ELIGIBLE. 종합 시 **가장 보수적** 채택,
  시장반응 미확인 시 매수계열은 WATCH_ONLY로 강등.
- **로직 분리 + 배관 공유**: 공시/뉴스는 collector·analyzer·스키마·정책 따로,
  NormalizedItem·decision·storage는 공유(중복 방지).
- **사전필터로 LLM 비용 절감**: 뉴스 키워드 drop·출처 BLOCK은 LLM 호출 전 차단.
- **증분 처리**: 같은 accession이면 재분석/재저장 skip ("변화 트리거").
- **컨센서스(애널 예상치)는 유료** → MVP는 XBRL YoY만, Surprise는 Phase 2.

---

## 5. 디렉토리 구조

```
quantinue/
├─ app/
│  ├─ common/      schemas(NormalizedItem) · llm_client
│  ├─ collectors/  sec_collector(8-K) · sec_xbrl_collector(10-Q/K) ·
│  │               sec_form4_collector · news_collector(RSS)
│  ├─ router/      form_type_router · form_8k_item_router
│  ├─ policies/    hard_risk_policy · source_trust_policy(뉴스)
│  ├─ analyzers/   disclosure_analyzer · news_analyzer · form4_scorer · prompts/
│  ├─ schemas/     disclosure_analysis · news_analysis · xbrl_metrics · form4
│  ├─ decision/    trade_permission_policy(공통)
│  ├─ storage/     db(SQLite, 공통)
│  ├─ universe/    repository · seed · batch_runner
│  ├─ pipeline.py       공시 오케스트레이션
│  └─ news_pipeline.py  뉴스 오케스트레이션
├─ config/         item_event_map · hard_risk_policy · news_trust_policy · news_keyword_filter (yaml)
├─ data/           quantinue.sqlite (gitignore)
├─ run_skeleton.py · run_news.py · run_universe.py
└─ requirements.txt · .env(.example) · README.md · WORKLOG.md
```

---

## 6. 남은 작업 (우선순위 순, 매수권한 제외)

1. **수집 스케줄러 + 뉴스 배치 통합** — 50개 안에서 공시·뉴스를 주기적으로 같이.
   우선순위 큐 + 증분을 **메타레벨로 최적화**(submissions만 보고 doc 다운로드 전 비교).
2. **유니버스 2000개 확장** — yfinance/Finnhub로 `market_cap` 채워 priority 정렬.
3. **뉴스 DB 저장** — `news_signals` 테이블 별도(현재 뉴스는 저장 안 함).
4. **백테스트 피드백 루프** — `return_1d/3d/5d` 채우고 출처/이벤트별 성과로 가중치 튜닝.
   (메모리 핵심 철학, 아직 0%)
5. (Phase 2) 10-Q/K 본문 리스크문구 파싱(going concern 등) · XBRL 컨센서스 Surprise ·
   이벤트 클러스터링 · 온톨로지 정교화(현재 other 많음) · EPS YoY 보완.

---

## 7. 알려진 한계

- **증분이 SEC 수집 후 비교** → 수집 호출은 매번 발생(LLM/저장만 skip). 메타레벨 최적화 필요.
- **배치 순차 실행**(SEC rate limit) → 2000개면 느림, 스케줄러/큐 필요.
- **event_type=other 빈발** — 온톨로지가 실제 뉴스 패턴에 덜 맞음. 데이터 보며 조정.
- **뉴스 본문이 헤드라인 위주**(RSS 한계) — 깊은 분석엔 본문 수집 필요.
- **시장반응·실제 매수권한 없음** — 의도된 것. Strategist 에이전트가 담당.

---

## 8. 보안 메모

- `.env`는 `.gitignore`로 제외됨. 비밀키는 **IDE에 연 채로 편집 금지**
  (열린 파일 변경분이 어시스턴트 컨텍스트로 자동 주입돼 1회 노출된 적 있음 → 폐기 권고함).
- SEC는 키 불필요(User-Agent만). OpenAI 키만 비밀.
