"""Three bounded Gemini Jamie auditions; no production imports or publishing."""
import base64, io, json, os, time, wave
from pathlib import Path
import requests
from pydub import AudioSegment

OUT = Path("auditions/jamie_gemini_output")
VOICES = ["Sulafat", "Aoede", "Zephyr"]
TEXT = """Okay, this is the bit I actually love. Imagine turning a messy meeting transcript into a useful plan—owners, deadlines, and the decisions nobody quite made.
Rufus, don't give me that look. Yes, I checked the output.
Oh, you want to check my checking? Lovely. We've invented a committee.
But hang on. This part matters. If the tool guesses who agreed to do something, that isn't a shortcut. That's an argument waiting for Monday.
So give it one harmless sample. Ask it to flag missing information instead of filling the gaps. Then compare the plan with what was actually said.
See? Useful, without pretending it's magic.
And if it gives you twenty minutes back, don't spend them finding twenty more tasks. Have a cup of tea. Call someone.
Alex, you can bring us back to the news now. Rufus needs a moment to recover from agreeing with me."""
STYLE = """Jamie is an adult American female podcast co-host talking with two trusted friends, Alex and the dry British Rufus. Close-microphone conversation, not an advertisement or presenter monologue. Start with genuine delighted discovery and brisk rhythm. Tease Rufus warmly on 'that look'; pause briefly for his imagined reaction. Give a small spontaneous chuckle before 'Lovely', and amused understated sarcasm on 'committee'. Shift into lower, serious concern on 'But hang on'. Explain the practical steps clearly with varying phrase lengths and emphasis. Slow and soften for 'Have a cup of tea. Call someone.' Finish with a smiling, playful challenge. Keep laughter brief, intelligible, not forced. Use natural pitch and tempo variation; do not shout. Speak only the transcript. Never read acting instructions."""
def main():
    if os.getenv("GITHUB_RUN_ATTEMPT", "1") != "1":
        raise SystemExit("Paid reruns disabled. Use preserved takes.")
    OUT.mkdir(parents=True, exist_ok=True)
    report = {"model": "gemini-3.8-flash-tts", "production_changed": False,
              "fictional_rehearsal": True, "listened": False,
              "maximum_requests": 3, "retries": 0, "takes": []}
    (OUT / "transcript.txt").write_text(TEXT)
    (OUT / "direction.txt").write_text(STYLE)
    for index, voice in enumerate(VOICES):
        if index:
            time.sleep(20)
        entry = {"voice": voice, "characters": len(TEXT)}
        try:
            response = requests.post(
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash-tts:generateContent",
                headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
                json={"contents": [{"role": "user", "parts": [{"text": TEXT, "speech_metadata": {"style": STYLE}}]}],
                      "generationConfig": {"responseModalities": ["AUDIO"],
                                           "speechConfig": {"voiceConfig": {"voice": voice}}}},
                timeout=(10, 180))
            if not response.ok:
                raise RuntimeError("Gemini HTTP " + str(response.status_code))
            parts = response.json()["candidates"][0]["content"]["parts"]
            inline = next(p["inlineData"] for p in parts if "inlineData" in p)
            data = base64.b64decode(inline["data"])
            (OUT / (voice + ".provider_audio")).write_bytes(data)
            if data.startswith(b"RIFF"):
                clip = AudioSegment.from_file(io.BytesIO(data), format="wav")
            elif "audio/L16" in inline.get("mimeType", "") and "rate=24000" in inline.get("mimeType", ""):
                clip = AudioSegment(data=data, sample_width=2, frame_rate=24000, channels=1)
            else:
                raise RuntimeError("Unsupported provider audio format; original preserved")
            if not 15000 < len(clip) < 120000 or clip.dBFS == float("-inf"):
                raise RuntimeError("Invalid audio duration or silence; original preserved")
            clip.export(OUT / (voice + ".wav"), format="wav").close()
            clip.export(OUT / (voice + ".mp3"), format="mp3", bitrate="192k",
                        parameters=["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"]).close()
            entry.update(status="ok", seconds=len(clip)/1000, mp3=voice+".mp3")
        except Exception as error:
            entry.update(status="failed", error=str(error) if isinstance(error, RuntimeError) else type(error).__name__)
        report["takes"].append(entry)
        (OUT / "manifest.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report))
    if not all(x["status"] == "ok" for x in report["takes"]):
        raise SystemExit("Partial audition: inspect preserved takes; no automatic retries.")
if __name__ == "__main__":
    main()
