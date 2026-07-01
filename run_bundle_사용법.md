# `run_bundle.py` 사용법 — Strategist 입력 번들 생성기

> 한 종목의 **공시 + 뉴스**를 돌려 **종목당 1개 `AnalysisBundle`**(Strategist 입력)로 집계·출력한다.
> 계약·근거는 [`인터페이스명세_정보분석→Strategist.md`](인터페이스명세_정보분석→Strategist.md) 참고.

---

## 1. 사전 준비 (1회)

```bash
cd quantinue
pip install -r requirements.txt
cp .env.example .env      # 아래 키 채우기
```

`.env`에 필요한 값:
```
SEC_USER_AGENT="이름 you@email.com"    # SEC 요구 (공시 수집용, 키 아님·UA만)
OPENAI_API_KEY=sk-...                   # LLM 분석용 (gpt-4o-mini)
LLM_ANALYST_MODEL=openai:gpt-4o-mini
```
- 뉴스(Google News RSS)는 키 불필요.
- **`--llm` 없이도 실행**은 되지만, 그러면 sentiment·event_type이 안 채워져 **빈 번들**이 나온다(배선 확인용).

> ⚠️ 보안: `.env`는 `.gitignore` 제외. **비밀키는 IDE에 연 채 편집 금지**(자동 주입 유출 방지).

---

## 2. 기본 실행

```bash
# 공시(8-K) + 뉴스 8건 → LLM 분석 → 번들 출력
python run_bundle.py --ticker NVDA --form 8-K --news-limit 8 --llm

# 번들 JSON까지 (코드/PM용 원자료)
python run_bundle.py --ticker NVDA --form 8-K --llm --json
```

Windows PowerShell에서 SEC UA를 인라인으로 줄 때:
```powershell
$env:SEC_USER_AGENT="Quantinue you@email.com"; python run_bundle.py --ticker NVDA --llm
```
(또는 `.env`에 넣어두면 매번 안 줘도 됨)

---

## 3. 옵션

| 옵션 | 기본값 | 뜻 |
|---|---|---|
| `--ticker` | `NVDA` | 대상 종목 (미국 티커) |
| `--form` | `8-K` | 공시 종류: `8-K` · `10-Q` · `10-K` · `4` |
| `--news-limit` | `8` | 수집할 뉴스 헤드라인 수 |
| `--llm` | off | LLM 분석 실행 (없으면 빈 번들) |
| `--json` | off | 번들 JSON도 함께 출력 |

---

## 4. 출력 예시 (실제 NVDA)

```
▶️  NVDA 공시(8-K) 수집·분석 …
▶️  NVDA 뉴스 수집·분석 (limit 8) …
   뉴스 8건 수집 · 사전필터 통과 8

============================================================
📦 AnalysisBundle.to_prompt() — Strategist가 보는 입력:

[NVDA] as_of 2026-07-01
 공시: management_change / positive(+4) 중요도4 conf0.9 확정
       "사외이사 10명 선출, 경영진 보수 승인 → 주주 신뢰 높음."
 뉴스: 8건(확정1·루머7) → positive(+3) 중요도5 conf0.14 [최고imp7·저신뢰]
       "Investopedia: Nvidia Earnings Live: AI Chip Giant Beats Street Expectation"
 종합: net_sentiment +4 · hard_block=false
============================================================
```

> LLM 비결정성으로 실행마다 점수가 ±1~2 흔들릴 수 있다(정상).

---

## 5. 출력 읽는 법

```
[티커] as_of 날짜
 공시: {event_type} / {sentiment}({score:±}) 중요도{importance} conf{신뢰0~1} {확정/미확정}
       "한 줄 근거"
 뉴스: {건수}(확정n·루머m) → {sentiment}({score:±}) 중요도{importance} conf{신뢰} [최고imp{peak}·저신뢰]
       "대표 헤드라인"
 종합: net_sentiment {±} · hard_block={true/false}
```

- `score(±)` : 방향(부호)+강도, −10~+10. PM의 EV 계산이 쓰는 값.
- `conf` : 신뢰도 0~1. **뉴스가 루머 위주면 낮게** 나옴(정상 — "루머뿐이면 신뢰↓").
- `[최고imp7·저신뢰]` : 잠재적으론 중요한 뉴스(예 실적)가 있지만 저신뢰라 눌렸다는 표시.
- `hard_block=true` : 상폐·거래정지·going concern 등 → **매수금지 override** (LLM 판단 무관).

전체 필드 의미·설계 근거는 명세 문서 §2·§3 참고.

---

## 6. 다른 예

```bash
# 재무보고서(10-Q)로 — 본문 going concern 등 리스크문구까지 스캔
python run_bundle.py --ticker AAPL --form 10-Q --llm --json

# 내부자 거래(Form 4) 중심 (LLM 없이 코드 스코어링만으로도 신호 나옴)
python run_bundle.py --ticker AAPL --form 4 --news-limit 4 --llm

# 빈 번들(배선만, LLM/키 불필요) — 형식 확인용
python run_bundle.py --ticker TSLA
```

---

## 7. 트러블슈팅

| 증상 | 원인 · 대응 |
|---|---|
| `⚠️ LLM 키 없음 → 빈 번들` | `.env`에 `OPENAI_API_KEY` 없음 → 채우기. (없어도 배선은 확인 가능) |
| `SEC_USER_AGENT 환경변수가 필요` | `.env`에 `SEC_USER_AGENT="이름 메일"` 추가 |
| `CIK를 찾지 못했습니다` | 티커 오타 / SEC 미등록 종목 → 다른 티커로 |
| 공시 `event_type=other` 잦음 | 온톨로지 미스매치(알려진 한계) → `app/common/ontology.py`에서 조정 |
| 뉴스 conf가 늘 낮음 | RSS는 헤드라인만이라 다수가 미확정 처리(정상) → 공시·가격이 교차검증 |

---

## 8. 관련 파일

- 어댑터/계약: `app/common/analysis_bundle.py`
- 공유 event_type: `app/common/ontology.py` (통일 11종)
- 명세·근거: `인터페이스명세_정보분석→Strategist.md`
- 상세 작업노트: `WORKLOG.md`
