#!/usr/bin/env python3
"""
Soldier Boy Voice Sample Synthesizer & Audio Player.
Generates speech audio using Fish Audio API (Voice ID: e81ae965a9a94ed69ff05eed7e7a57c7)
with 100% local zero-shot fallback (assets/soldierboy_reference.wav).
"""
import sys
import subprocess
from pathlib import Path

# Add project root directory to sys.path
PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from narrative.soldierboy_voice import SoldierBoyVoice

def main():
    print("=" * 60)
    print(" 🎙️  Soldier Boy Voice Generator & Audio Player")
    print("=" * 60)

    # Default monologue sample
    sample_text = (
        "I've been looking at your digital footprint. "
        "Every search, every login, every post... it all tells a story. "
        "And trust me, I'm paying very close attention."
    )

    if len(sys.argv) > 1:
        sample_text = " ".join(sys.argv[1:])

    print(f"\n[+] Script text to synthesize:\n    \"{sample_text}\"\n")
    print("[*] Initializing SoldierBoyVoice engine...")

    voice_engine = SoldierBoyVoice()

    print("[*] Synthesizing speech...")
    audio_bytes = voice_engine.narrate(sample_text)

    if not audio_bytes:
        print("[!] Failed to generate audio. Check Fish Audio API key or assets/soldierboy_reference.wav.")
        return

    ext = "mp3" if audio_bytes.startswith(b'\xff\xfb') or audio_bytes.startswith(b'ID3') else "wav"
    output_file = PROJECT_ROOT / f"soldierboy_voice_sample.{ext}"
    output_file.write_bytes(audio_bytes)
    print(f"[✓] Audio generated successfully! ({len(audio_bytes)} bytes)")
    print(f"[✓] Saved audio file to: {output_file}\n")

    print("[*] Playing audio...")
    players = [
        ["aplay", "-q", str(output_file)],
        ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(output_file)],
        ["vlc", "--intf", "dummy", "--play-and-exit", str(output_file)]
    ]

    played = False
    for cmd in players:
        try:
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if res.returncode == 0:
                played = True
                break
        except Exception:
            continue

    if played:
        print("[✓] Playback finished!")
    else:
        print(f"[!] Audio player binary finished or not available. You can manually listen to: {output_file}")

    print("\nTip: Pass custom text to synthesize your own line:")
    print("  python3 listen_joe_voice.py \"Hello there. What are you up to today?\"\n")

if __name__ == "__main__":
    main()
