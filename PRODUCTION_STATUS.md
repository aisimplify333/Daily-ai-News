# The AI Edge production handoff

Release prepared September 3 Pacific / September 4 UTC, 2026.

## September 8 research recovery

- Title follow-up: storyboard now requires an explicit, source-backed listener
  payoff and considers decision/tradeoff/explanation angles in the existing call.
  A lightweight payoff-cue check falls back without retries or a publishing gate.
  Writer receives the episode-specific promise for opening and closing delivery.
  This is not semantic proof, a listened audio review, or conversion evidence.
  No paid audio or previously published episode was regenerated for this change.

- Follow-up: delivery target is BY 06:30 Eastern every weekday, using
  America/New_York local time (daylight saving observed). Requested production
  start moved to 06:17 UTC: 02:17 EDT / 01:17 EST, providing 4h13 / 5h13 of
  start-to-delivery buffer. Early publication is allowed. GitHub delays and
  Spotify ingestion remain outside this cron's control; this is not a guarantee
  of precise arrival. No second paid full-production retry has been added.
- Corrected the September 8 live-run mismatch: the research layer now requires
  the requested n stories (five in production), while the trusted-source minimum
  stays three. Three accepted stories now trigger the alternate refill rather
  than being cached and returned to a caller requiring five. Exhaustion raises
  before writing/TTS. Two regression tests cover the actual production contract.

- Retain valid candidates and make one explicit OpenAI web-search refill when
  the initial grounded result fails the minimum valid/trusted count. Search
  across models, policy, finance, infrastructure and security; preserve freshness
  and factual requirements. No cast, sponsor, music or publishing changes.
- Bound: existing initial Gemini call with its one error fallback, plus at most
  one alternate refill (at most three provider requests, excluding SDK retries).
  No refill when the initial slate meets requirements. Research costs are not
  zero; provider invoice totals remain unmeasured.
- Save rejection counts and sanitized error types to grounded_research_report.json
  and include it in always-uploaded production artifacts. Deduplicate canonical
  URLs and headlines; prioritize trusted sources before truncation.
- Offline regression tests cover sparse slates, no-extra-call success, stale and
  unverified records, duplicates, provider failure, exhausted recovery and trusted
  source selection. Live scheduled delivery and Spotify propagation still require
  a successful run; this change alone does not establish consistent delivery.

## September 4 listener-feedback revision

- Follow-up character direction shared by writer, punch-up and rescue: Rufus's
  understated British wit, reciprocal Jamie teasing, and Alex's varied returns
  to facts and consequences. Removed fixed British-phrase and comic-reaction
  quotas from the persona brief; counts elsewhere remain advisory, not proof of
  artistic success. The remembered cotton-socks phrase is a tone reference, not
  a recurring required line or a verified audience metric. No new paid calls.

- Alex and Rufus restored to `tts-1-hd` with onyx/fable, keeping speeds 1.01/0.99
  and gains +3.5/+0.3 dB. Jamie stays Grok Ursa with Celeste fallback, speed 1.05.
  HD does not accept per-line mood instructions; voice identity is the priority here.
- Primary sponsor and end tag are dry voice; sponsor and inherited segment/intro
  beds are suppressed under their copy. Existing music assets are unchanged.
- Silence trimming now retains small boundary margins rather than leaving long
  provider silences. No added tail padding; ordinary/reaction gaps are 100/70 ms.
- Writer guidance shortens opening exposition, requires responsive substantive
  handoffs, and preserves number/timeframe/announcement qualifiers. These are
  editorial instructions, not proof of performance in an ungenerated episode.
- Compulsory concessions and automatic fabricated Alex reversals removed. Natural
  disagreement or evidence-earned changes of view remain welcome.
- No replacement master or paid audition requested. Actual next-episode chemistry,
  accent, sponsor clarity, and publication still require post-run verification.

## Implemented and offline-tested

| Area | Implemented contract |
|---|---|
| Editorial | Top AI stories from 24–48 hours; one lead debate and supporting evidence across five segments. |
| Positioning | What changed. Who wins. What you do next. |
| Cast | Alex leads; Jamie is the fast, opinionated comic catalyst; Rufus is measured and British. |
| Jamie performance | Ursa/Celeste, distinct native laughs/chuckles/giggles; sponsor reads remain clean. Comic counts are advisory, not a laugh quota or a blocking gate. |
| Relationship | Predictions, positions, disagreements, running bits, outcomes and questions retained in memory. Only supplied real poll results are acknowledged. |
| Audience authenticity | Invented cast bits and clearly hypothetical questions are allowed. Invented fans, emails, reviews, vote totals and testimonials are not. |
| Production | Existing cold open/intro/outro assets; four transitions; dry sponsor read; alternating short end tag. |
| Closing | Final positions, synthesis, one audience question and one follow CTA. |
| Delivery | 25-minute target; 19–26 preferred, 30 maximum; same-day paid audio reused. |
| Metadata | Entity-led title, episode structure, listener promise, keywords, follow CTA and sponsor link. |
| Accessibility | Script transcript; chapters derived from measured assembly timings, with an explicit estimate fallback. |
| Clips | A measured 20–45 second contiguous exchange, MP3, caption file and captioned vertical MP4 from the paid master. Word-group captions are approximate. |
| Trailer | One-time 60–90 second assembly from actual cold open, music, cast intro, exchange, promise and CTA; existing trailer preserved. If required beats do not fit, report a warning and retain the prepared trailer script. |
| Reliability | Required audio/RSS checks remain; voice/creative/companion warnings do not discard paid audio. Artifacts retained for recovery. |
| Testing | Offline tests include actual synthetic-audio clip, captioned video and trailer exports without TTS calls. |
| Schedule | Monday–Friday at 10:17 UTC (03:17 Pacific daylight / 02:17 Pacific standard time). Requested start, not an exact delivery guarantee. |

## Not equivalent to completion

| Remaining check | Status at handoff |
|---|---|
| First revised scheduled episode and Spotify arrival | Must be verified after the scheduled run. |
| Final listening judgment: chemistry, pacing, accent, music, sponsor and shareability | Requires listening to the actual episode. |
| Spotify poll publication/result collection | Payload/handoff available; native dashboard work requires authenticated Creator access. |
| Spotify clip upload and trailer pinning | Local generated assets do not publish themselves to these surfaces. Requires Creator access and generated-asset review. |
| External social profile updates and automatic social distribution | Prepared copy available; publishing remains disabled. |
| Complete provider billing and retention attribution | Current telemetry is partial, not an invoice or Spotify analytics integration. |
| Outbound failure email | Not implemented/verified. GitHub notification preferences require account confirmation. |
| Automatic recovery of an uncommitted master from a previous failed runner | Artifacts are saved; restoration into a fresh runner is not automatic. |
| Current top-ten competitor ranking and controlled voice comparison | Not established by these code tests; do not claim a chart position or best-in-market performance. |

Do not regenerate a completed master for a packaging or subjective quality warning.
Do not count a generated poll, clip or trailer as published without platform evidence.

## September 4 scheduling incident

The scheduled production run [33881752206](https://github.com/aisimplify333/Daily-ai-News/actions/runs/33881752206)
started automatically at 14:05:46 UTC on the deployed `ba293b1` revision,
4 hours 5 minutes after the former 10:00 UTC schedule. It was not a manual run.
This proves the scheduler is active; it does not identify the reason for GitHub's delay.

The automatic run generated and committed the September 4 episode at 14:22:29 UTC
(`fa7d34e`): 24 minutes 26 seconds, all delivery checks passed, transcript and chapters
present, intro/outro and four transitions confirmed by audio QA. Jamie used Ursa
for all 48 Grok chunks with no fallback. These are production reports, not a
subjective listening endorsement. Public deployment and Spotify ingestion must
be checked separately. No duplicate production run was started.

The schedule is moved to minute 17, following GitHub's
[off-hour scheduling guidance](https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#schedule).
This mitigates a documented delay risk but cannot guarantee GitHub's start time.
Manual dispatch remains available, push-triggered production remains disabled,
and existing same-date audio is reused. Do not launch another run while the
scheduled episode is still running. Deploy the schedule adjustment only after
that run finishes, so its episode commit is not rejected by a concurrent push.
