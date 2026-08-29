#!/usr/bin/env /home/joe/Project-Hellhound/JOE-GOLDBERG/joe-env/bin/python3
"""
Diagnostic script to test real-time speech recognition and "Joe" wake-phrase parsing.
Run this script from your terminal:
    ./test_joe_wake.py
OR
    joe-env/bin/python3 test_joe_wake.py
"""

import os
import sys
import time
import re
import subprocess

# Ensure virtualenv site-packages are loaded
venv_site = os.path.join(os.path.dirname(__file__), "joe-env", "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages")
if os.path.exists(venv_site) and venv_site not in sys.path:
    sys.path.insert(0, venv_site)

try:
    import speech_recognition as sr
except ImportError:
    print("[ERROR] SpeechRecognition module not found in current Python environment.")
    print("Run with joe-env:")
    print("    joe-env/bin/python3 test_joe_wake.py")
    sys.exit(1)

def test_mic_sources():
    print("=" * 60)
    print("  JOE GOLDBERG VOICE DIAGNOSTIC TEST")
    print("=" * 60)

    print("\n1. Testing system audio capture tools...")
    tools = ["ffmpeg", "arecord", "rec"]
    for t in tools:
        path = subprocess.run(["which", t], capture_output=True, text=True).stdout.strip()
        if path:
            print(f"   ✓ {t}: {path}")
        else:
            print(f"   ✗ {t}: NOT FOUND")

    print("\n2. Initializing Speech Recognizer...")
    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 300
    recognizer.dynamic_energy_threshold = True

    print("\n3. Starting Real-Time Voice Loop...")
    print("   -> Speak into your microphone!")
    print("   -> Try saying: 'Joe tell me a story' or 'Hey Joe search github'")
    print("   -> Press Ctrl+C to stop testing.\n")
    print("-" * 60)

    wav_path = "/tmp/joe_diagnostic_test.wav"

    count = 0
    try:
        while True:
            count += 1
            print(f"\r[Frame {count:03d}] 🎤 Listening (3 seconds)... ", end="", flush=True)

            rec_cmds = [
                ["arecord", "-D", "default", "-f", "S16_LE", "-r", "16000", "-c", "1", "-d", "3", wav_path],
                ["arecord", "-D", "plughw:1,0", "-f", "S16_LE", "-r", "16000", "-c", "1", "-d", "3", wav_path],
                ["ffmpeg", "-y", "-f", "alsa", "-i", "default", "-ar", "16000", "-ac", "1", "-t", "3", wav_path],
                ["ffmpeg", "-y", "-f", "pulse", "-i", "default", "-ar", "16000", "-ac", "1", "-t", "3", wav_path]
            ]
            recorded = False
            for cmd in rec_cmds:
                proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                try:
                    proc.wait(timeout=4)
                    if os.path.exists(wav_path) and os.path.getsize(wav_path) > 1000:
                        recorded = True
                        break
                except Exception:
                    proc.kill()

            if not recorded or not os.path.exists(wav_path) or os.path.getsize(wav_path) == 0:
                print("No audio data recorded!")
                time.sleep(0.5)
                continue

            try:
                with sr.AudioFile(wav_path) as source:
                    audio = recognizer.record(source)
                    text = recognizer.recognize_google(audio).strip()

                if text:
                    print(f"\n\n[HEARD SPEECH]: \"{text}\"")
                    match = re.search(r'\b(hey\s+)?joe\b\s*,?\s*(.*)', text, re.IGNORECASE)
                    if match:
                        prompt_after_joe = match.group(2).strip()
                        print("  ✓ WAKE WORD DETECTED! ('Joe')")
                        if prompt_after_joe:
                            print(f"  🎯 PROMPT AFTER 'JOE': \"{prompt_after_joe}\"")
                        else:
                            print("  ⚠️ Wake word 'Joe' detected, but no prompt followed.")
                    else:
                        print(f"  ℹ️ Speech recognized, but 'Joe' wake-word was not in phrase.")
                    print("-" * 60)
            except sr.UnknownValueError:
                pass
            except sr.RequestError as e:
                print(f"\n[STT API ERROR]: {e}")
            except Exception as e:
                print(f"\n[ERROR]: {e}")

            time.sleep(0.2)

    except KeyboardInterrupt:
        print("\n\nStopped diagnostic test.")
        if os.path.exists(wav_path):
            try:
                os.remove(wav_path)
            except Exception:
                pass

if __name__ == "__main__":
    test_mic_sources()
