# Major Sites Index — where to look things up

A curated reference of major websites grouped by the kind of information each
contains. Use it to pick a good *starting source* before running a web search or
crawl. Pair with the `web_search` / `web_fetch` / `web_crawler` tools.

## Official documentation & references (APIs, languages, frameworks)
- **docs.python.org** — official Python language & standard-library reference.
- **developer.mozilla.org (MDN)** — web standards: HTML, CSS, JavaScript, HTTP, Web APIs.
- **devdocs.io** — aggregated API docs for many frameworks in one searchable UI.
- **readthedocs.org** — hosted docs for countless Python/JS libraries.
- **cloud docs** — **docs.aws.amazon.com**, **cloud.google.com/docs**,
  **learn.microsoft.com** — provider-specific cloud/SDK references.

## Source code & developer Q&A
- **github.com** — source repositories, releases, issues, discussions.
- **gitlab.com** — repos and CI; mirrors many open-source projects.
- **stackoverflow.com** — practitioner Q&A; fast answers to concrete errors.
- **news.ycombinator.com (Hacker News)** — tech news + discussion, founder/startup signal.

## News & current events
- **reuters.com**, **apnews.com** — wire-service, generally unbiased breaking news.
- **bbc.com**, **nytimes.com**, **theguardian.com** — international & national reporting.
- **techcrunch.com**, **theverge.com**, **arstechnica.com** — technology product/news.

## Encyclopedic & factual lookups
- **wikipedia.org** — broad overview of nearly any topic; good first stop for context.
- **wikidata.org** — structured, machine-readable facts (useful for grounding).
- **britannica.com** — curated encyclopedic articles.
- **wolframalpha.com** — computational facts, math, units, data queries.

## Science, data & academic
- **arxiv.org** — preprints across physics/CS/math/quant-bio.
- **scholar.google.com** — broad academic paper search with citation counts.
- **pubmed.ncbi.nlm.nih.gov** — biomedical literature.
- **kaggle.com** — datasets and notebooks.
- **ourworldindata.org** — well-sourced global statistics and charts.

## Reference & utilities
- **timeanddate.com** — time zones, calendars, holidays.
- **openstreetmap.org** — maps and geographic data.
- **imdb.com** — film/TV/actor metadata.
- **worldbank.org**, **data.oecd.org** — macroeconomic and development indicators.

## Government, legal & official
- ***.gov** (e.g. whitehouse.gov, cdc.gov, census.gov) — official US government data & policy.
- **europa.eu** — European Union institutions and law.
- **supremecourt.gov**, **law.cornell.edu** — US case law and statutes.
- **un.org** — international treaties and statistics.

## Commerce, product & consumer
- **amazon.com** — product listings, prices, reviews.
- **crunchbase.com** — company/funding data for startups.
- **appstore.com / play.google.com** — mobile app listings and ratings.

## Social & community
- **reddit.com** — interest communities; useful for real-world sentiment and how-tos.
- **x.com (Twitter)** — real-time announcements, support, public figures.
- **linkedin.com** — professional/company profiles.

## Tips for agents
- For *factual/overview* questions, start at Wikipedia/Wikidata, then a primary source.
- For *code errors*, prefer Stack Overflow / the project's GitHub issues / official docs.
- For *current events*, prefer Reuters/AP over aggregators; verify with a second source.
- For *data*, prefer primary sources (government, World Bank, Our World in Data).
- For *academic*, prefer arXiv/Google Scholar over blog summaries.
- When unsure which source fits, run `web_search` first, then `web_fetch` the most
  authoritative result rather than crawling indiscriminately.
