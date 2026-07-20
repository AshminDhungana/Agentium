---
name: web_crawling
description: >-
  Crawl a website beyond a single page using the web_crawler tool: depth-limited,
  polite link traversal that follows links and returns each page as clean Markdown.
  Use it when you need multi-page content, sitelinks, or structured site reading
  rather than one URL (web_fetch) or search results (web_search). Covers
  robots.txt respect, rate limiting, and depth limits. Skill file at
  backend/.agentium/skills/web_crawling/SKILL.md.
skill_type: research
domain: general
complexity: intermediate
tags: [web, crawl, scraping, traversal, robots.txt, markdown, retrieval]
creator_tier: head
---

# Web Crawling

The `web_crawler` tool fetches a start URL and follows its links up to a depth
and page budget, returning every visited page as clean Markdown. It is polite by
default: it honors `robots.txt`, rate-limits requests, and blocks private hosts
(SSRF guard).

## Steps
1. Call `web_crawler` with `action="crawl"` and a start `url` (http/https).
2. Set `max_depth` (how many link hops, default 1) and `max_pages` (page cap,
   default 20) to bound the crawl.
3. Keep `stay_on_domain=true` (default) unless you pass `allowed_domains` to
   widen scope; both prevent runaway off-site traversal.
4. Leave `respect_robots=true` (default) — the crawler fetches and honors
   `robots.txt` `Disallow`/`Allow` rules and skips any blocked path.
5. Tune `rate_limit_ms` (default 200) to be gentle on small sites; raise
   `max_tokens` (default 2000) for long pages.
6. Use `web_fetch` instead for a single known URL, and `web_search` to discover
   URLs first. Full tool reference: `backend/.agentium/skills/web_crawling/SKILL.md`.
7. For picking good starting sources by topic, read the curated list in
   `__SKILL_DIR__/datasets/major_sites.md` (~100 major sites by category).

## Major Sites Index (where to look things up)
Before searching or crawling, pick a good starting source by category. The full
curated list (≈50 sites with one-line descriptions) lives in
`__SKILL_DIR__/datasets/major_sites.md`. High-level map:
- **Docs/reference:** docs.python.org, developer.mozilla.org (MDN), devdocs.io,
  readthedocs.org, docs.aws.amazon.com, cloud.google.com/docs, learn.microsoft.com
- **Code & Q&A:** github.com, gitlab.com, stackoverflow.com, news.ycombinator.com
- **News:** reuters.com, apnews.com, bbc.com, techcrunch.com, theverge.com
- **Encyclopedic/factual:** wikipedia.org, wikidata.org, britannica.com, wolframalpha.com
- **Science/academic:** arxiv.org, scholar.google.com, pubmed.ncbi.nlm.nih.gov, kaggle.com, ourworldindata.org
- **Reference/utilities:** timeanddate.com, openstreetmap.org, imdb.com, worldbank.org
- **Government/legal:** *.gov, europa.eu, law.cornell.edu, un.org
- **Commerce/company:** amazon.com, crunchbase.com, appstore.com, play.google.com
- **Social/community:** reddit.com, x.com, linkedin.com
Rule of thumb: factual/overview → Wikipedia/Wikidata then a primary source; code
errors → Stack Overflow / GitHub issues / official docs; current events → Reuters/AP
(verify with a second source); data → primary sources; academic → arXiv/Scholar.

## Validation
- The crawl returns `status: success` with `pages_fetched`, `pages_failed`, and
  per-page `markdown`, `title`, `token_count`.
- Browsing stops at `max_depth`/`max_pages` and never fetches `robots.txt`-blocked
  paths or private hosts (SSRF guard).
- Failures are reported in `failed` without raising into the agent context.
