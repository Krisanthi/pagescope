# PageScope - AI Website Audit Tool
## Submission Report - AI-Native Software Engineer Assignment

**Candidate:** Krisanthi Segar
**Date:** March 27, 2026

---

## Deliverables Checklist

| # | Deliverable | Status | Location |
|---|------------|--------|----------|
| 1 | GitHub repository | Done | [github.com/Krisanthi/pagescope](https://github.com/Krisanthi/pagescope) |
| 2 | Deployed tool | Done | [pagescope-1.onrender.com](https://pagescope-1.onrender.com) |
| 3 | README with architecture, AI decisions, trade-offs, improvements | Done | [README.md](README.md) |
| 4 | Prompt logs / reasoning traces | Done | [prompt_logs/example_audit.json](prompt_logs/example_audit.json) + live in UI |

---

## 1. What It Does

PageScope is a lightweight AI-powered website audit tool that:
1. **Accepts a single URL** via a web interface or API
2. **Extracts factual metrics** deterministically (word count, headings, CTAs, links, images, alt text, meta tags)
3. **Generates AI insights** grounded in those metrics (SEO, messaging, CTA, content depth, UX)
4. **Provides 3-5 prioritized recommendations** with impact/effort ratings

---

## 2. How to Run

```bash
git clone https://github.com/Krisanthi/pagescope.git
cd pagescope
pip install -r requirements.txt
# Add your Groq API key to .env (see .env.example)
uvicorn backend.main:app --reload --port 8000
# Open http://localhost:8000
```

No build step. No database. No paid API keys required (uses Groq's free tier).

---

## 3. Architecture

```
Browser (HTML/CSS/JS) --> POST /audit --> FastAPI Backend
                                            |
                                    1. SCRAPER LAYER
                                       (requests + BeautifulSoup)
                                       Deterministic metric extraction
                                            |
                                    2. AI LAYER
                                       (Groq API / Llama 3.3 70B)
                                       Structured prompt with metrics
                                            |
                                    3. RESPONSE ASSEMBLY
                                       Pydantic validation
                                       Returns metrics + insights + prompt log
```

**Key design choice:** Metrics are extracted first by deterministic code, then passed as structured data to the LLM. The AI never "invents" metrics - it can only reason about what was actually measured.

---

## 4. AI Design Decisions

1. **Metrics-first approach** - Scraper extracts numbers deterministically; AI receives them as labelled structured input. Prevents hallucinated metrics.

2. **Schema-enforced output** - System prompt defines a strict JSON schema. Response is validated against Pydantic models. If the model deviates, it throws a parseable error.

3. **Metric references as quality signal** - Each insight includes a `metric_refs` array (e.g., "H1 count: 1") forcing the model to stay grounded. The UI surfaces these as tags.

4. **Persona-driven prompting** - System prompt establishes the model as a "senior web strategist and SEO consultant" for agency-relevant output vs. generic assistant framing.

5. **Token budget management** - Page text capped at 4,000 chars to keep costs predictable and prevent context overflow.

6. **Prompt logs as first-class feature** - Every API response includes the full prompt trace (system prompt, user prompt, structured input, raw output, token usage). Surfaced in UI as tabbed panels.

---

## 5. Trade-offs

| Decision | Gained | Sacrificed |
|----------|--------|-----------|
| Deterministic scraper + AI in sequence | Reliable metrics, grounded insights | Two-step latency |
| No JS rendering (requests, not Playwright) | Speed, simplicity, zero browser deps | JS-heavy SPAs may show lower counts |
| 4,000-char text truncation | Cost/latency control | AI may miss content on long pages |
| Schema-enforced JSON output | Reliable parsing via Pydantic | Slightly reduces model flexibility |
| Single-page no-framework frontend | Zero build step, portable | Less component reuse at scale |
| Groq/Llama 3.3 70B | Free, fast inference | Slightly less capable than GPT-4/Claude |

---

## 6. What I Would Improve With More Time

1. **JavaScript rendering** (Playwright) for SPA-heavy sites
2. **Streaming AI responses** for progressive UI updates
3. **Caching layer** (Redis) to avoid re-auditing identical pages
4. **Audit history / diff mode** to show score progression over time
5. **Expanded CTA detection** via ML classifier instead of regex
6. **Lighthouse integration** for Core Web Vitals
7. **Multi-page crawl** for site-wide health reports

---

## 7. Prompt Logs

Prompt logs are available in two ways:

1. **Live in the UI** - Click "PROMPT LOGS & REASONING TRACES" in any audit result to see tabbed panels for: System Prompt, User Prompt, Structured Input, Raw Model Output, Token Usage

2. **Example file** - See [`prompt_logs/example_audit.json`](prompt_logs/example_audit.json) for a complete trace from a real audit of eight25media.com

---

## 8. Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python, FastAPI |
| Scraping | requests, BeautifulSoup4, lxml |
| AI/LLM | Groq API, Llama 3.3 70B Versatile |
| Validation | Pydantic v2 |
| Frontend | Vanilla HTML/CSS/JS (no framework) |
| Config | python-dotenv |

---

## 9. Project Structure

```
pagescope/
  backend/
    main.py              # FastAPI: scraper + AI layer + API routes
  frontend/
    index.html           # Single-file frontend (HTML + CSS + JS)
  prompt_logs/
    example_audit.json   # Sample prompt log from a real audit
  .env.example           # Environment template
  requirements.txt       # Python dependencies
  README.md              # Full documentation
  SUBMISSION.md          # This report
```
