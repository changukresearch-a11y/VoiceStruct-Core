# Quantinue 작업노트 (WORKLOG)

> 마지막 업데이트: 2026-07-03
> 이 파일 하나만 읽으면 다음 세션에서 바로 이어갈 수 있게 정리한 작업노트.
> (프로젝트 소개·구조는 `README.md`, 설계 배경은 Claude 메모리 `quantinue-*` 참고)
>
> ⚠️ **개인 작업노트 — 팀 공유용 아님.** 팀 담당 경계·공유는 `개발공유_2026-07-01.md`·`인계_정보분석파트_*.md` 참고.
> 내 실제 담당(R.md)은 **`agents/collector.py` = ①공시 + ②뉴스**. 여기 적힌 **유니버스·수집 스케줄러·백테스트·저장(DB)** 은
> ①② 검증용으로 만든 것이며 R.md상 **팀장(김지현) 영역**과 겹침 → 팀 통합 시 중복 정리 필요(팀 레포엔 collector만 커밋).

---

## 0. 한 줄 요약

정보분석(공시·뉴스) **단건 코어** + **수집 스케줄러(주기·메타증분·뉴스통합)** + **뉴스 DB 저장** +
**유니버스 시총 확장** + **백테스트 피드백(전방수익률 채우기·성과 리포트)** 까지 동작.
MVP 정보분석 파트 **한 바퀴 완성**. 남은 건 Phase 2 정교화(리스크문구·Surprise·sector 등).
(실제 매수권한·시장반응은 이 파트 범위 밖 — 별도 Strategist 에이전트 몫)

---

## 0.5 최근 변경 이력 (2026-07-02 ~ 07-03)

Strategist 전달 계약(구 `AnalysisBundle`)을 팀 회의 피드백으로 대개편하고, 이후 필드·정책을 추가했다.

- **인터페이스 대개편 (07-02):** 공시·뉴스를 **완전 별개 2객체**(`DisclosureBundle`/`NewsBundle`)로 분리,
  모든 점수 **0~1 소수점 통일**(방향은 `sentiment_score`+라벨), 회사명·카테고리 필드.
  명세: `데이터스키마_인터페이스명세_v2.md`(+`.html`).
- **화제성(Buzz) 제거 (07-03):** 07-02에 넣은 클러스터링을 오버기능으로 판단해 삭제.
- **스크리닝→정보분석 입력 계약 (07-03):** 스크리닝 에이전트가 주는 50종목 JSON 스키마 + 로더
  `run_screening_input.py`(유니버스 적재·`--exclusive`·`--run`). 문서 `스크리닝_입력스키마_*`.
- **상세 설계서 (07-03):** `공시_상세설계서.html`·`뉴스_상세설계서.html`(라이트 테마, 팀 설계서 0701.html 형식).
- **번들 필드 확장 (07-03):**
  - `sentiment_score` **비대칭 신뢰 감쇠**(호재만 감쇠·악재 유지) + 대표 신호 **신뢰가중(imp×conf)** 선정.
  - `summary`(전문 3~4줄)·`keywords`(5개)·`verdict`(호재/악재 판정 한 문장).
  - **출력 영어화** — 자유서술·`to_prompt()` 라벨을 전략가 에이전트용 영어(verdict=Bullish/Bearish/Neutral).
  - **원문 식별** — 공시 `filing_title`·`filing_no`·`filed_at`(**초 포함** acceptanceDateTime) /
    뉴스 `news_title`·`source`·`published_at`(**초 포함**).
  - `fact_check`(코드 판정 팩트체크 한 문장) · `created_at`(레코드 생성시각, 초 포함).

반영 위치: `app/common/analysis_bundle.py` · `app/schemas/*` · `app/analyzers/prompts/*` ·
`app/collectors/sec_collector.py` · `app/pipeline.py` · `app/storage/db.py`.
엔트리 `run_bundle.py`(단건) / `run_screening_input.py`(스크리닝 배치).

- **0~1 지표 산출 정확·일관화 (07-03):** 뉴스 집계 버그·비일관성 수정.
  ① `importance`를 **방향과 독립**한 부호 없는 강도의 신뢰가중 평균으로(구: `|agg_signed|`라
     호·악재 섞이면 0으로 **붕괴**) → 같은 강도면 항상 같은 값. ② `sentiment` 라벨을
     **`sentiment_score`에서 파생**해 라벨↔점수 항상 일치 + 진짜 충돌이면 `mixed`.
  ③ **`_news_conf` 버그 수정** — `source_trust or 1.0`이 `source_trust=0.0`(무신뢰)을
     1.0으로 오인 → 명시적 None 검사로. ④ 전부 저신뢰(가중치 0)면 **등가중 폴백**(강도 붕괴 방지,
     confidence는 정직하게 낮게). ⑤ `peak_importance` **이중 정규화 버그** 수정(`_n10(max(mags))`→`max(mags)`).
  결과값 필드 레퍼런스 §4·§6 갱신.

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
# Google News RSS 실수집 + 출처3단계 + 키워드필터 (LLM 없이 사전필터만)
python run_news.py --ticker AAPL --limit 8

# 통과분 LLM 분석까지 (+ DB 저장, 중복 skip)
python run_news.py --ticker AAPL --limit 4 --llm --save
```

### 유니버스 배치·확장 (run_universe.py)
```bash
python run_universe.py --seed                        # 대표 시드 50개 적재 (1회)
python run_universe.py --run --limit 5 --save        # 배치(배선+저장, 증분)
python run_universe.py --run --limit 5 --llm --save  # + LLM

# ── 2000개 확장 (시총 기반 우선순위) ──
python run_universe.py --enrich --reprioritize                 # 시드 시총 채우고 순위화
python run_universe.py --expand 250 --enrich --reprioritize --keep-top 100
python run_universe.py --expand 0 --enrich --reprioritize --keep-top 2000  # 진짜 전체(SEC 전량)
```
- `--expand N`(0=SEC 전량) 후보 적재 → `--enrich` Yahoo 배치로 market_cap 채움 →
  `--reprioritize --keep-top K` priority=시총순위 + 상위 K만 active. (get_active_tickers가 priority순)

### 수집 스케줄러 (run_scheduler.py) ★신규
```bash
# 1회 순회 — 메타레벨 증분(submissions만 보고 처리한 accession은 문서 다운로드 skip)
python run_scheduler.py --once --limit 3 --forms 8-K,4 --save

# 1회 + LLM (새 공시만 분석)
python run_scheduler.py --once --limit 5 --forms 8-K --llm --save

# 뉴스까지 통합해 주기 실행 (15분 간격, Ctrl+C 종료)
python run_scheduler.py --interval 900 --limit 10 --forms 8-K,10-Q --news --llm --save
```
- `--forms`는 쉼표 구분(여러 form 동시). `--news`면 같은 순회에 뉴스도 처리.
- 재실행 시 이미 처리한 accession은 `unchanged (skip)` — **문서 다운로드/LLM 안 함**.

### Strategist 입력 번들 (run_bundle.py) ★신규
```bash
# 종목의 공시+뉴스를 종목당 1개 AnalysisBundle로 집계 → to_prompt() 출력
python run_bundle.py --ticker NVDA --form 8-K --news-limit 8 --llm --json
```
- 이은미(Strategist)에 넘길 형식. 명세·근거: `인터페이스명세_정보분석→Strategist.md`.
- event_type은 `app/common/ontology.py` 통일 11종(공시/뉴스 공유).

### 백테스트 피드백 (run_backtest.py) ★신규
```bash
python run_backtest.py --fill              # 5거래일 지난 신호에 return_1d/3d/5d 채움
python run_backtest.py --fill --min-age 5
python run_backtest.py --report            # 이벤트/출처/센티먼트별 적중률·평균수익률
python run_backtest.py --fill --report
```
- 종목별 종가 1회 조회(Yahoo chart v8, 키 불필요) → +1/+3/+5 거래일 수익률.
- 5일 미경과분은 return_5d 비워 재시도. **가중치는 자동조정 안 함**(측정·리포트까지만).

### DB 빠른 확인
```bash
python -c "from app.storage.db import recent; [print(dict(r)) for r in recent(10)]"
python -c "from app.storage.db import recent_news; [print(dict(r)) for r in recent_news(10)]"
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
| 뉴스 | Google News RSS 수집 → 출처3단계(ALLOW/GRAY/BLOCK, 소셜=GRAY) + 키워드필터(화이트우선) → LLM(is_confirmed·source_trust) |
| 공통 배관 | NormalizedItem · 최종권한 결정(6단계, 가장 보수적) · SQLite 저장 |
| 유니버스 | companies 테이블 · 시드 50 · 배치 러너 · 증분 처리 · **SEC 후보 대량적재 + Yahoo 시총 enrich + priority=시총순위(상위 K만 active)** |
| 스케줄러 | 우선순위 순회 · **메타레벨 증분(peek→문서 전 skip)** · 뉴스 통합 · 주기 루프(run_forever) · processed_filings 테이블 |
| 뉴스 저장 | **news_signals 테이블**(드롭 포함) · google_link 키로 **DB 기반 dedup**(재시작에도 유지) · run_news/스케줄러 `--save` |
| 백테스트 | **전방수익률(1/3/5거래일) 채우기**(Yahoo chart) · outcome=센티먼트 방향적중 · **성과 리포트**(이벤트/출처/센티먼트별 적중률·평균) · 가중치 자동조정은 안 함 |
| Phase2 정교화 | **filed_at 저장**(공시 제출일 → 백테스트 day0 정확도) · **10-Q/K 본문 리스크문구 스캔**(going concern·material weakness 등 원문에서 check_hard_risk) |
| Strategist 인터페이스 | **AnalysisBundle**(종목당1개 집계+`to_prompt()`) · 공유 온톨로지 `ontology.py`(통일 event_type 11종, 공시/뉴스 import) · `run_bundle.py` · 명세문서(근거+실물샘플) · NVDA 실검증 |

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
- **메타레벨 증분(스케줄러)**: `peek_recent_filings`가 submissions 1회만 호출해 form별 최신
  accession을 얻고, `processed_filings`(accession PK, form 무관)로 처리 여부 판정 → **새 건일 때만**
  문서 다운로드·LLM. 비용의 대부분(문서+LLM)을 unchanged에서 원천 제거.
- **뉴스 dedup 키 = google_link**: `item.url`은 출처 도메인(예 reuters.com)이라 같은 언론사 기사가
  뭉개짐 → 기사별 유니크한 RSS `<link>`(meta.google_link)를 키로. news_signals.news_key UNIQUE +
  `INSERT OR IGNORE`로 DB 레벨 dedup. 드롭 뉴스도 저장해 "본 것"을 남김(재분석 방지).
- **시총 소스 = Yahoo(키 불필요)**: yfinance(무겁고 대량 불안정) 대신 httpx로 쿠키+crumb 받아 v7
  quote 배치 호출(응답은 `quoteResponse.result`, marketCap 포함). Finnhub는 키 필요라 보류.
  priority=시총 내림차순 순위(시총 없는 종목은 뒤로), `--keep-top`으로 working-set 고정.
- **백테스트 = 측정까지만, 자동튜닝 안 함**: 메모리 MVP 컷라인("표본 부족 시 과적합→수동 기록부터")대로
  return 채우고 이벤트/출처별 성과를 **리포트로 보여주는 데서 멈춤**. 가중치 코드 수정은 사람이.
  가격소스는 Yahoo chart v8(crumb 불필요). day0 종가 = 신호일 이하 마지막 거래일, +h는 h번째 뒤 거래일.
- **filed_at = 백테스트 day0(공시)**: 8-K/Form4는 submissions filingDate, 10-Q/K는 companyconcept의
  `filed`(+ 본문 수집 시 submissions filingDate로 갱신). day0=COALESCE(filed_at, analyzed_at). 기존 DB는
  `_migrate`가 ALTER로 컬럼 보강.
- **10-Q/K 리스크문구 = 원문 스캔**: XBRL 경로는 수치 요약만 body라 going concern류를 못 잡음 →
  `fetch_report_text`로 원문 별도 다운로드해 `check_hard_risk`(정책에 이미 going concern·material weakness 등).
  파이프라인 XBRL 분기에서 set → step3은 `hard_risk is None`일 때만 덮어씀. LLM 입력 body는 안 늘림(수치만 유지).
- **컨센서스(애널 예상치)는 유료** → MVP는 XBRL YoY만, Surprise는 Phase 2.

---

## 5. 디렉토리 구조

```
quantinue/
├─ app/
│  ├─ common/      schemas(NormalizedItem) · llm_client · ontology(공유 event_type) · analysis_bundle(Strategist 계약)
│  ├─ collectors/  sec_collector(8-K) · sec_xbrl_collector(10-Q/K) ·
│  │               sec_form4_collector · news_collector(RSS)
│  ├─ router/      form_type_router · form_8k_item_router
│  ├─ policies/    hard_risk_policy · source_trust_policy(뉴스)
│  ├─ analyzers/   disclosure_analyzer · news_analyzer · form4_scorer · prompts/
│  ├─ schemas/     disclosure_analysis · news_analysis · xbrl_metrics · form4
│  ├─ decision/    trade_permission_policy(공통)
│  ├─ storage/     db(SQLite, 공통)
│  ├─ universe/    repository · seed(+load_sec_universe) · batch_runner · market_data(Yahoo 시총)
│  ├─ scheduler/   scheduler(run_cycle·run_forever, 메타레벨 증분·뉴스 통합)
│  ├─ backtest/    price_data(Yahoo chart) · fill_returns · report
│  ├─ pipeline.py       공시 오케스트레이션
│  └─ news_pipeline.py  뉴스 오케스트레이션
├─ config/         item_event_map · hard_risk_policy · news_trust_policy · news_keyword_filter (yaml)
├─ data/           quantinue.sqlite (gitignore)
├─ run_skeleton.py · run_news.py · run_universe.py · run_scheduler.py · run_backtest.py · run_bundle.py
└─ requirements.txt · .env(.example) · README.md · WORKLOG.md
```

---

## 6. 남은 작업 (우선순위 순, 매수권한 제외)

1. ✅ **(완료 2026-07-01) 수집 스케줄러 + 뉴스 배치 통합** — `app/scheduler/` + `run_scheduler.py`.
   우선순위 순회 · **메타레벨 증분**(peek_recent_filings로 submissions만 보고 처리한 accession은
   문서 다운로드/LLM skip) · 뉴스 통합(프로세스 내 seen 집합으로 재LLM 방지) · 주기 루프(run_forever).
   실데이터 검증: 2회차 6건 전부 unchanged-skip, processed_filings 테이블로 form 무관 dedup.
2. ✅ **(완료 2026-07-01) 뉴스 DB 저장** — `news_signals` 테이블(드롭 포함) + `save_news`/`recent_news`.
   dedup을 프로세스 메모리 → **DB 기반**으로 승격(`is_news_seen`, 키=google_link). `run_news`/스케줄러 `--save`.
   실검증: 2회차 fresh 0/5·저장 0(별도 프로세스에도 skip), news_signals 적재 확인.
3. ✅ **(완료 2026-07-01) 유니버스 2000개 확장** — `market_data.py`(Yahoo 쿠키+crumb 배치, 키 불필요) +
   `seed.load_sec_universe`(SEC 후보 대량적재) + `repository`(set_market_cap·reprioritize_by_market_cap).
   `run_universe.py --expand/--enrich/--reprioritize --keep-top`. priority=시총순위, 상위 K만 active.
   실검증: 시드50 시총 채움→NVDA#1($4.85T)~NKE#50, expand250→상위100 active 컷 정확. **진짜 2000은
   `--expand 0 --keep-top 2000`**(SEC 전량 enrich, ~수십~170 배치콜).
4. ✅ **(완료 2026-07-01) 백테스트 피드백 루프** — `app/backtest/`(price_data·fill_returns·report) +
   `run_backtest.py --fill/--report`. Yahoo chart로 +1/3/5거래일 수익률→return 컬럼, outcome=센티먼트
   방향적중, 이벤트/출처/센티먼트별 적중률·평균 리포트. **가중치 자동조정은 안 함**(과적합 방지, 수동 분석).
   실검증: 합성 과거신호(AAPL/NVDA/MSFT 2026-06-02)로 채우기→리포트 전 경로, 5일 미경과 partial 처리 확인.
5. (Phase 2) ✅ ~~10-Q/K 본문 리스크문구~~ · ✅ ~~공시 filed_at 저장~~ (완료 2026-07-01) /
   남음: XBRL 컨센서스 Surprise(컨센서스 유료→보류) · sector 채우기(quoteSummary) ·
   이벤트 클러스터링 · 온톨로지 정교화(현재 other 많음) · EPS YoY 보완 ·
   백테스트로 실제 가중치 튜닝(표본 충분해진 뒤) · 리스크스캔 성능(전체 유니버스 시 문서 다운로드 비용).

---

## 7. 알려진 한계

- ~~증분이 SEC 수집 후 비교~~ → **해결(스케줄러 경로)**: peek로 submissions만 보고 문서 다운로드 전 skip.
  단, run_universe.py(batch_runner) **구경로는 여전히 수집 후 비교** — 스케줄러로 대체 예정.
- **새 accession일 땐 peek(submissions) + 파이프라인이 submissions를 한 번 더** 호출(이중). 문서 다운로드/LLM을
  아끼는 게 핵심이라 허용. 완전 제거하려면 peek 메타를 파이프라인에 주입하는 리팩터 필요(후순위).
- ~~뉴스 dedup이 프로세스 메모리~~ → **해결**: news_signals(google_link 키) DB 기반 dedup으로 승격.
  단 `--save` 없이 돌리면 여전히 메모리 seen만 사용(저장 안 하니 당연). dedup 지속은 `--save` 전제.
- **뉴스 저장 키가 google_link** → RSS에 없으면 url·title로 폴백. 극히 드물게 재분석 가능(허용).
- **배치/순회 순차 실행**(SEC rate limit) → 2000개면 느림, 동시성/큐 분산 필요.
- **Yahoo crumb 소스는 비공식** → 대량(수천) 시 rate limit·간헐 실패 가능(배치별 skip으로 방어).
  ADR·복수클래스 등 일부 티커는 시총 미조회될 수 있음(그 종목은 priority 뒤로). sector는 아직 미채움.
- **enrich는 수동 실행** → 시총은 자주 안 변하니 주기 재실행은 낮은 빈도로(스케줄러엔 미통합).
- ~~백테스트 day0 = analyzed_at 근사~~ → **해결**: filed_at 저장·day0 우선 사용. 단 **기존에 저장된
  옛 행은 filed_at NULL** → 그 행만 analyzed_at로 폴백. return은 5거래일 지나야 확정 → 전엔 partial 재시도.
- **10-Q/K 리스크스캔은 원문(수십~수백 KB) 다운로드** → 종목당 1회. 전체 유니버스 주기 스캔 시 비용 큼
  (스케줄러 증분으로 새 10-Q/K일 때만 받게 됨). going concern은 주석·감사의견 깊은 곳 → 전체 스캔(2MB 상한).
- **백테스트도 Yahoo 비공식 소스** → 상장폐지·심볼변경·해외종목은 종가 미조회 가능(그 신호는 보류).
- **event_type=other 빈발** — 온톨로지가 실제 뉴스 패턴에 덜 맞음. 데이터 보며 조정.
- **뉴스 본문이 헤드라인 위주**(RSS 한계) — 깊은 분석엔 본문 수집 필요.
- **시장반응·실제 매수권한 없음** — 의도된 것. Strategist 에이전트가 담당.

---

## 8. 보안 메모

- `.env`는 `.gitignore`로 제외됨. 비밀키는 **IDE에 연 채로 편집 금지**
  (열린 파일 변경분이 어시스턴트 컨텍스트로 자동 주입돼 1회 노출된 적 있음 → 폐기 권고함).
- SEC는 키 불필요(User-Agent만). OpenAI 키만 비밀.
