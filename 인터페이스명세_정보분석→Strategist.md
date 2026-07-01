# 정보분석(①공시·②뉴스) → ⑤Strategist 인터페이스 명세 + 근거

> 작성: 정보분석 담당(정창욱) · 대상: Strategist 담당(이은미)
> 목적: **Strategist에 넘길 값의 형식(스키마)** 과 **각 파라미터를 왜 그렇게 잡았는지(근거)** 를 함께 정리.
> 이 계약(`AnalysisBundle`)을 `app/common/`에 공유로 두고 양쪽이 같은 틀을 본다.

---

## ⚡ TL;DR (3줄 요약)

1. **무엇을** — 공시·뉴스 신호를 **종목당 1개 `AnalysisBundle`** 로 압축·집계해서 Strategist에 넘긴다. (날것 신호 다발 X)
2. **왜 이 형식** — Strategist는 **종목 단위 종합자 + 강한 모델(Claude)** 이라, 정제된 입력이 토큰·정확도에 유리. LLM엔 `to_prompt()` 압축 텍스트, 코드엔 타입 객체 (한 객체 두 얼굴).
3. **놓치면 안 되는 3규칙** — ① **종목당 1개로 집계**(뉴스 10건 덤프 금지) ② **하드리스크(상폐·going concern)는 sentiment에 안 녹이고 `hard_block` 별도 플래그** ③ **CoT·근거 전체는 프롬프트에서 빼고 DB에만**(비용↓·정확도↑).

> 상세 근거는 아래 §2~§6, **공유할 event_type 표준안은 §10**, 이은미와 정할 것은 §9.

---

## 0. 이 문서 읽는 법 — 근거 출처 3종

각 결정의 "왜"는 아래 출처로 표기한다:

| 표기 | 뜻 |
|---|---|
| **[설계 §N]** | 팀 상세 설계서 `0701.html`의 해당 섹션 원칙 |
| **[메모리]** | 우리 정보분석 개발에서 이미 확정한 결정(컷라인) |
| **[데이터]** | SEC 공시·RSS 뉴스의 실제 특성(구현하며 확인) |

---

## 1. 왜 이 계약이 필요한가 (전체 근거)

- **Strategist는 "종목 단위 종합자"** — 분석가 4명(공시·뉴스·기술·매크로) 신호를 종목 하나씩 모아 "살까/팔까"를 제안. **[설계 §05-⑤]**
- **Strategist는 강한 모델(Claude Opus)** 이고 호출이 적다 → 입력은 **압축·정제**돼야 토큰·정확도에 유리. **[설계 §01, §05-⑤]**
- **출력 스키마를 강제(PydanticAI)** 해 "출력 깨짐"을 막는 게 이 시스템의 핵심 안전장치 → **입력도 타입 계약으로** 고정하는 게 같은 사상. **[설계 §08]**
- 그래서 우리(공시·뉴스)는 **날것 신호를 던지지 않고**, 종목당 1개로 집계·압축한 **`AnalysisBundle`** 을 넘긴다.

---

## 2. `AnalystSignal` — 공시·뉴스 공통 신호 (envelope)

Strategist가 공시/뉴스를 **균일하게** 소비하도록, 둘을 같은 모양으로 감싼다.

```python
class AnalystSignal(BaseModel):
    source: Literal["disclosure", "news"]
    event_type: EventType              # app/common/ontology.py 공유 (통일 11종)
    sentiment: Literal["positive", "negative", "neutral", "mixed"]
    score: int             # -10 .. +10  (방향×신뢰반영 강도)
    importance: int        # 0 .. 10     (뉴스는 신뢰가중 평균)
    peak_importance: int   # 0 .. 10     (집계 전 최고 잠재 중요도)
    confidence: float      # 0.0 .. 1.0
    is_confirmed: bool
    reason: str
    ref: str
```

| 파라미터 | 잡은 값 | **왜 이렇게 잡았나 (근거)** |
|---|---|---|
| `source` | `disclosure`/`news` | 공시·뉴스는 **판단 로직은 분리, 배관은 공유** 원칙 → 출처만 태깅해 같은 틀로. Strategist가 유형별 가중치 줄 때 "공시 가중/뉴스 가중"을 구분해야 함(안정형=공시, 공격형=뉴스). **[메모리]·[설계 §05-⑤, §09]** |
| `event_type` | **통일 11종**(§10) | 이벤트 종류로 1차 성격이 갈림(8-K=사건, 10-Q/K=실적, Form4=내부자…). **19종으로 잘게 안 나눔** — 종목당 표본 부족 → 성과검증 무의미. 공시·뉴스가 `app/common/ontology.py` 한 곳을 공유. **[설계 §05-①]·[메모리]** |
| `sentiment` | positive/negative/neutral/**mixed** | 설계의 호재/악재/중립에 **mixed** 추가 — 실제 공시·뉴스엔 "호재+악재 혼재"가 잦아 억지 3분류는 정보 손실. **[설계 §05-①]·[데이터]** |
| `score` | **−10 ~ +10** | **방향(부호)+강도를 한 숫자로.** 뒤의 PM이 **EV=상승확률×이익−하락확률×손실**을 계산할 때 부호 있는 수치가 바로 필요. 0~10(강도만)이면 방향을 또 봐야 함. **[설계 §05-⑦, §06]** |
| `importance` | **0 ~ 10** | 설계가 명시한 공시 중요도 척도 그대로(거래정지=10, 대형 M&A=8~9, 자사주=6~7…). **점수 높은 것만 크게 반영**하는 게 설계 규칙이라 척도를 맞춤. 뉴스 집계 시엔 **신뢰가중 평균**(score와 같은 기준으로 통일). **[설계 §05-①]** |
| `peak_importance` | 0 ~ 10 | 뉴스 여러 건 집계 전 **최고 잠재 중요도**. 실적 헤드라인처럼 "잠재적으론 큰데 저신뢰라 눌린" 경우를 Strategist가 알 수 있게 병기(`[최고imp7·저신뢰]`). 공시는 0(단건). **[데이터]** |
| `confidence` | **0.0 ~ 1.0** (certainty × is_confirmed × source_trust 종합) | 뉴스는 **찌라시·루머**가 많아 "얼마나 믿을 값이냐"를 방향과 **별도**로 줘야 함. 설계의 신뢰도 4겹(출처·교차·사실여부·가격반응)을 하나의 0~1로 압축. Strategist·Risk Critic이 "미확인은 약하게" 판단하는 근거. **[설계 §05-②, §06]** |
| `is_confirmed` | bool | 설계가 명시한 필드. "~알려져/전망/소문"(추측) vs "발표/공시"(확정) 구분. **루머 단독 시그널은 Risk Critic이 기각**하므로 반드시 넘겨야 함. **[설계 §05-②-신뢰도필터]** |
| `reason` | 한 줄 문자열 | 설계의 공시/뉴스 출력에 `reason` 명시. **결정 저널("왜 샀나")에 기록**되므로 짧고 근거 명확하게. **[설계 §05-①, §05-⑤]** |
| `ref` | accession/링크 | **감사추적·백테스트 replay용.** 프롬프트엔 안 넣어도 되지만 DB/저널엔 필수(공시 filed 원문·기사 링크 역추적). **[메모리]·[데이터]** |

---

## 3. `AnalysisBundle` — 종목당 1개 (Strategist 입력 단위)

```python
class AnalysisBundle(BaseModel):
    ticker: str
    as_of: str
    disclosure: AnalystSignal | None
    news: AnalystSignal | None        # 여러 건을 집계한 대표 1개
    news_count: int                   # 확정 n · 루머 m
    net_sentiment: int                # -10 .. +10 (공시+뉴스 종합)
    hard_block: bool
    hard_block_reason: str | None
    top_evidence: list[str]           # 최대 2개
    def to_prompt(self) -> str: ...
```

| 파라미터 | 잡은 값 | **왜 이렇게 잡았나 (근거)** |
|---|---|---|
| **종목당 1개(Bundle)** | ticker 단위 | Strategist는 **종목 하나씩** 종합. 뉴스 10건을 그대로 주면 토큰 폭증+노이즈 → 우리가 미리 합쳐서 준다. **[설계 §05-⑤]** |
| `disclosure` / `news` | 각 1개(nullable) | 공시만/뉴스만 있는 종목이 흔함 → **없으면 None**. Strategist가 "한쪽만 있으니 보수적으로"를 판단. **[데이터]** |
| `news_count` | 확정 n·루머 m | 뉴스는 **다중 출처 교차확인**이 신뢰의 핵심 → "확정 3·루머 2"를 보여주면 Strategist가 "확정 여러 곳이면 신뢰↑, 한 곳뿐이면 루머 의심". **[설계 §05-②-신뢰도필터]** |
| `net_sentiment` | −10~+10 | 공시+뉴스를 합친 **한 눈에 보는 방향**. 단 **강한 악재가 있으면 보수적으로 그쪽**(가장 보수적 채택). **[메모리]** |
| **`hard_block`** | bool (override) | ⭐ 상폐·거래정지·going concern은 **LLM이 반박·해석하면 안 되는 안전장치**. sentiment에 녹이지 않고 **별도 플래그**로 박아 게이트가 즉시 매수금지·강제청산. "지능이 아니라 안전장치". **[설계 §05-①-🔗, §10-하드룰]·[메모리]** |
| `hard_block_reason` | str/None | 왜 막혔는지(예: "going concern") — 결정 저널·리뷰용. **[설계 §05-⑨]** |
| `top_evidence` | 최대 2개 | 근거 헤드라인 top 2만. **나머지는 DB에.** 프롬프트 비용↓, 판단엔 대표 근거면 충분. **[메모리]** |
| `to_prompt()` | 압축 텍스트 | LLM은 20필드 JSON보다 **라벨된 짧은 텍스트**를 더 잘 분석 → 같은 객체에서 코드용(타입)·LLM용(텍스트) 두 얼굴 제공. **[설계 §08]** |

---

## 4. 여러 건 → 종목당 1개 "집계 규칙" (+근거)

가장 중요한 부분. 어떻게 합치느냐로 신호 품질이 갈린다.

| 항목 | 규칙 | **근거** |
|---|---|---|
| **방향(sentiment/score)** | **확정(is_confirmed) 뉴스 위주** + source_trust·최신성 가중 평균. 루머는 감점 | 미확인·소문에 휘둘리면 펌프에 당함. 설계의 신뢰도 4겹·"미확인 감점". **[설계 §05-②]** |
| **강한 악재 우선** | 신뢰가중 평균이되, **강한 악재 1건이라도 있으면 그쪽으로 보수적** | "틀려도 작게 잃기"·"가장 보수적 채택". **[설계 §01-5원칙]·[메모리]** |
| **hard_block** | 공시·뉴스 어디든 BLOCK류면 `true` | 안전장치는 **가장 강한 것 하나면 발동**. **[설계 §10]** |
| **confidence** | certainty × is_confirmed × source_trust 조합 | 방향과 신뢰를 분리해야 Strategist가 "방향은 호재지만 신뢰 낮음"을 구분. **[설계 §05-②]** |
| **재평가 트리거** | 새 공시·뉴스 없으면 Bundle 안 바뀜(변화 트리거) | "상황 안 바뀌면 결론도 같다" → 재평가·재호출 스킵으로 비용↓. **[설계 §05-⑥-변화트리거]·[메모리]** |

---

## 5. 포함 / 제외 (+근거)

| 프롬프트에 **넣기** | DB에만 **남기기(제외)** | **왜 제외** |
|---|---|---|
| sentiment·score·importance·confidence | `reasoning`(CoT 전체) | 판단용 아님. 넣으면 토큰↑·노이즈↑ → 오히려 분석 흐림 |
| is_confirmed·event_type·한줄 reason | `evidence_quotes` 전체 | 대표 2개면 충분, 전체는 감사용 |
| hard_block(+이유)·net_sentiment | `risk_score` 내부값·`trade_permission` 원본 | 내부 계산치 → 최종 hard_block만 있으면 됨 |
| top 2 근거 | 원문 본문 | 이미 우리가 해석 완료 |

> 근거: **[메모리]** CoT·증거는 **감사·백테스트·결정저널용**이지 Strategist 판단용이 아님. 빼면 비용↓ + 판단 정확도↑.

---

## 6. 전달 "방식" (+근거)

- **주 경로 = in-memory 객체.** 설계 파이프라인이 **단방향 1패스(같은 프로세스)** 라, 우리 signals → `AnalysisBundle` 어댑터로 변환해 Strategist 함수에 객체째 전달. LLM 프롬프트엔 `to_prompt()` 텍스트만. **[설계 §03, §08]**
- **부 경로 = DB(`disclosure_signals`/`news_signals`) 사본** — audit·백테스트·결정저널·replay용. 이미 구현됨. **[메모리]**

---

## 7. 기존 스키마 → envelope 매핑 (참고)

이미 구현된 `DisclosureSignal`/`NewsSignal`에서 어떻게 뽑는지:

| envelope 필드 | 공시(DisclosureSignal)에서 | 뉴스(NewsSignal)에서 |
|---|---|---|
| `event_type` | `event_type` | `event_type` |
| `sentiment` | `sentiment` | `sentiment` |
| `score` | `importance` × sentiment 부호 | `importance` × sentiment 부호 |
| `importance` | `importance` | `importance` |
| `confidence` | `certainty_level`→수치화 | `certainty_level` × `is_confirmed` × `source_trust` |
| `is_confirmed` | 공시는 기본 True(도장 찍힌 사실) | `is_confirmed` |
| `hard_block` | `final_permission`∈{BLOCK_ALL,BLOCK_BUY} | 〃 |
| `reason` | `reason` | `reason` |
| `ref` | `accession_no`/url | 기사 link |

> 공시가 `is_confirmed=True` 기본인 근거: 공시는 **법적 의무 제출·거짓 시 처벌 = "도장 찍힌 사실"**. **[설계 §05-①]**

---

## 8. `to_prompt()` 렌더 예시 (Strategist가 실제로 보는 것)

**(가상 예시 — 형식 이해용)**
```
[NVDA] as_of 2026-07-01
 공시: guidance_change / positive(+7) 중요도7 conf0.8 확정
       "가이던스 상향, 데이터센터 매출 사상 최고"
 뉴스: 5건(확정3·루머2) → positive(+6) conf0.6
       "Reuters: 신제품 대량 공급계약"
 종합: net_sentiment +6 · hard_block=false
```

하드리스크(가상) 예시:
```
[XYZ] as_of 2026-07-01
 공시: delisting_halt / negative(-9) 중요도9 conf0.9 확정
       "10-Q 본문에 going concern(계속기업 불확실성)"
 종합: net_sentiment -9 · hard_block=TRUE  ← 매수금지 override
```

### ✅ 실제 실행 결과 (2026-07-01 NVDA · 라이브 파이프라인)

`python run_bundle.py --ticker NVDA --form 8-K --news-limit 8 --llm` 실제 출력:
```
[NVDA] as_of 2026-07-01
 공시: management_change / positive(+4) 중요도4 conf0.9 확정
       "사외이사 10명 선출, 경영진 보수 승인 → 주주 신뢰 높음."
 뉴스: 8건(확정1·루머7) → positive(+3) 중요도5 conf0.14 [최고imp7·저신뢰]
       "Investopedia: Nvidia Earnings Live: AI Chip Giant Beats Street Expectation"
 종합: net_sentiment +4 · hard_block=false
```

**이 실물이 보여주는 것 (설계 작동 증거):**
- **뉴스 conf 0.14 (낮음)** — 8건 중 **확정 1·루머 7**이라 신뢰가 확 깎임. "루머뿐이면 신뢰↓"(§4) 실작동.
- **`[최고imp7·저신뢰]` 병기** — 실적 beat 헤드라인(잠재 중요도 7)이 있지만 대부분 저신뢰라, **신뢰반영 중요도는 5·score +3**으로 눌림. 잠재값과 반영값을 **둘 다** 보여줘 판단 정보 유지.
- **net +4** — 공시(conf0.9)가 뉴스(conf0.14)보다 신뢰 높아 **신뢰가중 평균이 공시 쪽으로** 기욺.
- LLM 비결정성으로 실행마다 ±1~2 흔들릴 수 있음(정상).

---

## 9. 이은미와 합의할 열린 질문

1. **`score`(−10~+10) vs `importance`(0~10) 둘 다 필요?** — Strategist가 방향은 sentiment로 보고 강도는 importance만 쓰면 score 생략 가능. 단 PM의 EV 계산엔 부호 있는 score가 편함. → **어디서 방향×강도를 합칠지** 합의.
2. **집계 가중치(신뢰·최신성) 계수** — 초기값은 임의라, **백테스트로 튜닝**할 것(자동조정 아님·수동). **[메모리]** 초기 계수 같이 정하자.
3. **`event_type` 표준 목록** — 공시/뉴스가 쓰는 종류를 **하나로 통일**해야 Strategist·백테스트 집계가 맞음. → **초안을 §10에 제시**했으니 이걸 베이스로 확정하자.
4. **매크로/기술 신호와의 결합 위치** — Bundle은 공시·뉴스만. 기술(③)·매크로(④)는 Strategist가 별도로 받아 합치는지, 아니면 공통 Bundle에 합류시킬지.

---

## 10. `event_type` 표준목록 초안 (논의 베이스)

지금 코드는 **공시 9종 / 뉴스 8종**으로 따로 돌아간다. 겹치는 건 합치고 고유한 건 살려 **통일 10종(+other)** 으로 제안한다. (Strategist 가중치·백테스트 집계가 같은 라벨을 봐야 하므로 통일 필수)

**현재 코드 실제 목록**
- 공시(`DisclosureEventType`): `earnings · guidance_change · ma · management_change · capital_raise · delisting_halt · material_agreement · insider_trade · other`
- 뉴스(`NewsEventType`): `earnings · guidance_change · ma · analyst_rating · product · regulation_legal · management_change · other`

**제안 통일 표준 (10 + other)**

| 표준 event_type | 뜻 | 주 출처 | 현재 매핑 |
|---|---|---|---|
| `earnings` | 실적 발표 | 공시·뉴스 | 그대로 |
| `guidance_change` | 가이던스 상/하향 | 공시·뉴스 | 그대로 |
| `ma` | M&A(인수·합병·피인수) | 공시·뉴스 | 그대로 |
| `capital_raise` | 증자·신주·전환사채(희석) | 공시 | 그대로 |
| `management_change` | 임원·이사 변경 | 공시·뉴스 | 그대로 |
| `insider_trade` | 내부자 거래(Form 4) | 공시 | 그대로 |
| `product_deal` | 제품 출시·대형 계약 | 공시·뉴스 | 공시 `material_agreement` + 뉴스 `product` **통합** |
| `analyst_rating` | 애널리스트 등급 조정 | 뉴스 | 그대로(뉴스 고유) |
| `regulation_legal` | 규제·소송·조사 | 공시·뉴스 | 뉴스에 있음 → **공시에도 추가**(8-K 소송·조사) |
| `delisting_halt` | 상장폐지·거래정지 | 공시 | 그대로 · **hard_block 트리거** |
| `other` | 그 외 | 공시·뉴스 | 그대로 |

**제안 근거**
- **10종으로 제한** — 19종 세분화는 종목당 표본 부족으로 백테스트 무의미(과세분화 함정). 통일해도 두 자릿수 초반 유지. **[메모리]**
- **`material_agreement`+`product` → `product_deal` 통합** — 둘 다 "제품/계약 발표"라 의미 중복. 라벨 줄여 표본 확보.
- **`regulation_legal`을 공시에도** — 8-K에 소송·정부조사가 흔한데 현재 공시 목록에 없어 `other`로 샘. 추가 시 위험 이벤트를 제대로 포착. **[데이터]**
- **`delisting_halt` = `hard_block` 연동** — 이 이벤트는 곧 매수금지 override(§3). **[설계 §10]**

**✅ 상수화 완료 (2026-07-01)** — `app/common/ontology.py`에 통일 `EventType`(11종) 단일 정의.
공시·뉴스 스키마가 **같은 `EventType`을 import**(구 라벨은 `norm_event`로 자동 정규화). 드리프트 제거됨.
남은 건 라벨 목록 자체를 이은미와 최종 확정하는 것(추가/삭제 시 이 한 파일만 고침).

---

## 참고 출처

- 팀 상세 설계서 `0701.html` (ver2, 2026-06-30) — §05-①/②/⑤/⑦, §08, §09, §10
- 정보분석 개발 메모리 (`quantinue-*`) — 컷라인·역할경계·보수적 채택
- 구현 코드 — `app/schemas/disclosure_analysis.py`, `news_analysis.py`, `app/decision/trade_permission_policy.py`
