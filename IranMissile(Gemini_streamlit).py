from __future__ import annotations
import html
import os
import re
from datetime import date, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="Epic Fury Tracker – Streamlit",
    page_icon="📊",
    layout="wide",
)

BLUE = "#0969da"
BLUE_SOFT = "#58a6ff"
BG = "#ffffff"
CARD = "#f6f8fa"
TEXT = "#24292f"
MUTED = "#57606a"
LINE = "#d0d7de"
WARN_BG = "#fff8c5"
WARN_BORDER = "#d4a72c"
UI_BUILD_TAG = "2026-03-09-AI-Update"
OVERRIDE_FILE = Path(__file__).with_name("uae_daily_updates.csv")
DEFAULT_GPT_THINKING_URL = "https://chatgpt.com/?model=gpt-5.4-thinking"
GPT_THINKING_URL = os.getenv("GPT54_THINKING_URL", DEFAULT_GPT_THINKING_URL)

MONTH_MAP = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def normalize_date(value: str) -> str | None:
    dt = pd.to_datetime(str(value), errors="coerce")
    if pd.isna(dt):
        return None
    return dt.strftime("%Y-%m-%d")


def load_daily_overrides() -> pd.DataFrame:
    cols = ["date", "missiles", "drones", "note", "source_url", "source_kind", "updated_at"]
    if not OVERRIDE_FILE.exists():
        return pd.DataFrame(columns=cols)
    try:
        df = pd.read_csv(OVERRIDE_FILE, dtype=str)
    except Exception:
        return pd.DataFrame(columns=cols)
    if df.empty:
        return pd.DataFrame(columns=cols)
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    return df[cols]


def persist_daily_override(
    date_str: str,
    missiles: int,
    drones: int,
    note: str,
    source_url: str = "",
    source_kind: str = "manual",
) -> None:
    new_row = {
        "date": date_str,
        "missiles": str(int(missiles)),
        "drones": str(int(drones)),
        "note": (note or "").strip(),
        "source_url": (source_url or "").strip(),
        "source_kind": source_kind,
        "updated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    old = load_daily_overrides()
    all_rows = pd.concat([old, pd.DataFrame([new_row])], ignore_index=True)
    all_rows["date"] = all_rows["date"].apply(normalize_date)
    all_rows = all_rows[all_rows["date"].notna()].copy()
    all_rows["missiles"] = pd.to_numeric(all_rows["missiles"], errors="coerce").fillna(0).astype(int)
    all_rows["drones"] = pd.to_numeric(all_rows["drones"], errors="coerce").fillna(0).astype(int)
    all_rows = all_rows.sort_values(["date", "updated_at"]).drop_duplicates("date", keep="last")
    all_rows.to_csv(OVERRIDE_FILE, index=False)


def build_daily_frame(base_rows: list[dict], overrides: pd.DataFrame) -> pd.DataFrame:
    merged: dict[str, dict] = {}
    for r in base_rows:
        d = normalize_date(r.get("date", ""))
        if not d:
            continue
        merged[d] = {
            "date": d,
            "missiles": int(r.get("missiles", 0)),
            "drones": int(r.get("drones", 0)),
            "note": str(r.get("note", "")).strip(),
        }
    if not overrides.empty:
        for r in overrides.to_dict("records"):
            d = normalize_date(r.get("date", ""))
            if not d:
                continue
            note = str(r.get("note", "")).strip() or "手動更新"
            url = str(r.get("source_url", "")).strip()
            if url:
                note = f"{note}（來源：{url}）"
            missile_val = pd.to_numeric(r.get("missiles"), errors="coerce")
            drone_val = pd.to_numeric(r.get("drones"), errors="coerce")
            missile_val = 0 if pd.isna(missile_val) else int(missile_val)
            drone_val = 0 if pd.isna(drone_val) else int(drone_val)
            merged[d] = {
                "date": d,
                "missiles": missile_val,
                "drones": drone_val,
                "note": note,
            }
    daily_rows = [merged[k] for k in sorted(merged)]
    df = pd.DataFrame(daily_rows)
    if df.empty:
        return pd.DataFrame(columns=["date", "missiles", "drones", "note", "missiles_pct", "drones_pct", "total"])
    prev_m = df["missiles"].shift(1)
    prev_d = df["drones"].shift(1)
    df["missiles_pct"] = ((df["missiles"] - prev_m) / prev_m * 100).where(prev_m != 0)
    df["drones_pct"] = ((df["drones"] - prev_d) / prev_d * 100).where(prev_d != 0)
    df["total"] = df["missiles"] + df["drones"]
    return df


def strip_html_text(raw_html: str) -> str:
    txt = re.sub(r"<script[\s\S]*?</script>", " ", raw_html, flags=re.IGNORECASE)
    txt = re.sub(r"<style[\s\S]*?</style>", " ", txt, flags=re.IGNORECASE)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = html.unescape(txt)
    return re.sub(r"\s+", " ", txt).strip()


def parse_article_date(text: str) -> str | None:
    patterns = [
        r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s*(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})\b",
        r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+),\s*(20\d{2})\b",
    ]
    for p in patterns:
        m = re.search(p, text, flags=re.IGNORECASE)
        if not m:
            continue
        day = int(m.group(1))
        month = MONTH_MAP.get(m.group(2).lower())
        year = int(m.group(3))
        if not month:
            continue
        try:
            return datetime(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def parse_daily_counts(text: str) -> tuple[int | None, int | None]:
    combo = re.search(
        r"today[^.]{0,240}?detected\s+(\d{1,4})\s+ballistic missiles[^.]{0,260}?(?:a total of\s+)?(\d{1,4})\s+drones?\s+were also detected",
        text,
        flags=re.IGNORECASE,
    )
    if combo:
        return int(combo.group(1)), int(combo.group(2))

    m_missile = re.search(r"today[^.]{0,220}?detected\s+(\d{1,4})\s+ballistic missiles", text, flags=re.IGNORECASE)
    m_drone = re.search(r"(?:a total of\s+)?(\d{1,4})\s+drones?\s+were also detected", text, flags=re.IGNORECASE)
    missiles = int(m_missile.group(1)) if m_missile else None
    drones = int(m_drone.group(1)) if m_drone else None

    if missiles is None:
        m_fallback = re.search(r"intercept(?:ed|s)\s+(\d{1,4})\s+ballistic missiles", text, flags=re.IGNORECASE)
        if m_fallback:
            missiles = int(m_fallback.group(1))
    if drones is None:
        d_fallback = re.search(r"intercept(?:ed|s)\s+\d{1,4}\s+ballistic missiles,\s*(\d{1,4})\s+drones", text, flags=re.IGNORECASE)
        if d_fallback:
            drones = int(d_fallback.group(1))
    return missiles, drones


def parse_date_from_url(url: str) -> str | None:
    parsed = urlparse(url.strip())
    q = parse_qs(parsed.query)
    # QNA 常見 date=8/03/2026 格式
    for d in q.get("date", []):
        dt = pd.to_datetime(d, errors="coerce", dayfirst=True)
        if not pd.isna(dt):
            return dt.strftime("%Y-%m-%d")
    m = re.search(r"/(20\d{2})-(\d{1,2})/(\d{1,2})(?:/|$)", parsed.path)
    if m:
        year, month, day = map(int, m.groups())
        try:
            return datetime(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def parse_counts_from_generic_text(text: str) -> tuple[int | None, int | None]:
    missile_patterns = [
        r"(\d{1,4})\s+(?:ballistic\s+)?missiles?",
        r"(\d{1,4})\s+rockets?",
        r"(\d{1,4})\s*飛彈",
    ]
    drone_patterns = [
        r"(\d{1,4})\s+drones?",
        r"(\d{1,4})\s*無人機",
    ]
    missiles = None
    drones = None
    for p in missile_patterns:
        ms = re.findall(p, text, flags=re.IGNORECASE)
        if ms:
            missiles = int(ms[0])
            break
    for p in drone_patterns:
        ds = re.findall(p, text, flags=re.IGNORECASE)
        if ds:
            drones = int(ds[0])
            break
    return missiles, drones


def parse_counts_from_url(url: str) -> tuple[int | None, int | None]:
    path = unquote(urlparse(url.strip()).path.lower())
    pair = re.search(r"missiles-(\d{1,4}).{0,24}?drones?-(\d{1,4})", path)
    if pair:
        return int(pair.group(1)), int(pair.group(2))
    pair_rev = re.search(r"drones?-(\d{1,4}).{0,24}?missiles-(\d{1,4})", path)
    if pair_rev:
        return int(pair_rev.group(2)), int(pair_rev.group(1))
    missiles = None
    drones = None
    return missiles, drones


def parse_from_source_metadata(url: str, source_groups: list[dict]) -> dict | None:
    target = url.strip().rstrip("/")
    for group in source_groups:
        for item in group.get("items", []):
            source_url = str(item.get("url", "")).strip().rstrip("/")
            if source_url != target:
                continue
            title = str(item.get("title", ""))
            use = str(item.get("use", ""))
            date_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", f"{title} {use}")
            parsed_date = normalize_date(date_match.group(1)) if date_match else None
            missiles, drones = parse_counts_from_generic_text(use)
            if missiles is None or drones is None:
                m2, d2 = parse_counts_from_generic_text(title)
                missiles = missiles if missiles is not None else m2
                drones = drones if drones is not None else d2
            return {
                "date": parsed_date,
                "missiles": missiles,
                "drones": drones,
                "note": "來源清單備援解析",
                "source_url": target,
            }
    return None


def backfill_from_existing(
    parsed_date: str | None,
    missiles: int | None,
    drones: int | None,
    df_daily: pd.DataFrame,
) -> tuple[int | None, int | None]:
    if not parsed_date:
        return missiles, drones
    row = df_daily[df_daily["date"] == parsed_date]
    if row.empty:
        return missiles, drones
    if missiles is None:
        missiles = int(row.iloc[0]["missiles"])
    if drones is None:
        drones = int(row.iloc[0]["drones"])
    return missiles, drones


def fetch_daily_from_article(url: str, source_groups: list[dict], df_daily: pd.DataFrame) -> dict:
    source_url = url.strip()
    parsed_date = parse_date_from_url(source_url)
    missiles, drones = parse_counts_from_url(source_url)
    note = "來源頁面自動解析"

    try:
        req = Request(source_url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=18) as resp:
            raw = resp.read()
            charset = resp.headers.get_content_charset() or "utf-8"
        html_text = raw.decode(charset, errors="ignore")
        text = strip_html_text(html_text)
        if len(text) > 120:
            parsed_date = parse_article_date(text) or parsed_date
            m1, d1 = parse_daily_counts(text)
            m2, d2 = parse_counts_from_generic_text(text)
            missiles = missiles if missiles is not None else m1
            drones = drones if drones is not None else d1
            missiles = missiles if missiles is not None else m2
            drones = drones if drones is not None else d2
    except Exception:
        pass

    meta = parse_from_source_metadata(source_url, source_groups)
    if meta:
        parsed_date = parsed_date or meta["date"]
        missiles = missiles if missiles is not None else meta["missiles"]
        drones = drones if drones is not None else meta["drones"]
        note = "來源頁面 + 來源清單備援解析"

    before_m, before_d = missiles, drones
    missiles, drones = backfill_from_existing(parsed_date, missiles, drones, df_daily)
    if (before_m is None or before_d is None) and (missiles is not None and drones is not None):
        note = "來源備援解析（同日既有資料補齊）"
    if parsed_date and missiles is not None and drones is not None:
        return {
            "date": parsed_date,
            "missiles": missiles,
            "drones": drones,
            "note": note,
            "source_url": source_url,
        }
    raise ValueError(
        f"無法完整解析（date={parsed_date or 'N/A'}, missiles={missiles}, drones={drones}）。"
        "請改用下方「手動補登最近一日」。"
    )


def make_gpt_prompt(df_daily: pd.DataFrame) -> str:
    latest = df_daily.iloc[-1]
    lines = [
        "你是軍事與情報分析助理，請用結構化方式延伸分析。",
        f"最新日期：{latest['date']}",
        f"最新日數據：飛彈 {int(latest['missiles'])}，無人機 {int(latest['drones'])}",
        f"期間累計：飛彈 {int(df_daily['missiles'].sum())}，無人機 {int(df_daily['drones'].sum())}",
        "請完成：",
        "1) 近 3 日趨勢與可能原因",
        "2) 與前一週平均相比的變化百分比",
        "3) 明日風險等級（高/中/低）與依據",
        "4) 需要補查的來源清單（按優先順序）",
        "請用繁體中文，先給 3 行重點摘要，再給詳細分析。",
    ]
    return "\n".join(lines)

st.markdown(
    f"""
    <style>
    .stApp {{ background: {BG}; color: {TEXT}; }}
    .main .block-container {{ padding-top: 1.6rem; padding-bottom: 2rem; max-width: 1360px; }}
    h1, h2, h3 {{ color: {TEXT}; letter-spacing: -0.02em; }}
    div[data-testid="stMetric"] {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 16px; padding: 10px 14px; }}
    .hero {{ border: 1px solid {LINE}; background: linear-gradient(180deg, #ffffff 0%, {CARD} 100%); border-radius: 18px; padding: 24px; margin-bottom: 18px; }}
    .muted {{ color: {MUTED}; font-size: 0.95rem; }}
    .warning-box {{ margin-top: 14px; border: 1px solid {WARN_BORDER}; background: {WARN_BG}; border-radius: 12px; padding: 12px 14px; font-size: 0.95rem; }}
    .note-box {{ border: 1px solid {LINE}; background: {CARD}; border-radius: 16px; padding: 16px 18px; height: 100%; }}
    .chip-row {{ display:flex; gap:10px; flex-wrap:wrap; margin: 4px 0 10px 0; }}
    .chip {{ border: 1px solid {LINE}; background: white; border-radius: 999px; padding: 7px 11px; font-size: 0.85rem; }}
    .small-muted {{ color: {MUTED}; font-size: 0.84rem; }}
    a {{ color: {BLUE}; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    @media (max-width: 768px) {{
      .main .block-container {{ padding-top: 0.8rem; padding-bottom: 1.2rem; padding-left: 0.8rem; padding-right: 0.8rem; }}
      h1 {{ font-size: 1.45rem !important; line-height: 1.3; }}
      h2 {{ font-size: 1.2rem !important; }}
      h3 {{ font-size: 1.05rem !important; }}
      div[data-testid="stMetric"] {{ padding: 9px 10px; border-radius: 12px; }}
      div[data-testid="stMetricLabel"] p {{ font-size: 0.82rem !important; }}
      div[data-testid="stMetricValue"] {{ font-size: 1.3rem !important; }}
      .hero {{ padding: 16px; border-radius: 14px; margin-bottom: 12px; }}
      .warning-box {{ padding: 10px 12px; font-size: 0.9rem; }}
      .note-box {{ padding: 12px 14px; border-radius: 12px; }}
      .chip {{ width: 100%; border-radius: 12px; }}
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

uae_daily = [
    {
        'date': '2026-02-28',
        'missiles': 137,
        'drones': 209,
        'missiles_pct': None,
        'drones_pct': None,
        'note': 'UAE 官方 opening-day cumulative。作為本頁逐日序列起點。',
    },
    {
        'date': '2026-03-01',
        'missiles': 28,
        'drones': 332,
        'missiles_pct': -79.56204379562044,
        'drones_pct': 58.85167464114832,
        'note': '採 3/1 官方文內 second-day 分項：20 枚攔截＋8 枚落海；311 架擊落＋21 架擊中/落地。',
    },
    {
        'date': '2026-03-02',
        'missiles': 9,
        'drones': 148,
        'missiles_pct': -67.85714285714286,
        'drones_pct': -55.42168674698795,
        'note': '官方逐日公告。另有 6 枚巡弋飛彈遭攔截，但本頁主統計僅納入飛彈/無人機兩類。',
    },
    {
        'date': '2026-03-03',
        'missiles': 12,
        'drones': 123,
        'missiles_pct': 33.33333333333333,
        'drones_pct': -16.89189189189189,
        'note': '官方逐日公告。',
    },
    {
        'date': '2026-03-04',
        'missiles': 3,
        'drones': 129,
        'missiles_pct': -75.0,
        'drones_pct': 4.878048780487805,
        'note': '官方逐日公告。',
    },
    {
        'date': '2026-03-05',
        'missiles': 7,
        'drones': 131,
        'missiles_pct': 133.33333333333331,
        'drones_pct': 1.550387596899225,
        'note': '官方逐日公告。',
    },
    {
        'date': '2026-03-06',
        'missiles': 9,
        'drones': 112,
        'missiles_pct': 28.57142857142857,
        'drones_pct': -14.50381679389313,
        'note': '官方逐日公告。',
    },
    {
        'date': '2026-03-07',
        'missiles': 16,
        'drones': 121,
        'missiles_pct': 77.77777777777779,
        'drones_pct': 8.035714285714286,
        'note': '官方逐日公告。',
    },
    {
        'date': '2026-03-08',
        'missiles': 17,
        'drones': 117,
        'missiles_pct': 6.25,
        'drones_pct': -3.3057851239669422,
        'note': '官方逐日公告。',
    },
]

countries = [
    {'country': 'UAE', 'missiles': 238, 'drones': 1422, 'cutoff': '2026-03-08', 'method': '官方累計', 'note': '採 UAE MoD / WAM 3/8 累計。'},
    {'country': 'Kuwait', 'missiles': 212, 'drones': 394, 'cutoff': '2026-03-06', 'method': '官方累計', 'note': '採 Kuwait MoD 3/6 對外簡報累計。3/7–3/8 有後續作戰更新，但公開可得來源未提供一致的新累計總表。'},
    {'country': 'Bahrain', 'missiles': 95, 'drones': 164, 'cutoff': '2026-03-08', 'method': '官方累計', 'note': '採 Bahrain Defence Force / BNA 經 WAM、QNA 轉載之 3/8 累計。'},
    {'country': 'Jordan', 'missiles': 60, 'drones': 59, 'cutoff': '2026-03-07', 'method': '官方累計', 'note': 'Jordan 官方記者會口徑為 119 枚/架，其中 60 rockets、59 drones；本頁將 rockets 歸為飛彈欄。'},
    {'country': 'Qatar', 'missiles': 125, 'drones': 43, 'cutoff': '2026-03-08', 'method': '推估累計', 'note': '以 3/3 官方累計（101 飛彈、39 無人機）加上 3/5 日增（14、4）與 3/8 日增（10、0）反推。'},
]

history_data = [
    {'conflict': '2024/10 True Promise II', 'missiles': 200, 'drones': 0, 'label_note': '約數；主要為彈道飛彈齊射'},
    {'conflict': '2025/06 12日戰爭', 'missiles': 550, 'drones': 1000, 'label_note': 'IDF / Times of Israel 約數'},
    {'conflict': '2026 Epic Fury', 'missiles': 500, 'drones': 2000, 'label_note': 'CENTCOM 口徑為「超過 500 枚飛彈、超過 2,000 架無人機」'},
]

source_groups = [
    {'group': 'UAE（逐日 / 官方）', 'items': [
        {'title': 'UAE MoD / WAM – 2026-02-28 opening-day cumulative', 'url': 'https://www.wam.ae/en/article/173jo13-uae-air-defences-intercept-137-missiles-209-drones', 'use': '2/28 官方起始日'},
        {'title': 'UAE MoD / WAM – 2026-03-01 cumulative + day-two detail', 'url': 'https://www.wam.ae/en/article/byzgpgf-uae-air-defences-intercept-165-ballistic-two', 'use': '3/1 官方 second-day 分項（28 missiles / 332 drones）'},
        {'title': 'UAE MoD / WAM – 2026-03-02', 'url': 'https://www.wam.ae/en/article/bz0257y-ministry-defense-uae%E2%80%99s-air-defenses-successfully', 'use': '3/2 官方逐日'},
        {'title': 'UAE MoD / WAM – 2026-03-03', 'url': 'https://www.wam.ae/en/article/bz0nkqp-uae-air-defences-intercept-ballistic-missiles-123', 'use': '3/3 官方逐日'},
        {'title': 'UAE MoD / WAM – 2026-03-04', 'url': 'https://www.wam.ae/en/article/bz190ft-uae-air-defences-intercept-ballistic-missiles-129', 'use': '3/4 官方逐日'},
        {'title': 'UAE MoD / WAM – 2026-03-05', 'url': 'https://www.wam.ae/en/article/bz1ufvk-uae-air-defences-intercept-ballistic-missiles-125', 'use': '3/5 官方逐日'},
        {'title': 'UAE MoD / WAM – 2026-03-06', 'url': 'https://www.wam.ae/en/article/bz2fvh8-uae-air-defences-intercept-nine-ballistic', 'use': '3/6 官方逐日'},
        {'title': 'UAE MoD / WAM – 2026-03-07', 'url': 'https://www.wam.ae/en/article/bz31axa-uae-air-defences-intercept-ballistic-missiles-119', 'use': '3/7 官方逐日'},
        {'title': 'UAE MoD / WAM – 2026-03-08', 'url': 'https://www.wam.ae/en/article/bz3mqg3-uae-air-defences-intercept-ballistic-missiles-113', 'use': '3/8 官方逐日與最新 UAE 累計'},
    ]},
    {'group': 'Kuwait（累計 / 官方）', 'items': [
        {'title': 'Kuwait MoD via QNA – 2026-03-06 cumulative', 'url': 'https://qna.org.qa/en/news/news-details?id=kuwaiti-defense-ministry-two-killed-67-injured-among-armed-forces-since-start-of-operations&date=6/03/2026', 'use': '212 missiles / 394 drones cumulative'},
        {'title': 'KUNA – 2026-03-01 snippet', 'url': 'https://www.kuna.net.kw/ArticleDetails.aspx?id=3278224&language=en', 'use': '97 missiles / 283 drones prior cumulative checkpoint'},
        {'title': 'KUNA – 2026-03-02 snippet', 'url': 'https://www.kuna.net.kw/ArticleDetails.aspx?id=3278843&language=en', 'use': '178 missiles / 384 drones prior cumulative checkpoint'},
    ]},
    {'group': 'Bahrain（累計 / 官方）', 'items': [
        {'title': 'Bahrain Defence Force / BNA via WAM – 2026-03-08 cumulative', 'url': 'https://www.wam.ae/en/article/bz3mqg4-bahrain-defence-force-general-command-missiles-164', 'use': '95 missiles / 164 drones cumulative'},
        {'title': 'QNA relay – 2026-03-09', 'url': 'https://qna.org.qa/en/News-Area/News/2026-3/9/bahrain-says-95-missiles-164-drones-destroyed-since-start-of-iranian-attacks', 'use': '確認最新可見轉載數字未變'},
    ]},
    {'group': 'Jordan（累計 / 官方）', 'items': [
        {'title': 'Jordan Times quoting Brig. Gen. Mustafa Hiyari – 2026-03-07', 'url': 'https://jordantimes.com/news/local/army-downs-108-of-119-missiles-drones-targeting-vital-facilities-hiyari', 'use': '60 rockets / 59 drones cumulative'},
        {'title': 'QNA relay – 2026-03-07', 'url': 'https://qna.org.qa/en/News-Area/News/2026-3/7/jordan-reports-engaging-119-missiles-drones-in-one-week', 'use': '交叉核對 119 total'},
    ]},
    {'group': 'Qatar（累計 / 推估）', 'items': [
        {'title': 'Qatar MoD / QNA cumulative summary – 2026-03-03', 'url': 'https://qna.org.qa/en/news/news-details?id=ministry-of-defense-unveils-summary-of-total-attacks-since-start-of-iranian-aggression&date=3/03/2026', 'use': '101 ballistic missiles / 39 drones cumulative baseline'},
        {'title': 'Qatar MoD / QNA daily – 2026-03-05', 'url': 'https://qna.org.qa/en/News-Area/News/2026-3/5/ministry-of-defense-announces-interception-of-13-ballistic-missiles-four-drones-with-no-casualties', 'use': '+14 ballistic missiles / +4 drones'},
        {'title': 'Qatar MoD / QNA daily – 2026-03-08', 'url': 'https://qna.org.qa/en/news/news-details?id=ministry-of-defense-intercepts-6-ballistic-missiles-2-cruise-missiles-without-casualties&date=8/03/2026', 'use': '+10 ballistic missiles / +0 drones'},
    ]},
    {'group': 'CENTCOM / FDD / 歷史比較', 'items': [
        {'title': 'DefenseScoop quoting CENTCOM Adm. Brad Cooper video – 2026-03-04', 'url': 'https://defensescoop.com/2026/03/04/iranian-attack-drone-launches-decrease-operation-epic-fury/', 'use': 'Epic Fury regional total >500 ballistic missiles and >2,000 drones'},
        {'title': 'CENTCOM official press release – 2026-02-28', 'url': 'https://www.centcom.mil/MEDIA/PRESS-RELEASES/Press-Release-View/Article/4418396/us-forces-launch-operation-epic-fury/', 'use': '官方僅稱 defended against hundreds of missile and drone attacks'},
        {'title': 'FDD – Why Iran’s ballistic missile launches are declining', 'url': 'https://www.fdd.org/analysis/2026/03/04/why-irans-ballistic-missile-launches-are-declining/', 'use': '彈道飛彈發射趨勢與歷史比較'},
        {'title': 'U.S. DoD – Oct. 1, 2024 approximately 200 ballistic missiles', 'url': 'https://www.war.gov/News/News-Stories/Article/Article/3923123/us-assets-in-mediterranean-again-helped-defend-israel-against-iranian-missiles/', 'use': 'True Promise II 參考值'},
        {'title': 'Times of Israel – Jun. 2025 war by the numbers', 'url': 'https://www.timesofisrael.com/the-israel-iran-war-by-the-numbers-after-12-days-of-fighting/', 'use': '12-day war 約 550 ballistic missiles / 約 1,000 drones'},
    ]},
]

override_df = load_daily_overrides()
df_daily = build_daily_frame(uae_daily, override_df)
df_history = pd.DataFrame(history_data)

def pct_str(v):
    if pd.isna(v):
        return "—"
    return f"{v:+.1f}%"

def fmt_int(v):
    return f"{int(v):,}"

sum_missiles = int(df_daily["missiles"].sum())
sum_drones = int(df_daily["drones"].sum())
peak_row = df_daily.loc[df_daily["total"].idxmax()]
latest_date = str(df_daily["date"].max())
start_date = str(df_daily["date"].min())
range_label = f"{pd.to_datetime(start_date).strftime('%m/%d')}–{pd.to_datetime(latest_date).strftime('%m/%d')}"

df_countries = pd.DataFrame(countries)
uae_mask = df_countries["country"] == "UAE"
if uae_mask.any():
    df_countries.loc[uae_mask, "missiles"] = sum_missiles
    df_countries.loc[uae_mask, "drones"] = sum_drones
    df_countries.loc[uae_mask, "cutoff"] = latest_date
    df_countries.loc[uae_mask, "note"] = "由 UAE 逐日資料自動累計（含最新更新）"
country_total_m = int(df_countries["missiles"].sum())
country_total_d = int(df_countries["drones"].sum())
cutoff_label = " · ".join([f"{r.country}:{str(r.cutoff)[5:]}" for r in df_countries.itertuples()])

date_labels_full = [d.replace('-', '/') for d in df_daily['date'].tolist()]
date_labels_short = [pd.to_datetime(d).strftime('%m/%d') for d in df_daily['date']]

st.markdown("""
<div class="hero">
  <h1>Operation Epic Fury：2026 年 3 月伊朗飛彈 / 無人機統計追蹤</h1>
  <div class="muted">Streamlit 原生部署版本，整合 UAE 逐日官方公告、多國累計比較、逐日數據表、三場衝突歷史比較與來源連結。</div>
  <div class="warning-box"><strong>資料限制警告：</strong> 各國官方公布的截止時間不同，且公開口徑並不一致。UAE 為逐日官方公告；Kuwait、Bahrain、Jordan 多為累計口徑；Qatar 的最新累計需由 3/3 官方累計加上 3/5、3/8 逐日公告反推。比較圖請視為「截至各自最新可驗證 cutoff 的並列快照」，不可直接視為同一時間點的精確同步截面。</div>
</div>
""", unsafe_allow_html=True)
st.caption(f"介面版本：{UI_BUILD_TAG}")

m1, m2 = st.columns(2)
m3, m4 = st.columns(2)
m1.metric(f"UAE 期間飛彈（{range_label}）", fmt_int(sum_missiles), help="逐日官方統計合計")
m2.metric(f"UAE 期間無人機（{range_label}）", fmt_int(sum_drones), help="逐日官方統計合計")
m3.metric("UAE 峰值日", peak_row['date'].replace('-', '/'), help=f"{int(peak_row['missiles'])} 枚飛彈 / {int(peak_row['drones'])} 架無人機")
m4.metric("CENTCOM 區域總量（下限）", ">2,500", help=">500 missiles + >2,000 drones")

section_options = [
    "1. Epic Fury 逐日圖表",
    "2. 多國比較",
    "3. 數據表",
    "4. 三場衝突歷史比較",
    "5. 來源連結",
    "6. AI 延伸與最近日更新",
]
section = st.selectbox("頁面導覽", section_options, index=5)

if section == "1. Epic Fury 逐日圖表":
    st.subheader(f"UAE 逐日圖表（{start_date.replace('-', '/')}–{latest_date.replace('-', '/')}）")
    st.caption("雙 Y 軸 bar chart：左軸 = 飛彈、右軸 = 無人機。")
    fig = go.Figure()
    fig.add_bar(
        x=date_labels_full,
        y=df_daily['missiles'],
        name='飛彈（左軸）',
        marker_color=BLUE,
        offsetgroup='missiles',
        yaxis='y',
        customdata=date_labels_full,
        hovertemplate='日期：%{customdata}<br>飛彈：%{y}<extra></extra>',
    )
    fig.add_bar(
        x=date_labels_full,
        y=df_daily['drones'],
        name='無人機（右軸）',
        marker_color=BLUE_SOFT,
        offsetgroup='drones',
        yaxis='y2',
        customdata=date_labels_full,
        hovertemplate='日期：%{customdata}<br>無人機：%{y}<extra></extra>',
    )
    fig.update_layout(
        barmode='group',
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        hovermode='x unified',
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0),
        margin=dict(l=18, r=18, t=22, b=25),
        xaxis=dict(
            type='category',
            categoryorder='array',
            categoryarray=date_labels_full,
            tickmode='array',
            tickvals=date_labels_full,
            ticktext=date_labels_short,
            tickangle=-28,
            automargin=True,
            title='日期',
            gridcolor='#eaeef2',
            linecolor=LINE,
        ),
        yaxis=dict(title='飛彈', gridcolor='#eaeef2', linecolor=LINE, rangemode='tozero'),
        yaxis2=dict(title='無人機', overlaying='y', side='right', showgrid=False, rangemode='tozero'),
        height=450,
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    with st.expander("圖表解讀與方法註記", expanded=False):
        st.markdown("""
        - **2/28 為官方起點：** 當日 137 枚飛彈、209 架無人機，為本頁逐日序列起始日。
        - **3/1 為無人機峰值：** 當日 28 枚飛彈、332 架無人機，單日總量 360，高於 2/28 的 346。
        - **之後快速鈍化：** 日總量由 3/1 的 360，降至 3/8 的 134，顯示打擊密度明顯下降。
        - **口徑說明：** 本頁「飛彈」欄優先指彈道飛彈；若官方單獨列出巡弋飛彈，另在備註說明，不併入雙欄主統計。
        - **資料方法：** 2/28 採 UAE 官方 opening-day cumulative；3/1 採官方文內 second-day 分項，不再寫成單純差額反推。
        """)

elif section == "2. 多國比較":
    st.subheader("多國比較（截至各國最新可驗證 cutoff）")
    st.caption("橫向 bar chart；UAE 由逐日資料自動累計至最新日，其他國家維持各自最新可驗證 cutoff。")
    st.markdown(f"<div class='chip-row'><div class='chip'>已追蹤國家合計飛彈：<strong>{country_total_m:,}</strong></div><div class='chip'>已追蹤國家合計無人機：<strong>{country_total_d:,}</strong></div><div class='chip'>cutoff：<strong>{cutoff_label}</strong></div></div>", unsafe_allow_html=True)
    compare = go.Figure()
    compare.add_bar(y=df_countries['country'], x=df_countries['missiles'], name='飛彈', orientation='h', marker_color=BLUE)
    compare.add_bar(y=df_countries['country'], x=df_countries['drones'], name='無人機', orientation='h', marker_color=BLUE_SOFT)
    compare.update_layout(
        barmode='group',
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        hovermode='y unified',
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0),
        margin=dict(l=18, r=18, t=10, b=20),
        xaxis=dict(gridcolor='#eaeef2', linecolor=LINE, title='累計數量'),
        yaxis=dict(linecolor=LINE),
        height=460,
    )
    st.plotly_chart(compare, use_container_width=True, config={"displayModeBar": False})
    show_df = df_countries.copy()
    show_df.columns = ['國家', '飛彈累計', '無人機累計', '截止時間', '方法', '備註']
    st.dataframe(show_df, use_container_width=True, hide_index=True, height=280)
    st.warning("UAE 是逐日數字，其他國家多為累計；Qatar 的 D3 之後需由累計基準加上後續日報反推。請勿將各國數字視為完全同步的同一時點截面。")

elif section == "3. 數據表":
    st.subheader("UAE 逐日明細表")
    st.caption("含飛彈 / 無人機日數與環比變化。可輸入關鍵字篩選日期或備註。")
    keyword = st.text_input("篩選關鍵字", placeholder="例如：巡弋、官方、2026-03-06", key='daily_filter')
    daily_show = df_daily.copy()
    daily_show['飛彈環比'] = daily_show['missiles_pct'].apply(pct_str)
    daily_show['無人機環比'] = daily_show['drones_pct'].apply(pct_str)
    daily_show = daily_show.rename(columns={'date':'日期','missiles':'飛彈','drones':'無人機','note':'備註'})
    daily_show = daily_show[['日期','飛彈','飛彈環比','無人機','無人機環比','備註']]
    if keyword.strip():
        mask = daily_show.apply(lambda s: s.astype(str).str.contains(keyword, case=False, regex=False)).any(axis=1)
        daily_show = daily_show[mask]
    st.dataframe(daily_show, use_container_width=True, hide_index=True, height=420)
    st.markdown("<div class='small-muted'>註：3/2 官方另有 6 枚巡弋飛彈遭攔截，但主統計未併入飛彈欄。</div>", unsafe_allow_html=True)

elif section == "4. 三場衝突歷史比較":
    st.subheader("三場衝突歷史比較")
    st.caption("2026 Epic Fury 採 CENTCOM 相關公開口徑的下限值；與 2024/10、2025/06 的地理範圍與統計口徑並非完全相同，宜視為規模級距比較。")
    hist = go.Figure()
    hist.add_bar(x=df_history['conflict'], y=df_history['missiles'], name='飛彈', marker_color=BLUE)
    hist.add_bar(x=df_history['conflict'], y=df_history['drones'], name='無人機', marker_color=BLUE_SOFT)
    hist.update_layout(
        barmode='group',
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        hovermode='x unified',
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0),
        margin=dict(l=18, r=18, t=10, b=20),
        xaxis=dict(linecolor=LINE, tickangle=-12),
        yaxis=dict(gridcolor='#eaeef2', linecolor=LINE, title='數量'),
        height=430,
    )
    st.plotly_chart(hist, use_container_width=True, config={"displayModeBar": False})
    hist_show = df_history.copy()
    hist_show.columns = ['衝突', '飛彈', '無人機', '備註']
    st.dataframe(hist_show, use_container_width=True, hide_index=True, height=200)

elif section == "5. 來源連結":
    st.subheader("來源連結")
    st.caption("列出本頁使用或交叉核對的核心來源。可用關鍵字過濾，例如輸入 UAE、Kuwait、CENTCOM、FDD。")
    q = st.text_input("來源關鍵字", placeholder="UAE / Kuwait / CENTCOM / FDD", key='source_filter').strip().lower()
    count = 0
    for group in source_groups:
        items = []
        for item in group['items']:
            hay = f"{group['group']} {item['title']} {item['use']} {item['url']}".lower()
            if not q or q in hay:
                items.append(item)
        if not items:
            continue
        st.markdown(f"### {group['group']}")
        for item in items:
            count += 1
            st.markdown(f"<div class='note-box' style='margin-bottom:10px;'><div><a href='{item['url']}' target='_blank'>{item['title']}</a></div><div class='small-muted'>{item['use']}</div></div>", unsafe_allow_html=True)
    if count == 0:
        st.info("沒有符合的來源，請換個關鍵字。")

elif section == "6. AI 延伸與最近日更新":
    st.subheader("AI 延伸與最近日更新")
    st.caption("可連結 GPT-5.4 Thinking 進行延伸分析，並把 UAE 逐日資料更新到最近一日。")
    st.markdown(f"<div class='chip-row'><div class='chip'>目前最新日：<strong>{latest_date}</strong></div><div class='chip'>更新檔：<strong>{OVERRIDE_FILE.name}</strong></div></div>", unsafe_allow_html=True)
    st.link_button("開啟 GPT-5.4 Thinking", GPT_THINKING_URL)
    st.text_area("建議貼給 GPT 的分析提示詞", value=make_gpt_prompt(df_daily), height=210)

    st.markdown("### A. 來源網址自動解析（建議）")
    default_source_url = source_groups[0]["items"][-1]["url"] if source_groups and source_groups[0]["items"] else ""
    source_url = st.text_input("官方來源網址（WAM / QNA 等）", value=default_source_url, key="auto_update_source")
    if st.button("自動解析並更新到最近一日", type="primary"):
        try:
            parsed = fetch_daily_from_article(source_url, source_groups, df_daily)
            parsed_dt = pd.to_datetime(parsed["date"]).date()
            latest_dt = pd.to_datetime(latest_date).date()
            persist_daily_override(
                parsed["date"],
                parsed["missiles"],
                parsed["drones"],
                parsed["note"],
                source_url=parsed["source_url"],
                source_kind="auto",
            )
            if parsed_dt > latest_dt:
                st.success(f"已新增 {parsed['date']}：飛彈 {parsed['missiles']}、無人機 {parsed['drones']}。")
            elif parsed_dt == latest_dt:
                st.success(f"已覆寫 {parsed['date']}：飛彈 {parsed['missiles']}、無人機 {parsed['drones']}。")
            else:
                st.warning(f"已寫入較早日期 {parsed['date']}（用於修正舊資料）。")
            st.rerun()
        except (HTTPError, URLError) as e:
            st.error(f"來源抓取失敗：{e}")
        except ValueError as e:
            st.error(f"解析失敗：{e}")
        except Exception as e:
            st.error(f"更新失敗：{e}")

    st.markdown("### B. 手動補登最近一日（備援）")
    with st.form("manual_daily_update_form", clear_on_submit=False):
        default_manual_date = max(pd.to_datetime(latest_date).date(), date.today())
        input_date = st.date_input("日期", value=default_manual_date)
        c1, c2 = st.columns(2)
        missiles_val = c1.number_input("飛彈數量", min_value=0, step=1, value=0)
        drones_val = c2.number_input("無人機數量", min_value=0, step=1, value=0)
        note = st.text_input("備註", value="手動更新")
        submitted = st.form_submit_button("儲存手動更新")
        if submitted:
            persist_daily_override(
                input_date.strftime("%Y-%m-%d"),
                int(missiles_val),
                int(drones_val),
                note.strip() or "手動更新",
                source_url="",
                source_kind="manual",
            )
            st.success("已儲存，資料已可用於圖表與統計。")
            st.rerun()

st.markdown("<div class='small-muted' style='margin-top:14px;'>執行提醒：請用 <code>streamlit run IranMissile.py</code>（或 <code>streamlit run app.py</code>）。若你開的是 <code>IranMissile.html</code>，不會有 AI 更新功能。</div>", unsafe_allow_html=True)
