# September 21, 2026 — editorial production upgrade

Implemented against main `347e4d7a08cbddcf95562ede56804f15723e578d`. Validation: **91 offline tests passed**, changed Python modules compile. This release has not yet generated an episode; no new audio was rendered or listened to during this upgrade.

## Evidence and response

Today's successful scheduled run (35602425452) produced a 20:55 episode. Its first story started at 169.6 seconds. Both Gemini storyboard attempts returned 503; the production used a source-headline fallback and empty scene plan. The Sonnet dialogue revision was rejected for runtime regression. Its actual candidate was not retained, so its quality and exact length cannot be reconstructed.

The three selected stories concerned governance. A research housekeeping message also survived as a supporting headline. Engineering telemetry reported -16.22 LUFS, -1.49 dBTP and 6 LU loudness range. These measurements do not establish comic timing, chemistry or listener enjoyment.

| Change | Implemented behavior |
| --- | --- |
| Story selection | Preserve the lead and source requirements; prefer credible subject variety among other ranked stories. One bounded variety refill when a sufficient initial slate is concentrated. No failure merely because a day's news remains concentrated. |
| Research hygiene | Reject “no verified result” housekeeping as a news headline. |
| Planning reliability | After both Gemini attempts fail, use one cross-provider planning fallback. Save provider outcomes and title source. Populate source-isolated scene records if needed. |
| Title selection | Examine alternate candidates before falling back to the headline; preserve lead alignment and anti-generic checks. Titles still require editorial judgment. |
| Writing | Replace the oversized writer brief with a focused five-segment brief. Warmth, curiosity and useful progress; no forced losers, joke quotas or manufactured danger. |
| Opening | Request 140–180 spoken words including sponsor, callbacks later, first story within roughly 90 seconds including music. Detect an already-named lead to prevent duplicate headline insertion. This is a target, not a demonstrated timing result. |
| Dialogue editing | Keep before/after scripts, word counts and rejection diagnostics. Planning floor 3,300 words; target 3,800. Actual assembled runtime remains decisive. |
| Review | Add a nonblocking listener-review report with observable failures and explicit listening requirements; no entertainment score. |
| Demonstration | Original and revised lead scene in auditions/SEPT21_EDITORIAL_COMPARISON.md. Text only, approximately three minutes pending rendering. |

Existing voice routing, performance-gap direction, pitch-preserving speed treatment, measured chapters/transitions, mastering, sponsor rules, memory, prediction, listener question, follow CTA and paid-audio protection remain in place. No extra full episode, voice replacement or publishing gate was introduced. The 19–26-minute preference and 30-minute maximum remain; the lower word floor is a planning heuristic, not permission to deliver undersized audio.

## Next verification

The next autonomous run must show which planning provider actually worked, whether the edit was retained, story variety, measured opening and total runtime, and actual TTS routing. Listen to the resulting master for responsive exchanges, warmth, joke delivery, fatigue and clipping before making an entertainment rating or rival comparison. Publication success does not prove Spotify availability, on-time 06:30 Eastern delivery, retention or sharing. Existing cron is unchanged; GitHub scheduling is not an exact delivery guarantee.
