"""Broad subject diversity among validated news; never a positivity quota."""
import re


def topic_family(story):
    # Classify the actual event headline, not incidental risk words in the summary.
    text = str(story.get("headline") or story.get("title") or "").lower()
    groups = (
        ("governance", r"\bfcc\b|robocall|\bban\b|lawsuit|antitrust|security council|\bun\b|regulat|legislat|treaty|summit|china talks|ai czar|ai force|diploma|incident alert|governance|safety pact|task force|reporting|policymaker|government|city council|dangers|oversight|subpoena|safety concern"),
        ("science_access", r"medical|clinical|patients?|restore speech|researchers? use|hospital|disabil|accessib|scient|research atlas|genome|protein|education|school|teacher|blind|deaf"),
        ("infrastructure", r"chip|gpu|data cent|power|energy|compute|semiconductor"),
        ("markets", r"funding|raises|raised|earnings|acqui|merger|investment|billion euros|stock"),
        ("security", r"breach|cyber|vulnerab|exploit|attack"),
        ("products", r"rolls out|interactive|interface|launch|release|model|tool|coding|agent|app|feature|creative|image|video"),
    )
    return next((name for name, pattern in groups if re.search(pattern, text)), "other")


def listener_frame(story):
    """A second axis prevents governance/security being mistaken for tonal variety."""
    # Emotional angle is independent of sector: a security acquisition is still
    # a risk story, even though its subject family is markets. Do not scan arbitrary
    # source facts for incidental risk words; use the headline's central action.
    headline = str(story.get("headline") or story.get("title") or "").lower()
    case = story.get("editorial_case") or {}
    # Only the central development/question, never incidental caveats in facts.
    headline += " " + " ".join(str(case.get(k) or "") for k in
                              ("new_development", "distinct_question")).lower()
    risk_angle = re.search(
        r"false front|deceptive|abuse|blocked|\bfcc\b|political robocall|rogue|unauthori[sz]ed|unapproved|security|cyber|breach|hacks?|"
        r"regulat|oversight|warnings?|dangers?|liability|surveillance|"
        r"safety|compliance|fraud|lawsuit|antitrust|ban\b", headline)
    if risk_angle:
        return "accountability_risk"
    family = topic_family(story)
    return "accountability_risk" if family in {"governance", "security"} else family


def concentrated(stories):
    families = [listener_frame(s) for s in stories[:3]]
    return len(families) == 3 and len(set(families)) == 1 and families[0] != "other"


def balanced_story_order(stories):
    """Keep the lead; diversify nearby ranked, comparably sourced alternatives.

    Keep all records. Unknown subjects get no novelty bonus. Never replace a
    trusted story with an untrusted one just to obtain variety.
    """
    if not stories:
        return []
    chosen, remaining = [dict(stories[0])], [dict(s) for s in stories[1:]]
    while remaining and len(chosen) < 3:
        seen = {listener_frame(s) for s in chosen}
        def penalty(pair):
            index, row = pair
            family = listener_frame(row)
            tier = int(row.get("source_tier", 2))
            return 100 * (tier < 2) + index + (8 if family in seen or family == "other" else 0)
        index, row = min(enumerate(remaining), key=penalty)
        chosen.append(row)
        remaining.pop(index)
    result = chosen + remaining
    for index, row in enumerate(result, 1):
        row.update(rank=index, story_tier="primary" if index <= 3 else "supporting",
                   topic_family=topic_family(row))
    return result


