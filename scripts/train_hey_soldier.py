#!/usr/bin/env python3
"""
Full openWakeWord Training Pipeline for 'Hey Soldier' Wake Word Model.

Steps:
1. Synthesize real positive audio clips ("Hey Soldier") across multiple TTS voices, speeds, and pitches (edge-tts, gTTS, espeak).
2. Synthesize real negative audio clips (non-target words, random speech, silence, background noise) across multiple voices.
3. Extract real openWakeWord acoustic embeddings (16x96 feature frames) using AudioFeatures.embed_clips().
4. Train PyTorch binary classifier (MLP) on the real acoustic embeddings.
5. Export trained weights to ONNX format (data/models/hey_soldier.onnx).
6. Verify model performance on real test audio clips (positive vs negative).
"""

import os
import sys
import glob
import shutil
import asyncio
import subprocess
import numpy as np
import soundfile as sf
import torch
import torch.nn as nn
import torch.optim as optim
import onnx
from onnx import helper, TensorProto
from pathlib import Path

# Ensure joe-env modules are importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from openwakeword.utils import AudioFeatures
from openwakeword.model import Model

TEMP_DIR = Path("/tmp/hey_soldier_dataset")
POS_DIR = TEMP_DIR / "positive"
NEG_DIR = TEMP_DIR / "negative"
MODEL_OUTPUT_PATH = Path(__file__).parent.parent / "data" / "models" / "hey_soldier.onnx"

EDGE_VOICES = [
    "en-US-GuyNeural", "en-US-ChristopherNeural", "en-US-EricNeural",
    "en-US-JennyNeural", "en-US-AriaNeural", "en-GB-RyanNeural",
    "en-GB-SoniaNeural", "en-AU-WilliamNeural", "en-CA-LiamNeural"
]

RATES = ["-15%", "-5%", "+0%", "+5%", "+15%"]
PITCHES = ["-10Hz", "+0Hz", "+10Hz"]

NEGATIVE_TEXTS = [
    "Hey Joe", "Hey Dean", "Hey Jarvis", "Hey Siri", "Alexa", "OK Google",
    "Soldier", "Hey", "Hello", "What is up", "Good morning", "System status",
    "Security audit", "Command line", "Terminal output", "Operating system",
    "Computer start", "Open terminal", "Play music", "Turn on lights",
    "Tell me a joke", "What is the weather today", "Execute payload"
]

async def generate_edge_tts(text: str, voice: str, rate: str, pitch: str, output_file: Path):
    """Generate audio using edge-tts."""
    try:
        import edge_tts
        communicate = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch)
        await communicate.save(str(output_file))
    except Exception as e:
        print(f"edge-tts error for {voice}: {e}")

def generate_espeak(text: str, voice: str, pitch: int, speed: int, output_file: Path):
    """Generate audio using espeak."""
    try:
        subprocess.run(
            ["espeak", "-v", voice, "-p", str(pitch), "-s", str(speed), "-w", str(output_file), text],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
        )
    except Exception:
        pass

def convert_to_16k_pcm(input_file: Path) -> np.ndarray:
    """Convert audio file to 16kHz mono int16 PCM array using ffmpeg."""
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
        
    pcm_int16 = (data * 32767).astype(np.int16)
    return pcm_int16

async def build_dataset():
    """Build positive and negative audio dataset."""
    if TEMP_DIR.exists():
        shutil.rmtree(TEMP_DIR)
    POS_DIR.mkdir(parents=True, exist_ok=True)
    NEG_DIR.mkdir(parents=True, exist_ok=True)

    print("[1/5] Synthesizing positive 'Hey Soldier' audio clips...")
    count = 0
    # 1. Edge TTS Positives
    for voice in EDGE_VOICES:
        for rate in RATES[:3]:
            for pitch in PITCHES[:2]:
                mp3_path = POS_DIR / f"pos_edge_{count}.mp3"
                await generate_edge_tts("Hey Soldier", voice, rate, pitch, mp3_path)
                count += 1
    
    # 2. Espeak Positives
    for voice in ["en-us", "en-uk", "en-scottish", "en-north"]:
        for pitch in [40, 50, 60]:
            for speed in [130, 150, 170]:
                wav_path = POS_DIR / f"pos_espeak_{count}.wav"
                generate_espeak("Hey Soldier", voice, pitch, speed, wav_path)
                count += 1
                
    print(f"Generated {count} positive audio samples.")

    print("[2/5] Synthesizing negative audio clips and background noise...")
    neg_count = 0
    # 1. Edge TTS Negatives
    for text in NEGATIVE_TEXTS:
        voice = EDGE_VOICES[neg_count % len(EDGE_VOICES)]
        mp3_path = NEG_DIR / f"neg_edge_{neg_count}.mp3"
        await generate_edge_tts(text, voice, "+0%", "+0Hz", mp3_path)
        neg_count += 1

    # 2. Espeak Negatives
    for text in NEGATIVE_TEXTS:
        wav_path = NEG_DIR / f"neg_espeak_{neg_count}.wav"
        generate_espeak(text, "en-us", 50, 150, wav_path)
        neg_count += 1

    # 3. Synthetic noise & silence samples
    sr = 16000
    for i in range(20):
        duration = np.random.uniform(1.0, 2.5)
        # Random noise / silence
        noise_type = i % 3
        if noise_type == 0:
            audio = np.random.randn(int(sr * duration)) * 0.005 # Quiet ambient room noise
        elif noise_type == 1:
            audio = np.random.randn(int(sr * duration)) * 0.02  # Medium noise
        else:
            audio = np.zeros(int(sr * duration))                # Pure silence
            
        noise_path = NEG_DIR / f"neg_noise_{i}.wav"
        sf.write(str(noise_path), audio, sr)
        neg_count += 1

    print(f"Generated {neg_count} negative audio samples.")

def extract_features():
    """Pass all audio clips through openWakeWord AudioFeatures embedding extractor."""
    print("[3/5] Extracting openWakeWord acoustic embeddings...")
    af = AudioFeatures()

    pos_files = sorted(list(POS_DIR.glob("*.*")))
    neg_files = sorted(list(NEG_DIR.glob("*.*")))

    X_pos_list = []
    for f in pos_files:
        try:
            pcm = convert_to_16k_pcm(f)
            if len(pcm) < 3200: # Need at least 200ms
                continue
            batch_pcm = np.expand_dims(pcm, 0)
            emb = af.embed_clips(batch_pcm) # Shape (1, N_frames, 96)
            if emb.shape[1] >= 16:
                # Extract 16-frame windows
                for i in range(0, emb.shape[1] - 16 + 1, 2):
                    window = emb[0, i:i+16, :] # (16, 96)
                    X_pos_list.append(window.flatten())
            elif emb.shape[1] > 0:
                # Pad to 16 frames if shorter
                padded = np.zeros((16, 96), dtype=np.float32)
                padded[:emb.shape[1], :] = emb[0, :, :]
                X_pos_list.append(padded.flatten())
        except Exception as e:
            print(f"Skipping {f.name}: {e}")

    X_neg_list = []
    for f in neg_files:
        try:
            pcm = convert_to_16k_pcm(f)
            if len(pcm) < 3200:
                continue
            batch_pcm = np.expand_dims(pcm, 0)
            emb = af.embed_clips(batch_pcm)
            if emb.shape[1] >= 16:
                for i in range(0, emb.shape[1] - 16 + 1, 2):
                    window = emb[0, i:i+16, :]
                    X_neg_list.append(window.flatten())
            elif emb.shape[1] > 0:
                padded = np.zeros((16, 96), dtype=np.float32)
                padded[:emb.shape[1], :] = emb[0, :, :]
                X_neg_list.append(padded.flatten())
        except Exception as e:
            print(f"Skipping {f.name}: {e}")

    X_pos = np.array(X_pos_list, dtype=np.float32)
    X_neg = np.array(X_neg_list, dtype=np.float32)

    print(f"Extracted {len(X_pos)} positive feature frames, {len(X_neg)} negative feature frames.")
    return X_pos, X_neg

class HeySoldierNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.fc1 = nn.Linear(1536, 32)
        self.relu = nn.ReLU()
        self.fc2 = nn.Linear(32, 1)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        x = x.view(-1, 1536)
        x = self.fc1(x)
        x = self.relu(x)
        x = self.fc2(x)
        x = self.sigmoid(x)
        return x

def train_and_export_onnx(X_pos, X_neg):
    """Train PyTorch model on real extracted embeddings and export ONNX model graph."""
    print("[4/5] Training classifier on real openWakeWord embeddings...")

    # Create dataset
    y_pos = np.ones((len(X_pos), 1), dtype=np.float32)
    y_neg = np.zeros((len(X_neg), 1), dtype=np.float32)

    X = np.vstack([X_pos, X_neg])
    y = np.vstack([y_pos, y_neg])

    # Shuffle dataset
    indices = np.arange(len(X))
    np.random.shuffle(indices)
    X = torch.tensor(X[indices], dtype=torch.float32)
    y = torch.tensor(y[indices], dtype=torch.float32)

    model = HeySoldierNet()
    criterion = nn.BCELoss()
    optimizer = optim.Adam(model.parameters(), lr=0.005)

    model.train()
    for epoch in range(120):
        optimizer.zero_grad()
        outputs = model(X)
        loss = criterion(outputs, y)
        loss.backward()
        optimizer.step()
        if (epoch + 1) % 30 == 0:
            print(f"  Epoch {epoch+1}/120 - Loss: {loss.item():.4f}")

    model.eval()

    # Extract weights to construct clean ONNX graph matching openWakeWord spec
    W1 = model.fc1.weight.detach().numpy().T # (1536, 32)
    b1 = model.fc1.bias.detach().numpy()      # (32,)
    W2 = model.fc2.weight.detach().numpy().T # (32, 1)
    b2 = model.fc2.bias.detach().numpy()      # (1,)

    input_tensor = helper.make_tensor_value_info('onnx::Flatten_0', TensorProto.FLOAT, [1, 16, 96])
    output_tensor = helper.make_tensor_value_info('output', TensorProto.FLOAT, [1, 1])

    W1_init = helper.make_tensor('W1', TensorProto.FLOAT, [1536, 32], W1.flatten().tolist())
    b1_init = helper.make_tensor('b1', TensorProto.FLOAT, [32], b1.tolist())
    W2_init = helper.make_tensor('W2', TensorProto.FLOAT, [32, 1], W2.flatten().tolist())
    b2_init = helper.make_tensor('b2', TensorProto.FLOAT, [1], b2.tolist())

    flatten_node = helper.make_node('Flatten', inputs=['onnx::Flatten_0'], outputs=['flattened'], axis=1)
    gemm1_node = helper.make_node('Gemm', inputs=['flattened', 'W1', 'b1'], outputs=['hidden'], alpha=1.0, beta=1.0)
    relu_node = helper.make_node('Relu', inputs=['hidden'], outputs=['relu_out'])
    gemm2_node = helper.make_node('Gemm', inputs=['relu_out', 'W2', 'b2'], outputs=['logits'], alpha=1.0, beta=1.0)
    sigmoid_node = helper.make_node('Sigmoid', inputs=['logits'], outputs=['output'])

    graph_def = helper.make_graph(
        [flatten_node, gemm1_node, relu_node, gemm2_node, sigmoid_node],
        'hey_soldier_wake_word_model',
        [input_tensor],
        [output_tensor],
        [W1_init, b1_init, W2_init, b2_init]
    )

    model_def = helper.make_model(graph_def, producer_name='soldierboy-openwakeword')
    model_def.opset_import[0].version = 14

    MODEL_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    onnx.checker.check_model(model_def)
    onnx.save(model_def, str(MODEL_OUTPUT_PATH))
    print(f"Saved real trained ONNX model to: {MODEL_OUTPUT_PATH}")

async def verify_onnx_model():
    """Verify model performance on freshly synthesized test audio clips."""
    print("[5/5] Testing ONNX model on held-out real spoken audio clips...")

    # Generate held-out test clips
    test_pos_file = TEMP_DIR / "test_positive_spoken.mp3"
    test_neg_file = TEMP_DIR / "test_negative_spoken.mp3"

    await generate_edge_tts("Hey Soldier", "en-US-SteffanNeural", "+0%", "+0Hz", test_pos_file)
    await generate_edge_tts("What is the security status", "en-US-SteffanNeural", "+0%", "+0Hz", test_neg_file)

    pos_pcm = convert_to_16k_pcm(test_pos_file)
    neg_pcm = convert_to_16k_pcm(test_neg_file)

    oww = Model(wakeword_model_paths=[str(MODEL_OUTPUT_PATH)])

    # Predict positive clip
    oww.reset()
    pos_scores = []
    chunk_size = 1280
    for i in range(0, len(pos_pcm) - chunk_size + 1, chunk_size):
        chunk = pos_pcm[i:i+chunk_size]
        res = oww.predict(chunk)
        pos_scores.append(res.get('hey_soldier', 0.0))

    # Predict negative clip
    oww.reset()
    neg_scores = []
    for i in range(0, len(neg_pcm) - chunk_size + 1, chunk_size):
        chunk = neg_pcm[i:i+chunk_size]
        res = oww.predict(chunk)
        neg_scores.append(res.get('hey_soldier', 0.0))

    max_pos = max(pos_scores) if pos_scores else 0.0
    max_neg = max(neg_scores) if neg_scores else 0.0

    print("\n" + "="*55)
    print("REAL AUDIO VERIFICATION RESULTS:")
    print(f"  Positive Clip ('Hey Soldier' spoken) Peak Score: {max_pos:.4f}")
    print(f"  Negative Clip ('What is security status') Peak Score: {max_neg:.4f}")
    print("="*55)

    if max_pos > 0.4 and max_neg < 0.2:
        print("SUCCESS: Model cleanly discriminates 'Hey Soldier' from negative speech!")
    else:
        print("NOTICE: Scores require further tuning, but pipeline executed on real speech.")

async def main():
    await build_dataset()
    X_pos, X_neg = extract_features()
    train_and_export_onnx(X_pos, X_neg)
    await verify_onnx_model()

if __name__ == "__main__":
    asyncio.run(main())
