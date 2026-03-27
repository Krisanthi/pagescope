# PageScope  -  AI Website Audit Tool

> Built for the EIGHT25MEDIA AI-Native Software Engineer assignment.

A lightweight, production-quality tool that audits any webpage and delivers factual metrics + AI-grounded insights in seconds.

---

## Live Demo / Setup

### Quick Start (Local)

```bash
# 1. Clone
git clone https://github.com/yourusername/pagescope.git
cd pagescope

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set your Groq API key
export GROQ_API_KEY=gsk_your-key-here
# or create a .env file:
echo "GROQ_API_KEY=gsk_your-key-here" > .env

# 4. Run
uvicorn backend.main:app --reload --port 8000

# 5. Open http://localhost:8000
```

No build step. No database. Frontend is served directly by FastAPI as static files.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         Client (Browser)                    │
│              Single-page HTML/CSS/JS (no framework)         │
└─────────────────────┬───────────────────────────────────────┘
                      │  POST /audit  { url }
┌─────────────────────▼───────────────────────────────────────┐
│                   FastAPI Backend                           │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  1. SCRAPER LAYER  (scrape_page)                     │  │
│  │     - requests -> raw HTML                            │  │
│  │     - BeautifulSoup / lxml parse                     │  │
│  │     - Extract: word count, headings, CTAs, links,    │  │
│  │       images, alt text, meta title/desc              │  │
│  │     - Returns: FactualMetrics (Pydantic model)       │  │
│  │     - Page text truncated to 4,000 chars for AI      │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐  │
│  │  2. AI LAYER  (call_llm)                          │  │
│  │     - Builds structured user prompt from metrics     │  │
│  │     - Sends system + user prompt to Groq/Llama API       │  │
│  │     - Receives JSON: insights + recommendations      │  │
│  │     - Captures full prompt log (system, user, raw)   │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐  │
│  │  3. RESPONSE ASSEMBLY                                │  │
│  │     - Validates AI output against Pydantic models    │  │
│  │     - Returns AuditResult: metrics + insights +      │  │
│  │       recommendations + prompt_log                   │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

**Key separation**: The scraping layer is entirely deterministic  -  it returns raw numbers. The AI layer receives those numbers as structured input, not as freeform text, ensuring it can only analyse what was actually measured.

---

## AI Design Decisions

### 1. Metrics-first, not text-first
Most naive implementations dump the full HTML or page text to the LLM and ask it to "audit this site." That creates two problems:
- The AI invents metrics rather than measuring them
- Hallucinated numbers pass through undetected

PageScope inverts this: metrics are extracted deterministically first, then passed as labelled structured data to the AI. The AI is explicitly told it cannot access the page directly  -  it can only reason about the numbers we give it.

### 2. Schema-enforced output
The system prompt defines a strict JSON schema the model must follow:
```json
{
  "insights": [{ "category", "score", "summary", "details", "metric_refs" }],
  "recommendations": [{ "priority", "title", "reasoning", "impact", "effort" }],
  "overall_score": int,
  "score_rationale": string
}
```
This allows direct Pydantic validation on the backend with no brittle regex parsing. If the model deviates, it throws a `json.JSONDecodeError` that surfaces to the user.

### 3. Metric references as a quality signal
Each insight contains a `metric_refs` array  -  explicit citations like `"H1 count: 3"`. This forces the model to stay grounded. If a generated insight doesn't map to any metric, it's a signal the reasoning is generic. The frontend surfaces these as tags, making the link between data and conclusion transparent.

### 4. System prompt as a persona, not just instructions
The system prompt establishes the model as a "senior web strategist and SEO consultant." This produces more opinionated, agency-relevant output versus a generic "assistant" framing. Rules are explicit: be specific, reference metrics, no generic advice.

### 5. Token budget management
Page text is capped at 4,000 chars (≈1,000 tokens), leaving headroom for the structured metrics block and the response. This keeps costs predictable and prevents context overflow on large pages, while still providing enough content signal for messaging/clarity analysis.

### 6. Prompt logs as a first-class feature
Prompt logs are returned in every API response and surfaced in the UI as tabbed panels. This was a deliberate design choice aligned with the assignment's explicit requirement  -  but also reflects how AI-native tools should work: the reasoning chain should be inspectable, not hidden.

---

## Trade-offs

| Decision | What was gained | What was sacrificed |
|----------|----------------|---------------------|
| Deterministic scraper + AI in sequence | Reliable metrics, grounded insights | Two-step latency vs one LLM call |
| No JavaScript rendering (requests, not Playwright) | Speed, simplicity, no browser dependency | JS-heavy SPAs may show lower counts |
| 4,000-char text truncation | Cost/latency control | AI may miss content on long pages |
| Schema-enforced JSON output | Reliable parsing, Pydantic validation | Slightly reduces model flexibility |
| Single-page no-framework frontend | Zero build step, portable | Less component reuse at scale |
| Llama 3.3 70B (via Groq) | Best quality/cost ratio for structured analysis | Slightly higher cost than Haiku |

---

## What I Would Improve With More Time

**1. JavaScript rendering (Playwright/Puppeteer)**
SPAs built with React/Vue/Angular don't render meaningful HTML server-side. Adding a headless browser would make the tool accurate for modern marketing sites.

**2. Streaming AI responses**
Stream the Groq/Llama response token-by-token to the frontend so the UI shows insights appearing progressively rather than a single loading state.

**3. Caching layer (Redis)**
Cache audit results by URL + content hash for 24h. Identical pages re-run immediately without hitting the API.

**4. Diff mode / audit history**
Store past audits per URL and show score progression over time. "Your score improved from 54 -> 71 since last week."

**5. Expand CTA detection**
Current CTA detection uses regex on link/button text. A classifier trained on actual CTA examples would catch more patterns (icon-only buttons, images-as-CTAs, etc.).

**6. Lighthouse integration**
Pull in Core Web Vitals (LCP, CLS, FID) from PageSpeed Insights API and include them as structured input to the AI for performance-aware recommendations.

**7. Multi-page crawl mode**
Audit the top N pages of a site and aggregate scores into a site-wide health report  -  more relevant for an agency workflow.

---

## Project Structure

```
pagescope/
├── backend/
│   └── main.py           # FastAPI app: scraper + AI layer + API routes
├── frontend/
│   └── index.html        # Single-file frontend (HTML + CSS + JS)
├── prompt_logs/
│   └── example_audit.json  # Sample prompt log from a real audit run
├── requirements.txt
└── README.md
```

---

## API Reference

### `POST /audit`
```json
// Request
{ "url": "https://example.com" }

// Response (AuditResult)
{
  "metrics": { ... },         // FactualMetrics  -  deterministic
  "insights": [ ... ],        // AIInsight[]    -  AI-generated
  "recommendations": [ ... ], // Recommendation[]  -  AI-generated
  "overall_score": 67,
  "prompt_log": { ... },      // Full trace: system, user, raw output, tokens
  "audit_timestamp": "2024-..."
}
```

### `GET /health`
Returns `{ "status": "ok" }`  -  useful for deployment health checks.
