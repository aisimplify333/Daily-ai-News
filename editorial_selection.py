"""Broad subject diversity among validated news; never a positivity quota."""
import re


def topic_family(story):
    # Classify the actual event headline, not incidental risk words in the summary.
    text = str(story.get("headline") or story.get("title") or "").lower()
    groups = (
        ("governance", r"lawsuit|antitrust|security council|\bun\b|regulat|legislat|treaty|summit|china talks|ai czar|ai force|diploma|incident alert|governance|safety pact"),
        ("science_access", r"medical|clinical|hospital|disabil|accessib|scient|research atlas|genome|protein|education|school|teacher|blind|deaf"),
        ("infrastructure", r"chip|gpu|data cent|power|energy|compute|semiconductor"),
        ("markets", r"funding|raises|raised|earnings|acqui|merger|investment|billion euros|stock"),
        ("security", r"breach|cyber|vulnerab|exploit|attack"),
        ("products", r"launch|release|model|tool|coding|agent|app|feature|creative|image|video"),
    )
    return next((name for name, pattern in groups if re.search(pattern, text)), "other")


def concentrated(stories):
    families = [topic_family(s) for s in stories[:3]]
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
        seen = {topic_family(s) for s in chosen}
        def penalty(pair):
            index, row = pair
            family = topic_family(row)
            tier = int(row.get("source_tier", 2))
            return 100 * (tier < 2) + index + (5 if family in seen and family != "other" else 0)
        index, row = min(enumerate(remaining), key=penalty)
        chosen.append(row)
        remaining.pop(index)
    result = chosen + remaining
    for index, row in enumerate(result, 1):
        row.update(rank=index, story_tier="primary" if index <= 3 else "supporting",
                   topic_family=topic_family(row))
    return result
