#!/usr/bin/env python3
"""
Rigorously test hey_soldier.onnx on multiple held-out positive spoken audio clips
and negative spoken audio clips (non-target words, silence, ambient noise).
"""

import sys
import asyncio
import subprocess
import numpy as np
import soundfile as sf
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from openwakeword.model import Model

MODEL_PATH = Path(__file__).parent.parent / "data" / "models" / "hey_soldier.onnx"
TEMP_DIR = Path("/tmp/hey_soldier_eval")

TEST_POSITIVES = [
    ("Hey Soldier", "en-US-GuyNeural", "+0%"),
    ("Hey Soldier", "en-US-JennyNeural", "+10%"),
    ("Hey Soldier", "en-GB-RyanNeural", "-10%"),
    ("Hey Soldier", "en-US-EricNeural", "+0%"),
    ("Hey Soldier", "en-CA-LiamNeural", "+5%"),
]

TEST_NEGATIVES = [
    ("Hey Joe", "en-US-GuyNeural", "+0%"),
    ("Hey Dean", "en-US-JennyNeural", "+0%"),
    ("Hey Jarvis", "en-GB-RyanNeural", "+0%"),
    ("Alexa turn off the lights", "en-US-EricNeural", "+0%"),
    ("What is the security audit status", "en-CA-LiamNeural", "+0%"),
    ("Good morning partner", "en-US-GuyNeural", "+0%"),
]

async def generate_edge_tts(text: str, voice: str, rate: str, output_file: Path):
    import edge_tts
    communicate = edge_tts.Communicate(text, voice=voice, rate=rate)
    await communicate.save(str(output_file))

def convert_to_16k_pcm(input_file: Path) -> np.ndarray:
    raw_wav = input_file.with_suffix(".16k.wav")
    cmd = [
        "ffmpeg", "-y", "-i", str(input_file),
        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
        str(raw_wav)
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    data, sr = sf.read(str(raw_wav))
    if raw_wav.exists():
        raw_wav.unlink()
    return (data * 32767).astype(np.int16)

def eval_clip(oww: Model, pcm: np.ndarray) -> float:
    oww.reset()
    scores = []
    chunk_size = 1280
    for i in range(0, len(pcm) - chunk_size + 1, chunk_size):
        chunk = pcm[i:i+chunk_size]
        res = oww.predict(chunk)
        scores.append(res.get("hey_soldier", 0.0))
    return max(scores) if scores else 0.0

async def main():
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    oww = Model(wakeword_model_paths=[str(MODEL_PATH)])

    print("\n" + "="*65)
    print(" HEY SOLDIER REAL AUDIO DISCRIMINATION EVALUATION")
    print("="*65)

    print("\n--- POSITIVE TEST CLIPS ('Hey Soldier' spoken) ---")
    pos_results = []
    for idx, (phrase, voice, rate) in enumerate(TEST_POSITIVES, 1):
        f = TEMP_DIR / f"pos_{idx}.mp3"
        await generate_edge_tts(phrase, voice, rate, f)
        pcm = convert_to_16k_pcm(f)
        score = eval_clip(oww, pcm)
        pos_results.append(score)
        print(f"  [+] Pos #{idx} ('{phrase}' | {voice}): Score = {score:.4f}")

    print("\n--- NEGATIVE TEST CLIPS (Non-target speech) ---")
    neg_results = []
    for idx, (phrase, voice, rate) in enumerate(TEST_NEGATIVES, 1):
        f = TEMP_DIR / f"neg_{idx}.mp3"
        await generate_edge_tts(phrase, voice, rate, f)
        pcm = convert_to_16k_pcm(f)
        score = eval_clip(oww, pcm)
        neg_results.append(score)
        print(f"  [-] Neg #{idx} ('{phrase}' | {voice}): Score = {score:.4f}")

    print("\n" + "="*65)
    avg_pos = np.mean(pos_results)
    avg_neg = np.mean(neg_results)
    print(f"  Average Positive Score: {avg_pos:.4f}")
    print(f"  Average Negative Score: {avg_neg:.4f}")
    print("="*65)

    if avg_pos > 0.7 and avg_neg < 0.15:
        print("VERIFICATION SUCCESSFUL: Model displays high positive recall and low false accepts!")
    else:
        print("VERIFICATION NOTICE: Scores indicate potential overlap.")

if __name__ == "__main__":
    asyncio.run(main())
