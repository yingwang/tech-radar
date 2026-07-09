# 技术雷达

每天自动抓取 [Hacker News](https://news.ycombinator.com/) 与 [GitHub Trending](https://github.com/trending)，按关注方向筛选，生成一份中文导览的摘要并发布到 GitHub Pages。

**在线阅读**：https://yingwang.github.io/tech-radar/

## 特点

- 纯 Python 标准库实现，无第三方依赖，运行**不需要任何 API key**。
- 数据源均为公开、免鉴权：Hacker News 官方 Firebase API、GitHub Trending 页面。
- 全流程跑在 GitHub Actions 上，**不依赖本机开机**。
- 每天写出一份按日期命名的新摘要，因此每天都会产生一次提交。

## 调整关注方向

编辑 `fetch_radar.py` 顶部：

- `KEYWORDS`：Hacker News 标题命中其中任一关键词即收录。
- `TRENDING_LANGS`：GitHub Trending 追踪的语言列表（空串代表「全部语言」）。

## 运行频率

`.github/workflows/daily-radar.yml` 每天 07:23 UTC（约斯德哥尔摩夏令时 09:23）触发一次，也可在 Actions 页面手动 `workflow_dispatch`。每次运行：抓取 → 生成当日摘要 → 以作者身份提交 → `mkdocs gh-deploy` 部署。

## 本地试跑

```bash
python3 fetch_radar.py      # 生成 docs/digests/YYYY-MM-DD.md 等
```
