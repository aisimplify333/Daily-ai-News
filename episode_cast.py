"""Choose a consistent cast before assembly, preserving generated Gemini assets."""
from pathlib import Path
import tempfile

def prepare(router, render_items, chunker, chunk_limit):
    router._RT['episode_provider'] = {}
    router._RT['prepared_audio'] = {}
    targets = [s for s in ('ALEX', 'RUFUS') if router._provider_for(s) == 'gemini']
    if not targets:
        return
    staged = {}
    calls_start = len(router.STATS['calls'])
    # Kept outside assembly's scratch folder, which main clears before mixing.
    folder = Path(tempfile.mkdtemp(prefix='ai-edge-cast-'))
    try:
        for speaker, text in render_items:
            if speaker not in targets:
                continue
            for chunk in chunker(text, max_chars=chunk_limit(speaker)):
                key = (speaker, chunk)
                if key in staged:
                    continue
                path = folder / f'{len(staged):04d}.mp3'
                router._gemini_tts_to_file(chunk, speaker, router.infer_mood(chunk, speaker), path)
                if not path.exists() or path.stat().st_size <= 1000:
                    raise RuntimeError('Prepared take missing or invalid')
                staged[key] = str(path)
        router._RT['prepared_audio'] = staged
        router.STATS['episode_cast'] = {'decision': 'gemini_complete', 'prepared_takes': len(staged)}
    except Exception as exc:
        # No audio has entered assembly yet. Use the established fallback cast
        # for the entire episode, including its opening, without rewriting news.
        router._RT['episode_provider'] = {speaker: 'openai' for speaker in targets}
        router.STATS['episode_cast'] = {
            'decision': 'whole_episode_openai_fallback', 'hosts': targets,
            'prepared_takes_preserved': len(staged), 'reason': str(exc)[:500]}
        router._safe_print('Gemini unavailable: selecting consistent OpenAI fallback cast before assembly.')
    finally:
        router.STATS['cast_preparation_calls'] = router.STATS['calls'][calls_start:]
        del router.STATS['calls'][calls_start:]
        router._write_report()
