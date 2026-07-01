"""
[이식 초안] 팀 레포 `agents/collector.py` 골격 — 정창욱 (collector-agent)

⚠️ 이 파일은 **팀 레포(jx-hxxx/quantinue)의 agents/collector.py 에 넣을 템플릿**이다.
   - `core.schemas` / `core.llm` 은 팀 레포(팀장 소유)에 있어 **개인 레포에선 실행 안 됨(정상)**.
   - 팀 `core/schemas.py`의 **실제 필드에 맞춰 리턴부를 조정**할 것. 우리 스키마가 더 풍부하면
     (reasoning·certainty·event_type·is_confirmed·source_trust·trade_permission 등) → **PR로 필드 추가 협의**.
     근거 자료 = `인터페이스명세_정보분석→Strategist.md`.
   - R.md 경계: **SEC/뉴스 원문 "수집"은 datasources/(팀장)** 영역, collector 는 "받은 텍스트/데이터 → 신호".
   - 아래 값(HARD_RISK·ITEM_EVENT·SOURCE_POLICY·키워드)은 우리 config/*.yaml 을 **그대로 이식**한 것.

우리 개인 레포 대응(원본):
   config/hard_risk_policy.yaml · item_event_map.yaml · news_trust_policy.yaml · news_keyword_filter.yaml
   app/analyzers/form4_scorer.py · app/schemas/form4.py · app/analyzers/prompts/*.md
"""
from __future__ import annotations

# 팀 계약 (팀 레포에 존재) ─ 개인 레포에선 ImportError 나는 게 정상
from core.schemas import DisclosureSignal, NewsSignal
from core.llm import analyst_agent   # 모델(GPT-5.4 mini 등)은 core/llm.py가 관리


# ══════════════════════════════════════════════════════════════
# ① 공시 (Disclosure)  →  DisclosureSignal
# ══════════════════════════════════════════════════════════════

# --- 하드룰: LLM 전에 위험 문구 강제 차단 (config/hard_risk_policy.yaml 이식) ---
#     keyword -> (권한, 위험유형, risk_score_min)
HARD_RISK: dict[str, tuple[str, str, float]] = {
    "delisting notice": ("BLOCK_BUY", "delisting", 9.0),
    "notice of delisting": ("BLOCK_BUY", "delisting", 9.0),
    "non-compliance with listing rules": ("BLOCK_BUY", "delisting", 9.0),
    "trading halt": ("BLOCK_ALL", "trading_halt", 10.0),
    "trading suspension": ("BLOCK_ALL", "trading_halt", 10.0),
    "bankruptcy": ("BLOCK_BUY", "bankruptcy", 9.5),
    "chapter 11": ("BLOCK_BUY", "bankruptcy", 9.5),
    "going concern": ("BLOCK_BUY", "bankruptcy", 9.5),
    "financial restatement": ("BLOCK_BUY", "accounting_issue", 8.5),
    "accounting irregularity": ("BLOCK_BUY", "accounting_issue", 8.5),
    "material weakness": ("BLOCK_BUY", "accounting_issue", 8.5),
    "resignation of independent registered public accounting firm":
        ("BLOCK_BUY", "auditor_change", 8.0),
    "change in accountant": ("BLOCK_BUY", "auditor_change", 8.0),
    "dismissal of auditor": ("BLOCK_BUY", "auditor_change", 8.0),
    "secondary offering": ("BLOCK_BUY", "dilution", 8.0),
    "share dilution": ("BLOCK_BUY", "dilution", 8.0),
    "convertible notes": ("BLOCK_BUY", "dilution", 8.0),
    "at-the-market offering": ("BLOCK_BUY", "dilution", 8.0),
}


def hard_risk(text: str) -> tuple[str, str, float] | None:
    """본문에서 하드리스크 키워드 첫 매치 → (권한, 유형, 최소위험점수). 없으면 None."""
    low = text.lower()
    for kw, hit in HARD_RISK.items():
        if kw in low:
            return hit
    return None


# --- 8-K Item 번호 → 기본 이벤트/중요도/권한 (config/item_event_map.yaml 이식) ---
ITEM_EVENT: dict[str, dict] = {
    "1.01": {"event": "product_deal",      "imp": 6.5, "perm": "WATCH_ONLY", "hard": False},
    "1.02": {"event": "product_deal",      "imp": 6.5, "perm": "WATCH_ONLY", "hard": False},
    "2.01": {"event": "ma",                "imp": 7.0, "perm": "WATCH_ONLY", "hard": False},
    "2.02": {"event": "earnings",          "imp": 7.5, "perm": "WATCH_ONLY", "hard": False},
    "2.05": {"event": "other",             "imp": 5.0, "perm": "WATCH_ONLY", "hard": False},
    "2.06": {"event": "other",             "imp": 7.5, "perm": "WATCH_ONLY", "hard": True},
    "3.01": {"event": "delisting_halt",    "imp": 9.5, "perm": "BLOCK_BUY",  "hard": True},
    "4.01": {"event": "other",             "imp": 8.5, "perm": "BLOCK_BUY",  "hard": True},
    "5.02": {"event": "management_change", "imp": 6.5, "perm": "WATCH_ONLY", "hard": False},
    "8.01": {"event": "other",             "imp": 4.0, "perm": "WATCH_ONLY", "hard": False},
}
_ITEM_DEFAULT = {"event": "other", "imp": 3.0, "perm": "WATCH_ONLY", "hard": False}


# --- 프롬프트 (app/analyzers/prompts/disclosure_8k_prompt.md 이식) ---
_DISC_PROMPT = (
    "너는 미국 주식 1~5일 스윙 트레이딩을 보조하는 SEC 공시 분석 전문가다. "
    "주어진 공시를 읽고 매매 판단용 구조화 신호를 만든다. 요약하지 말고 스키마 필드만 채운다.\n"
    "- reasoning: 결론 전에 핵심 팩트(수치·사건·규모)부터 단계적으로 추론.\n"
    "- certainty_level: 단정적 사실이면 High, 해석 여지 크면 Low.\n"
    "- importance(0~10): 상폐·거래정지=10, 대형 M&A·실적쇼크=8~9, 일상보고=1~2.\n"
    "- trade_permission: 보수적으로. 시장반응 확인 전엔 호재여도 WATCH_ONLY 기본.\n"
    "- reason: 한 줄, 가능하면 수치 포함. 원문에 없는 내용은 지어내지 마라.\n"
    "확실하지 않으면 sentiment=neutral, certainty_level=Low, trade_permission=WATCH_ONLY."
)


def analyze_disclosure(filing_text: str, form_type: str = "8-K",
                       item_no: str | None = None, form4=None) -> DisclosureSignal:
    """공시 → DisclosureSignal.  (filing_text 수집은 datasources/sec.py 담당 가정)

    form_type: 8-K / 10-Q / 10-K / 4
    form4    : Form 4 파싱 객체(있으면 코드 스코어링, LLM 미사용)
    """
    # 1) Form 4 = 100% 코드 스코어링
    if form_type == "4":
        return score_form4(form4)

    # 2) 하드룰 (LLM 무관 강제 차단)
    blocked = hard_risk(filing_text)

    # 3) 8-K Item 기본 분류
    item = ITEM_EVENT.get(item_no or "", _ITEM_DEFAULT)

    # 4) LLM 해석 (8-K 본문 / 10-Q·K 수치요약)
    agent = analyst_agent(DisclosureSignal, _DISC_PROMPT)
    sig = agent.run_sync(filing_text)          # → DisclosureSignal

    # 5) 코드 규칙으로 보정 (가장 보수적 채택)
    #    TODO: 팀 core/schemas.py 의 DisclosureSignal 필드명 확인 후 매핑
    if blocked:
        perm, risk_type, risk_min = blocked
        # sig.trade_permission = perm           # 하드룰이 LLM보다 우선
        # sig.hard_risk_flag = True
        # sig.risk_score = max(sig.risk_score, risk_min)
        pass
    # if item["hard"]: sig.trade_permission = _more_conservative(sig.trade_permission, item["perm"])
    return sig


# --- Form 4 코드 스코어러 (app/analyzers/form4_scorer.py + form4.py 이식) ---
_SENIOR = ("ceo", "cfo", "chief", "president")


def score_form4(f) -> DisclosureSignal:
    """내부자 거래 규칙 스코어링. 공개시장 매수=호재/매도=약한 악재/베스팅·세금=중립, 직급 가중.

    f 는 파싱된 Form 4 객체(예: datasources 가 넘김). 필요 인터페이스:
      f.owner_title, f.is_officer, f.is_director, f.is_10b5_1, f.transactions
      f.open_market_buy_value(), f.open_market_sell_value()
      (거래코드: P=공개매수 / S=공개매도 / A,M,F,G,C=중립)
    """
    buy = f.open_market_buy_value()
    sell = f.open_market_sell_value()
    senior = bool(f.owner_title) and any(k in f.owner_title.lower() for k in _SENIOR)

    if buy > sell and buy > 0:
        sentiment = "positive"
        importance = 5 + (2 if senior else 0) + (1 if buy >= 1_000_000 else 0)
        reason = f"내부자 공개시장 매수 ${buy:,.0f} (자신감 신호)"
    elif sell > buy and sell > 0:
        if f.is_10b5_1:
            sentiment, importance = "neutral", 2
            reason = f"매도 ${sell:,.0f} but 10b5-1 예정매도 → 중립"
        else:
            sentiment = "negative"
            importance = 3 + (1 if senior else 0)
            reason = f"내부자 공개시장 매도 ${sell:,.0f} (약한 악재)"
    else:
        sentiment, importance = "neutral", 2
        reason = "베스팅/옵션행사/세금 관련 거래 → 매매 신호 약함"

    importance = max(0, min(10, importance))
    reasoning = (f"보고자={f.owner_title or '내부자'}(officer={f.is_officer}, "
                 f"director={f.is_director}, senior={senior}). "
                 f"매수=${buy:,.0f}/매도=${sell:,.0f}, 10b5-1={f.is_10b5_1} → {sentiment}.")
    evidence = [f"{t.code} {t.shares:.0f}주" + (f" @${t.price:.2f}" if t.price else "")
                for t in f.transactions][:6]

    # TODO: 팀 DisclosureSignal 필드에 맞춰 조정 (아래는 우리 스키마 기준)
    return DisclosureSignal(
        reasoning=reasoning,
        certainty_level="High",
        event_type="insider_trade",
        sentiment=sentiment,
        importance=importance,
        risk_score=2.0 if sentiment != "negative" else 4.0,
        hard_risk_flag=False,
        trade_permission="WATCH_ONLY",        # 실제 매수 판단은 Strategist 몫
        reason=reason,
        evidence_quotes=evidence,
    )


# ══════════════════════════════════════════════════════════════
# ② 뉴스 (News)  →  NewsSignal
# ══════════════════════════════════════════════════════════════

# --- 출처 4단계 (config/news_trust_policy.yaml 이식) ---
SOURCE_POLICY: dict[str, str] = {
    # ALLOW (공식·1급)
    **{d: "ALLOW" for d in (
        "sec.gov", "nasdaq.com", "nyse.com", "finra.org", "fda.gov",
        "reuters.com", "bloomberg.com", "wsj.com", "apnews.com", "cnbc.com",
        "marketwatch.com", "barrons.com", "ft.com",
        "businesswire.com", "prnewswire.com", "globenewswire.com")},
    # GRAY (2급 — 단독 매수 금지)
    **{d: "GRAY" for d in (
        "benzinga.com", "seekingalpha.com", "fool.com", "investorplace.com",
        "zacks.com", "thestreet.com", "tipranks.com")},
    # WATCH_ONLY (소셜 — 조기감지 전용)
    **{d: "WATCH_ONLY" for d in (
        "x.com", "twitter.com", "reddit.com", "stocktwits.com", "youtube.com",
        "telegram.org", "discord.com", "substack.com")},
}


def source_grade(url: str | None) -> str:
    """URL 도메인 → ALLOW/GRAY/WATCH_ONLY. 미등록은 GRAY(보수적 기본)."""
    if not url:
        return "GRAY"
    low = url.lower()
    for domain, grade in SOURCE_POLICY.items():
        if domain in low:
            return grade
    return "GRAY"


# --- 키워드 사전필터: 화이트 우선 (config/news_keyword_filter.yaml 이식) ---
WHITELIST = (   # 신뢰도 높은 이벤트 → 블랙보다 우선(false negative 방지)
    "share buyback", "repurchase", "special dividend", "guidance raised",
    "acquisition", "buyout", "merger", "strategic partnership", "spin-off",
    "fda approval", "fda cleared", "clinical trial success", "patent granted",
)
BLACKLIST = (   # 노이즈·추측·낚시 → drop
    "class action", "investor alert", "law firm reminds investors",
    "shareholder alert", "deadline",
    "reportedly", "sources say", "people familiar with", "rumor",
    "why shares are", "time to buy", "stocks to watch",
    "best stocks to buy", "top picks",
)


def keyword_screen(text: str) -> str:   # -> "whitelist" | "drop" | "pass"
    low = text.lower()
    if any(w in low for w in WHITELIST):
        return "whitelist"
    if any(b in low for b in BLACKLIST):
        return "drop"
    return "pass"


# --- 프롬프트 (app/analyzers/prompts/news_prompt.md 이식) ---
_NEWS_PROMPT = (
    "너는 미국 주식 1~5일 스윙 트레이딩을 보조하는 금융 뉴스 분석가다. 스키마 필드만 채운다.\n"
    "- is_confirmed: '발표/공시/계약 체결'이면 True. '~알려져/전망/소문/reportedly/sources say'면 False.\n"
    "- source_trust(0~1): 주어진 출처 등급(ALLOW/GRAY/WATCH_ONLY)과 본문 톤을 함께 반영. 소셜·추측은 낮게.\n"
    "- certainty_level: 단정적이면 High, 모호하면 Low.\n"
    "- importance(0~10): 자사주매입·M&A확정=7~9, 단순 제품/애널등급=4~5.\n"
    "- reason: 한 줄 근거. 없는 내용 지어내지 마라. 미확인·소셜단독·이미 급등은 보수적으로."
)


def analyze_news(headline: str, url: str | None = None) -> NewsSignal | None:
    """뉴스 헤드라인 → NewsSignal. 사전필터 통과분만 LLM 호출(비용·노이즈 절감).

    반환 None = 출처 BLOCK(WATCH_ONLY 이하 소셜 단독은 정책상 매수불가지만 조기감지용으론
    분석할 수도 있음 — 팀 정책에 맞춰 조정) 또는 키워드 drop.
    """
    grade = source_grade(url)
    verdict = keyword_screen(headline)
    if verdict == "drop":
        return None                          # 노이즈 → LLM 안 부름
    # 참고: grade를 프롬프트 입력에 함께 넘겨 LLM이 source_trust에 반영하게 함
    agent = analyst_agent(NewsSignal, _NEWS_PROMPT)
    return agent.run_sync(f"[출처등급 {grade}] {headline}")   # → NewsSignal


# ══════════════════════════════════════════════════════════════
# 이식 체크리스트 (클론 후 순서대로)
# ══════════════════════════════════════════════════════════════
#  [ ] 팀 core/schemas.py 의 DisclosureSignal / NewsSignal 실제 필드 확인
#  [ ] 필드 부족하면 → 인터페이스명세 근거로 PR 제안(event_type·is_confirmed·source_trust·trade_permission 등)
#  [ ] analyze_disclosure 5) 보정부의 주석 해제 + 필드명 매핑 (하드룰/Item 권한을 가장 보수적으로)
#  [ ] Form 4 파싱 객체를 누가 넘길지 datasources 와 인터페이스 합의 (open_market_buy/sell_value 등)
#  [ ] 소셜(WATCH_ONLY) 뉴스를 분석할지/막을지 팀 정책 결정
#  [ ] SEC/RSS 수집 위치(datasources vs collector) 팀장과 경계 합의
