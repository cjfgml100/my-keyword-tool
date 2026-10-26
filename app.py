import base64
import hashlib
import hmac
import re
import time
from datetime import datetime, timedelta

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="나만의 키워드 채굴기", page_icon="⛏️", layout="wide")

# ------------------------------------------------------------------
# 1. 등급 기준표 (검색량 구간별 S / A / B 발행량 상한, 초과하면 F)
# ------------------------------------------------------------------
GRADE_TABLE = [
    (500, 1000, 5, 15, 30),
    (1000, 3000, 10, 30, 60),
    (3000, 5000, 30, 50, 80),
    (5000, 10000, 50, 100, 150),
    (10000, 30000, 100, 150, 250),
    (30000, 100000, 150, 250, 450),
    (100000, float("inf"), 200, 350, 600),
]


def get_grade(volume, posts):
    if posts is None:
        return "?"
    if volume < 500:
        return "F"
    for low, high, s, a, b in GRADE_TABLE:
        if low <= volume < high:
            if posts <= s:
                return "S"
            if posts <= a:
                return "A"
            if posts <= b:
                return "B"
            return "F"
    return "F"


# ------------------------------------------------------------------
# 2. 네이버 검색광고 API (월 검색량)
# ------------------------------------------------------------------
def make_signature(timestamp, method, uri, secret_key):
    message = f"{timestamp}.{method}.{uri}"
    digest = hmac.new(
        secret_key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def to_int(value):
    """검색광고 API는 10 미만을 '< 10' 문자열로 준다."""
    if isinstance(value, int):
        return value
    digits = re.sub(r"\D", "", str(value))
    return int(digits) if digits else 5


@st.cache_data(ttl=3600, show_spinner=False)
def get_search_volumes(keyword):
    uri = "/keywordstool"
    ts = str(int(time.time() * 1000))
    headers = {
        "X-Timestamp": ts,
        "X-API-KEY": st.secrets["AD_API_KEY"],
        "X-Customer": str(st.secrets["AD_CUSTOMER_ID"]),
        "X-Signature": make_signature(ts, "GET", uri, st.secrets["AD_SECRET_KEY"]),
    }
    params = {"hintKeywords": keyword.replace(" ", ""), "showDetail": "1"}
    r = requests.get(
        "https://api.searchad.naver.com" + uri, headers=headers, params=params, timeout=15
    )
    if r.status_code != 200:
        raise RuntimeError(f"검색광고 API 오류 {r.status_code}: {r.text[:200]}")
    rows = []
    for item in r.json().get("keywordList", []):
        pc = to_int(item["monthlyPcQcCnt"])
        mo = to_int(item["monthlyMobileQcCnt"])
        rows.append({"keyword": item["relKeyword"], "volume": pc + mo})
    return rows


# ------------------------------------------------------------------
# 3. 블로그 최근 1개월 발행량
#    (키/주소는 Secrets로 바꿀 수 있게 해둠: API HUB 대응용)
# ------------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def get_blog_count(keyword):
    """반환: (발행량 또는 None, 오류 메시지 또는 None)"""
    cid = st.secrets.get("NAVER_CLIENT_ID")
    csec = st.secrets.get("NAVER_CLIENT_SECRET")
    if not cid or not csec:
        return None, "블로그 API 키가 설정되지 않음"

    url = st.secrets.get("BLOG_API_URL", "https://openapi.naver.com/v1/search/blog.json")
    id_header = st.secrets.get("BLOG_ID_HEADER", "X-Naver-Client-Id")
    secret_header = st.secrets.get("BLOG_SECRET_HEADER", "X-Naver-Client-Secret")
    headers = {id_header: cid, secret_header: csec}

    cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
    count = 0
    for start in range(1, 1001, 100):
        r = requests.get(
            url,
            headers=headers,
            params={"query": keyword, "display": 100, "start": start, "sort": "date"},
            timeout=10,
        )
        if r.status_code != 200:
            return None, f"{r.status_code}: {r.text[:120]}"
        items = r.json().get("items", [])
        if not items:
            break
        recent = 0
        for it in items:
            day = re.sub(r"\D", "", str(it.get("postdate", "")))[:8]
            if day and day >= cutoff:
                recent += 1
        count += recent
        # 이 페이지에 기간 밖 글이 섞였거나 마지막 페이지면 종료
        if recent < len(items) or len(items) < 100:
            break
        time.sleep(0.1)
    return count, None


# ------------------------------------------------------------------
# 4. 화면
# ------------------------------------------------------------------
st.title("⛏️ 나만의 키워드 채굴기")
st.caption("네이버 월 검색량과 최근 1개월 블로그 발행량을 분석해 S~F 등급을 판정합니다.")

seed = st.text_input("분석할 대표 키워드를 입력하세요", value="")
col1, col2 = st.columns(2)
max_kw = col1.slider("분석할 연관 키워드 수", 5, 50, 20)
min_vol = col2.number_input("최소 월 검색량", min_value=0, value=500, step=100)

if st.button("🚀 키워드 채굴 시작", use_container_width=True):
    if not seed.strip():
        st.warning("키워드를 입력해 주세요.")
        st.stop()

    try:
        with st.spinner("검색량 조회 중..."):
            volumes = get_search_volumes(seed.strip())
    except Exception as e:
        st.error(str(e))
        st.stop()

    volumes = [v for v in volumes if v["volume"] >= min_vol]
    volumes.sort(key=lambda v: v["volume"], reverse=True)
    volumes = volumes[:max_kw]

    results, errors = [], []
    bar = st.progress(0.0, text="발행량 조회 중...")
    for i, v in enumerate(volumes):
        posts, err = get_blog_count(v["keyword"])
        if err:
            errors.append(f"{v['keyword']}: {err}")
        results.append(
            {
                "등급": get_grade(v["volume"], posts),
                "키워드": v["keyword"],
                "월 검색량": v["volume"],
                "월 발행량": posts if posts is not None else None,
            }
        )
        bar.progress((i + 1) / len(volumes), text=f"발행량 조회 중... {i + 1}/{len(volumes)}")
    bar.empty()
    st.session_state["results"] = results
    st.session_state["errors"] = errors

if "results" in st.session_state:
    df = pd.DataFrame(st.session_state["results"])

    if st.session_state["errors"]:
        st.error(
            f"발행량 조회 실패 {len(st.session_state['errors'])}건 (등급은 '?'로 표시)"
        )
        with st.expander("오류 내용 보기"):
            st.write(st.session_state["errors"][:5])

    if df.empty:
        st.info("조건에 맞는 키워드가 없어요. 최소 월 검색량을 낮춰 보세요.")
    else:
        cols = st.columns(5)
        for c, g in zip(cols, ["S", "A", "B", "F", "?"]):
            c.metric(f"{g} 등급", f"{(df['등급'] == g).sum()}개")

        picked = st.multiselect(
            "필터링할 등급", ["S", "A", "B", "F", "?"], default=["S", "A", "B"]
        )
        view = df[df["등급"].isin(picked)]
        st.dataframe(view, use_container_width=True, hide_index=True)
        st.download_button(
            "CSV 다운로드",
            view.to_csv(index=False).encode("utf-8-sig"),
            "keywords.csv",
            "text/csv",
        )
