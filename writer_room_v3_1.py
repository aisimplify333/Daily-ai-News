# -*- coding: utf-8 -*-
"""
The AI Edge v3.2 — Hard Debate Human Program writer room.

Paste this entire file as: writer_room_v3_1.py

This replaces the lesson-first v3.1 creative layer with the format the data points to:
- Hard AI debate first
- Education hidden inside the argument
- Obvious listener questions
- Data receipts
- Jamie as the human reactor / translator
- Rufus as dry British counterpunch
- Alex as pressure-question host
- Top AI events from the day, not forced sector coverage

It does not replace main.py.
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import os
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

SHOW_TITLE = os.getenv("PODCAST_SHOW_TITLE", "The AI Edge").strip() or "The AI Edge"
SHOW_DESCRIPTION = os.getenv(
    "PODCAST_SHOW_DESCRIPTION",
    "A hard-debate daily AI podcast where Alex, Jamie, and Rufus argue through the AI story that changes who gets power, who gets blamed, and what matters tomorrow.",
).strip()

# Keep env names stable so the existing workflow does not need rewiring.
STORY_BOARD_MODEL = os.getenv("STORY_BOARD_MODEL", "gemini-3.1-flash-lite").strip()
STORY_BOARD_FALLBACK_MODEL = os.getenv("STORY_BOARD_FALLBACK_MODEL", "gemini-3-flash-preview").strip()
SCENE_WRITER_MODEL = os.getenv("SCENE_WRITER_MODEL", "claude-sonnet-4-6").strip()
SCENE_WRITER_FALLBACK_MODEL = os.getenv("SCENE_WRITER_FALLBACK_MODEL", "claude-opus-4-7").strip()
PUNCHUP_MODEL = os.getenv("PUNCHUP_MODEL", "grok-4.3").strip()
RESCUE_MODEL = os.getenv("RESCUE_MODEL", "gpt-5.5").strip()
RESCUE_FALLBACK_MODEL = os.getenv("RESCUE_FALLBACK_MODEL", "gpt-5.4-mini").strip()
OPENAI_CHEAP_MODEL = os.getenv("OPENAI_CHEAP_MODEL", "gpt-5.4-mini").strip()

PRE_TTS_MIN_SCORE = int(os.getenv("PRE_TTS_MIN_SCORE", "84"))
ENABLE_GROK_PUNCHUP = os.getenv("ENABLE_GROK_PUNCHUP", "true").strip().lower() in ("1", "true", "yes")
ENABLE_OPENAI_RESCUE = os.getenv("ENABLE_OPENAI_RESCUE", "true").strip().lower() in ("1", "true", "yes")
HARD_FAIL_PRE_TTS = os.getenv("HARD_FAIL_PRE_TTS", "false").strip().lower() in ("1", "true", "yes")

SIGNAL_ROOM_RE = re.compile(r"\b(?:AI\s+Signal\s+Room|Signal\s+Room)\b", re.IGNORECASE)
SPEAKER_RE = re.compile(r"^(ALEX|JAMIE|RUFUS)\s*:\s*(.+)$", re.IGNORECASE)
NUMERIC_RE = re.compile(r"(?:\$|€|£)\s?\d[\d,.]*(?:\s?(?:million|billion|trillion|m|b))?|\b\d+(?:\.\d+)?%\b|\b\d[\d,]*\b|\bQ[1-4]\b", re.IGNORECASE)
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)

MAJOR_AI_ACTORS = [
    "OpenAI", "Anthropic", "Google", "Gemini", "DeepMind", "Microsoft", "NVIDIA", "Meta",
    "Apple", "Amazon", "AWS", "xAI", "Mistral", "Perplexity", "Tesla", "Oracle", "Salesforce",
    "Adobe", "GitHub", "Cursor", "Databricks", "Snowflake", "Cohere", "Stability", "Hugging Face",
    "White House", "EU", "China", "FTC", "DOJ", "FDA", "SEC", "Gates Foundation",
]

TOP_EVENT_TERMS = {
    "launch": 18, "launches": 18, "unveils": 18, "releases": 14, "announces": 10,
    "lawsuit": 24, "sues": 22, "court": 18, "judge": 18, "antitrust": 22,
    "regulation": 22, "regulator": 22, "ban": 20, "banned": 20, "policy": 16,
    "funding": 16, "pledge": 16, "investment": 16, "acquisition": 20, "deal": 16,
    "security": 24, "cybersecurity": 24, "breach": 24, "hack": 24, "vulnerability": 24,
    "health": 20, "healthcare": 22, "clinical": 22, "doctor": 18, "patient": 18,
    "agent": 18, "agents": 18, "coding agent": 22, "model": 12, "benchmark": 12,
    "chip": 18, "gpu": 18, "compute": 18, "data center": 18, "datacenter": 18,
    "job": 18, "jobs": 18, "layoff": 22, "school": 16, "student": 16,
    "privacy": 22, "scam": 20, "fraud": 20, "deepfake": 18, "copyright": 18,
    "military": 18, "defense": 18, "election": 20, "government": 16,
}

LOW_VALUE_PATTERNS = [
    r"\b\d+\s+best\b", r"\bbest\s+.+alternatives\b", r"\balternatives\b", r"\bhow to\b",
    r"\btips\b", r"\bguide\b", r"\bwebinar\b", r"\bsponsored\b", r"\bguest post\b",
    r"\bwhat is\b", r"\bexplained\b", r"\breview\b", r"\broundup\b",
]

AUTHORITY_PUBLISHER_LIFT = {
    "reuters": 22, "associated press": 20, "ap news": 20, "bloomberg": 22,
    "financial times": 22, "ft": 20, "wall street journal": 22, "wsj": 22,
    "new york times": 18, "washington post": 18, "the verge": 14, "wired": 16,
    "techcrunch": 14, "semianalysis": 18, "the information": 20, "axios": 16,
    "cnbc": 14, "fortune": 14, "forbes": 10, "geekwire": 10,
    "microsoft": 8, "google": 8, "anthropic": 8, "openai": 8, "nvidia": 8,
}


def _safe_print(g: Dict[str, Any], msg: str) -> None:
    fn = g.get("_safe_print")
    if callable(fn):
        fn(msg)
    else:
        print(msg, flush=True)


def _headline(story: Dict[str, Any]) -> str:
    return str(story.get("headline") or story.get("title") or story.get("name") or "").strip()


def _summary(story: Dict[str, Any]) -> str:
    return str(story.get("summary") or story.get("why_shocking") or story.get("description") or story.get("rss_summary") or "").strip()


def _publisher(story: Dict[str, Any]) -> str:
    return str(story.get("publisher") or story.get("source") or "").strip()


def _url(story: Dict[str, Any]) -> str:
    return str(story.get("source_url") or story.get("link") or story.get("url") or "").strip()


def _blob(story: Dict[str, Any]) -> str:
    return f"{_headline(story)} {_summary(story)} {_publisher(story)} {_url(story)}".lower()


def _normalize_text(s: str) -> str:
    s = URL_RE.sub(" ", s or "")
    s = re.sub(r"[^a-z0-9\s]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def _identity_key(story: Dict[str, Any]) -> str:
    u = _url(story).lower().strip()
    if u:
        return re.sub(r"[?#].*$", "", u)
    words = [w for w in _normalize_text(_headline(story)).split() if w not in {"the", "a", "an", "and", "or", "to", "of", "in", "for", "on", "with", "ai"}]
    return " ".join(words[:12])


def _family_key(story: Dict[str, Any]) -> str:
    words = [w for w in _normalize_text(_headline(story)).split() if w not in {"the", "a", "an", "and", "or", "to", "of", "in", "for", "on", "with", "ai", "new", "today"}]
    return " ".join(words[:9])


def _token_overlap(a: str, b: str) -> float:
    sa = set(a.split())
    sb = set(b.split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / max(1, min(len(sa), len(sb)))


def _published_age_hours(story: Dict[str, Any]) -> Optional[float]:
    raw = str(story.get("published") or story.get("published_at") or story.get("date") or "").strip()
    if not raw:
        return None
    try:
        cleaned = raw.replace("Z", "+00:00")
        dt = _dt.datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_dt.timezone.utc)
        return max(0.0, (_dt.datetime.now(_dt.timezone.utc) - dt.astimezone(_dt.timezone.utc)).total_seconds() / 3600.0)
    except Exception:
        return None


def _number_count(story: Dict[str, Any]) -> int:
    text = f"{_headline(story)} {_summary(story)} " + " ".join([str(x) for x in story.get("data_points") or []])
    return len(NUMERIC_RE.findall(text))


def _major_actor_count(story: Dict[str, Any]) -> int:
    text = _blob(story)
    return sum(1 for actor in MAJOR_AI_ACTORS if actor.lower() in text)


def _authority_lift(story: Dict[str, Any]) -> float:
    pub = _publisher(story).lower()
    url = _url(story).lower()
    text = f"{pub} {url}"
    lift = 0.0
    for key, pts in AUTHORITY_PUBLISHER_LIFT.items():
        if key in text:
            lift = max(lift, float(pts))
    if ".gov" in url or ".edu" in url:
        lift = max(lift, 22.0)
    return lift


def _top_event_score(story: Dict[str, Any]) -> float:
    text = _blob(story)
    score = 0.0

    # Preserve any existing growth score, but do not let sector quotas dominate.
    try:
        score += min(35.0, float(story.get("growth_score") or 0.0) * 0.35)
    except Exception:
        pass
    bd = story.get("score_breakdown") if isinstance(story.get("score_breakdown"), dict) else {}
    for k, weight in [("ai_heat", 0.20), ("authority", 0.16), ("forward_consequence", 0.20), ("numeric_density", 0.12), ("clipability", 0.10), ("listener_tension", 0.18), ("universal_relevance", 0.12)]:
        try:
            score += float(bd.get(k) or 0.0) * weight
        except Exception:
            pass

    for term, pts in TOP_EVENT_TERMS.items():
        if term in text:
            score += pts

    score += min(30.0, _major_actor_count(story) * 8.0)
    score += min(24.0, _number_count(story) * 5.0)
    score += _authority_lift(story)

    age = _published_age_hours(story)
    if age is not None:
        if age <= 8:
            score += 18
        elif age <= 24:
            score += 12
        elif age <= 48:
            score += 6
        elif age > 96:
            score -= 20

    h = _headline(story).lower()
    for pat in LOW_VALUE_PATTERNS:
        if re.search(pat, h, flags=re.IGNORECASE):
            score -= 45

    # Routine listicles and SEO posts are not top news events.
    if "google news" in text and len(h) < 20:
        score -= 8
    if not any(actor.lower() in text for actor in MAJOR_AI_ACTORS) and not any(term in text for term in ["ai", "artificial intelligence", "agent", "model"]):
        score -= 40

    return round(max(0.0, score), 2)


def _select_top_ai_events(intel_items: List[Dict[str, Any]], n: int = 5) -> List[Dict[str, Any]]:
    ranked: List[Tuple[float, Dict[str, Any]]] = []
    for raw in intel_items or []:
        if not isinstance(raw, dict):
            continue
        h = _headline(raw)
        if not h:
            continue
        item = dict(raw)
        item["top_event_score"] = _top_event_score(item)
        ranked.append((float(item["top_event_score"]), item))

    ranked.sort(key=lambda x: x[0], reverse=True)

    selected: List[Dict[str, Any]] = []
    used_keys: set[str] = set()
    families: List[str] = []

    for score, item in ranked:
        if score < float(os.getenv("TOP_EVENT_MIN_SCORE", "38")) and len(selected) >= max(3, n - 1):
            continue
        key = _identity_key(item)
        fam = _family_key(item)
        if key and key in used_keys:
            continue
        if fam and any(_token_overlap(fam, old) >= 0.72 for old in families):
            continue
        item["story_role"] = "top_ai_event"
        item["story_tier"] = "primary" if len(selected) < 3 else "supporting"
        item["bucket"] = item.get("bucket") or "top_ai_event"
        selected.append(item)
        if key:
            used_keys.add(key)
        if fam:
            families.append(fam)
        if len(selected) >= n:
            break

    if len(selected) < n:
        for _, item in ranked:
            key = _identity_key(item)
            if key and key in used_keys:
                continue
            item = dict(item)
            item["story_role"] = "top_ai_event"
            item["story_tier"] = "supporting"
            selected.append(item)
            if key:
                used_keys.add(key)
            if len(selected) >= n:
                break

    return selected[:n]


def _openai_text(g: Dict[str, Any], prompt: str, model: str, max_tokens: int = 6200, temperature: float = 0.70) -> str:
    client = g.get("openai_client")
    if not client:
        return ""
    try:
        if hasattr(client, "responses"):
            resp = client.responses.create(model=model, input=prompt, max_output_tokens=max_tokens)
            text = getattr(resp, "output_text", None)
            if text:
                return str(text).strip()
        resp = client.chat.completions.create(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return str(resp.choices[0].message.content or "").strip()
    except Exception as e:
        _safe_print(g, f"    ⚠️ OpenAI call failed on {model}: {e}")
        return ""


def _gemini_text(g: Dict[str, Any], prompt: str, model: str, max_tokens: int = 2400) -> str:
    client = g.get("gemini_client")
    types = g.get("genai_types")
    if not client:
        return ""
    try:
        if types:
            config = types.GenerateContentConfig(temperature=0.35, max_output_tokens=max_tokens)
            resp = client.models.generate_content(model=model, contents=prompt, config=config)
        else:
            resp = client.models.generate_content(model=model, contents=prompt)
        return str(getattr(resp, "text", "") or "").strip()
    except Exception as e:
        _safe_print(g, f"    ⚠️ Gemini call failed on {model}: {e}")
        return ""


def _anthropic_text(g: Dict[str, Any], prompt: str, model: str, max_tokens: int = 7000) -> str:
    api_key = (os.getenv("ANTHROPIC_API_KEY", "") or os.getenv("CLAUDE_API_KEY", "")).strip()
    if not api_key:
        return ""
    try:
        import anthropic  # type: ignore
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=0.75,
            system=(
                "You are the head writer/showrunner for a premium daily AI debate podcast. "
                "Write only clean spoken dialogue. Make it human, sharp, factual, and useful."
            ),
            messages=[{"role": "user", "content": prompt}],
        )
        return "\n".join(str(getattr(block, "text", "")) for block in getattr(resp, "content", []) if getattr(block, "text", "")).strip()
    except Exception as e:
        _safe_print(g, f"    ⚠️ Anthropic call failed on {model}: {e}")
        return ""


def _xai_text(g: Dict[str, Any], prompt: str, model: str, max_tokens: int = 6200) -> str:
    api_key = (os.getenv("XAI_API_KEY", "") or os.getenv("GROK_XAI_API_KEY", "") or os.getenv("GROK_API_KEY", "")).strip()
    if not api_key:
        return ""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=os.getenv("XAI_BASE_URL", "https://api.x.ai/v1"))
        resp = client.chat.completions.create(
            model=model,
            temperature=0.65,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": "You are a sharp panel-podcast punch-up editor. Preserve facts. Add friction, wit, and memorable lines."},
                {"role": "user", "content": prompt},
            ],
        )
        return str(resp.choices[0].message.content or "").strip()
    except Exception as e:
        _safe_print(g, f"    ⚠️ xAI/Grok call failed on {model}: {e}")
        return ""


def _extract_json(text: str, default: Any) -> Any:
    if not text:
        return default
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    m = re.search(r"(\{.*\}|\[.*\])", cleaned, flags=re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            return default
    return default


def _story_lines(stories: List[Dict[str, Any]]) -> str:
    rows = []
    for i, s in enumerate(stories[:8], start=1):
        rows.append(
            f"{i}. {_headline(s)}\n"
            f"   Publisher: {_publisher(s) or 'unknown'}\n"
            f"   Top-event score: {s.get('top_event_score', '')}\n"
            f"   Summary: {_summary(s)[:900]}\n"
            f"   Data points: {', '.join([str(x) for x in (s.get('data_points') or [])[:5]])}\n"
            f"   URL: {_url(s)}"
        )
    return "\n".join(rows)


def _lead_blob(stories: List[Dict[str, Any]]) -> str:
    return _blob(stories[0]) if stories else ""


def _central_fight(stories: List[Dict[str, Any]]) -> str:
    b = _lead_blob(stories)
    if any(x in b for x in ["health", "clinical", "doctor", "patient", "hospital", "gates foundation"]):
        return "If AI moves into care, who gets blamed when the answer is wrong?"
    if any(x in b for x in ["security", "cyber", "breach", "vulnerability", "benchmark"]):
        return "Are AI agents becoming productivity tools, or a new attack surface with a nicer logo?"
    if any(x in b for x in ["coding", "developer", "codebase", "github"]):
        return "If AI can code this fast, what is still a moat — skill, taste, security, or distribution?"
    if any(x in b for x in ["lawsuit", "copyright", "court", "antitrust"]):
        return "Did AI just hit the part of the market where the lawyers set the roadmap?"
    if any(x in b for x in ["chip", "gpu", "nvidia", "compute", "data center", "datacenter"]):
        return "Is the AI race really a model race, or a power bill with better PR?"
    if any(x in b for x in ["china", "export", "white house", "government", "regulation"]):
        return "Who controls the AI race when policy, compute, and money collide?"
    if any(x in b for x in ["agent", "agents", "workflow", "copilot"]):
        return "If your AI agent can act for you, who decided where its authority stops?"
    return "What changed in AI today, who gained power, and who is exposed tomorrow?"


def _hard_title(stories: List[Dict[str, Any]], date_str: str) -> str:
    b = _lead_blob(stories)
    entity = "AI"
    for actor in MAJOR_AI_ACTORS:
        if actor.lower() in b:
            entity = actor
            break
    if any(x in b for x in ["health", "clinical", "doctor", "patient", "hospital", "gates foundation"]):
        return "AI Is Entering Healthcare. Who Gets Blamed When It Is Wrong?"
    if any(x in b for x in ["security", "cyber", "breach", "vulnerability"]):
        return "AI Agents Are Becoming a Security Problem"
    if any(x in b for x in ["coding", "developer", "codebase", "github"]):
        return "AI Coding Agents Just Put the Moat on Trial"
    if any(x in b for x in ["benchmark", "mythos", "cybersecurity"]):
        return "The AI Benchmark Fight Is Really About Trust"
    if any(x in b for x in ["lawsuit", "copyright", "court", "antitrust"]):
        return "AI Just Ran Into the One Thing It Cannot Prompt Away"
    if any(x in b for x in ["china", "export", "white house", "government", "regulation"]):
        return "The AI Race Has a Control Problem"
    if any(x in b for x in ["agent", "agents", "workflow", "copilot"]):
        return "AI Agents Are Getting More Power. Who Is Watching?"
    return f"{entity}'s AI Move Has a Bigger Fight Behind It"


def _board(g: Dict[str, Any], stories: List[Dict[str, Any]], date_str: str) -> Dict[str, Any]:
    default = {
        "format": "hard_debate_hybrid",
        "published_title": _hard_title(stories, date_str),
        "central_fight": _central_fight(stories),
        "opening_question": _central_fight(stories),
        "listener_promise": "By the end, listeners will know what happened, why it matters, who wins, who is exposed, and what to watch tomorrow.",
        "who_wins": "the organizations that control distribution, permissions, data, or trust",
        "who_is_exposed": "operators, users, doctors, developers, companies, or families who inherit the risk without seeing the handoff",
        "normal_person_payoff": "AI matters when it touches work, money, health, privacy, family, safety, or trust — not when a press release says it is impressive.",
        "mandatory_receipts": ["Use the top-event score story facts", "Use at least three concrete numbers or named institutions", "Explain why each number changes incentives"],
        "forwardable_targets": [
            "The demo is not the story. The blame chain is the story.",
            "If nobody owns the outcome, the AI is not ready for the workflow.",
            "The moat is not the model. It is who controls what the AI is allowed to do.",
            "Every agent that can act is also a new thing that can break.",
        ],
    }
    prompt = f"""
Return STRICT JSON only. Build a hard-debate editorial board for today's episode of {SHOW_TITLE}.

Do not use Signal Room language. Do not create an academic lesson title.
The show is a hard human debate where education happens inside the argument.

Stories:
{_story_lines(stories)}

Return this JSON shape:
{{
  "published_title": "urgent listener-facing title, not 'Today's AI Lesson'",
  "central_fight": "the main obvious argument",
  "opening_question": "the first question Alex should ask",
  "listener_promise": "what the audience will know by the end",
  "who_wins": "...",
  "who_is_exposed": "...",
  "normal_person_payoff": "...",
  "mandatory_receipts": ["...", "...", "..."],
  "forwardable_targets": ["...", "...", "...", "..."]
}}
"""
    for model in [STORY_BOARD_MODEL, STORY_BOARD_FALLBACK_MODEL]:
        txt = _gemini_text(g, prompt, model=model, max_tokens=2200)
        parsed = _extract_json(txt, None)
        if isinstance(parsed, dict):
            default.update({k: v for k, v in parsed.items() if v})
            break
    if str(default.get("published_title", "")).lower().startswith("today"):
        default["published_title"] = _hard_title(stories, date_str)
    return default


def _writer_prompt(stories: List[Dict[str, Any]], sponsors: List[Dict[str, Any]], date_str: str, board: Dict[str, Any]) -> str:
    sponsor = sponsors[0] if sponsors else {}
    sponsor_cta = sponsor.get("cta") or "Subscribe to The Ledger at T-H-E-L-E-D-G-R dot I-O."
    return f"""
Write the complete spoken script for {SHOW_TITLE} on {date_str}.

CREATIVE MANDATE:
This is NOT an AI lesson show. This is a hard human debate program where the audience learns because Alex, Jamie, and Rufus argue through the obvious stakes.
Make it data-centric, tense, warm, funny, and useful.
The debate must hit hard, but the answers must be obvious enough for a normal listener to follow.

PUBLIC TITLE TO EARN:
{board.get('published_title')}

CENTRAL FIGHT:
{board.get('central_fight')}

OPENING QUESTION:
{board.get('opening_question')}

WHO WINS:
{board.get('who_wins')}

WHO IS EXPOSED:
{board.get('who_is_exposed')}

NORMAL PERSON PAYOFF:
{board.get('normal_person_payoff')}

FORWARDABLE TARGETS:
{json.dumps(board.get('forwardable_targets') or [], ensure_ascii=False, indent=2)}

MANDATORY RECEIPTS:
{json.dumps(board.get('mandatory_receipts') or [], ensure_ascii=False, indent=2)}

TODAY'S TOP AI EVENTS — selected by event importance, not sector quotas:
{_story_lines(stories)}

SPONSOR:
TheLEDGR. Spoken name is "The Ledger". Spoken URL is T-H-E-L-E-D-G-R dot I-O.
Use one short early CTA after [MUSIC], and one useful The Ledger Readout near the end.
Raw CTA material: {sponsor_cta}

CAST:
ALEX — Host. Curious, blunt, high-agency. Asks the obvious question smart people avoid. Keeps the room moving.
JAMIE — Heavy reactor. Warm, sharp, funny, human. Pushes back on the men, laughs when something is absurd, translates jargon instantly.
RUFUS — British dry wit. Data, finance, regulation, and blame-chain lens. Compact, surgical, quietly brutal.

NON-NEGOTIABLES:
- Five segments, 20–26 minute target.
- Dialogue only with exact labels ALEX:, JAMIE:, RUFUS: plus segment headers and one [MUSIC].
- Segment 1 starts with a cold open argument, not a summary.
- Put exactly one [MUSIC] marker after the cold open.
- After [MUSIC], Alex gives a short The Ledger CTA.
- Every story must become an argument: who wins, who loses, who is exposed, who gets blamed, what changes tomorrow.
- Include at least 6 concrete receipts: numbers, dollar amounts, dates, named institutions, rankings, benchmark results, or explicit counts.
- Explain each important number in normal-person terms.
- At least 8 friction beats: wait, hold on, no, come on, pushback, correction, disagreement, skeptical question.
- At least 4 Rufus dry British lines, but no obscure British-only jokes that confuse the listener.
- At least 5 Jamie heavy-reactor moments: amused disbelief, concern, translation, challenge, or laughter.
- At least 5 Alex pressure questions.
- No polite "Exactly, Alex" filler.
- No "Today’s AI Lesson" title/framing.
- No Signal Room language.
- No listicle/digest energy.
- No monologues: normal spoken turns should be 8–38 words; hard max 55.

STRUCTURE:
### SEGMENT 1 — Cold Open: The Fight
Open with Alex asking the obvious hard question. Jamie reacts. Rufus undercuts. Then [MUSIC]. Then short The Ledger CTA.

### SEGMENT 2 — Receipts: What Actually Happened
Hard facts on the top event. Alex challenges. Jamie translates. Rufus follows money/blame/permission.

### SEGMENT 3 — The Argument: Who Wins, Who Is Exposed
The hosts disagree. No fake consensus. Make the tradeoff obvious.

### SEGMENT 4 — The Pattern Across the Other Top AI Events
Bring in the other top AI events only if they prove or challenge the main argument. Fast, sharp, data-first.

### SEGMENT 5 — The Ledger Readout + Final Button
Answer exactly: what changed, who wins, who is exposed, what to watch tomorrow. End with a sticky unresolved question.

OUTPUT ONLY THE SCRIPT.
""".strip()


def _clean_script(text: str) -> str:
    text = text or ""
    text = re.sub(r"^```(?:text|markdown)?\s*", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    text = SIGNAL_ROOM_RE.sub(SHOW_TITLE, text)
    lines: List[str] = []
    music_seen = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.upper() == "[MUSIC]":
            if not music_seen:
                lines.append("[MUSIC]")
                music_seen = True
            continue
        if re.match(r"^(###\s*)?SEGMENT\s+[1-5]\b", line, flags=re.IGNORECASE):
            if not line.startswith("###"):
                line = "### " + line
            lines.append(line)
            continue
        m = SPEAKER_RE.match(line)
        if m:
            spk = m.group(1).upper()
            spoken = m.group(2).strip()
            spoken = SIGNAL_ROOM_RE.sub(SHOW_TITLE, spoken)
            # Spoken brand correction: TheLEDGR should not be pronounced as a word.
            spoken = re.sub(r"\bTheLEDGR\b", "The Ledger", spoken)
            spoken = re.sub(r"\bTHELEDGR\b", "The Ledger", spoken)
            spoken = re.sub(r"\[(?:leans in|stage direction|smiles|smirks silently)[^\]]*\]", "", spoken, flags=re.IGNORECASE).strip()
            if spoken:
                lines.append(f"{spk}: {spoken}")
    cleaned = "\n".join(lines).strip()
    if "[MUSIC]" not in cleaned:
        # Insert after first three spoken lines if writer forgot it.
        out: List[str] = []
        spoken = 0
        inserted = False
        for ln in cleaned.splitlines():
            out.append(ln)
            if SPEAKER_RE.match(ln):
                spoken += 1
            if not inserted and spoken >= 3:
                out.append("[MUSIC]")
                inserted = True
        cleaned = "\n".join(out)
    return cleaned


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text or ""))


def _quality_report(script: str, stories: List[Dict[str, Any]], board: Dict[str, Any]) -> Dict[str, Any]:
    full = script or ""
    low = full.lower()
    lines = [ln for ln in full.splitlines() if SPEAKER_RE.match(ln)]
    first_18 = "\n".join(lines[:18]).lower()
    title = str(board.get("published_title") or "")

    alex_questions = len(re.findall(r"^ALEX:.*\?", full, flags=re.IGNORECASE | re.MULTILINE))
    jamie_reactions = len(re.findall(r"^JAMIE:.*\b(wait|hold on|come on|that scares|that is|the simple version|plain english|what that means|I mean|laugh|honestly|normal person|people|patient|worker|family|privacy|money|job)\b", full, flags=re.IGNORECASE | re.MULTILINE))
    rufus_dry = len(re.findall(r"^RUFUS:.*\b(lovely|rather|quite|brilliant|marvellous|splendid|bleak|lawsuit|liability|invoice|permission|regulator|terms of service|nothing says|of course|convenient)\b", full, flags=re.IGNORECASE | re.MULTILINE))
    friction = len(re.findall(r"\b(wait|hold on|hang on|come on|no,|not quite|push back|that sounds|is this|who gets|who is|so you are telling me|let me stop you|I disagree)\b", low))
    receipts = len(NUMERIC_RE.findall(full)) + sum(1 for actor in MAJOR_AI_ACTORS if actor.lower() in low)
    ledger = "the ledger" in low and "t-h-e-l-e-d-g-r dot i-o" in low
    who_wins = "who wins" in low or "wins" in low
    who_exposed = "who is exposed" in low or "exposed" in low or "gets blamed" in low
    top_events = sum(1 for s in stories[:5] if _headline(s).lower()[:30] in low or any(x.lower() in low for x in _headline(s).split()[:3] if len(x) > 4))

    overlong = 0
    max_turn = 0
    for ln in lines:
        m = SPEAKER_RE.match(ln)
        wc = _word_count(m.group(2) if m else ln)
        max_turn = max(max_turn, wc)
        if wc > 55:
            overlong += 1

    checks = {
        "no_signal_room": not SIGNAL_ROOM_RE.search(full),
        "not_lesson_first_title": not title.lower().startswith("today"),
        "first_90_has_hard_fight": any(x in first_18 for x in ["who gets", "who is", "blamed", "sued", "exposed", "watching", "breaks", "money", "doctor", "job", "privacy"]),
        "alex_pressure_questions": alex_questions >= 5,
        "jamie_heavy_reactor": jamie_reactions >= 5,
        "rufus_dry_wit": rufus_dry >= 3,
        "real_friction": friction >= 8,
        "data_receipts": receipts >= 45,
        "top_events_not_sector_digest": top_events >= 3,
        "ledger_cta_complete": ledger,
        "readout_answers_wins": who_wins,
        "readout_answers_exposed": who_exposed,
        "no_monologue_bloat": overlong <= 12 and max_turn <= 72,
    }
    score = round(100 * sum(1 for v in checks.values() if v) / max(1, len(checks)))
    return {
        "version": "v3.2-hard-debate-human-program-top-events",
        "score": score,
        "target": PRE_TTS_MIN_SCORE,
        "pass": score >= PRE_TTS_MIN_SCORE,
        "checks": checks,
        "failed": [k for k, ok in checks.items() if not ok],
        "metrics": {
            "words": _word_count(full),
            "speaker_lines": len(lines),
            "alex_questions": alex_questions,
            "jamie_reactions": jamie_reactions,
            "rufus_dry_hits": rufus_dry,
            "friction_hits": friction,
            "receipt_hits": receipts,
            "top_event_mentions": top_events,
            "overlong_turns": overlong,
            "max_turn_words": max_turn,
            "title": title,
        },
    }


def _punchup_prompt(script: str, board: Dict[str, Any]) -> str:
    return f"""
Punch up this podcast script. Preserve facts and structure.
Add harder debate, Jamie reactions, Rufus dry wit, Alex pressure questions, clearer obvious stakes.
Do not add fake facts. Do not add Signal Room. Do not make it a lesson lecture.
Keep exact speaker labels and [MUSIC]. Return full script only.

Board:
{json.dumps(board, ensure_ascii=False, indent=2)}

Script:
{script}
""".strip()


def _rescue_prompt(script: str, report: Dict[str, Any], board: Dict[str, Any], stories: List[Dict[str, Any]]) -> str:
    return f"""
Repair this script before TTS. It failed checks:
{json.dumps(report.get('failed') or [], ensure_ascii=False)}

Make it a hard debate human program, not an AI lesson class.
Requirements:
- Open with the obvious hard question.
- More Jamie reactive wit and plain-English translation.
- More Rufus dry British undercuts.
- More Alex pressure questions.
- The Ledger CTA must include T-H-E-L-E-D-G-R dot I-O.
- The Ledger Readout must answer: what changed, who wins, who is exposed, what to watch tomorrow.
- Include the actual top AI events below. Do not switch back to sector coverage.
- Preserve facts, do not invent numbers.
- Return full script only.

Board:
{json.dumps(board, ensure_ascii=False, indent=2)}

Top events:
{_story_lines(stories)}

Script:
{script}
""".strip()


def _script_via_models(g: Dict[str, Any], prompt: str) -> str:
    for model in [SCENE_WRITER_MODEL, SCENE_WRITER_FALLBACK_MODEL]:
        txt = _anthropic_text(g, prompt, model=model, max_tokens=int(os.getenv("ANTHROPIC_SCRIPT_MAX_TOKENS", "7000")))
        if txt:
            _safe_print(g, f"    ✅ Hard-debate writer pass succeeded: {model}")
            return txt
    _safe_print(g, "    ⚠️ Anthropic unavailable; trying OpenAI writer fallback.")
    for model in [RESCUE_MODEL, RESCUE_FALLBACK_MODEL, OPENAI_CHEAP_MODEL, os.getenv("OPENAI_CHAT_MODEL", "gpt-4o")]:
        txt = _openai_text(g, prompt, model=model, max_tokens=7000, temperature=0.72)
        if txt:
            _safe_print(g, f"    ✅ OpenAI writer pass succeeded: {model}")
            return txt
    return ""


def _marketing_pack(stories: List[Dict[str, Any]], date_str: str, listen_url: str, board: Dict[str, Any], tracking: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    tracking = tracking or {}
    title = str(board.get("published_title") or _hard_title(stories, date_str))
    title = SIGNAL_ROOM_RE.sub(SHOW_TITLE, title)
    if title.lower().startswith("today"):
        title = _hard_title(stories, date_str)
    bullets = "\n".join([f"• {_headline(s)}" for s in stories[:5] if _headline(s)])
    listen = tracking.get("listen", listen_url)
    subscribe = "https://theledgr.io?utm_source=podcast&utm_medium=show_notes&utm_campaign=daily_ai_edge"
    hook = str(board.get("central_fight") or _central_fight(stories))
    desc = (
        f"{hook}\n\n"
        f"Alex, Jamie, and Rufus debate the top AI events of the day — not as a headline list, but as a fight over who wins, who is exposed, who gets blamed, and what changes tomorrow.\n\n"
        f"Top AI events covered:\n{bullets}\n\n"
        f"The Ledger Readout: what changed, who wins, who is exposed, and what to watch next.\n\n"
        f"Subscribe to TheLEDGR for decision-grade AI signal: {subscribe}"
    )
    return {
        "title": title,
        "yt_title": title,
        "youtube_title": title,
        "spotify_title": title,
        "hook": hook,
        "show_notes_hook": hook,
        "description": desc,
        "show_notes": desc,
        "yt_description": desc[:1500],
        "episode_blurb": "A hard human debate about the top AI events of the day: who wins, who is exposed, and what changes tomorrow.",
        "tomorrow_tease": "Tomorrow, the question is not which AI headline was loudest. It is which one quietly changed the rules.",
        "tweet1": f"{title}\n\n{hook}\n\nListen: {listen}",
        "tweet2": f"The headline is not the story. The fight underneath is.\n\nSubscribe to TheLEDGR: {subscribe}\n\n#AI #TheAIEdge #AINews",
        "seo_keywords": "AI news, artificial intelligence, AI agents, OpenAI, Anthropic, Google, Microsoft, NVIDIA, AI regulation, AI security",
        "hashtags": "#AI #TheAIEdge #AINews #AIAgents #AISecurity #HealthAI",
        "title_candidates_v3_2": board,
    }


def install_v3_1(g: Dict[str, Any]) -> None:
    _safe_print(g, ">> ✅ Installing The AI Edge v3.2 hard-debate/top-events writer room")

    rss = g.get("RSS_SETTINGS")
    if isinstance(rss, dict):
        rss["title"] = SHOW_TITLE
        rss["description"] = SHOW_DESCRIPTION

    original_pick_top_stories = g.get("pick_top_stories")
    original_generate_episode_script = g.get("generate_episode_script")
    original_generate_marketing_pack = g.get("generate_marketing_pack")
    original_build_episode_aircheck = g.get("build_episode_aircheck")

    last_board: Dict[str, Any] = {}
    last_selected: List[Dict[str, Any]] = []

    def pick_top_stories_v3_2(intel_items: List[Dict[str, Any]], n: int = 5, date_str: Optional[str] = None) -> List[Dict[str, Any]]:
        nonlocal last_selected
        selected = _select_top_ai_events(intel_items, n=n)
        last_selected = selected
        try:
            path = g.get("STORY_SLATE_DECISION_PATH") or Path("story_slate_decision.json")
            payload = {
                "version": "v3.2-top-ai-events-no-sector-quota",
                "date": date_str or _dt.date.today().isoformat(),
                "selection_rule": "rank all AI stories by event importance, authority, receipts, conflict, human stakes, recency; do not force sector coverage",
                "selected": [
                    {
                        "rank": i + 1,
                        "headline": _headline(s),
                        "publisher": _publisher(s),
                        "top_event_score": s.get("top_event_score"),
                        "bucket_original": s.get("bucket"),
                        "source_url": _url(s),
                    }
                    for i, s in enumerate(selected)
                ],
            }
            Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception:
            pass
        return selected

    def generate_episode_script_v3_2(stories: List[Dict[str, Any]], sponsors: List[Dict[str, Any]], date_str: str) -> str:
        nonlocal last_board
        _safe_print(g, " >> ✍️ WRITING EPISODE WITH V3.2 HARD-DEBATE HUMAN PROGRAM")
        board = _board(g, stories, date_str)
        last_board = board
        try:
            path = g.get("STORY_SLATE_DECISION_PATH") or Path("story_slate_decision.json")
            existing = {}
            try:
                existing = json.loads(Path(path).read_text(encoding="utf-8"))
            except Exception:
                existing = {}
            existing["v3_2_debate_board"] = board
            Path(path).write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception:
            pass

        prompt = _writer_prompt(stories, sponsors, date_str, board)
        script = _script_via_models(g, prompt)

        if not script and callable(original_generate_episode_script):
            _safe_print(g, "    ⚠️ Hard-debate writer unavailable; falling back to prior generator.")
            script = original_generate_episode_script(stories, sponsors, date_str)

        script = _clean_script(script)
        report = _quality_report(script, stories, board)

        if ENABLE_GROK_PUNCHUP:
            punched = _xai_text(g, _punchup_prompt(script, board), model=PUNCHUP_MODEL, max_tokens=6200)
            if punched:
                cand = _clean_script(punched)
                cand_report = _quality_report(cand, stories, board)
                if cand_report["score"] >= report["score"] - 4:
                    script, report = cand, cand_report
                    _safe_print(g, f"    ✅ Grok hard-debate punch-up applied. Score: {report['score']}")

        if ENABLE_OPENAI_RESCUE and report["score"] < PRE_TTS_MIN_SCORE:
            _safe_print(g, f"    ⚠️ Hard-debate score {report['score']} below {PRE_TTS_MIN_SCORE}. Running rescue before TTS.")
            for model in [RESCUE_MODEL, RESCUE_FALLBACK_MODEL, OPENAI_CHEAP_MODEL]:
                repaired = _openai_text(g, _rescue_prompt(script, report, board, stories), model=model, max_tokens=7000, temperature=0.65)
                if repaired:
                    cand = _clean_script(repaired)
                    cand_report = _quality_report(cand, stories, board)
                    if cand_report["score"] >= report["score"]:
                        script, report = cand, cand_report
                        _safe_print(g, f"    ✅ Hard-debate rescue applied. Score: {report['score']}")
                    break

        report = _quality_report(script, stories, board)
        try:
            path = g.get("SCRIPT_AIRCHECK_PATH") or Path("script_aircheck.json")
            Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception:
            pass

        if report["score"] < PRE_TTS_MIN_SCORE:
            msg = f"    ⚠️ V3.2 hard-debate score below target ({report['score']}/{PRE_TTS_MIN_SCORE}): {report['failed']}"
            _safe_print(g, msg)
            if HARD_FAIL_PRE_TTS:
                raise RuntimeError(msg)
        else:
            _safe_print(g, f"    ✅ V3.2 hard-debate script passed pre-TTS gate: {report['score']}/100")
        return script

    def generate_marketing_pack_v3_2(
        stories: List[Dict[str, Any]],
        episode_date: str,
        listen_url: str,
        tracking: Optional[Dict[str, Any]] = None,
        experiments: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        board = last_board or _board(g, stories, episode_date)
        pack = _marketing_pack(stories, episode_date, listen_url, board, tracking=tracking)
        if callable(original_generate_marketing_pack):
            # Do not inherit old lesson-first title. Only merge non-title utility fields.
            try:
                old = original_generate_marketing_pack(stories, episode_date, listen_url, tracking=tracking or {}, experiments=experiments or {})
                if isinstance(old, dict):
                    for k in ["tracking", "episode_url"]:
                        if k in old and k not in pack:
                            pack[k] = old[k]
            except Exception:
                pass
        return pack

    def build_episode_aircheck_v3_2(
        script: str,
        stories: List[Dict[str, Any]],
        pack: Optional[Dict[str, Any]] = None,
        sponsors: Optional[List[Dict[str, Any]]] = None,
        date_str: str = "",
    ) -> Dict[str, Any]:
        board = last_board or _board(g, stories, date_str or _dt.date.today().isoformat())
        report = _quality_report(script, stories, board)
        base: Dict[str, Any] = {}
        if callable(original_build_episode_aircheck):
            try:
                base = original_build_episode_aircheck(script, stories, pack or {}, sponsors or [], date_str)
            except Exception as e:
                base = {"base_aircheck_error": str(e)}
        merged = dict(base) if isinstance(base, dict) else {}
        merged["v3_2_hard_debate"] = report
        merged["score"] = report["score"]
        merged["target_band"] = "88-95"
        merged["pass"] = report["score"] >= PRE_TTS_MIN_SCORE
        merged["passed"] = merged["pass"]
        merged["failed"] = report.get("failed", [])
        return merged

    g["pick_top_stories"] = pick_top_stories_v3_2
    g["generate_episode_script"] = generate_episode_script_v3_2
    g["generate_marketing_pack"] = generate_marketing_pack_v3_2
    g["build_episode_aircheck"] = build_episode_aircheck_v3_2
    g["V3_1_WRITER_ROOM_INSTALLED"] = True
    g["V3_2_HARD_DEBATE_WRITER_ROOM_INSTALLED"] = True
