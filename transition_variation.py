"""Small deterministic edits of the approved transition; no new sound generation."""
import datetime as dt


def story_transition(clip, audit, segment, date_str):
    # Retain the recognizable opening attack. Never touch intro/outro/host cues.
    variants = ((1.0, 100), (.85, 180), (.72, 220), (.92, 260))
    index = (dt.date.fromisoformat(date_str).toordinal() + int(segment) - 2) % 4
    fraction, fade = variants[index]
    duration = max(500, min(len(clip), round(len(clip) * fraction)))
    result = clip[:duration].fade_out(min(fade, duration // 3))
    provenance = dict(audit)
    provenance.update(variant=index, edit="approved source: shortened tail and fade only",
                      duration_seconds=len(result) / 1000)
    return result, provenance
