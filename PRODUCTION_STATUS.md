# The AI Edge production handoff

Release prepared September 3 Pacific / September 4 UTC, 2026.

## September 9 editorial improvement

- September 9 scheduled run 34345922884 passed research and wrote a script, but
  failed before TTS after the second fact repair. The loop used the pre-repair
  negative verdict to reject the newly corrected script. Fixed by allowing two
  repair rounds followed by a verification-only third audit. A clean first audit
  still costs one call; unresolved errors and unmatched corrections still fail.
- Save corrected-script checkpoints and upload original/repaired fact candidates,
  the fact report and grounded slate even on failure. The previous workflow omitted
  these artifacts, limiting recovery of its paid writing work.
- PENDING DEPLOYMENT: user explicitly approved dynamic audio pacing, but automatic
  approval review rejected main.py upload even after safer defaults were prepared.
  The following remains local and is NOT active in this release: existing
  pitch-preserving assembly applies mood speed multipliers of 0.97–1.05 and
  level deltas of -0.3 to +0.4 dB to Alex/Rufus editorial chunks. Jamie and sponsor
  chunks remain at baseline. Disable DYNAMIC_PERFORMANCE_ENABLED to revert.
  Actual effects are logged in measured timeline markers. No extra TTS calls,
  voice/model switches, ElevenLabs activation or new music. This is pacing/level
  contrast, not native HD emotional direction or proof of a listening score.
- Also local only: aligned standalone main.py defaults with the production workflow: OpenAI backend,
  automatic brandkit generation off, ElevenLabs dialogue off. This removes legacy
  opt-out defaults; enabling specialty generation still requires explicit settings.
- Scheduler fired around 11:30 UTC despite requested 06:17 UTC. This code repair
  addresses the fact-loop failure, not GitHub scheduler delays or Spotify timing.

- Following the September 8 transcript review: merge matching event keys and
  matching named company/product pairs so corroborating Muse coverage cannot
  fill three slots. This heuristic may merge separate same-product updates;
  distinct-event live search success still needs verification.
- One assembly-owned closing loop removes model-written poll invitations/options
  and follow CTAs. No claims of native Spotify poll publication or future results.
- Chapter 3 now describes lead-story costs/tradeoffs; chapter 4 describes supporting
  stories, rather than assigning titles from unrelated story-array positions.
- Shared writer/punch-up/rescue directions prohibit the Alex-concession holiday bit,
  repetitive argument padding, unsupported motives and absence-of-evidence claims.
- Enabled existing pre-TTS grounded fact audit, capped at two passes. Extra research
  spend is intentional; unresolved critical factual errors stop before voices.
  Creative warnings still do not discard a paid master. No voice/music changes.
- This release does not establish an 8.5/10 listening score. Next generated audio,
  actual factual corrections, editorial variety and publication must be reviewed.

## September 8 research recovery

- Follow-up to failed run 34284168953: offline checks and preflight passed;
  primary returned two usable stories and refill added one. Thirteen candidates
  were outside 48 hours. No script or TTS generation ran.
- Connected the previously ignored RSS pool to grounded discovery. Only fresh,
  dated, deduplicated headlines (maximum 40) become search leads, never verified
  facts. Original publication dates and article facts still require verification.
- Replaced the inclusive calendar-date prompt with the exact rolling UTC window.
  Recovery receives rejection reasons and reported dates. One final targeted pass
  is allowed only with fresh discovery leads: maximum four provider requests
  including primary fallback, excluding SDK retries; no added calls on success.
- Removed the legacy fabricated TestWire item when RSS is empty. Grounded search
  remains responsible for finding real stories. Empty research still stops before TTS.
- Regression coverage reproduces the two-plus-one stale-result failure pattern and
  exercises the installed writer selector through research using mocked providers.
  Live provider search success, completed audio and Spotify arrival remain unproven.

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
| Schedule | Monday–Friday at 06:17 UTC, targeting delivery by 06:30 America/New_York. Requested start, not an exact delivery guarantee. |

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
