import time
import json
import re
import csv
from urllib.parse import urlparse
from urllib import robotparser
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup

from openai import OpenAI  # pip install openai


st.set_page_config(page_title="Multi-URL Web Scraper UI", layout="wide")

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ResearchScraper/1.0; +https://example.com/bot)"
}


def normalize_url(u: str) -> str:
    u = u.strip()
    if not u:
        return ""
    if not re.match(r"^https?://", u, re.I):
        u = "https://" + u
    return u


def get_robots_parser(url: str, timeout: int = 10):
    """用 requests 讀 robots.txt（含 timeout），避免 robotparser.read() 卡住。"""
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = robotparser.RobotFileParser()
    rp.set_url(robots_url)

    try:
        r = requests.get(robots_url, headers=DEFAULT_HEADERS, timeout=timeout)
        if r.status_code >= 400:
            return None
        rp.parse(r.text.splitlines())
        return rp
    except Exception:
        return None


def can_fetch(url: str, user_agent: str, obey_robots: bool, robots_cache: dict, timeout: int):
    if not obey_robots:
        return True, None

    parsed = urlparse(url)
    key = f"{parsed.scheme}://{parsed.netloc}"
    if key not in robots_cache:
        robots_cache[key] = get_robots_parser(url, timeout=timeout)

    rp = robots_cache[key]
    if rp is None:
        return True, "robots.txt unavailable; proceeded with caution."

    ok = rp.can_fetch(user_agent, url)
    return ok, None if ok else "Blocked by robots.txt"


def extract_page_fields(html: str, url: str, extract_tables: bool):
    soup = BeautifulSoup(html, "html.parser")

    title = soup.title.get_text(strip=True) if soup.title else ""

    desc_tag = soup.find("meta", attrs={"name": "description"})
    meta_desc = desc_tag.get("content", "").strip() if desc_tag else ""

    h1 = soup.find("h1")
    h1_text = h1.get_text(" ", strip=True) if h1 else ""

    # 去噪音
    for t in soup(["script", "style", "noscript", "header", "footer", "nav", "aside"]):
        t.decompose()

    text = soup.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()

    links_count = len(soup.find_all("a"))

    tables = []
    if extract_tables:
        try:
            dfs = pd.read_html(html)
            for df in dfs[:5]:
                tables.append(df.to_dict(orient="records"))
        except Exception:
            tables = []

    snippet = text[:400] + ("..." if len(text) > 400 else "")

    return {
        "url": url,
        "title": title,
        "meta_description": meta_desc,
        "h1": h1_text,
        "full_text": text,          # ✅ CSV / GPT 用完整內文
        "text_snippet": snippet,    # UI 總覽用摘要
        "text_length": len(text),
        "links_count": links_count,
        "tables": tables,
    }


def fetch_one(url: str, settings: dict, robots_cache: dict):
    t0 = time.time()
    s = requests.Session()

    headers = troubled_headers = dict(DEFAULT_HEADERS)
    headers["User-Agent"] = settings["user_agent"]

    ok, robots_note = can_fetch(
        url=url,
        user_agent=settings["user_agent"],
        obey_robots=settings["obey_robots"],
        robots_cache=robots_cache,
        timeout=settings["timeout"],
    )
    if not ok:
        return {
            "url": url,
            "status": "blocked",
            "error": "Blocked by robots.txt",
            "elapsed_s": round(time.time() - t0, 3),
            "robots_note": None,
        }

    last_err = None
    for _ in range(settings["retries"] + 1):
        try:
            if settings["delay_s"] > 0:
                time.sleep(settings["delay_s"])

            r = s.get(url, headers=headers, timeout=settings["timeout"])
            r.raise_for_status()

            data = extract_page_fields(
                html=r.text,
                url=url,
                extract_tables=settings["extract_tables"],
            )
            return {
                **data,
                "status": "ok",
                "http_status": r.status_code,
                "elapsed_s": round(time.time() - t0, 3),
                "robots_note": robots_note,
                "error": None,
            }
        except Exception as e:
            last_err = str(e)

    return {
        "url": url,
        "status": "error",
        "error": last_err,
        "elapsed_s": round(time.time() - t0, 3),
        "robots_note": robots_note,
    }


def build_gpt_input(results: list[dict], per_url_chars: int, total_chars: int) -> tuple[str, dict]:
    """把多網址內容組成 GPT 輸入（含字數裁切），回傳 (text, stats)。"""
    parts = []
    used = 0
    included = 0
    skipped = 0

    for r in results:
        if r.get("status") != "ok":
            skipped += 1
            continue

        body = (r.get("full_text") or "")
        if per_url_chars and per_url_chars > 0:
            body = body[:per_url_chars]

        block = (
            f"URL: {r.get('url','')}\n"
            f"TITLE: {r.get('title','')}\n"
            f"META: {r.get('meta_description','')}\n"
            f"H1: {r.get('h1','')}\n"
            f"CONTENT:\n{body}\n"
        )

        # total limit
        if total_chars and total_chars > 0:
            if used >= total_chars:
                break
            remaining = total_chars - used
            if len(block) > remaining:
                block = block[:remaining]

        parts.append(block)
        used += len(block)
        included += 1

        if total_chars and used >= total_chars:
            break

    text = "\n\n---\n\n".join(parts)
    stats = {"included_ok_pages": included, "skipped_non_ok": skipped, "final_chars": len(text)}
    return text, stats


def send_to_gpt(api_key: str, model: str, instructions: str, input_text: str) -> str:
    client = OpenAI(api_key=api_key)
    # Responses API：instructions + input
    resp = client.responses.create(
        model=model,
        instructions=instructions,
        input=input_text,
    )
    return getattr(resp, "output_text", "") or ""


# ---------------- UI ----------------
st.title("Multi-URL Web Scraper → GPT")
st.caption("多網址抓取後，匯出 CSV（含全文）或把全文送到 GPT API 做摘要/分類/抽取。")

# Sidebar
with st.sidebar:
    st.subheader("抓取設定")
    obey_robots = st.checkbox("遵守 robots.txt", value=True)
    timeout = st.number_input("Timeout（秒）", min_value=3, max_value=60, value=15, step=1)
    retries = st.number_input("重試次數", min_value=0, max_value=5, value=1, step=1)
    delay_s = st.number_input("每次請求延遲（秒）", min_value=0.0, max_value=10.0, value=0.2, step=0.1)
    max_workers = st.number_input("並發數（同時抓幾個）", min_value=1, max_value=30, value=8, step=1)
    extract_tables = st.checkbox("擷取表格（read_html，最多 5 個）", value=False)
    user_agent = st.text_input("User-Agent", value=DEFAULT_HEADERS["User-Agent"])

    st.divider()
    st.subheader("OpenAI（送到 GPT）")
    api_key = st.text_input("OpenAI API Key", type="password", placeholder="sk-...（不會顯示）")
    model = st.text_input("Model", value="gpt-5.2")
    prompt_instructions = st.text_area(
        "Prompt / Instructions（給模型的指令）",
        height=160,
        placeholder="例如：請將每個網址的內容摘要成 5 點重點，並列出可交易的關鍵事件與價格影響。",
    )
    per_url_chars = st.number_input("每個網址最多送出字元數", min_value=500, max_value=200000, value=8000, step=500)
    total_chars = st.number_input("總送出字元上限", min_value=2000, max_value=500000, value=50000, step=2000)
    auto_send = st.checkbox("抓完後自動送出到 GPT", value=False)

st.subheader("輸入網址（每行一個，可多個）")
urls_text = st.text_area(
    label="",
    height=180,
    placeholder="https://example.com/page1\nhttps://example.com/page2\n...\n",
)

colA, colB = st.columns([1, 4])
with colA:
    run = st.button("開始抓取", type="primary")
with colB:
    st.write("")

# state init
if "results" not in st.session_state:
    st.session_state["results"] = None
if "gpt_output" not in st.session_state:
    st.session_state["gpt_output"] = None
if "gpt_input_stats" not in st.session_state:
    st.session_state["gpt_input_stats"] = None

if run:
    raw = [normalize_url(x) for x in urls_text.splitlines()]
    urls = []
    seen = set()
    for u in raw:
        if u and u not in seen:
            seen.add(u)
            urls.append(u)

    if not urls:
        st.warning("請至少輸入 1 個網址（每行一個）。")
        st.stop()

    settings = {
        "obey_robots": obey_robots,
        "timeout": int(timeout),
        "retries": int(retries),
        "delay_s": float(delay_s),
        "extract_tables": extract_tables,
        "user_agent": user_agent.strip() or DEFAULT_HEADERS["User-Agent"],
    }

    st.info(f"準備抓取 {len(urls)} 個網址（並發 {int(max_workers)}）")
    progress = st.progress(0)
    status_box = st.empty()

    robots_cache = {}
    results = []
    done = 0

    with ThreadPoolExecutor(max_workers=int(max_workers)) as ex:
        futures = {ex.submit(fetch_one, u, settings, robots_cache): u for u in urls}
        for fut in as_completed(futures):
            res = fut.result()
            results.append(res)
            done += 1
            progress.progress(done / len(urls))
            status_box.write(f"完成 {done}/{len(urls)}：{res['url']} → {res.get('status')}")

    st.session_state["results"] = results
    st.session_state["gpt_output"] = None
    st.session_state["gpt_input_stats"] = None

# If have results, show summary + export + GPT
results = st.session_state.get("results")
if results:
    df = pd.DataFrame(results)

    df_display = df.drop(columns=[c for c in ["tables", "full_text"] if c in df.columns])
    df_export = df.drop(columns=[c for c in ["tables"] if c in df.columns])

    st.subheader("抓取結果（總覽）")
    st.dataframe(df_display, use_container_width=True)

    st.subheader("匯出")
    csv_bytes = df_export.to_csv(
        index=False,
        encoding="utf-8-sig",
        quoting=csv.QUOTE_ALL,  # ✅ 內文有逗號/換行不亂欄
    ).encode("utf-8-sig")

    json_bytes = json.dumps(results, ensure_ascii=False, indent=2).encode("utf-8")

    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "下載 CSV（含完整內文）",
            data=csv_bytes,
            file_name="scrape_results_fulltext.csv",
            mime="text/csv",
        )
    with c2:
        st.download_button(
            "下載 JSON（含 tables）",
            data=json_bytes,
            file_name="scrape_results.json",
            mime="application/json",
        )

    st.subheader("送到 GPT")
    gpt_input_text, stats = build_gpt_input(results, int(per_url_chars), int(total_chars))
    st.session_state["gpt_input_stats"] = stats

    st.write(f"將送出：成功頁數 {stats['included_ok_pages']}（跳過 {stats['skipped_non_ok']}）| 字元數 {stats['final_chars']:,}")

    send_btn = st.button("傳送到 GPT（使用左側 API Key + Prompt）", type="secondary")

    if (auto_send or send_btn):
        if not api_key:
            st.error("左側請先輸入 OpenAI API Key")
        elif not prompt_instructions.strip():
            st.error("左側請先輸入 Prompt / Instructions")
        elif not gpt_input_text.strip():
            st.error("沒有可送出的內容（可能全部抓取失敗或被 robots 擋下）")
        else:
            with st.spinner("呼叫 GPT API 中…"):
                try:
                    out = send_to_gpt(
                        api_key=api_key.strip(),
                        model=model.strip(),
                        instructions=prompt_instructions.strip(),
                        input_text=gpt_input_text,
                    )
                    st.session_state["gpt_output"] = out
                except Exception as e:
                    st.error(f"API 呼叫失敗：{e}")

    if st.session_state.get("gpt_output"):
        st.subheader("GPT 輸出")
        st.text_area("Output", st.session_state["gpt_output"], height=300)

        md_bytes = st.session_state["gpt_output"].encode("utf-8")
        st.download_button("下載 GPT 輸出（.md）", data=md_bytes, file_name="gpt_output.md", mime="text/markdown")

    st.subheader("逐筆詳情")
    for i, r in enumerate(results, start=1):
        with st.expander(f"{i}. {r.get('status')} | {r.get('title','')[:60]} | {r['url']}"):
            st.write(f"**URL**: {r['url']}")
            st.write(f"**Status**: {r.get('status')}  |  **Elapsed(s)**: {r.get('elapsed_s')}")
            if r.get("robots_note"):
                st.warning(r["robots_note"])
            if r.get("error"):
                st.error(r["error"])
            st.write(f"**Title**: {r.get('title','')}")
            st.write(f"**H1**: {r.get('h1','')}")
            st.write(f"**Meta Description**: {r.get('meta_description','')}")
            st.write(f"**Text length**: {r.get('text_length')}")
            st.write(f"**Links count**: {r.get('links_count')}")

            st.write("**Text snippet**:")
            st.code(r.get("text_snippet", ""), language="text")
            st.text_area("Full text", r.get("full_text", ""), height=250)

            if extract_tables:
                tables = r.get("tables") or []
                st.write(f"**Tables**: {len(tables)}")
                for ti, t in enumerate(tables, start=1):
                    st.write(f"Table {ti}")
                    try:
                        st.dataframe(pd.DataFrame(t), use_container_width=True)
                    except Exception:
                        st.json(t)
