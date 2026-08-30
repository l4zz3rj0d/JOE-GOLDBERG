# generate_joe_sample.py
"""
Script to synthesize a local Joe Goldberg voice sample using chatterbox / assets/joe_reference.wav.
Saves the generated sample to assets/joe_sample_monologue.wav for listening evaluation.
"""

import os
import sys
import time
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).parent.resolve()))

SAMPLE_TEXT = (
    "Hello operator. I have been keeping a close eye on your target. "
    "Every digital footprint tells a story... and I intend to read every single page."
)

OUTPUT_WAV = Path(__file__).parent / "assets" / "joe_sample_monologue.wav"
REF_WAV = Path(__file__).parent / "assets" / "joe_reference.wav"

def main():
    print("=" * 60)
    print("  Joe Goldberg Local Voice Synthesizer Sample Generator")
    print("=" * 60)

    if not REF_WAV.exists():
        print(f"[-] Error: Reference voice clip missing at {REF_WAV}")
        return

    print(f"[+] Reference voice clip loaded: {REF_WAV}")
    print(f"[+] Sample text to synthesize: '{SAMPLE_TEXT}'")
    print("[+] Starting zero-shot local voice synthesis...")

    start_time = time.time()
    try:
        from core.local_voice_clone import LocalVoiceClone
        vc = LocalVoiceClone(reference_path=str(REF_WAV))

        if vc.available:
            audio_bytes = vc.synthesize(SAMPLE_TEXT)
            if audio_bytes:
                with open(OUTPUT_WAV, "wb") as f:
                    f.write(audio_bytes)
                elapsed = time.time() - start_time
                print(f"[✓] Voice sample successfully synthesized in {elapsed:.2f}s!")
                print(f"[✓] Audio sample saved to: {OUTPUT_WAV.resolve()}")
                print("[✓] You can now play this file using your media player or a audio command.")
            else:
                print("[-] Synthesis returned empty audio bytes.")
        else:
            print("[-] Local voice clone engine not initialized properly.")
    except Exception as e:
        import traceback
        print(f"[-] Error during synthesis: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()
