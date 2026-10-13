# The AI Edge — release evidence

A successful generation job is not proof of listener-visible delivery or an engaging performance.
Keep these evidence types separate. Do not invent a listening rating from test counts or voice prompts.

| Standard | Daily evidence |
|---|---|
| Three distinct, well-supported stories from the rolling 48-hour window | `grounded_research_report.json`, `grounded_story_slate.json`; explicit source URLs, dates, rejections, and listener frames |
| Useful discovery and possibility alongside the strongest lead; no compulsory optimistic story | `final_acceptance_report.json`: `useful_discovery`, with actual script evidence |
| Reciprocal banter, warmth, dry British wit, Alex participating, Jamie curious and engaged | Final acceptance checks `responsive_banter`, `cast_warmth` assess the whole conversation with actual script evidence. No joke quotas or required exchange template. The shared three-friends brief applies to writing, revision and performance; actual audio review remains separate |
| Rufus's clearly imagined global dispatch: supported setting, studio interaction, dry reply and payoff | `rufus_scene`, `editorial_contract_report.json`, timed assembly markers; 100–220 words is an advisory planning band |
| One earned ending per story and one closing follow invitation | `single_endings`, `script_aircheck.json` |
| Material factual errors and numerical comparisons corrected before TTS | `grounded_fact_check.json`; last audit must evaluate the actual repaired script |
| Scene-specific direction reaches each voice request | `performance_plan.json`, `hybrid_tts_report.json`, `listener_review_report.json` |
| Consistent approved daily cast | Alex: Gemini Charon; Jamie: Grok Ursa; Rufus: Gemini Iapetus. ElevenLabs specialty assets do not replace the cast |
| Reviewed specialty audio and signature Rufus entrance | Hashed `specialty_audio/library/manifest.json` assets; timeline records the actual entrance; missing optional effects preserve clean dialogue |
| Runtime and pacing | Planning range 3,150–4,800 words; target 25 minutes; 19–30 minute delivery window with existing 30-second minimum grace |
| Encoded-master loudness and quiet spans | `audio_engineering_report.json`: −16 ±1 LUFS target, encoded true peak no higher than −1 dBTP; contextual review of quiet spans |
| Story transitions, outro, sponsor placement and chapters | `audio_qa_report.json`, timeline, `sponsor_delivery_report.json`, chapter sidecar |
| What the rendered voices actually sound like | `rendered_audio_review.json`: full-master coverage, clip timestamps, audio hash, observed defects and model ratings. This is automated review, never human approval |
| Public release | `public_delivery_report.json`: exactly one dated RSS enclosure, dated page containing its audio URL, and an MP3 response. Spotify ingestion and human playback are separate checks |

## Recovery behavior

- Source recovery retains valid candidates and requests specific missing evidence; it does not change old dates or accept homepages.
- An unusable factual correction gets one alternate-provider recovery request; a pass-only response cannot erase the concern. Any applied edit is audited again.
- Two failed scheduled attempts with no episode produce a failed workflow, not a green skipped release.
- Only files generated during the current run enter the diagnostic artifact bundle.
- Sparse checkout omits historical MP3/MP4 files and old voice cache from the runner, while preserving them in GitHub.
- A reviewed transcript, direction requests, technical measurements, model audio review, and a human entertainment assessment are different claims. The desired 8.5+/10 audience experience must be judged from the finished show.
