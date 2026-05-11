# writer_room_v3_1.py
# ============================================================
# THE AI EDGE v3.1 — EXPANSION-READY WRITER'S ROOM
# ============================================================
#
# CREATE this as a new file in the repo root:
#   writer_room_v3_1.py
#
# Purpose:
# - Keep the production spine that worked for a year.
# - Upgrade the show into a simple, useful, data-rich daily AI lesson.
# - Make every episode understandable to a normal person.
# - Prevent repeated titles/frames.
# - Build TheLEDGR subscriber conversion into the show.

from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Tuple

SHOW_TITLE = os.getenv("PODCAST_SHOW_TITLE", "The AI Edge").strip() or "The AI Edge"
SHOW_DESCRIPTION = os.getenv(
    "PODCAST_SHOW_DESCRIPTION",
    "The daily AI show that explains the one story today that could touch your work, money, health, privacy, family, school, safety, or trust.",
).strip()

WRITERS_ROOM_MODE = os.getenv("WRITERS_ROOM_MODE", "budget_plus").strip().lower()

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

SIGNAL_ROOM_RE = re.compile(r"\b(?:AI\s+Signal\s+Room|Signal\s+Room)\b", re.IGNORECASE)
SPEAKER_RE = re.compile(r"^(ALEX|JAMIE|RUFUS)\s*:\s*(.+)$", re.IGNORECASE)
NUMERIC_RE = re.compile(r"(\$|€|£)?\s?\d[\d,]*(?:\.\d+)?%?|\bQ[1-4]\b|\b20\d{2}\b", re.IGNORECASE)

LIFE_LANES_RE = re.compile(
    r"\b("
    r"mom|mother|dad|father|parent|kid|kids|son|daughter|student|school|teacher|"
    r"job|work|worker|boss|paycheck|money|bill|bills|mortgage|rent|shopping|bank|"
    r"doctor|health|hospital|medicine|patient|privacy|phone|family|home|safety|"
    r"trust|scam|government|law|lawsuit|insurance|car|creator|small business|"
    r"normal person|everyday|kitchen table|grandparent|retiree"
    r")\b",
    re.IGNORECASE,
)

JARGON_RE = re.compile(
    r"\b("
    r"transformer|embedding|vector|token|inference|fine-tuning|latency|"
    r"orchestration|agentic|benchmark|SWE-bench|MCP|API|RAG|"
    r"frontier model|parameters|multimodal|model weights|context window"
    r")\b",
    re.IGNORECASE,
)

PLAIN_ENGLISH_RE = re.compile(
    r"\b(simple version|plain english|what that means|in normal terms|"
    r"translation|think of it like|for a normal person|the everyday version|"
    r"put differently|in human terms)\b",
    re.IGNORECASE,
)

TITLE_STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "in", "for", "on", "with", "as", "is", "are",
    "ai", "news", "today", "tomorrow", "what", "why", "how", "when", "can", "will", "gets", "get",
    "episode", "alex", "jamie", "rufus",
}


def _safe_print(g: Dict[str, Any], msg: str) -> None:
    fn = g.get("_safe_print")
    if callable(fn):
        fn(msg)
    else:
        print(msg, flush=True)


def _readable_story_title(story: Dict[str, Any]) -> str:
    return str(story.get("title") or story.get("headline") or story.get("name") or "Untitled story").strip()


def _story_summary(story: Dict[str, Any]) -> str:
    return str(story.get("summary") or story.get("why_shocking") or story.get("description") or "").strip()


def _story_publisher(story: Dict[str, Any]) -> str:
    return str(story.get("publisher") or story.get("source") or "").strip()


def _story_url(story: Dict[str, Any]) -> str:
    return str(story.get("link") or story.get("source_url") or story.get("url") or "").strip()


def _compact_story(story: Dict[str, Any], idx: int) -> Dict[str, Any]:
    score = story.get("score_breakdown") if isinstance(story.get("score_breakdown"), dict) else {}
    return {
        "rank": idx,
        "title": _readable_story_title(story),
        "publisher": _story_publisher(story),
        "summary": _story_summary(story)[:900],
        "url": _story_url(story),
        "weighted_score": score.get("weighted"),
        "ai_heat": score.get("ai_heat"),
        "listener_tension": score.get("listener_tension"),
        "universal_relevance": score.get("universal_relevance"),
        "forward_consequence": score.get("forward_consequence"),
        "numeric_density": score.get("numeric_density"),
        "clipability": score.get("clipability"),
        "bucket": story.get("bucket") or "general",
    }


def _extract_json(text: str, default: Any) -> Any:
    if not text:
        return default
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
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


def _openai_text(g: Dict[str, Any], prompt: str, model: str, max_tokens: int = 2600) -> str:
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
            temperature=0.6,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return str(resp.choices[0].message.content or "").strip()
    except Exception as e:
        _safe_print(g, f"    ⚠️ OpenAI call failed on {model}: {e}")
        return ""


def _gemini_text(g: Dict[str, Any], prompt: str, model: str, max_tokens: int = 2200) -> str:
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


def _anthropic_text(g: Dict[str, Any], prompt: str, model: str, max_tokens: int = 6200) -> str:
    api_key = (os.getenv("ANTHROPIC_API_KEY", "") or os.getenv("CLAUDE_API_KEY", "")).strip()
    if not api_key:
        return ""
    try:
        import anthropic  # type: ignore

        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=0.72,
            system=(
                "You are the head writer/showrunner for a premium daily AI podcast. "
                "Write clean spoken dialogue only. No production explanations."
            ),
            messages=[{"role": "user", "content": prompt}],
        )
        return "\n".join(
            str(getattr(block, "text", ""))
            for block in getattr(resp, "content", [])
            if getattr(block, "text", "")
        ).strip()
    except Exception as e:
        _safe_print(g, f"    ⚠️ Anthropic call failed on {model}: {e}")
        return ""


def _xai_text(g: Dict[str, Any], prompt: str, model: str, max_tokens: int = 5200) -> str:
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
                {
                    "role": "system",
                    "content": (
                        "You are a sharp comedy/panel editor for a serious AI news podcast. "
                        "Improve only wit, friction, warmth, and memorable phrasing. Preserve facts."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )
        return str(resp.choices[0].message.content or "").strip()
    except Exception as e:
        _safe_print(g, f"    ⚠️ xAI/Grok call failed on {model}: {e}")
        return ""


def _call_json_planner(g: Dict[str, Any], prompt: str, default: Any) -> Any:
    for model in [STORY_BOARD_MODEL, STORY_BOARD_FALLBACK_MODEL]:
        text = _gemini_text(g, prompt, model=model, max_tokens=2400)
        parsed = _extract_json(text, None)
        if parsed:
            return parsed
    text = _openai_text(g, prompt, model=OPENAI_CHEAP_MODEL, max_tokens=2200)
    return _extract_json(text, default)


def _norm_title(text: str) -> str:
    text = re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())
    return re.sub(r"\s+", " ", text).strip()


def _title_tokens(text: str) -> set[str]:
    return {t for t in _norm_title(text).split() if len(t) > 2 and t not in TITLE_STOPWORDS}


def _title_similarity(a: str, b: str) -> float:
    sa, sb = _title_tokens(a), _title_tokens(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / max(1, len(sa | sb))


def _recent_feed_titles(g: Dict[str, Any], limit: int = 14) -> List[str]:
    path = g.get("FEED_XML_PATH") or Path("feed.xml")
    try:
        root = ET.fromstring(Path(path).read_text(encoding="utf-8", errors="ignore"))
        titles: List[str] = []
        for item in root.findall(".//item"):
            t = item.findtext("title") or ""
            if t.strip():
                titles.append(t.strip())
            if len(titles) >= limit:
                break
        return titles
    except Exception:
        return []


def _is_repeat_title(candidate: str, recent_titles: List[str]) -> bool:
    c = _norm_title(candidate)
    if not c:
        return True
    for old in recent_titles:
        if c == _norm_title(old):
            return True
        if _title_similarity(candidate, old) >= 0.82:
            return True
    return False


def _story_blob(stories: List[Dict[str, Any]]) -> str:
    return " ".join((_readable_story_title(s) + " " + _story_summary(s)) for s in stories[:5]).lower()


def _entity_from_stories(stories: List[Dict[str, Any]]) -> str:
    blob = _story_blob(stories)
    for ent in ["OpenAI", "Google", "Anthropic", "NVIDIA", "Microsoft", "Meta", "Apple", "Amazon", "xAI", "China"]:
        if ent.lower() in blob:
            return ent
    return "AI"


def _stakes_from_stories(stories: List[Dict[str, Any]]) -> str:
    blob = _story_blob(stories)
    if "health" in blob or "doctor" in blob or "diagnosis" in blob:
        return "Who Gets Sued?"
    if "agent" in blob or "permission" in blob:
        return "Who Is Watching?"
    if "china" in blob or "export" in blob:
        return "Who Controls the Race?"
    if "compute" in blob or "gpu" in blob or "data center" in blob:
        return "Who Pays for It?"
    if "code" in blob or "developer" in blob or "github" in blob:
        return "What Is the Moat?"
    if "security" in blob or "privacy" in blob:
        return "What Breaks First?"
    if "school" in blob or "student" in blob or "kids" in blob:
        return "What Do Families Need to Know?"
    if "bank" in blob or "shopping" in blob or "money" in blob:
        return "Who Protects Your Money?"
    return "What Changes Now?"


def _life_lane_from_stories(stories: List[Dict[str, Any]]) -> str:
    blob = _story_blob(stories)
    if any(x in blob for x in ["doctor", "health", "hospital", "patient", "medicine"]):
        return "health"
    if any(x in blob for x in ["job", "work", "boss", "employee", "office"]):
        return "work"
    if any(x in blob for x in ["school", "student", "teacher", "kids", "children"]):
        return "school and family"
    if any(x in blob for x in ["bank", "money", "shopping", "fraud", "scam", "payment"]):
        return "money and shopping"
    if any(x in blob for x in ["privacy", "security", "phone", "data", "breach"]):
        return "privacy and safety"
    if any(x in blob for x in ["government", "law", "lawsuit", "regulation"]):
        return "trust, law, and government"
    return "daily life"


def _deterministic_title_pack(g: Dict[str, Any], stories: List[Dict[str, Any]], date_str: str) -> Dict[str, Any]:
    blob = _story_blob(stories)
    entity = _entity_from_stories(stories)
    stakes = _stakes_from_stories(stories)
    recent = _recent_feed_titles(g, limit=int(os.getenv("NO_REPEAT_TITLE_WINDOW", "14")))

    candidates: List[str] = []
    if "china" in blob:
        candidates += ["How China Just Changed the AI Race", "The AI Race Has a China Problem Again"]
    if "agent" in blob or "agents" in blob:
        candidates += ["AI Agents Are Getting More Access. Who Is Watching?", "Your AI Agent Has Permissions. That Is the Story."]
    if "health" in blob or "doctor" in blob or "diagnosis" in blob:
        candidates += ["AI Got the Diagnosis Right. Now Who Gets Sued?", "Your Doctor May Trust AI. The Legal System Is Not Ready."]
    if "compute" in blob or "gpu" in blob or "nvidia" in blob or "data center" in blob:
        candidates += ["AI’s Compute Problem Is Becoming Everyone’s Problem", "The AI Race Is Starting to Look Like a Power Bill"]
    if "lawsuit" in blob or "court" in blob or "copyright" in blob:
        candidates += ["The AI Lawsuit That Could Change the Rules", "AI Is Running Into the One Thing It Cannot Prompt Away"]
    if "developer" in blob or "code" in blob or "github" in blob:
        candidates += ["If AI Can Code This Fast, What Is the Moat?", "Developers Just Found the Leverage Before the Market Did"]
    if "school" in blob or "student" in blob or "kids" in blob:
        candidates += ["AI Is Entering School Life. What Should Families Know?", "The AI Story Students and Parents Should Hear Today"]
    if "shopping" in blob or "bank" in blob or "money" in blob:
        candidates += ["AI Is Moving Into Your Money. Who Protects You?", "Your Next AI Agent May Touch Your Wallet"]

    candidates += [
        f"{entity}'s AI Move Has a Bigger Problem Behind It",
        f"The Demo Is Not the Story. {stakes}",
        f"AI Is Moving Into Everyday Life. {stakes}",
        "The AI Story Your Family May Feel Next",
        "The AI Story Your Boss Will Ask About Next",
        f"What Changed in AI Today — {date_str}",
    ]

    selected = ""
    for title in candidates:
        title = SIGNAL_ROOM_RE.sub(SHOW_TITLE, title).strip()
        if 28 <= len(title) <= 96 and not _is_repeat_title(title, recent):
            selected = title
            break

    if not selected:
        selected = f"What Changed in AI Today — {date_str}"

    seo_terms = []
    for term in ["OpenAI", "Google", "Anthropic", "NVIDIA", "AI Agents", "Health AI", "AI Coding", "Enterprise AI", "AI Regulation"]:
        if term.lower() in blob:
            seo_terms.append(term)

    return {
        "big_headline_title": selected,
        "human_stakes_title": selected,
        "seo_title": ", ".join(seo_terms[:4] or ["AI News", "AI Tools", "Everyday AI"]) + ": What Changed Today",
        "published_title": selected,
        "life_lane": _life_lane_from_stories(stories),
        "recent_titles_checked": recent[:8],
    }


def _build_story_board(g: Dict[str, Any], stories: List[Dict[str, Any]], date_str: str) -> Dict[str, Any]:
    compact = [_compact_story(s, i + 1) for i, s in enumerate(stories[:8])]
    default_title_pack = _deterministic_title_pack(g, stories, date_str)

    planner_prompt = f"""
Return STRICT JSON only.

You are building the editorial board for a 20–26 minute AI podcast called {SHOW_TITLE}.

Do NOT use "Signal Room" language.
Do NOT rename the show.
The show promise:
The AI Edge explains the one AI story today that could touch your work, money, health, privacy, family, school, safety, or trust.

Audience:
Everyone. A parent in the car, a high-school student, a college student, a worker, a founder, a nurse, a teacher, a retiree, and a skeptical listener who does not follow AI every day.

Date: {date_str}

Stories:
{json.dumps(compact, ensure_ascii=False, indent=2)}

Create:
{{
  "lead_story": {{"rank": 1, "why_today": "...", "human_stakes": "...", "listener_question": "..."}},
  "episode_promise": "By the end, the listener will understand ...",
  "central_tension": "A clean unresolved question that pulls the episode forward.",
  "everyday_life_lane": "work|school|money|health|privacy|family|shopping|safety|government|trust",
  "one_reusable_lesson": "A simple idea the listener can repeat to someone else.",
  "data_receipts_needed": ["specific number or fact to include", "specific number or fact to include", "specific number or fact to include"],
  "title_candidates": {{
    "big_headline_title": "...",
    "human_stakes_title": "...",
    "seo_title": "...",
    "published_title": "..."
  }},
  "segment_arc": [
    {{"segment": 1, "job": "cold open + why normal people care", "story_ranks": [1], "must_include": ["human stakes in first 90 seconds"]}},
    {{"segment": 2, "job": "what happened + receipts", "story_ranks": [1, 2], "must_include": ["Jamie plain-English translation"]}},
    {{"segment": 3, "job": "who feels it next", "story_ranks": [2, 3], "must_include": ["work/money/health/privacy/family relevance"]}},
    {{"segment": 4, "job": "the useful lesson", "story_ranks": [3, 4], "must_include": ["one reusable concept"]}},
    {{"segment": 5, "job": "TheLEDGR Readout + callback", "story_ranks": [1, 5], "must_include": ["what to watch tomorrow"]}}
  ],
  "forwardable_line_targets": ["...", "...", "..."],
  "theledgr_readout_angle": "..."
}}
"""
    board = _call_json_planner(g, planner_prompt, default={})
    if not isinstance(board, dict):
        board = {}

    title_pack = board.get("title_candidates")
    if not isinstance(title_pack, dict):
        title_pack = {}

    merged_title_pack = dict(default_title_pack)
    merged_title_pack.update({k: v for k, v in title_pack.items() if isinstance(v, str) and v.strip()})

    recent = _recent_feed_titles(g, limit=int(os.getenv("NO_REPEAT_TITLE_WINDOW", "14")))
    proposed = str(merged_title_pack.get("published_title") or "").strip()
    if _is_repeat_title(proposed, recent):
        merged_title_pack = default_title_pack

    board["title_candidates"] = merged_title_pack
    board.setdefault("episode_promise", "By the end, the listener will know what changed in AI today and what it could mean in everyday life.")
    board.setdefault("central_tension", "Is this just another AI headline, or something people will actually feel?")
    board.setdefault("everyday_life_lane", default_title_pack.get("life_lane", "daily life"))
    board.setdefault("one_reusable_lesson", "AI only matters when it changes who can act, who pays, who is trusted, or who is responsible.")
    board.setdefault("data_receipts_needed", ["at least three numbers or concrete facts from the story slate"])
    board.setdefault("forwardable_line_targets", [
        "The moat is not the model; it is who controls what the AI is allowed to do.",
        "If nobody owns the outcome, the AI is not ready for the workflow.",
        "The demo is impressive. The real story begins when it touches your money, health, work, or privacy.",
    ])
    return board


def _story_lines_for_prompt(stories: List[Dict[str, Any]]) -> str:
    rows = []
    for i, story in enumerate(stories[:8], start=1):
        rows.append(
            f"{i}. {_readable_story_title(story)}\n"
            f"   Publisher: {_story_publisher(story) or 'unknown'}\n"
            f"   Summary: {_story_summary(story)[:750]}\n"
            f"   URL: {_story_url(story)}"
        )
    return "\n".join(rows)


def _writer_prompt(stories: List[Dict[str, Any]], sponsors: List[Dict[str, Any]], date_str: str, board: Dict[str, Any]) -> str:
    title_pack = board.get("title_candidates", {})
    sponsor = sponsors[0] if sponsors else {}
    sponsor_cta = sponsor.get("cta") or "Subscribe to TheLEDGR at T-H-E-L-E-D-G-R dot I-O."

    return f"""
Write the complete spoken script for today's automated podcast episode.

SHOW:
- Name: {SHOW_TITLE}
- Length target: 20–26 minutes.
- Format: five segments.
- Public promise: The AI Edge explains the one AI story today that could touch your work, money, health, privacy, family, school, safety, or trust.
- Do not use the phrases "Signal Room" or "AI Signal Room".
- Keep the show identity. Do not invent a new brand.

AUDIENCE:
- Everyone. A parent in the car, a high-school student, a college student, a worker, a founder, a nurse, a teacher, a retiree, and a skeptical listener who does not follow AI every day.
- Simple enough for someone's mom to follow.
- Useful enough for someone's boss to care.
- Interesting enough for someone's son or daughter to remember.
- No insider-only AI jargon unless Jamie immediately translates it.
- The listener should never need to know model architecture, benchmarks, venture capital, or enterprise software to understand why the story matters.

PUBLISHED TITLE TO EARN:
{title_pack.get("published_title")}

EDITORIAL BOARD:
{json.dumps(board, ensure_ascii=False, indent=2)}

STORIES:
{_story_lines_for_prompt(stories)}

SPONSOR:
TheLEDGR. Use one short early spoken CTA after the cold open, and one useful "TheLEDGR Readout" near the end.
Sponsor CTA raw material: {sponsor_cta}

CAST:
ALEX:
- The host. Curious, grounded, and high-agency.
- He asks the kitchen-table question: what would a normal family ask if they heard this headline?
- He pressure-tests the story for the listener.
- He controls the room without narrating everything.

JAMIE:
- Warm, sharp, emotionally intelligent.
- She translates complexity into clear human meaning.
- She says the simple version when the room gets too technical.
- She makes a parent, student, worker, and retiree feel included.

RUFUS:
- British, dry, skeptical, data-driven.
- He uses wit to clarify, not exclude.
- He lands numbers cleanly.
- His quips should make the issue easier to remember.

NON-NEGOTIABLE UNIVERSAL VALUE:
- First 90 seconds must answer: why should a normal person care today?
- Every major story must connect to at least one everyday life lane: work, school, money, health, privacy, family, shopping, creativity, safety, government, or trust.
- Jamie must translate any technical term into plain English immediately.
- Alex must ask the kitchen-table question.
- Rufus can be dry and British, but the joke must clarify the issue, not make the listener feel excluded.
- The episode must teach one useful idea a listener can repeat to someone else.

NON-NEGOTIABLE DATA/PURPOSE:
- Include at least 3 concrete data receipts: numbers, dates, dollar amounts, percentages, rankings, counts, or named institutions.
- Do not throw numbers around. Explain what each number means for a normal person.
- Every segment must have a purpose: what happened, why it matters, who feels it, what lesson to take, what to watch next.
- The episode cannot be a list of headlines.

NON-NEGOTIABLE CHEMISTRY:
- Alex must ask a listener-facing question every few minutes.
- Jamie must simplify at least once per major story.
- Rufus must land at least 3 dry lines.
- Include at least 6 real frictions: pushbacks, corrections, challenges, interruptions, or "wait —" moments.
- Include at least 3 forwardable lines.
- Ending must callback to the cold open.
- Normal host turns should be short. Avoid monologues.
- Spoken cues are okay only when natural: "I mean...", "wait", "right", "look", "come on", "mm", "honestly".
- Do NOT write bracket-heavy acting notes.

STRUCTURE:
SEGMENT 1 — Cold open + why normal people care + early TheLEDGR CTA.
SEGMENT 2 — What happened + receipts + Jamie plain-English translation.
SEGMENT 3 — Who feels it next: work, money, health, privacy, family, school, safety, or trust.
SEGMENT 4 — The useful lesson: one reusable idea.
SEGMENT 5 — TheLEDGR Readout + what to watch tomorrow + callback.

OUTPUT RULES:
- Dialogue only.
- Use exact speaker labels: ALEX:, JAMIE:, RUFUS:
- Include SEGMENT 1 through SEGMENT 5 headers.
- Put exactly one [MUSIC] marker after the cold open/intro beat.
- No markdown table.
- No citations.
- No source list.
- No "Signal Room".
"""


def _clean_script(text: str) -> str:
    text = text or ""
    text = re.sub(r"^```(?:text|markdown)?\s*", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    text = SIGNAL_ROOM_RE.sub(SHOW_TITLE, text)
    text = re.sub(r"\bTHE LEDGER\b", "TheLEDGR", text, flags=re.IGNORECASE)
    text = re.sub(r"\bThe Ledger\b", "TheLEDGR", text)
    lines: List[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.upper() == "[MUSIC]":
            lines.append("[MUSIC]")
            continue
        if re.match(r"^SEGMENT\s+[1-5]\b", line, flags=re.IGNORECASE):
            lines.append(line.upper())
            continue
        m = SPEAKER_RE.match(line)
        if m:
            speaker = m.group(1).upper()
            spoken = m.group(2).strip()
            spoken = re.sub(r"\[(?:smiles?|smirks?|laughs warmly|leans in|stage direction)[^\]]*\]", "", spoken, flags=re.IGNORECASE).strip()
            if spoken:
                lines.append(f"{speaker}: {spoken}")
    return "\n".join(lines).strip()


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text or ""))


def _universal_audience_report(script: str) -> Dict[str, Any]:
    full = script or ""
    life_lane_hits = len(LIFE_LANES_RE.findall(full))
    jargon_hits = len(JARGON_RE.findall(full))
    translation_hits = len(PLAIN_ENGLISH_RE.findall(full))
    first_90 = "\n".join([ln for ln in full.splitlines() if SPEAKER_RE.match(ln)][:14])
    first_90_universal = bool(LIFE_LANES_RE.search(first_90))

    return {
        "life_lane_hits": life_lane_hits,
        "jargon_hits": jargon_hits,
        "plain_english_translation_hits": translation_hits,
        "first_90_has_everyday_relevance": first_90_universal,
        "jargon_is_translated": jargon_hits <= 6 or translation_hits >= max(2, jargon_hits // 3),
        "passed": (
            life_lane_hits >= 8
            and first_90_universal
            and (jargon_hits <= 6 or translation_hits >= max(2, jargon_hits // 3))
        ),
    }


def _quality_report(script: str, stories: List[Dict[str, Any]], title: str = "") -> Dict[str, Any]:
    speaker_lines = [ln for ln in script.splitlines() if SPEAKER_RE.match(ln)]
    first_90 = "\n".join(speaker_lines[:14]).lower()
    full = script.lower()
    universal = _universal_audience_report(script)

    alex_questions = len(re.findall(r"^ALEX:.*\?", script, flags=re.IGNORECASE | re.MULTILINE))
    jamie_simple = len(re.findall(r"^JAMIE:.*\b(simple version|plain english|what this means|what people will feel|the useful part|what that means|in normal terms)\b", script, flags=re.IGNORECASE | re.MULTILINE))
    rufus_dry = len(re.findall(r"^RUFUS:.*\b(lovely|quite|rather|brilliant|marvellous|terms-of-service|puddle|moat|permission|liability|because apparently|nothing says|bold strategy)\b", script, flags=re.IGNORECASE | re.MULTILINE))
    friction = len(re.findall(r"\b(wait|hold on|hang on|come on|that sounds|is this real|who gets sued|who is watching|nobody knows|not so fast|push back|uncomfortable)\b", full))
    forwardables = len(re.findall(r"\b(the moat is|the invoice is|if nobody owns|who gets sued|who is watching|this is not|that is the risk|the real story|what people will feel)\b", full))
    numeric = len(NUMERIC_RE.findall(script))
    signal_room_mentions = len(SIGNAL_ROOM_RE.findall(script))

    max_turn_words = 0
    overlong_turns = 0
    for ln in speaker_lines:
        m = SPEAKER_RE.match(ln)
        words = _word_count(m.group(2) if m else ln)
        max_turn_words = max(max_turn_words, words)
        if words > 52:
            overlong_turns += 1

    checks = {
        "no_signal_room_language": signal_room_mentions == 0,
        "title_has_listener_tension": bool(title and any(x in title.lower() for x in [
            "who", "why", "how", "problem", "race", "sued", "watching", "trust", "keys", "rules", "boss", "doctor", "china", "moat", "family"
        ])),
        "first_90_seconds_explain_human_stakes": any(x in first_90 for x in [
            "your", "boss", "doctor", "company", "job", "privacy", "security", "lawsuit", "who gets sued",
            "people will feel", "why this matters", "family", "school", "money", "health"
        ]),
        "alex_listener_questions": alex_questions >= 5,
        "jamie_simplification": jamie_simple >= 2,
        "rufus_dry_wit": rufus_dry >= 2,
        "real_friction": friction >= 6,
        "forwardable_lines": forwardables >= 2,
        "numeric_receipts": numeric >= 45,
        "no_monologue_bloat": overlong_turns <= 14 and max_turn_words <= 72,
        "universal_life_relevance": universal["life_lane_hits"] >= 8,
        "first_90_has_everyday_relevance": universal["first_90_has_everyday_relevance"],
        "jargon_is_translated": universal["jargon_is_translated"],
    }
    score = max(0, min(100, round(100 * sum(1 for ok in checks.values() if ok) / max(1, len(checks))) - (30 if signal_room_mentions else 0)))
    return {
        "version": "v3.1-expansion-ready-universal-data-purpose",
        "score": score,
        "checks": checks,
        "metrics": {
            "speaker_lines": len(speaker_lines),
            "words": _word_count(script),
            "alex_questions": alex_questions,
            "jamie_simple_version_hits": jamie_simple,
            "rufus_dry_wit_hits": rufus_dry,
            "friction_hits": friction,
            "forwardable_hits": forwardables,
            "numeric_receipts": numeric,
            "max_turn_words": max_turn_words,
            "overlong_turns": overlong_turns,
            "signal_room_mentions": signal_room_mentions,
            "universal_life_lane_hits": universal["life_lane_hits"],
            "jargon_hits": universal["jargon_hits"],
            "plain_english_translation_hits": universal["plain_english_translation_hits"],
        },
        "failed": [k for k, ok in checks.items() if not ok],
    }


def _punchup_prompt(script: str, board: Dict[str, Any]) -> str:
    return f"""
Punch up this script for memorable human chemistry without changing facts.

Rules:
- Preserve the five-segment structure and speaker labels.
- Do not add bracket-heavy stage directions.
- Add friction, dry Rufus wit, Jamie warmth, Alex pressure-testing.
- Make the story easier for a normal person to understand.
- Keep turns short.
- Do not use "Signal Room".
- Preserve TheLEDGR CTA and TheLEDGR Readout.
- Do not remove data receipts.

Return the full improved script only.

Board:
{json.dumps(board, ensure_ascii=False, indent=2)}

Script:
{script}
"""


def _rescue_prompt(script: str, report: Dict[str, Any], board: Dict[str, Any]) -> str:
    return f"""
This script failed the pre-TTS quality gate. Repair it.

Failed checks:
{json.dumps(report.get("failed", []), ensure_ascii=False)}

Metrics:
{json.dumps(report.get("metrics", {}), ensure_ascii=False)}

Repair requirements:
- Remove all Signal Room language.
- First 90 seconds must clearly explain why a normal person should care.
- Make the episode understandable to a parent, student, worker, and retiree.
- Connect every major story to work, school, money, health, privacy, family, shopping, safety, government, or trust.
- Translate jargon immediately. Do not assume the listener follows AI every day.
- Include at least 3 concrete data receipts and explain why each matters.
- Add Alex listener questions.
- Add Jamie simplification beats.
- Add Rufus dry wit, but keep it believable.
- Add forwardable lines.
- Add real friction without chaos.
- Keep the episode coherent and clean for TTS.

Return the full repaired script only.

Board:
{json.dumps(board, ensure_ascii=False, indent=2)}

Script:
{script}
"""


def install_v3_1(g: Dict[str, Any]) -> None:
    _safe_print(g, ">> ✅ Installing The AI Edge v3.1 expansion-ready writer room")

    original_generate_episode_script = g.get("generate_episode_script")
    original_generate_marketing_pack = g.get("generate_marketing_pack")
    original_build_episode_aircheck = g.get("build_episode_aircheck")

    rss = g.get("RSS_SETTINGS")
    if isinstance(rss, dict):
        rss["title"] = SHOW_TITLE
        rss["description"] = SHOW_DESCRIPTION

    def generate_episode_script_v3_1(stories: List[Dict[str, Any]], sponsors: List[Dict[str, Any]], date_str: str) -> str:
        _safe_print(g, " >> ✍️ WRITING EPISODE WITH V3.1 UNIVERSAL DATA/PURPOSE WRITER ROOM")
        board = _build_story_board(g, stories, date_str)
        title = board.get("title_candidates", {}).get("published_title", "")

        try:
            path = g.get("STORY_SLATE_DECISION_PATH")
            if path:
                path.write_text(json.dumps({"v3_1_board": board}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception:
            pass

        prompt = _writer_prompt(stories, sponsors, date_str, board)

        script = ""
        for model in [SCENE_WRITER_MODEL, SCENE_WRITER_FALLBACK_MODEL]:
            script = _anthropic_text(g, prompt, model=model, max_tokens=int(os.getenv("ANTHROPIC_SCRIPT_MAX_TOKENS", "6200")))
            if script:
                _safe_print(g, f"    ✅ Claude writer pass succeeded: {model}")
                break

        if not script:
            _safe_print(g, "    ⚠️ Anthropic unavailable; using OpenAI fallback writer.")
            for model in [RESCUE_MODEL, RESCUE_FALLBACK_MODEL, OPENAI_CHEAP_MODEL, os.getenv("OPENAI_CHAT_MODEL", "gpt-4o")]:
                script = _openai_text(g, prompt, model=model, max_tokens=6200)
                if script:
                    _safe_print(g, f"    ✅ OpenAI fallback writer pass succeeded: {model}")
                    break

        if not script and callable(original_generate_episode_script):
            _safe_print(g, "    ⚠️ V3.1 writer unavailable; falling back to prior generator so automation does not die.")
            script = original_generate_episode_script(stories, sponsors, date_str)

        script = _clean_script(script)
        report = _quality_report(script, stories, title=title)

        if ENABLE_GROK_PUNCHUP:
            punched = _xai_text(g, _punchup_prompt(script, board), model=PUNCHUP_MODEL, max_tokens=5200)
            if punched:
                candidate = _clean_script(punched)
                candidate_report = _quality_report(candidate, stories, title=title)
                if candidate_report["score"] >= report["score"] - 4:
                    script, report = candidate, candidate_report
                    _safe_print(g, f"    ✅ Grok punch-up applied. Pre-TTS score: {report['score']}")
                else:
                    _safe_print(g, f"    ⚠️ Grok punch-up rejected. Candidate score: {candidate_report['score']} vs {report['score']}")

        if ENABLE_OPENAI_RESCUE and report["score"] < PRE_TTS_MIN_SCORE:
            _safe_print(g, f"    ⚠️ Pre-TTS score {report['score']} below {PRE_TTS_MIN_SCORE}. Running premium rescue.")
            repaired = ""
            for model in [RESCUE_MODEL, RESCUE_FALLBACK_MODEL, OPENAI_CHEAP_MODEL]:
                repaired = _openai_text(g, _rescue_prompt(script, report, board), model=model, max_tokens=6200)
                if repaired:
                    break
            if repaired:
                candidate = _clean_script(repaired)
                candidate_report = _quality_report(candidate, stories, title=title)
                if candidate_report["score"] >= report["score"]:
                    script, report = candidate, candidate_report
                    _safe_print(g, f"    ✅ Rescue applied. Pre-TTS score: {report['score']}")

        script = SIGNAL_ROOM_RE.sub(SHOW_TITLE, script)
        report = _quality_report(script, stories, title=title)

        try:
            path = g.get("SCRIPT_AIRCHECK_PATH")
            if path:
                path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception:
            pass

        if report["score"] < PRE_TTS_MIN_SCORE:
            _safe_print(g, f"    ⚠️ V3.1 score below target ({report['score']}/{PRE_TTS_MIN_SCORE}). Duplicate guard still protects public feed.")
        else:
            _safe_print(g, f"    ✅ V3.1 script passed pre-TTS gate: {report['score']}/100")

        return script

    def build_episode_aircheck_v3_1(
        script: str,
        stories: List[Dict[str, Any]],
        pack: Dict[str, Any] | None = None,
        sponsors: List[Dict[str, Any]] | None = None,
        date_str: str = "",
    ) -> Dict[str, Any]:
        base: Dict[str, Any] = {}
        if callable(original_build_episode_aircheck):
            try:
                base = original_build_episode_aircheck(script, stories, pack or {}, sponsors or [], date_str)
            except Exception as e:
                base = {"passed": False, "error": str(e)}
        report = _quality_report(script, stories)
        merged = dict(base) if isinstance(base, dict) else {}
        merged["v3_1_writer_room"] = report
        merged["passed"] = bool(merged.get("passed", True)) and report["score"] >= PRE_TTS_MIN_SCORE
        merged["failed"] = list(dict.fromkeys(list(merged.get("failed") or []) + report.get("failed", [])))
        return merged

    def generate_marketing_pack_v3_1(
        stories: List[Dict[str, Any]],
        episode_date: str,
        listen_url: str,
        tracking: Dict[str, Any] | None = None,
        experiments: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        board = _build_story_board(g, stories, episode_date)
        title_pack = board.get("title_candidates", _deterministic_title_pack(g, stories, episode_date))
        title = SIGNAL_ROOM_RE.sub(SHOW_TITLE, title_pack.get("published_title") or SHOW_TITLE)
        lane = board.get("everyday_life_lane") or title_pack.get("life_lane") or _life_lane_from_stories(stories)

        pack: Dict[str, Any] = {}
        if callable(original_generate_marketing_pack):
            try:
                pack = original_generate_marketing_pack(stories, episode_date, listen_url, tracking=tracking, experiments=experiments)
            except TypeError:
                try:
                    pack = original_generate_marketing_pack(stories, episode_date, listen_url, tracking=tracking or {}, experiments=experiments or {})
                except Exception:
                    pack = {}
            except Exception:
                pack = {}

        if not isinstance(pack, dict):
            pack = {}

        desc = (
            f"{title}\n\n"
            f"Why it matters: this is not just an AI industry story. It touches {lane} — "
            f"the way people work, learn, spend, protect their privacy, make decisions, or trust what they see.\n\n"
            f"In this episode, Alex, Jamie, and Rufus make the story simple, useful, data-backed, and worth repeating.\n\n"
            f"Subscribe to TheLEDGR for decision-grade AI signal: "
            f"https://theledgr.io?utm_source=podcast&utm_medium=show_notes&utm_campaign=daily_ai_edge"
        )

        pack.update({
            "title": title,
            "title_candidates_v3_1": title_pack,
            "central_tension": board.get("central_tension"),
            "episode_promise": board.get("episode_promise"),
            "one_reusable_lesson": board.get("one_reusable_lesson"),
            "everyday_life_lane": lane,
            "description": SIGNAL_ROOM_RE.sub(SHOW_TITLE, desc),
            "episode_url": listen_url,
            "subscriber_cta": "Subscribe to TheLEDGR for decision-grade AI signal: https://theledgr.io?utm_source=podcast&utm_medium=show_notes&utm_campaign=daily_ai_edge",
        })
        return pack

    g["generate_episode_script"] = generate_episode_script_v3_1
    g["build_episode_aircheck"] = build_episode_aircheck_v3_1
    g["generate_marketing_pack"] = generate_marketing_pack_v3_1
    g["V3_1_WRITER_ROOM_INSTALLED"] = True
