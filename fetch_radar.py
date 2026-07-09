#!/usr/bin/env python3
"""每日技术雷达。

从 Hacker News 与 GitHub Trending 抓取当日热门，按关注方向的关键词筛选，
生成一份中文导览的 markdown 摘要，写入 docs/digests/YYYY-MM-DD.md，
并同步刷新 docs/index.md（最新一期）与 docs/archive.md（历史索引）。

设计要点：
- 纯 Python 标准库实现，无第三方依赖，运行不需要任何 API key。
- 数据源均为公开、免鉴权：Hacker News 官方 Firebase API、GitHub Trending 页面。
- 无论抓取成功与否，每次运行都会写出一个按日期命名的新文件，
  以保证每天都产生一次提交（GitHub 贡献绿格靠的是提交，不挑内容）。
- 想加减关注方向，改下面的 KEYWORDS 与 TRENDING_LANGS 即可。
"""

import datetime
import html
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

# 关注关键词：Hacker News 标题命中其一即收录（小写匹配）。想加减方向就改这里。
KEYWORDS = [
    "llm", "language model", "gpt", "claude", "anthropic", "openai", "gemini",
    "diffusion", "transformer", "neural", "machine learning", "deep learning",
    "pytorch", "inference", "quantization", "fine-tun", "retrieval", "agent",
    "super-resolution", "super resolution", "image", "vision", "video",
    "android", "kotlin", "wear os", "watch", "jetpack", "compose",
    "rust", "compiler", "gpu", "cuda",
]

# GitHub Trending 追踪的语言（空串代表「全部语言」）。想加减就改这里。
TRENDING_LANGS = [""]

HN_TOP = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM = "https://hacker-news.firebaseio.com/v0/item/{}.json"
HN_ITEM_WEB = "https://news.ycombinator.com/item?id={}"
HN_SCAN = 90           # 扫描 HN 前多少条 top story
HN_MAX = 15            # 最多收录多少条命中关键词的 HN
HN_FALLBACK = 6        # 命中太少时，用得分最高的补足到这个数
GH_MAX_PER_LANG = 8    # 每种语言最多收录多少个 trending repo

ROOT = Path(__file__).resolve().parent
DIGEST_DIR = ROOT / "docs" / "digests"

UA = "tech-radar/1.0 (+https://github.com/yingwang/tech-radar)"


def get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def get_json(url: str):
    return json.loads(get(url).decode("utf-8"))


def snippet(text: str, limit: int = 240) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    dot = cut.rfind(". ")
    if dot > limit * 0.5:
        return cut[: dot + 1]
    return cut.rstrip() + "…"


def fetch_excerpt(url: str) -> str:
    """从文章页取几行摘录：优先 og:description / meta description，取不到就返回空串。"""
    try:
        page = get(url, timeout=10).decode("utf-8", "replace")
    except Exception:
        return ""
    found = {"og:description": "", "description": "", "twitter:description": ""}
    for tag in re.findall(r"<meta\b[^>]*>", page, re.I):
        km = re.search(r'(?:property|name)\s*=\s*(["\'])(.*?)\1', tag, re.I)
        if not km:
            continue
        key = km.group(2).strip().lower()
        if key not in found or found[key]:
            continue
        cm = re.search(r'content\s*=\s*(["\'])(.*?)\1', tag, re.I | re.S)
        if cm:
            found[key] = html.unescape(re.sub(r"\s+", " ", cm.group(2))).strip()
    for key in ("og:description", "description", "twitter:description"):
        if found[key]:
            return snippet(found[key])
    return ""


def hn_excerpt(story: dict) -> str:
    """Ask/Show HN 自带正文用 text 字段；外链帖抓文章页描述。"""
    if story.get("text"):
        plain = html.unescape(re.sub(r"<[^>]+>", " ", story["text"]))
        return snippet(re.sub(r"\s+", " ", plain).strip())
    if story.get("url"):
        return fetch_excerpt(story["url"])
    return ""


def fetch_hn() -> list:
    ids = get_json(HN_TOP)[:HN_SCAN]
    stories = []
    for sid in ids:
        try:
            item = get_json(HN_ITEM.format(sid))
        except Exception:
            continue
        if not item or item.get("type") != "story" or not item.get("title"):
            continue
        stories.append(item)

    hits, rest = [], []
    for s in stories:
        title = s.get("title", "").lower()
        (hits if any(k in title for k in KEYWORDS) else rest).append(s)

    hits.sort(key=lambda s: s.get("score", 0), reverse=True)
    picked = hits[:HN_MAX]
    if len(picked) < HN_FALLBACK:
        rest.sort(key=lambda s: s.get("score", 0), reverse=True)
        picked += rest[: HN_FALLBACK - len(picked)]
    return picked


def fetch_github_trending(lang: str) -> list:
    url = "https://github.com/trending"
    if lang:
        url += "/" + urllib.parse.quote(lang)
    url += "?since=daily"
    page = get(url).decode("utf-8", "replace")

    repos = []
    for block in re.split(r'<article class="Box-row">', page)[1:]:
        m = re.search(r'<h2[^>]*>\s*<a[^>]*href="/([^"]+)"', block)
        if not m:
            continue
        path = m.group(1).strip().strip("/")
        if path.count("/") != 1:          # 只要 owner/repo 两段
            continue

        desc = ""
        dm = re.search(r'<p[^>]*col-9[^>]*>(.*?)</p>', block, re.S)
        if dm:
            desc = html.unescape(re.sub(r"<[^>]+>", "", dm.group(1))).strip()

        sm = re.search(r"([\d,]+)\s+stars today", block)
        stars_today = sm.group(1) if sm else ""

        repos.append({"path": path, "desc": desc, "stars_today": stars_today})
        if len(repos) >= GH_MAX_PER_LANG:
            break
    return repos


def build_digest(date_str: str) -> str:
    lines = [
        f"# 技术雷达 · {date_str}",
        "",
        "> 自动抓取，数据来自 Hacker News 与 GitHub Trending，按关注方向筛选。"
        "标题与描述保留英文原文，链接可直达。",
        "",
    ]
    total = 0

    lines += ["## Hacker News 热门", ""]
    hn_failed = False
    try:
        hn = fetch_hn()
    except Exception as exc:
        hn, hn_failed = [], True
        lines += [f"（Hacker News 抓取失败：{exc}）", ""]
    if hn:
        for s in hn:
            total += 1
            link = s.get("url") or HN_ITEM_WEB.format(s["id"])
            title = html.unescape(s.get("title", "").strip())
            lines.append(f"### [{title}]({link})")
            lines.append("")
            lines.append(
                f"- {s.get('score', 0)} 分 · {s.get('descendants', 0)} 条讨论 · "
                f"[HN 讨论帖]({HN_ITEM_WEB.format(s['id'])})"
            )
            lines.append("")
            excerpt = hn_excerpt(s)
            if excerpt:
                lines.append(f"> {excerpt}")
                lines.append("")
    elif not hn_failed:
        lines += ["（今日无匹配条目。）", ""]

    lines += ["## GitHub Trending", ""]
    for lang in TRENDING_LANGS:
        lines += [f"### {lang if lang else '全部语言'}", ""]
        try:
            repos = fetch_github_trending(lang)
        except Exception as exc:
            lines += [f"（抓取失败：{exc}）", ""]
            continue
        if not repos:
            lines += ["（今日无数据。）", ""]
            continue
        for r in repos:
            total += 1
            star = f" · +{r['stars_today']} star/日" if r["stars_today"] else ""
            desc = f" — {r['desc']}" if r["desc"] else ""
            lines.append(f"- [{r['path']}](https://github.com/{r['path']}){star}{desc}")
        lines.append("")

    lines += ["---", "", f"本期共收录 {total} 条。", ""]
    return "\n".join(lines)


def refresh_index_and_archive(digest_md: str) -> None:
    docs = ROOT / "docs"
    (docs / "index.md").write_text(digest_md, encoding="utf-8")

    files = sorted(DIGEST_DIR.glob("20*.md"), key=lambda p: p.stem, reverse=True)
    arch = ["# 历史雷达", "", "按日期倒序排列。", ""]
    arch += [f"- [{p.stem}](digests/{p.name})" for p in files]
    arch.append("")
    (docs / "archive.md").write_text("\n".join(arch), encoding="utf-8")


def main() -> None:
    today = datetime.datetime.utcnow().date().isoformat()
    DIGEST_DIR.mkdir(parents=True, exist_ok=True)
    try:
        digest_md = build_digest(today)
    except Exception as exc:
        # 兜底：即便整体失败也写出文件，保证今天仍有一次提交。
        digest_md = f"# 技术雷达 · {today}\n\n> 今日抓取失败：{exc}\n"
    (DIGEST_DIR / f"{today}.md").write_text(digest_md, encoding="utf-8")
    refresh_index_and_archive(digest_md)
    print(f"wrote radar for {today}")


if __name__ == "__main__":
    main()
