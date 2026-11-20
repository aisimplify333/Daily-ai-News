# The AI Edge

The weekday AI news and analysis podcast with Alex, Jamie and Rufus.

**What changed. Who wins. What you do next.**

Each episode explores three distinct artificial-intelligence stories from the previous
24–48 hours, with responsive exchanges, source-backed explanations and a separate
listener payoff for each. New episodes are produced automatically Monday through
Friday and delivered to Spotify through the public RSS feed.

The delivery target is a playable release by 06:30 America/New_York on weekdays.
The workflow requests guarded attempts at 06:17, 07:17, 08:17, 09:17 and 10:17 UTC.
These are requested starts, not proof of delivery; GitHub may start a run late. Check Actions before manually
starting a catch-up run. Existing same-date audio is reused, and ordinary code
pushes do not trigger paid production.

Alex leads and asks the listener's next question. Jamie is the quick, opinionated
comic catalyst, using Gemini Sulafat with Grok Ursa backup. Rufus is the measured British
foil. The cast may invent recurring bits and explicitly hypothetical questions,
but never listener submissions, poll results, reviews or audience numbers.

Production retains the established intro/outro music, four segment transitions,
an unmistakable Alex sponsor read and a rotating Jamie/Rufus end tag. Measured
assembly timings drive chapters and a captioned clip; a one-time trailer can be
assembled from the actual show without additional TTS. These promotional extras
are advisory and cannot block a completed episode. Their files are not equivalent
to uploading or pinning them in Spotify for Creators.

Run the offline production checks with `python -m unittest discover -s tests -v`
and `python preflight_guard_v3_1.py`. See [production handoff](PRODUCTION_STATUS.md)
for the remaining live-account checks.
