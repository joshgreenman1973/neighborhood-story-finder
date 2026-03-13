# NYC Neighborhood Story Finder

An early-warning system for neighborhood-level stories across New York City. It scans nine data sources — 311 complaints, community board budget requests, land use applications, constituent service cases, building permits, Reddit, local news, and community board meetings — and synthesizes them into story leads for each of the city's 59 community districts.

The tool is built on a simple editorial premise: local stories don't appear out of nowhere. Before a neighborhood concern becomes a media story, it leaves traces across multiple city systems. This tool surfaces those traces.

## The editorial logic

Each data source tells you something different:

- **311 complaints** tell you what is being reported — the raw signal of resident frustration, aggregated and tested for statistical anomalies.
- **Council constituent-service logs** tell you what is politically sticky — issues that residents have escalated to their elected officials.
- **Community board budget requests** tell you what districts keep asking the city to fund — the same request showing up year after year means the problem hasn't been solved.
- **ULURP / land use applications** tell you what is about to become a fight — rezonings, shelter sitings, street redesigns that haven't hit the news yet.
- **DOB building permits** tell you where the physical landscape is changing — spikes in new building or demolition filings signal development pressure.
- **Community board meetings** tell you what is becoming organized — when an issue gets on a committee agenda, it means someone is trying to do something about it.
- **Reddit and local news** tell you what the public conversation looks like — whether an issue has broken through or is still simmering.

### The convergence signal

The most valuable output of this tool is convergence. When 311 complaint spikes, community board committee topics, and council constituent cases all point at the same corner, corridor, school zone, or housing complex — that is often the moment before the issue graduates into a media story. The tool is designed to surface these convergences automatically.

## How it works

### Data pipeline (Python, daily)

A batch pipeline (`data/pipeline.py`) runs once per day via GitHub Actions and collects from eight data sources:

| Source | What it captures | API / Method |
|--------|-----------------|-------------|
| **311 complaints** | 90 days of service requests, z-score spike detection, 12-week sparklines | Socrata API (`erm2-nwe9`) |
| **CB budget requests** | What districts repeatedly ask the city to fix or fund | Socrata API (`vn4m-mk4t`) |
| **Land use / ULURP** | Active rezonings and development proposals before they hit the news | Socrata API (`hgx4-8ukb`) |
| **Council services** | Constituent complaints escalated to elected officials | Socrata API (`b9km-gdpy`) |
| **DOB permits** | New building, demolition, and major alteration filings | Socrata API (`w9ak-ipjd`) |
| **Reddit** | ~12 NYC subreddits, geo-mapped by neighborhood name matching | Public JSON API |
| **Local news** | 11 outlets (THE CITY, Gothamist, Hell Gate, City Limits, etc.) | RSS / feedparser |
| **Community boards** | Meeting dates and active topics from 59 CB pages | Web scraping (nyc.gov) |

After collection, an AI synthesis step (Claude Haiku) reads all available data for each district and produces 3-5 story leads with structured scoring. Without an API key, the pipeline falls back to purely statistical theme generation from 311 spike data.

Output is static JSON:
- `districts.json` — Summary for all 59 districts
- `districts/{cd}.json` — Full detail per district (themes, spikes, Reddit, news, budget requests, land use, permits, council cases)
- `trends.json` — Citywide hot spots ranked by activity
- `geo/community_districts.geojson` — District boundaries

### Frontend (vanilla JS + MapLibre GL)

A single-page application renders a choropleth map colored by activity score (0–100, combining complaint volume, spike severity, and category diversity). Clicking a district loads its detail JSON and shows:

- **Story leads** with severity, verifiability, freshness, and editorial potential badges
- **311 anomalies** with z-scores and percentage changes vs. baseline
- **12-week sparklines** for top complaint types (orange = spiking)
- **CB budget requests** — what the district keeps asking for
- **Active land use / ULURP applications** — what's in the pipeline
- **Building permit filings** — new construction, demolitions, major alterations
- **Council constituent cases** — what's being escalated
- **Reddit discussions** with engagement metrics and links
- **Local news** with outlet attribution and links
- **Community board** meeting info and topics
- **Sources** — direct links to NYC Open Data queries, ZAP, Reddit search, and CB pages

Every data point tracks back to a source. Nothing is paywalled.

## Story scoring

Each story lead is scored across six dimensions:

| Dimension | What it measures |
|-----------|-----------------|
| **Severity** | How serious is this for residents? |
| **Verifiability** | Can this be fact-checked with public data? |
| **Freshness** | Is this emerging now or long-running? |
| **Human interest** | Are there affected people to talk to? |
| **Data richness** | How much quantitative evidence exists? |
| **Editorial potential** | Brief, short, or feature-length story? |

Leads that appear across multiple data sources get higher scores. A 311 spike corroborated by a community board agenda item and a council constituent complaint is a much stronger signal than any one alone.

## Running locally

```bash
cd neighborhood-story-finder
pip install -r data/requirements.txt

# Without Claude API (statistical themes only)
python data/pipeline.py --no-claude

# With Claude API for AI-synthesized themes
export ANTHROPIC_API_KEY=sk-ant-...
python data/pipeline.py

# 311 data only (fastest, for testing)
python data/pipeline.py --311-only

# Skip community board scraping (slow)
python data/pipeline.py --no-cb
```

Output goes to `data/output/`. Open `index.html` in a browser (or run `python serve.py` for a dev server with no-cache headers on port 8803).

## Architecture decisions

- **Static JSON over live API**: Pre-computed output, no server, no API keys in the browser, no rate limits.
- **Community districts over neighborhoods**: 59 official districts with clear boundaries. 311 data uses them natively.
- **MapLibre GL**: Free, no token, same API surface as Mapbox.
- **Claude Haiku for synthesis**: ~$2–6/day for all 59 districts during batch.
- **Z-score spike detection**: Compares each week against an 8-week baseline. Z-scores above 1.8 with 3+ complaints trigger an alert.
- **GitHub Pages**: Zero hosting cost. Daily GitHub Actions cron updates the data.

## What's not yet included

The editorial framework behind this tool identifies several additional source layers that would strengthen the signal but aren't yet automated:

- **NYCHA resident councils** (~95% of developments have them)
- **School SLTs, PA/PTAs, and CECs** — what families are quietly worried about
- **Borough president hearings and service cabinets**
- **BIDs and merchant groups** — early detection of corridor deterioration
- **The informal layer**: tenant associations, block associations, precinct community WhatsApps, local Facebook groups, parent listservs, mosque/church/synagogue newsletters, mutual-aid chats

These aren't available through public APIs, but they represent where the most granular early signals live.

## File structure

```
neighborhood-story-finder/
  index.html              # Frontend
  app.js                  # Map, sidebar, interactions
  style.css               # Vital City dark theme
  lib/sparkline.js        # Canvas-based micro sparklines
  serve.py                # Dev server (port 8803)
  data/
    pipeline.py           # Orchestrator
    config.py             # Mappings, API config, categories
    requirements.txt      # Python dependencies
    collectors/
      three11.py          # 311 complaints
      reddit.py           # NYC subreddits
      news_rss.py         # Local news RSS
      community_boards.py # NYC.gov CB pages
      budget_requests.py  # CB budget requests (OMB)
      land_use.py         # ULURP / ZAP applications
      council_services.py # CouncilStat constituent cases
      dob_permits.py      # DOB NOW building permits
    processors/
      trend_detector.py   # Z-score spike detection
      theme_extractor.py  # Claude API synthesis
      data_compressor.py  # JSON output generation
      geo_mapper.py       # Text-to-district mapping
    output/               # Generated data (committed to repo)
  .github/workflows/
    update-data.yml       # Daily cron pipeline
```
