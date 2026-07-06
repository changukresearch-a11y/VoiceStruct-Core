# Quantinue — 정보분석(공시·뉴스) 에이전트

미국주식 자율매매 시스템 중 **정보분석 파트(①공시 + ②뉴스)**.
SEC 공시(8-K·10-Q/K·Form4)와 실시간 뉴스(RSS)를 **구조화 신호로 변환**해,
종목당 `DisclosureBundle`·`NewsBundle` 두 객체로 **Strategist 에이전트**에게 넘긴다.
(실제 매수결정·시장반응 검증·비중 계산은 이 파트 범위 밖 — Strategist 이후 몫)

> 📌 **진행상황·회귀 명령어·남은 작업은 [`WORKLOG.md`](WORKLOG.md)** (개인 작업노트).

---

## 📚 문서 (팀 공유)

> 📁 아래 문서 파일은 전부 **`Document/`** 폴더에 있다. (`README.md`·`WORKLOG.md`는 루트 유지)

| 문서 | 대상 | 내용 |
|---|---|---|
| **`정보분석_개발보고서.html`** | 개발자 | 파트 전체 조망 — 파이프라인·아키텍처·**0~1 지표 산출근거(공식·상수·임계값)**·코드vsLLM·저장·갭 |
| **`결과값_필드_레퍼런스.html`** | 개발자 | 필드 데이터 사전 — 공시18·뉴스28 필드별 출처·산출식·등급 경계 |
| **`데이터스키마_인터페이스명세_v2`** (md·html) | 이은미(Strategist) | 전달 계약 — Bundle 스키마·DB 스냅샷(tb_disclosure/tb_news)·to_prompt |
| **`공시_상세설계서.html` · `뉴스_상세설계서.html`** | 개발자 | 파이프라인별 상세 설계 |
| **`전략가_전달_예시_10건.json`** | 이은미 | 실제 로직으로 산출한 결과값 예시 10건(전 필드) |
| **`스크리닝_입력스키마_스크리닝→정보분석`** (md·html) | 스크리닝 담당 | 입력 계약(50종목 JSON) |

---

## 산출물 계약 & 0~1 지표

공시·뉴스는 **완전 별개 2객체**로 넘어간다(합치기는 Strategist). 정식 전달 = **DB 스냅샷 테이블** `tb_disclosure`(18)·`tb_news`(28), **PK=(ticker, collected_at)** 시계열 append → Strategist는 종목별 **최신 행**을 JOIN해 읽음. 보조 = `to_prompt()`·JSON.
모든 점수는 **0~1 소수 2자리**, 자유서술(summary·reason)·라벨은 **영어**(전략가 에이전트가 읽음). (회사명·카테고리는 tb_universe JOIN)

- **핵심 0~1 지표**: `sentiment_score`(0=악재·0.5=중립·1=호재, 호재만 신뢰 감쇠) · `importance`(방향 무관 강도) · `risk_score` · `confidence` · `source_trust`(뉴스) · `grade_score`(뉴스) · `confirmed_score`(뉴스)
- **원문 식별**: 공시 `filing_title·filing_no·filed_at`(초 단위) / 뉴스 `news_title·source·published_at`(초 단위)
- **부가**: `fact_check`(뉴스, 코드 판정) · `reason`(근거 한 줄) · `summary`(3~4줄) · `keywords`(5개) · `hard_block` · `collected_at`
  - ※ 2026-07-06 팀 명세 반영: 공시 24→18·뉴스 31→28필드(삭제 `company_name·category·verdict`+공시 `confirmed_score·fact_check·ref`), `as_of→trade_date`·`created_at→collected_at`.
- 산출 근거·임계값은 `결과값_필드_레퍼런스.html` §6, `정보분석_개발보고서.html` §6 참고.

---

## 구조

```
quantinue/
├─ app/
│  ├─ common/      schemas(NormalizedItem) · llm_client · ontology(공유 event_type 11종)
│  │              · analysis_bundle  ★ Bundle 산출·0~1 지표 계산의 중심
│  ├─ collectors/  sec_collector(8-K) · sec_xbrl_collector(10-Q/K) ·
│  │              sec_form4_collector · news_collector(Google News RSS)
│  ├─ router/      form_type_router · form_8k_item_router
│  ├─ policies/    hard_risk_policy · source_trust_policy(출처3단계+키워드필터)
│  ├─ analyzers/   disclosure_analyzer · news_analyzer · form4_scorer · prompts/
│  ├─ schemas/     disclosure_analysis · news_analysis · xbrl_metrics · form4
│  ├─ decision/    trade_permission_policy(6단계, 가장 보수적)
│  ├─ storage/     db(SQLite: disclosure_signals·news_signals·processed_filings·companies)
│  ├─ universe/    repository · seed · batch_runner · market_data(Yahoo 시총)
│  ├─ scheduler/   scheduler(메타레벨 증분·뉴스 통합)
│  ├─ backtest/    price_data · fill_returns · report
│  ├─ pipeline.py       공시 오케스트레이션
│  └─ news_pipeline.py  뉴스 오케스트레이션
├─ config/         item_event_map · hard_risk_policy · news_trust_policy · news_keyword_filter (yaml)
├─ data/           quantinue.sqlite (gitignore)
└─ run_*.py        bundle · screening_input · scheduler · universe · backtest · news · skeleton
```

---

## 실행

```bash
pip install -r requirements.txt
cp .env.example .env    # SEC_USER_AGENT="이름 you@email.com" · OPENAI_API_KEY=sk-... · LLM_ANALYST_MODEL=openai:gpt-4o-mini
```
- LLM provider = **OpenAI gpt-4o-mini**. SEC·Google News·Yahoo는 키 불필요(SEC는 User-Agent만).

```bash
# 단건 번들 (공시+뉴스 → Strategist 입력 2객체)
python run_bundle.py --ticker NVDA --category "Semiconductors" --llm --json

# 스크리닝 배치 (50종목 JSON 입력 → 유니버스 적재 + 번들 생성)
python run_screening_input.py --file screening_input.json --run --llm --json

# 수집 스케줄러 (메타레벨 증분: 새 accession만 문서·LLM)
python run_scheduler.py --once --limit 50 --forms 8-K,10-Q --news --llm --save

# 백테스트 (전방수익률·성과 리포트)
python run_backtest.py --fill --report

# 단건 공시(회귀 확인용)
python run_skeleton.py --ticker AAPL --form 8-K --live --llm --save
```

---

## 완료된 것 ✅ (전부 실데이터 검증)

- **공시 3축**: 8-K(Item라우터+LLM) · 10-Q/K(XBRL 수치+LLM 해석) · Form4(100% 코드 스코어링)
- **뉴스**: Google News RSS 수집 · 출처 **3단계**(ALLOW/GRAY/BLOCK, 소셜=GRAY) + 키워드 사전필터 · LLM(is_confirmed·source_trust) · 신뢰가중 집계
- **공통 배관**: 최종권한 6단계(가장 보수적) · SQLite 저장 · 하드리스크 룰
- **운영**: 유니버스 시총순위 확장(2000) · 메타레벨 증분 스케줄러 · 전방수익률 백테스트(측정만)
- **Strategist 계약**: 별개 2객체 · 0~1 통일 · 요약/키워드/판정 · 영어화 · 원문 식별 · 팩트체크/생성시각
- **입력 계약**: 스크리닝→정보분석 로더(`run_screening_input.py`)
- **0~1 지표 정확·일관화**: importance 방향 독립(상쇄 붕괴 해결) · 라벨↔점수 일치 + mixed · source_trust=0 버그 수정 · 저신뢰 폴백 · peak 이중정규화 수정

> 📌 MVP 정보분석 파트 **한 바퀴 완성** + Phase 2 정교화. (git 브랜치 `collector-agent`)

---

## 남은 단계 (Phase 2)

- `item_event_map`의 `hard_risk` 플래그를 권한 결정에 반영(2.06 등) — 팀 결정 대기
- XBRL 컨센서스 Surprise(유료 보류) · sector 채우기(quoteSummary)
- 이벤트 온톨로지 정교화(`other` 빈발) · 표본 쌓이면 실제 가중치 튜닝

> ※ 시장반응 검증·실제 매수권한은 별도 Strategist 에이전트 몫 (이 파트 범위 밖)
