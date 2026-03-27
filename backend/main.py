"""
Website Audit Tool - Backend
FastAPI server: scraping layer -> AI analysis layer (Groq/Llama)
"""

import re
import json
import time
import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from groq import Groq
import os
from dotenv import load_dotenv

load_dotenv()

# ── Groq config from environment ──
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_MAX_TOKENS = int(os.getenv("GROQ_MAX_TOKENS", "1024"))
GROQ_TEMPERATURE = float(os.getenv("GROQ_TEMPERATURE", "0.7"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Website Audit Tool", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────

class AuditRequest(BaseModel):
    url: str

class FactualMetrics(BaseModel):
    url: str
    word_count: int
    h1_count: int
    h2_count: int
    h3_count: int
    cta_count: int
    internal_links: int
    external_links: int
    image_count: int
    images_missing_alt: int
    images_missing_alt_pct: float
    meta_title: Optional[str]
    meta_description: Optional[str]
    page_title: Optional[str]
    load_status: int

class AIInsight(BaseModel):
    category: str
    score: int          # 1-10
    summary: str
    details: str
    metric_refs: list[str]

class Recommendation(BaseModel):
    priority: int
    title: str
    reasoning: str
    impact: str         # "High" | "Medium" | "Low"
    effort: str         # "High" | "Medium" | "Low"

class AuditResult(BaseModel):
    metrics: FactualMetrics
    insights: list[AIInsight]
    recommendations: list[Recommendation]
    overall_score: int
    prompt_log: dict
    audit_timestamp: str

# ─────────────────────────────────────────────
# Scraper Layer (pure extraction, no AI)
# ─────────────────────────────────────────────

CTA_PATTERNS = re.compile(
    r'\b(get started|sign up|subscribe|buy now|shop now|learn more|'
    r'contact us|request a demo|book a call|start free|try free|'
    r'download|register|join now|get a quote|schedule|apply now|'
    r'see pricing|view demo|get access|claim offer)\b',
    re.IGNORECASE
)

def scrape_page(url: str) -> tuple[BeautifulSoup, FactualMetrics, str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; WebAuditBot/1.0; "
            "+https://github.com/audit-tool)"
        ),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
    except requests.RequestException as e:
        raise HTTPException(status_code=422, detail=f"Failed to fetch URL: {e}")

    soup = BeautifulSoup(resp.text, "lxml")
    parsed = urlparse(url)
    base_domain = parsed.netloc

    # ── Text / word count ──
    for tag in soup(["script", "style", "noscript", "head"]):
        tag.decompose()
    visible_text = soup.get_text(separator=" ", strip=True)
    word_count = len(visible_text.split())

    # ── Headings ──
    h1 = len(soup.find_all("h1"))
    h2 = len(soup.find_all("h2"))
    h3 = len(soup.find_all("h3"))

    # ── CTAs: buttons + links matching CTA patterns ──
    cta_set = set()
    for btn in soup.find_all("button"):
        txt = btn.get_text(strip=True)
        if txt and CTA_PATTERNS.search(txt):
            cta_set.add(txt.lower())
    for a in soup.find_all("a", href=True):
        txt = a.get_text(strip=True)
        cls = " ".join(a.get("class", []))
        role = a.get("role", "")
        if CTA_PATTERNS.search(txt) or "cta" in cls.lower() or "btn" in cls.lower() or role == "button":
            if txt:
                cta_set.add(txt.lower()[:60])
    cta_count = len(cta_set)

    # ── Links ──
    internal_links = 0
    external_links = 0
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue
        full = urljoin(url, href)
        link_domain = urlparse(full).netloc
        if link_domain == base_domain or not link_domain:
            internal_links += 1
        else:
            external_links += 1

    # ── Images ──
    images = soup.find_all("img")
    image_count = len(images)
    missing_alt = sum(
        1 for img in images
        if not img.get("alt") or not img.get("alt", "").strip()
    )
    missing_alt_pct = round((missing_alt / image_count * 100) if image_count else 0, 1)

    # ── Meta ──
    meta_title_tag = soup.find("meta", attrs={"name": re.compile(r"^title$", re.I)})
    og_title = soup.find("meta", property="og:title")
    title_tag = soup.find("title")
    meta_title = (
        (meta_title_tag.get("content") if meta_title_tag else None)
        or (og_title.get("content") if og_title else None)
        or (title_tag.get_text(strip=True) if title_tag else None)
    )

    meta_desc_tag = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    og_desc = soup.find("meta", property="og:description")
    meta_description = (
        (meta_desc_tag.get("content") if meta_desc_tag else None)
        or (og_desc.get("content") if og_desc else None)
    )

    page_title = title_tag.get_text(strip=True) if title_tag else None

    metrics = FactualMetrics(
        url=url,
        word_count=word_count,
        h1_count=h1,
        h2_count=h2,
        h3_count=h3,
        cta_count=cta_count,
        internal_links=internal_links,
        external_links=external_links,
        image_count=image_count,
        images_missing_alt=missing_alt,
        images_missing_alt_pct=missing_alt_pct,
        meta_title=meta_title,
        meta_description=meta_description,
        page_title=page_title,
        load_status=resp.status_code,
    )

    # Truncated page text for AI context (keep tokens manageable)
    page_text_for_ai = visible_text[:4000]
    return soup, metrics, page_text_for_ai


# ─────────────────────────────────────────────
# AI Analysis Layer
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """You are a senior web strategist and SEO consultant at a high-performing digital marketing agency. You specialise in:
- SEO structure and technical on-page optimisation
- Conversion rate optimisation (CRO) and CTA strategy
- Content quality, messaging clarity, and audience alignment
- UX structure and information architecture

You will receive structured data extracted from a webpage - factual metrics AND a text sample.
Your job is to produce a rigorous, data-grounded audit. 

Rules:
1. Every insight MUST reference the specific metric that supports it (e.g. "With only 1 H1 and 14 H2s...").
2. Be specific. No generic advice like "improve your content." Name the actual problem.
3. Scores (1-10): 1-3 = serious problems, 4-6 = needs work, 7-8 = good, 9-10 = excellent.
4. Recommendations must be prioritised and actionable - not vague.
5. Return ONLY valid JSON matching the schema below. No markdown, no explanation outside JSON.

Response schema:
{
  "insights": [
    {
      "category": "SEO Structure" | "Messaging Clarity" | "CTA Usage" | "Content Depth" | "UX & Structure",
      "score": <int 1-10>,
      "summary": "<one sentence verdict>",
      "details": "<2-4 sentences grounded in the metrics>",
      "metric_refs": ["<metric name: value>", ...]
    }
  ],
  "recommendations": [
    {
      "priority": <int 1-5>,
      "title": "<action-oriented title>",
      "reasoning": "<why this matters, tied to a metric>",
      "impact": "High" | "Medium" | "Low",
      "effort": "High" | "Medium" | "Low"
    }
  ],
  "overall_score": <int 1-100>,
  "score_rationale": "<2 sentences explaining the overall score>"
}"""

def build_user_prompt(metrics: FactualMetrics, page_text: str) -> str:
    meta_title_len = len(metrics.meta_title) if metrics.meta_title else 0
    meta_desc_len = len(metrics.meta_description) if metrics.meta_description else 0

    return f"""Audit the following webpage.

## FACTUAL METRICS (extracted, not AI-generated)
- URL: {metrics.url}
- Word Count: {metrics.word_count}
- Headings: H1={metrics.h1_count}, H2={metrics.h2_count}, H3={metrics.h3_count}
- CTA Count: {metrics.cta_count}
- Internal Links: {metrics.internal_links}
- External Links: {metrics.external_links}
- Images: {metrics.image_count} total, {metrics.images_missing_alt} missing alt text ({metrics.images_missing_alt_pct}%)
- Meta Title: "{metrics.meta_title or 'MISSING'}" ({meta_title_len} chars)
- Meta Description: "{metrics.meta_description or 'MISSING'}" ({meta_desc_len} chars)
- HTTP Status: {metrics.load_status}

## PAGE TEXT SAMPLE (first ~4,000 chars of visible content)
{page_text}

Provide the structured JSON audit now."""


def call_llm(metrics: FactualMetrics, page_text: str) -> tuple[dict, dict]:
    """Returns (parsed_result, prompt_log)"""
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    user_prompt = build_user_prompt(metrics, page_text)

    prompt_log = {
        "system_prompt": SYSTEM_PROMPT,
        "user_prompt": user_prompt,
        "model": GROQ_MODEL,
        "max_tokens": GROQ_MAX_TOKENS,
        "temperature": GROQ_TEMPERATURE,
        "structured_input_summary": {
            "url": metrics.url,
            "word_count": metrics.word_count,
            "headings": {"h1": metrics.h1_count, "h2": metrics.h2_count, "h3": metrics.h3_count},
            "cta_count": metrics.cta_count,
            "links": {"internal": metrics.internal_links, "external": metrics.external_links},
            "images": {"total": metrics.image_count, "missing_alt": metrics.images_missing_alt},
            "meta_title_chars": len(metrics.meta_title) if metrics.meta_title else 0,
            "meta_desc_chars": len(metrics.meta_description) if metrics.meta_description else 0,
        },
        "timestamp": datetime.utcnow().isoformat(),
    }

    completion = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=GROQ_MAX_TOKENS,
        temperature=GROQ_TEMPERATURE,
    )

    raw_output = completion.choices[0].message.content
    prompt_log["raw_model_output"] = raw_output
    prompt_log["usage"] = {
        "prompt_tokens": completion.usage.prompt_tokens,
        "completion_tokens": completion.usage.completion_tokens,
        "total_tokens": completion.usage.total_tokens,
    }

    # Parse JSON (strip any accidental markdown fences)
    clean = raw_output.strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```[a-z]*\n?", "", clean)
        clean = re.sub(r"\n?```$", "", clean)

    parsed = json.loads(clean)
    return parsed, prompt_log


# ─────────────────────────────────────────────
# API Endpoints
# ─────────────────────────────────────────────

@app.post("/audit", response_model=AuditResult)
async def run_audit(req: AuditRequest):
    url = req.url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    logger.info(f"Auditing: {url}")

    # Step 1: Scrape
    _, metrics, page_text = scrape_page(url)

    # Step 2: AI analysis
    try:
        ai_result, prompt_log = call_llm(metrics, page_text)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=502,
            detail=f"AI returned invalid JSON: {e}"
        )
    except Exception as e:
        logger.exception("Unexpected error during AI analysis")
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {type(e).__name__}: {e}"
        )

    # Step 3: Assemble response
    insights = [AIInsight(**ins) for ins in ai_result["insights"]]
    recommendations = [Recommendation(**rec) for rec in ai_result["recommendations"]]

    return AuditResult(
        metrics=metrics,
        insights=insights,
        recommendations=recommendations,
        overall_score=ai_result["overall_score"],
        prompt_log=prompt_log,
        audit_timestamp=datetime.utcnow().isoformat(),
    )


@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


# Serve frontend
frontend_dir = os.path.join(os.path.dirname(__file__), "../frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(os.path.join(frontend_dir, "index.html"))
