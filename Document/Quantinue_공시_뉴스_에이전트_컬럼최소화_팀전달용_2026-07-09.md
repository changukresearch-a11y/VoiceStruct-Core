# Quantinue 공시·뉴스 에이전트 컬럼 최소화 및 Strategist 전달값 정리

**프로젝트 범위:** Quantinue 단독 프로젝트  
**제외 범위:** FinRadar 관련 해석, FinRadar식 찌라시/루머 수집 구조, 투자정보 큐레이션 서비스 관점  
**작성 목적:** 05 공시 분석 에이전트와 06 뉴스 분석 에이전트의 컬럼을 최소화하고, 07 Strategist에게 전달되는 값을 명확히 정리한다.  
**작성일:** 2026-07-09  
**팀 협의 반영:** 공시와 뉴스는 통합하지 않고 `tb_disclosure`, `tb_news`를 별도 테이블로 유지한다. 점수값은 0~1 범위, 소수점 2자리 기준으로 맞춘다.

---

## 0. 최종 결정 요약

### 유지할 방향

1. **공시와 뉴스 테이블은 분리한다.**
   - 공시: `tb_disclosure`
   - 뉴스: `tb_news`

2. **Strategist가 읽는 점수 체계는 동일하게 맞춘다.**
   - `importance_score`
   - `sentiment_score`
   - `risk_score`
   - `hard_block`
   - `summary`

3. **뉴스는 대표기사 1건으로 평가하지 않는다.**
   - 기사별로 점수를 산정한다.
   - 기사별 점수를 신뢰도, 최신성, 중복성, 중요도 기준으로 가중 집계한다.
   - 최종적으로 종목별 1행을 `tb_news`에 저장한다.

4. **공시는 공식 이벤트 신호로 본다.**
   - 공시는 SEC 등 공식 공시 기반이므로 별도 `trust_score` 컬럼을 두지 않는다.
   - 내부적으로 공시 신뢰도는 `1.00`으로 간주할 수 있다.
   - 파산, 상장폐지, 회계부정, 대규모 희석 등은 `hard_block=true`로 보존한다.

5. **대표 기사/대표 공시의 제목·링크·발행시각 등은 개별 컬럼으로 늘리지 않는다.**
   - 근거 목록은 `evidence_json`에 넣는다.
   - Strategist에게 직접 필요한 값과 추적/검증용 값을 분리한다.

---

## 1. 기존 명세에서 유지할 핵심 전제

### 1.1 공시 분석 에이전트

기존 Quantinue 명세에서 공시 분석은 다음 구조를 따른다.

| 항목 | 내용 |
|---|---|
| 단계 | 05 공시 분석 |
| 입력 | `tb_daily_pick`의 50개 티커 |
| 출력 | `tb_disclosure` |
| 실행 주기 | 1시간 간격 |
| 저장 방식 | 매 사이클 50종목 각각 1행 append |
| 공시 없는 종목 | `has_signal=false`, 뒤 분석 컬럼은 `null` |
| Strategist 사용 방식 | 종목별 최신 행을 읽음 |
| 핵심 방어 | 파산·상장폐지 등 `hard_block` 스캔 |

공시는 뉴스처럼 매체별 신뢰도 편차가 크지 않다. 따라서 공시 에이전트는 **공식 이벤트를 탐지하고, 그 이벤트가 전략 판단에 중요한지·위험한지·차단 대상인지**를 압축해서 넘기는 역할을 한다.

### 1.2 뉴스 분석 에이전트

기존 Quantinue 명세에서 뉴스 분석은 다음 구조를 따른다.

| 항목 | 내용 |
|---|---|
| 단계 | 06 뉴스 분석 |
| 입력 | `tb_daily_pick`의 50개 티커 |
| 출력 | `tb_news` |
| 실행 주기 | 5분 간격 |
| 저장 방식 | 매 사이클 50종목 각각 1행 append |
| 뉴스 없는 종목 | `has_signal=false`, 뒤 분석 컬럼은 `null` |
| Strategist 사용 방식 | 종목별 최신 행을 읽음 |
| 핵심 방어 | 저신뢰 기사, 펌프성 기사, 루머성 급등 신호 방어 |

뉴스는 대표기사 1개로 평가하면 왜곡 위험이 크다. 따라서 수정안에서는 **기사별 분석 → 종목 단위 가중 집계 → Strategist 입력값 생성** 구조로 바꾼다.

---

## 2. 점수 체계 공통 규칙

### 2.1 모든 점수는 0~1 범위

팀 협의에 따라 공시·뉴스 점수는 모두 `0.00 ~ 1.00`으로 통일한다.

| 컬럼 | 범위 | 의미 |
|---|---:|---|
| `importance_score` | 0.00~1.00 | 전략 판단에 얼마나 중요한 이벤트인가 |
| `sentiment_score` | 0.00~1.00 | 악재↔호재 방향성 |
| `risk_score` | 0.00~1.00 | 매수 시 위험도가 얼마나 높은가 |
| `trust_score` | 0.00~1.00 | 뉴스 출처 신뢰도 집계값. 뉴스 전용 |

### 2.2 소수점 2자리 저장

DB 저장 기준은 소수점 2자리로 통일한다.

```python
score = round(max(0, min(1, score)), 2)
```

권장 DB 타입:

```sql
NUMERIC(3,2)
```

체크 제약:

```sql
CHECK (score_column IS NULL OR score_column BETWEEN 0.00 AND 1.00)
```

### 2.3 내부 계산과 저장값 분리

- 내부 계산은 4자리 이상으로 해도 된다.
- 최종 저장값만 소수점 2자리로 반올림한다.
- 계산 중간부터 2자리로 자르면 가중 평균에서 오차가 커질 수 있다.

### 2.4 `sentiment_score` 해석

`sentiment_score`는 0~1 범위를 쓰되, `0.50`을 중립으로 고정한다.

| 값 | 해석 |
|---:|---|
| `0.00` | 강한 악재 |
| `0.25` | 약한 악재 |
| `0.50` | 중립 |
| `0.75` | 약한 호재 |
| `1.00` | 강한 호재 |

주의할 점:

- 뉴스 문장의 긍정/부정 감정과 투자 관점의 호재/악재는 다르다.
- 예를 들어 “자금 조달 성공”은 문장상 긍정이지만, 대규모 희석이면 투자 관점에서는 악재일 수 있다.
- 따라서 `sentiment_score`는 단순 감성분석보다 `event_type` 기반 방향성을 우선한다.

### 2.5 신호 없음 처리

`has_signal=false`일 때는 점수 컬럼에 `0.00`을 넣지 않는다.

권장값:

| 컬럼 | 값 |
|---|---|
| `has_signal` | `false` |
| `filing_count` / `article_count` | `0` |
| `source_count` | `0` |
| `event_type` | `null` |
| `importance_score` | `null` |
| `sentiment_score` | `null` |
| `risk_score` | `null` |
| `trust_score` | `null` |
| `hard_block` | `false` |
| `summary` | `null` |
| `evidence_json` | `[]` 또는 `null` |

`0.00`은 “강한 악재” 또는 “위험 없음”처럼 해석될 수 있으므로, 신호 없음에는 쓰지 않는다.

---

## 3. 공시 테이블 최종 최소안

## 3.1 테이블명

```text
tb_disclosure
```

## 3.2 역할

`tb_disclosure`는 1시간마다 오늘의 50개 종목에 대해 공식 공시 신호를 분석하고, 종목별 최신 공시 상태를 한 행으로 저장하는 테이블이다.

공시는 다음을 판단한다.

1. 공시가 있었는가
2. 어떤 이벤트인가
3. 전략 판단에 중요한가
4. 호재/악재 방향성이 있는가
5. 위험도가 높은가
6. 즉시 매수 차단 대상인가
7. Strategist가 읽을 수 있는 짧은 요약은 무엇인가
8. 나중에 검증할 근거 공시번호와 원문 정보는 무엇인가

---

## 3.3 `tb_disclosure` 최종 컬럼

| No | 컬럼 | 타입 예시 | 필수 | 설명 |
|---:|---|---|---|---|
| 1 | `disclosure_id` | UUID/TEXT | ✅ | 공시 분석 행 ID |
| 2 | `cycle_id` | TEXT | ✅ | Strategist 판단 사이클 연결용 ID |
| 3 | `ticker` | TEXT | ✅ | 종목 코드 |
| 4 | `collected_at` | TIMESTAMP | ✅ | 공시 수집·분석 시각 |
| 5 | `has_signal` | BOOLEAN | ✅ | 해당 시점에 분석할 공시가 있는지 |
| 6 | `filing_count` | INT | ✅ | 해당 구간 또는 당일 집계된 공시 수 |
| 7 | `main_filing_no` | TEXT | 선택 | 대표 공시 번호. SEC accession number 등 |
| 8 | `main_filing_type` | TEXT | 선택 | 8-K, 10-Q, 10-K, S-1 등 |
| 9 | `main_filed_at` | TIMESTAMP | 선택 | 대표 공시 제출 시각 |
| 10 | `event_type` | TEXT | 선택 | 대표 이벤트 유형 |
| 11 | `importance_score` | NUMERIC(3,2) | 선택 | 공시 중요도 |
| 12 | `sentiment_score` | NUMERIC(3,2) | 선택 | 공시 방향성. 0.50 중립 |
| 13 | `risk_score` | NUMERIC(3,2) | 선택 | 공시 기반 위험도 |
| 14 | `hard_block` | BOOLEAN | ✅ | 즉시 매수 차단 여부 |
| 15 | `summary` | TEXT | 선택 | Strategist가 읽을 공시 요약 |
| 16 | `evidence_json` | JSONB | 선택 | 근거 공시 목록 |

총 16개 컬럼이다.

---

## 3.4 공시에서 제거 또는 흡수하는 컬럼

| 기존 성격 | 처리 방향 | 이유 |
|---|---|---|
| `filing_title` | `evidence_json`으로 이동 | 대표값을 별도 컬럼으로 둘 필요 낮음 |
| `sentiment` | `sentiment_score`로 통합 | 문자열 방향성과 점수 중복 |
| `reason` | `summary`에 흡수 | Strategist용 설명은 한 문단이면 충분 |
| `hard_block_reason` | `summary`에 흡수 | 차단 사유는 요약에 포함 |
| `confidence` | 제거 | 1차 MVP에서는 과함 |
| `keywords` | 제거 | 검색/태그 기능 없으면 불필요 |
| `source_trust` | 컬럼으로 두지 않음 | 공시는 공식문서이므로 내부적으로 1.00 간주 |

---

## 3.5 공시 `event_type` 권장 목록

| event_type | 의미 |
|---|---|
| `earnings` | 실적 관련 공시 |
| `guidance` | 가이던스 상향/하향 |
| `mna` | 인수합병 |
| `offering` | 유상증자, 전환사채, 주식 발행 |
| `insider` | 내부자/임원 관련 |
| `management_change` | 경영진 변경 |
| `contract` | 대형 계약 |
| `litigation` | 소송 |
| `regulatory` | 규제, 조사 |
| `delisting` | 상장폐지 관련 |
| `bankruptcy` | 파산, going concern |
| `other` | 기타 |

---

## 3.6 공시 점수 산정 원칙

공시는 공식성이 높기 때문에 출처 신뢰도는 별도 계산하지 않는다. 핵심은 이벤트 종류, 중요도, 위험도, 방향성이다.

### `importance_score`

공식:

```text
importance_score =
0.50 * event_severity
+ 0.20 * recency_score
+ 0.20 * market_relevance
+ 0.10 * novelty_score
```

해석:

| 항목 | 의미 |
|---|---|
| `event_severity` | 사건 자체의 중대성 |
| `recency_score` | 최근 공시인지 |
| `market_relevance` | 가격 판단에 직접 연결되는지 |
| `novelty_score` | 기존에 알려진 내용이 아니라 새 정보인지 |

### `sentiment_score`

공식:

```text
sentiment_score =
0.70 * event_direction
+ 0.30 * text_direction
```

- `event_direction`: 이벤트 유형 기반 방향성
- `text_direction`: 공시 본문 또는 요약문 기반 방향성
- 최종값은 0~1, 중립은 0.50

### `risk_score`

공식:

```text
risk_score = max(event_risk_score, special_risk_score)
```

- `event_risk_score`: 이벤트 유형별 기본 위험도
- `special_risk_score`: 상폐, 파산, 회계부정, 대규모 희석 등 특수 위험

### `hard_block`

공식보다 규칙 기반으로 처리한다.

```text
hard_block = true
if event_type in HARD_BLOCK_EVENTS
or risk_score >= 0.90
```

권장 `HARD_BLOCK_EVENTS`:

```text
bankruptcy
delisting
going_concern
accounting_fraud
sec_investigation
trading_halt
offering_large_dilution
reverse_split_warning
```

---

## 3.7 공시 `evidence_json` 예시

```json
[
  {
    "filing_no": "0000000000-26-000001",
    "form_type": "8-K",
    "title": "Current Report",
    "filed_at": "2026-07-09T09:10:00",
    "url": "https://www.sec.gov/..."
  }
]
```

`evidence_json`은 Strategist가 반드시 읽는 값은 아니지만, Reviewer와 디버깅에서 필요하다.

---

## 4. 뉴스 테이블 최종 최소안

## 4.1 테이블명

```text
tb_news
```

## 4.2 역할

`tb_news`는 5분마다 오늘의 50개 종목에 대한 최근 뉴스를 수집하고, 기사별 점수를 가중 집계하여 종목별 1행으로 저장하는 테이블이다.

뉴스는 대표기사 하나로 판단하지 않는다.

뉴스 에이전트는 다음을 수행한다.

1. 종목별 최근 뉴스 수집
2. 중복 기사 제거
3. 기사별 점수 산정
4. 기사별 가중치 계산
5. 종목 단위 집계 점수 계산
6. `hard_block` 스캔
7. 종목 단위 요약 생성
8. 상위 근거 기사 목록 저장
9. Strategist가 읽을 최신 1행 append

---

## 4.3 `tb_news` 최종 컬럼

| No | 컬럼 | 타입 예시 | 필수 | 설명 |
|---:|---|---|---|---|
| 1 | `news_id` | UUID/TEXT | ✅ | 뉴스 집계 행 ID |
| 2 | `cycle_id` | TEXT | ✅ | Strategist 판단 사이클 연결용 ID |
| 3 | `ticker` | TEXT | ✅ | 종목 코드 |
| 4 | `collected_at` | TIMESTAMP | ✅ | 뉴스 수집·분석 시각 |
| 5 | `window_start` | TIMESTAMP | ✅ | 뉴스 집계 시작 시각 |
| 6 | `window_end` | TIMESTAMP | ✅ | 뉴스 집계 종료 시각 |
| 7 | `has_signal` | BOOLEAN | ✅ | 분석할 뉴스가 있는지 |
| 8 | `article_count` | INT | ✅ | 집계에 사용된 기사 수 |
| 9 | `source_count` | INT | ✅ | 서로 다른 출처 수 |
| 10 | `event_type` | TEXT | 선택 | 대표 이벤트 유형 |
| 11 | `importance_score` | NUMERIC(3,2) | 선택 | 기사별 중요도 가중 집계값 |
| 12 | `sentiment_score` | NUMERIC(3,2) | 선택 | 기사별 방향성 가중 집계값 |
| 13 | `risk_score` | NUMERIC(3,2) | 선택 | 평균 위험도와 최고 위험도 반영 |
| 14 | `trust_score` | NUMERIC(3,2) | 선택 | 전체 출처 신뢰도 집계 |
| 15 | `hard_block` | BOOLEAN | ✅ | 즉시 매수 차단 여부 |
| 16 | `summary` | TEXT | 선택 | 뉴스 전체 흐름 요약 |
| 17 | `evidence_json` | JSONB | 선택 | 상위 근거 기사 목록 |

총 17개 컬럼이다.

---

## 4.4 뉴스에서 제거 또는 흡수하는 컬럼

| 기존 성격 | 처리 방향 | 이유 |
|---|---|---|
| `news_title` | `evidence_json`으로 이동 | 대표기사 기준 평가를 폐기 |
| `source` | `evidence_json`으로 이동 | 개별 기사 속성 |
| `published_at` | `evidence_json`으로 이동 | 개별 기사 속성 |
| `ref` | `evidence_json`으로 이동 | 개별 기사 URL |
| `reason` | `summary`에 흡수 | 별도 한 줄 근거보다 종합 요약이 유용 |
| `keywords` | 제거 | MVP에서는 필수 아님 |
| `news_count` | `article_count`로 명확화 | 기사 수 의미를 분명히 함 |
| `source_trust` | `trust_score`로 명칭 변경 | 집계값임을 명확히 함 |
| `grade_score` | `trust_score`로 흡수 | 도메인 등급과 LLM 판단 중복 방지 |
| `peak_importance` | 컬럼 제거, 산식에 반영 | 최고 중요도는 계산에만 사용 |
| `confidence` | 제거 | MVP에서는 과함 |
| `top_evidence` | `evidence_json`으로 대체 | 근거 목록을 JSON으로 통합 |
| `disclosure_ref` | 2차로 보류 | 뉴스-공시 교차확인은 구현 난도 높음 |

---

## 4.5 뉴스 `event_type` 권장 목록

| event_type | 의미 |
|---|---|
| `earnings_news` | 실적 관련 기사 |
| `analyst_rating` | 애널리스트 등급/목표가 변경 |
| `product` | 제품, 기술, 서비스 관련 |
| `partnership` | 제휴, 계약 |
| `mna_rumor` | 인수합병 루머 |
| `lawsuit` | 소송 |
| `regulatory` | 규제, 승인, 조사 |
| `macro_sensitive` | 금리, 유가, 환율, 경기 등 외부 변수 관련 |
| `social_hype` | 밈, 커뮤니티 과열, 펌프성 이슈 |
| `other` | 기타 |

---

## 4.6 뉴스 기사별 점수 산정

뉴스는 먼저 기사별로 다음 값을 산정한다.

| 기사별 값 | 범위 | 설명 |
|---|---:|---|
| `article_importance_score` | 0.00~1.00 | 해당 기사의 중요도 |
| `article_sentiment_score` | 0.00~1.00 | 해당 기사의 호재/악재 방향성 |
| `article_risk_score` | 0.00~1.00 | 해당 기사 기반 위험도 |
| `article_trust_score` | 0.00~1.00 | 해당 기사 출처 신뢰도 |
| `article_recency_score` | 0.00~1.00 | 최신성 |
| `article_novelty_score` | 0.00~1.00 | 중복이 아닌 새 정보인지 |

기사별 점수는 저장 테이블 컬럼으로 만들 필요는 없다.  
다만 `evidence_json`에 상위 기사 몇 개의 점수는 남길 수 있다.

---

## 4.7 뉴스 기사별 가중치

기사별 가중치는 다음과 같이 계산한다.

```text
article_weight =
article_trust_score
* article_recency_score
* article_novelty_score
* article_importance_score
```

의미:

| 요소 | 역할 |
|---|---|
| `article_trust_score` | 믿을 수 있는 기사일수록 영향 증가 |
| `article_recency_score` | 최신 기사일수록 영향 증가 |
| `article_novelty_score` | 중복 기사 영향 감소 |
| `article_importance_score` | 중요한 기사일수록 영향 증가 |

단순 평균을 쓰지 않는 이유:

```text
고신뢰 기사 1건 + 저신뢰 펌프성 기사 5건
→ 단순 평균을 내면 저신뢰 기사 수가 많다는 이유로 전체 점수가 왜곡될 수 있음
```

---

## 4.8 뉴스 종목 단위 집계 공식

### `sentiment_score`

```text
sentiment_score =
Σ(article_sentiment_score_i * article_weight_i)
/
Σ(article_weight_i)
```

대표기사 하나의 감성이 아니라, 기사 묶음 전체의 가중 방향성이다.

### `importance_score`

```text
importance_score =
0.70 * weighted_avg(article_importance_score)
+ 0.30 * max(article_importance_score)
```

이유:

- 중요 뉴스 1건이 잡뉴스 여러 건에 묻히지 않게 한다.
- 동시에 전체 기사 흐름도 반영한다.

### `risk_score`

```text
risk_score =
max(
  weighted_avg(article_risk_score),
  max(article_risk_score)
)
```

이유:

- 위험 뉴스는 한 건만 있어도 중요하다.
- 파산, 상폐, 소송, 조사, 임상 실패, 대규모 희석 같은 위험이 평균에 묻히면 안 된다.

### `trust_score`

```text
trust_score =
weighted_avg(article_trust_score)
```

출처 신뢰도는 도메인 등급, 기사 품질, 다른 출처 확인 여부를 종합한다.

### `hard_block`

```text
hard_block = true
if any(article_hard_block == true and article_trust_score >= 0.60)
or risk_score >= 0.90
```

저신뢰 소문 하나만으로 바로 차단하지 않기 위해, 뉴스 기반 `hard_block`에는 최소 신뢰도 조건을 둔다.  
단, 공식 매체나 고신뢰 매체에서 파산·상폐·거래정지 등 치명적 이슈가 확인되면 즉시 차단한다.

---

## 4.9 뉴스 저신뢰 보정 규칙

뉴스는 LLM이 과도하게 호재/악재로 판단할 수 있으므로, 최종 저장 전 룰 보정이 필요하다.

권장 규칙:

```text
if trust_score < 0.30:
    importance_score = min(importance_score, 0.60)
    sentiment_score = clamp(sentiment_score, 0.35, 0.65)
```

의미:

- 신뢰도가 낮은 뉴스는 강한 호재/악재로 반영하지 않는다.
- 단, 위험 이슈는 완전히 무시하지 않는다.
- 저신뢰 뉴스라도 `risk_score`가 높으면 Strategist에게 “주의”로 전달할 수 있다.

---

## 4.10 뉴스 `evidence_json` 예시

```json
[
  {
    "title": "Apple shares rise after stronger iPhone demand report",
    "source": "Reuters",
    "url": "https://...",
    "published_at": "2026-07-09T09:22:00",
    "importance_score": 0.78,
    "sentiment_score": 0.72,
    "risk_score": 0.21,
    "trust_score": 0.92,
    "weight": 0.52
  },
  {
    "title": "Analysts raise Apple outlook",
    "source": "MarketWatch",
    "url": "https://...",
    "published_at": "2026-07-09T09:28:00",
    "importance_score": 0.64,
    "sentiment_score": 0.67,
    "risk_score": 0.25,
    "trust_score": 0.78,
    "weight": 0.31
  }
]
```

`evidence_json`에는 전체 기사를 모두 넣지 않고, 점수에 가장 크게 기여한 상위 2~3개만 넣어도 된다.  
전체 원문 저장이 필요하면 별도 raw 저장소나 로그 파일을 쓰는 것이 낫다.

---

## 5. Strategist에게 직접 전달되는 값

DB 컬럼 전체를 Strategist 프롬프트에 넣을 필요는 없다.  
Strategist에게는 압축된 신호만 전달한다.

---

## 5.1 공시 에이전트 → Strategist

```json
{
  "disclosure_signal": {
    "has_signal": true,
    "event_type": "earnings",
    "importance_score": 0.82,
    "sentiment_score": 0.76,
    "risk_score": 0.18,
    "hard_block": false,
    "summary": "공식 실적 공시에서 매출과 이익 개선이 확인됨."
  }
}
```

공시에서 Strategist가 직접 읽는 핵심값:

| 값 | 사용 목적 |
|---|---|
| `has_signal` | 공시 신호 존재 여부 |
| `event_type` | 사건 종류 |
| `importance_score` | 전략 판단상 중요도 |
| `sentiment_score` | 호재/악재 방향성 |
| `risk_score` | 공시 기반 위험도 |
| `hard_block` | 즉시 보류/차단 여부 |
| `summary` | GPT 판단 근거 |

공시의 `main_filing_no`, `main_filed_at`, `evidence_json`은 주로 추적·검증용이다.  
필요하면 Strategist 프롬프트 하단 근거로 붙일 수 있지만, 기본 입력값은 아니다.

---

## 5.2 뉴스 에이전트 → Strategist

```json
{
  "news_signal": {
    "has_signal": true,
    "article_count": 8,
    "source_count": 5,
    "event_type": "earnings_news",
    "importance_score": 0.71,
    "sentiment_score": 0.68,
    "risk_score": 0.29,
    "trust_score": 0.83,
    "hard_block": false,
    "summary": "실적 전망 상향과 긍정적 애널리스트 코멘트가 다수 확인됨."
  }
}
```

뉴스에서 Strategist가 직접 읽는 핵심값:

| 값 | 사용 목적 |
|---|---|
| `has_signal` | 뉴스 신호 존재 여부 |
| `article_count` | 이슈 확산도 |
| `source_count` | 다중 출처 확인 |
| `event_type` | 대표 사건 유형 |
| `importance_score` | 뉴스 묶음 중요도 |
| `sentiment_score` | 뉴스 묶음 방향성 |
| `risk_score` | 뉴스 기반 위험도 |
| `trust_score` | 출처 신뢰도 |
| `hard_block` | 즉시 보류/차단 여부 |
| `summary` | GPT 판단 근거 |

뉴스의 `evidence_json`은 주로 근거 확인용이다.  
대표기사 1개로 판단하지 않으므로, `evidence_json`은 점수 산정의 근거를 설명하는 보조값이다.

---

## 6. Strategist 판단에서 쓰는 기본 규칙

### 6.1 즉시 보류 규칙

```text
if disclosure_signal.hard_block == true:
    decision = HOLD

if news_signal.hard_block == true:
    decision = HOLD
```

`hard_block`은 점수보다 우선한다.

### 6.2 공시·뉴스가 모두 없을 때

```text
if disclosure_signal.has_signal == false
and news_signal.has_signal == false:
    Strategist는 기술분석, 매크로, 실시간시세 중심으로 판단
```

### 6.3 뉴스 신뢰도가 낮을 때

```text
if news_signal.trust_score < 0.40:
    news_signal은 약한 참고 신호로만 사용
```

### 6.4 위험도 우선 규칙

```text
if risk_score >= 0.80:
    매수 판단 시 강한 감점
```

특히 뉴스는 호재성 `sentiment_score`가 높아도 `risk_score`가 높을 수 있다.  
예를 들어 저신뢰 소형주 급등 뉴스는 `sentiment_score=0.70`, `risk_score=0.75`, `trust_score=0.35`가 될 수 있다.

---

## 7. SQL 예시

아래 SQL은 팀 구현 시 참고용이다. 실제 프로젝트의 ID 생성 방식, timezone, hypertable 정책에 맞춰 조정한다.

---

## 7.1 `tb_disclosure`

```sql
CREATE TABLE IF NOT EXISTS tb_disclosure (
    disclosure_id TEXT PRIMARY KEY,
    cycle_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    collected_at TIMESTAMPTZ NOT NULL,

    has_signal BOOLEAN NOT NULL DEFAULT FALSE,
    filing_count INT NOT NULL DEFAULT 0 CHECK (filing_count >= 0),

    main_filing_no TEXT,
    main_filing_type TEXT,
    main_filed_at TIMESTAMPTZ,

    event_type TEXT,

    importance_score NUMERIC(3,2)
        CHECK (importance_score IS NULL OR importance_score BETWEEN 0.00 AND 1.00),
    sentiment_score NUMERIC(3,2)
        CHECK (sentiment_score IS NULL OR sentiment_score BETWEEN 0.00 AND 1.00),
    risk_score NUMERIC(3,2)
        CHECK (risk_score IS NULL OR risk_score BETWEEN 0.00 AND 1.00),

    hard_block BOOLEAN NOT NULL DEFAULT FALSE,

    summary TEXT,
    evidence_json JSONB
);

CREATE INDEX IF NOT EXISTS idx_tb_disclosure_cycle_ticker
ON tb_disclosure (cycle_id, ticker);

CREATE INDEX IF NOT EXISTS idx_tb_disclosure_ticker_collected
ON tb_disclosure (ticker, collected_at DESC);
```

---

## 7.2 `tb_news`

```sql
CREATE TABLE IF NOT EXISTS tb_news (
    news_id TEXT PRIMARY KEY,
    cycle_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    collected_at TIMESTAMPTZ NOT NULL,

    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,

    has_signal BOOLEAN NOT NULL DEFAULT FALSE,
    article_count INT NOT NULL DEFAULT 0 CHECK (article_count >= 0),
    source_count INT NOT NULL DEFAULT 0 CHECK (source_count >= 0),

    event_type TEXT,

    importance_score NUMERIC(3,2)
        CHECK (importance_score IS NULL OR importance_score BETWEEN 0.00 AND 1.00),
    sentiment_score NUMERIC(3,2)
        CHECK (sentiment_score IS NULL OR sentiment_score BETWEEN 0.00 AND 1.00),
    risk_score NUMERIC(3,2)
        CHECK (risk_score IS NULL OR risk_score BETWEEN 0.00 AND 1.00),
    trust_score NUMERIC(3,2)
        CHECK (trust_score IS NULL OR trust_score BETWEEN 0.00 AND 1.00),

    hard_block BOOLEAN NOT NULL DEFAULT FALSE,

    summary TEXT,
    evidence_json JSONB
);

CREATE INDEX IF NOT EXISTS idx_tb_news_cycle_ticker
ON tb_news (cycle_id, ticker);

CREATE INDEX IF NOT EXISTS idx_tb_news_ticker_collected
ON tb_news (ticker, collected_at DESC);
```

---

## 8. 기존 명세 대비 수정 요약

### 8.1 공시

| 항목 | 기존 방향 | 수정 방향 |
|---|---|---|
| 컬럼 수 | 18필드 수준 | 16필드 최소안 |
| 공시 제목 | 별도 컬럼 | `evidence_json` |
| 점수 근거 | `reason` 별도 | `summary`에 흡수 |
| 차단 사유 | `hard_block_reason` 별도 | `summary`에 흡수 |
| 키워드 | 별도 컬럼 | 제거 |
| confidence | 별도 컬럼 | 제거 |
| source_trust | 별도 고려 가능 | 공시는 내부적으로 1.00 간주 |

### 8.2 뉴스

| 항목 | 기존 방향 | 수정 방향 |
|---|---|---|
| 대표기사 | 대표기사 1건 중심 | 기사별 점수의 종목 단위 집계 |
| `news_title` | 대표기사 제목 | `evidence_json`으로 이동 |
| `source` | 대표기사 출처 | `evidence_json`으로 이동 |
| `published_at` | 대표기사 발행시각 | `evidence_json`으로 이동 |
| `ref` | 대표기사 링크 | `evidence_json`으로 이동 |
| `news_count` | 기사 수 | `article_count`로 명확화 |
| `source_trust` + `grade_score` | 둘 다 존재 | `trust_score` 하나로 통합 |
| `peak_importance` | 별도 컬럼 | 집계 공식에만 반영 |
| `top_evidence` | 별도 컬럼 | `evidence_json`으로 대체 |
| `disclosure_ref` | 신설 제안 | 2차로 보류 |

---

## 9. 구현 흐름

## 9.1 공시 에이전트 처리 흐름

```text
1. cycle_id 수신 또는 생성
2. tb_daily_pick에서 50개 ticker 조회
3. 각 ticker별 최근 공시 수집
4. 공시 고유번호 기준 중복 제거
5. event_type 분류
6. importance_score, sentiment_score, risk_score 산정
7. hard_block 룰 스캔
8. summary 생성
9. evidence_json 구성
10. ticker당 1행씩 tb_disclosure append
11. 공시 없는 ticker도 has_signal=false로 1행 생성
```

## 9.2 뉴스 에이전트 처리 흐름

```text
1. cycle_id 수신 또는 생성
2. tb_daily_pick에서 50개 ticker 조회
3. 각 ticker별 최근 뉴스 수집
4. URL 또는 google_link 기준 중복 제거
5. 기사별 event_type, importance, sentiment, risk, trust 산정
6. 기사별 recency, novelty 산정
7. article_weight 계산
8. 종목 단위 weighted aggregate 계산
9. risk_score는 max 위험도 보존
10. hard_block 룰 스캔
11. summary 생성
12. evidence_json 구성
13. ticker당 1행씩 tb_news append
14. 뉴스 없는 ticker도 has_signal=false로 1행 생성
```

---

## 10. cycle_id 규칙

`cycle_id`는 07 Strategist, 08 Critic, 09 리스크·포트폴리오, 11 Reviewer까지 이어지는 연결 키다.  
따라서 공시·뉴스 에이전트가 임의로 서로 다른 `cycle_id`를 만들면 안 된다.

권장:

```text
cycle_id는 오케스트레이터 또는 스케줄러가 생성한다.
공시·뉴스·기술·매크로·Strategist가 같은 cycle_id를 공유한다.
```

예시:

```text
20260709_103500
```

만약 공시가 1시간 주기이고 뉴스가 5분 주기라면, Strategist는 다음 방식으로 읽을 수 있다.

```text
뉴스: 현재 cycle_id 또는 가장 가까운 최신 cycle
공시: 현재 시점 기준 가장 최신 tb_disclosure row
```

단, 가능하면 07 Strategist 실행 시점에 최신 뉴스·공시 row를 묶어 하나의 판단 입력 객체를 만드는 별도 adapter를 두는 것이 안전하다.

---

## 11. 최종 Strategist 입력 객체 예시

```json
{
  "ticker": "AAPL",
  "cycle_id": "20260709_103500",
  "disclosure_signal": {
    "has_signal": true,
    "event_type": "earnings",
    "importance_score": 0.82,
    "sentiment_score": 0.76,
    "risk_score": 0.18,
    "hard_block": false,
    "summary": "공식 실적 공시에서 매출과 이익 개선이 확인됨."
  },
  "news_signal": {
    "has_signal": true,
    "article_count": 8,
    "source_count": 5,
    "event_type": "earnings_news",
    "importance_score": 0.71,
    "sentiment_score": 0.68,
    "risk_score": 0.29,
    "trust_score": 0.83,
    "hard_block": false,
    "summary": "실적 전망 상향과 긍정적 애널리스트 코멘트가 다수 확인됨."
  }
}
```

---

## 12. 최종 체크리스트

### DB

- [ ] `tb_disclosure`와 `tb_news`는 분리 유지
- [ ] 공시 16개 컬럼으로 최소화
- [ ] 뉴스 17개 컬럼으로 최소화
- [ ] 점수 컬럼은 `NUMERIC(3,2)`
- [ ] 점수 범위 `0.00~1.00` 체크 제약 추가
- [ ] `has_signal=false`일 때 점수 컬럼은 `null`
- [ ] `hard_block`은 boolean 유지
- [ ] `evidence_json`은 JSONB 사용

### 공시 에이전트

- [ ] 1시간마다 50종목 처리
- [ ] 공시 없는 종목도 1행 생성
- [ ] 공시별 여러 행이 아니라 종목별 집계 1행
- [ ] `risk_score`는 치명적 위험이 평균에 묻히지 않게 처리
- [ ] `hard_block`은 룰 기반으로 확정
- [ ] 공시 신뢰도는 내부적으로 `1.00`

### 뉴스 에이전트

- [ ] 5분마다 50종목 처리
- [ ] 뉴스 없는 종목도 1행 생성
- [ ] 대표기사 1개로 점수 산정하지 않음
- [ ] 기사별 점수 산정 후 가중 집계
- [ ] 단순 평균 금지
- [ ] 위험도는 최고 위험 기사 보존
- [ ] `trust_score` 낮은 뉴스는 호재/악재 과대반영 방지
- [ ] 상위 근거 기사는 `evidence_json`에 저장

### Strategist

- [ ] 공시·뉴스의 전체 컬럼이 아니라 압축 신호만 입력
- [ ] `hard_block=true`면 GPT 판단 전 즉시 보류 가능
- [ ] `importance_score`, `sentiment_score`, `risk_score`는 핵심 판단값
- [ ] 뉴스의 `trust_score`가 낮으면 약한 참고 신호로 처리
- [ ] `summary`는 GPT 판단 근거로 사용

---

## 13. 최종 결론

이번 수정안의 핵심은 다음이다.

```text
공시·뉴스 테이블은 분리한다.
하지만 Strategist가 읽는 점수 체계는 최대한 통일한다.
뉴스는 대표기사 하나로 판단하지 않고 기사별 점수를 가중 집계한다.
공시는 공식 신호로 보고 trust_score 컬럼은 생략한다.
대표 기사/대표 공시의 세부 정보는 evidence_json으로 내린다.
Strategist에게는 압축된 신호값만 전달한다.
```

최종 테이블:

```text
tb_disclosure: 16개 컬럼
tb_news: 17개 컬럼
```

최종 핵심 점수:

```text
importance_score
sentiment_score
risk_score
trust_score(뉴스 전용)
hard_block
summary
```

이 구조가 1차 MVP에서 구현 복잡도를 낮추면서도, Strategist가 실제로 판단하는 데 필요한 신호는 유지하는 가장 현실적인 방식이다.
