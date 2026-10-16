# October 15 editorial revision

North star: come for consequential AI stories; return for Alex, Jamie and Rufus.

Prepared revision, not a claim of improved listening quality or chart position.
Preserves the cast, three-story structure, signature opening/closing and existing masters.

- Scene editor gets at most one corrective request per rejected scene, receiving the original, rejected candidate and exact rejection reason. Same numerical-token, word-budget and structural checks run again; failed repair retains the original. Successful scenes are not retried. Maximum six scene-editor application calls (three initial plus three corrective), excluding provider SDK retries. Provider errors preserve the scene without a new application request. Attempts remain in the report.
- Shared writing direction prioritizes responsive teasing, substantive differences, changing emotional states and new information rather than repeated conclusions. No forced jokes, concessions, fabricated experiences or invented reporting. Explicitly prohibits spoken self-congratulation about the format and places the farewell last.
- Title planning asks for concrete stakes accessible to a new listener, with a cold open and payoff aligned to the same sourced question. Existing title validation remains; this is not proof the next generated title will be strong.
- Performance planning follows emotional changes rather than fixed character roles. Existing Gemini directions specify restrained rising curiosity/delight and falling concern/dry endings. Gemini cache direction version increments so new directions do not reuse old takes. Grok's existing expressive controls remain; no unsupported prosody controls added.
- Explicitly imagined tech-company scenes can select the existing approved office atmosphere. Hash, approval, mix-level, duration and fallback rules remain unchanged. Global-desk-only speech does not automatically acquire an invented location.

Validation: 31 targeted offline tests passed, including corrective acceptance, repeated rejection, no retry on success, provider payloads and actual synthetic sound mixing/corruption fallback. Modified modules compile and git diff --check passes. No model or TTS calls; no episode regeneration or deployment.

Next proof: source-grounded script rehearsal, actual rendered performance review, title/cold-open payoff check, and final-master sound verification. Chemistry must be heard; direction labels and tests are not entertainment scores.

## October 16 sound-design revision: audition brief

Status: creative specification only; no new audio commissioned, heard or enabled.
Daniel requested a stronger location identity for Rufus, retained story transitions and possible ElevenLabs background music.

### Three distinct functions

- Story transition: preserve the approved transition as the reference. A short, clean chapter change; never reuse the Rufus location cue for ordinary story changes.
- Rufus on location: a dedicated 2–3 second departure/arrival signature. A soft recorder click and brief spatial movement resolve into a warm two-note motif; dry wit without a comedy horn. Reserve this cue for explicitly imagined location scenes, not every Rufus contribution. The dialogue must establish that the scene is imagined, never imply actual field reporting.
- Location atmosphere: setting-matched office, street, factory or other approved ambience introduced beneath the first scene sentence, then faded. No arbitrary city noise under a global-desk report. No intelligible background speech. Keep the existing approved-asset/hash safeguards.

Candidate ElevenLabs sound-effect prompt (one bounded candidate before evaluation):
"Original 2.5-second podcast location entrance: soft field-recorder click, a quick airy spatial sweep, then two warm wooden mallet notes with a dry playful finish. Suggest stepping out of a studio into a scene. Intimate, crisp on phone speakers, short clean tail. No horn, brass, siren, alarm, voices, laughter, crowd, cinematic boom or existing melody."

### Optional music audition

Commission separately from the sound-effect cue, using the supported ElevenLabs music interface after checking its current request and allowance requirements. The existing studio builder only calls sound generation; it does not commission background music.

Creative prompt:
"Original understated instrumental podcast bed, 30 seconds: warm electric piano, muted plucked bass and sparse brushed percussion; conversational, curious, lightly mischievous, approximately 94 BPM. Plenty of empty space for speech, no prominent lead melody, vocals, dramatic risers, brass, comedy stings or imitation of an existing track. Clean edit points and a natural ending."

First audition uses a brief welcome/title setup and a story handoff. Preserve the original signature opening and closing. Keep the cold-open exchange dry initially; compare music only if it improves the hook. Music drops out before sustained disagreement, sensitive human consequences, or a dry punchline. Do not put a continuous bed under the whole episode.

Start speech-underlay roughly 18–22 dB below measured speech, then adjust by listening; this is an audition starting point, not a loudness guarantee. Never layer music, location atmosphere and a cue over the same spoken syllables merely to make the mix feel busy.

### Concrete review sequence

1. Use identical existing cast excerpts for an A/B: current entrance versus candidate location cue plus matched ambience.
2. Include the preceding host handoff, Rufus's first sentence, the first response from another cast member and the return to studio. Audition the dramatic flow, not just isolated effects.
3. Compare dry versus music-supported welcome/handoff at matched perceived loudness. Check headphones, a phone speaker and mono; every consonant and punchline must survive.
4. Reject a candidate that still reads as a generic notification/horn, sounds like an alarm, obscures speech, leaves an awkward pause, or makes an imagined location sound like factual field reporting.
5. Retain cue timestamps, asset hashes, request/cost ledger and encoded-master measurements. Automated audio review is supplementary; do not label it human listening or proof of chemistry.

Implementation caution: the current studio workflow checks out main and writes its generated package back to main; the builder can enable assets after automated review. Do not use that workflow unchanged for this exploratory audition. Prepare a candidate-only output directory and artifact-only rehearsal path first. The completed commission ledger reuses the old source, so changing its prompt alone will not generate the requested new cue. Keep separate candidate identity and ledger; preserve the existing paid assets.
