# Quantinue — 정보분석(공시·뉴스) 에이전트

미국주식 자율매매 시스템 중 **정보분석 파트(①공시 + ②뉴스)**.
공시(8-K·10-Q/K·Form4) + 뉴스(RSS)를 구조화 신호로 변환하고, 유니버스 배치로
여러 종목에 적용한다. (실제 매수결정은 별도 Strategist 에이전트 몫)

> 📌 **진행상황·실행 명령어·남은 작업은 [`WORKLOG.md`](WORKLOG.md) 참고** (작업노트).

## 구조

```
quantinue/
├─ app/
│  ├─ common/        # 공통 레이어 (공시·뉴스 공유)
│  │  ├─ schemas.py      NormalizedItem (정규화 공통 입력)
│  │  └─ llm_client.py   Pydantic AI Agent 팩토리 (모델 추상화)
│  ├─ collectors/
│  │  └─ sec_collector.py   ★ 첫 구현 대상 (현재 샘플 반환 스텁)
│  ├─ router/
│  │  └─ form_8k_item_router.py   8-K Item → event/importance/permission
│  ├─ policies/
│  │  └─ hard_risk_policy.py      하드룰 키워드 검사
│  ├─ analyzers/
│  │  ├─ disclosure_analyzer.py   Pydantic AI 분석기
│  │  └─ prompts/disclosure_8k_prompt.md
│  ├─ schemas/
│  │  └─ disclosure_analysis.py   ★ DisclosureSignal (핵심 출력 스키마)
│  └─ pipeline.py    한 줄 관통 오케스트레이션
├─ config/
│  ├─ item_event_map.yaml     8-K Item 매핑
│  └─ hard_risk_policy.yaml   하드리스크 키워드
└─ run_skeleton.py   엔트리포인트
```

## 실행

```bash
pip install -r requirements.txt
cp .env.example .env          # SEC_USER_AGENT / ANTHROPIC_API_KEY 채우기

python run_skeleton.py        # 샘플 8-K로 배선 검증 (LLM 키 불필요)
python run_skeleton.py --llm  # LLM 분석까지 (ANTHROPIC_API_KEY 필요)
```

## 상태 (✅ 동작 / 🔲 스텁)

- ✅ DisclosureSignal 스키마 (CoT·certainty·event_type 8종·6단계 권한)
- ✅ 8-K Item 라우터 + config
- ✅ 하드리스크 룰 + config
- ✅ 파이프라인 배선 + 엔트리포인트
- ✅ `sec_collector` 실제 SEC 수집 (8-K: CIK → submissions → Item 청킹)
- ✅ LLM 분석기 실호출 검증 (gpt-4o-mini, 8-K·10-Q 둘 다)
- ✅ 10-Q/K XBRL 수치 경로 (companyconcept → YoY → LLM 수치 해석)
- ✅ Form 라우터 (8-K=Item / 10-Q·K=XBRL / Form4=코드)
- ✅ 최종 권한 결정 레이어 (하드룰/LLM/Item 중 가장 보수적, 시장반응 전 매수보류)
- ✅ SQLite 저장 (`data/quantinue.sqlite`, 백테스트 토대)

실행:
```bash
python run_skeleton.py --ticker AAPL --form 8-K  --live --llm --save
python run_skeleton.py --ticker AAPL --form 10-Q --live --llm --save
```

## 이후 완료된 것 (상세는 WORKLOG.md)

- ✅ Form 4 XML 파서 (내부자 거래, 100% 코드)
- ✅ 뉴스 어댑터 (RSS 실수집 + 출처 4단계 + 키워드 필터)
- ✅ 유니버스 배치 (`run_universe.py`, companies 50개 + 증분)
- ✅ **수집 스케줄러** (`run_scheduler.py`) — 주기 순회 + 메타레벨 증분(문서 다운로드 전 skip) + 뉴스 통합
  ```bash
  python run_scheduler.py --once --limit 3 --forms 8-K,4 --save
  python run_scheduler.py --interval 900 --limit 10 --forms 8-K,10-Q --news --llm --save
  ```
- ✅ **뉴스 DB 저장** (`news_signals` 테이블) — google_link 키로 DB 기반 dedup (재시작에도 유지)
- ✅ **유니버스 시총 확장** — Yahoo 배치(키 불필요)로 `market_cap` 채워 `priority`=시총순위, 상위 K만 active
  ```bash
  python run_universe.py --expand 0 --enrich --reprioritize --keep-top 2000
  ```
- ✅ **백테스트 피드백** — Yahoo chart로 +1/3/5거래일 수익률 채우고 이벤트/출처별 성과 리포트 (가중치 자동조정은 안 함)
  ```bash
  python run_backtest.py --fill --report
  ```

- ✅ **Phase 2**: 공시 `filed_at` 저장(백테스트 day0 정확도) · **10-Q/K 본문 리스크문구 스캔**(going concern 등 → BLOCK_BUY)

> 📌 MVP 정보분석 파트(공시·뉴스·유니버스·스케줄러·저장·백테스트) **한 바퀴 완성** + Phase 2 정교화 착수.

## 남은 단계 (Phase 2 나머지, WORKLOG.md 6절 참고)

- XBRL 컨센서스 Surprise(컨센서스 유료→보류) · sector 채우기(quoteSummary)
- 이벤트 온톨로지 정교화(other 빈발) · 클러스터링 · 표본 쌓이면 실제 가중치 튜닝

> ※ 시장반응 검증·실제 매수권한은 별도 Strategist 에이전트 몫 (이 파트 범위 밖)
