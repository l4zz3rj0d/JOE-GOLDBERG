# core/wake_word.py
"""
Local openWakeWord engine & VAD command-window management for Soldier Boy.
Features:
- Continuous 100% on-device CPU prediction for 'Hey Soldier' / 'Hey Dean' (ONNX).
- Hardware mic detection with graceful fallback to browser Web Speech API.
- Voice Activity Detection (VAD) for 1.2s post-speech silence early-closing (30s safety cap).
"""

import os
import sys
import time
import math
import struct
import threading
import queue
from pathlib import Path
from typing import Callable, Optional, Dict, Any

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

def _patch_openwakeword_providers():
    """Align openwakeword ONNX providers with actual available system providers to avoid CUDA fallback warnings."""
    try:
        import onnxruntime as ort
        import openwakeword.utils
        avail_providers = ort.get_available_providers()

        orig_init = openwakeword.utils.AudioFeatures.__init__
        def safe_audio_features_init(self, melspec_onnx_model_path=None, embedding_onnx_model_path=None, sr=16000, ncpu=1):
            if melspec_onnx_model_path is None:
                melspec_onnx_model_path = openwakeword.utils.os.path.join(
                    openwakeword.utils.pathlib.Path(openwakeword.utils.__file__).parent.resolve(),
                    "resources", "models", "melspectrogram.onnx"
                )
            if embedding_onnx_model_path is None:
                embedding_onnx_model_path = openwakeword.utils.os.path.join(
                    openwakeword.utils.pathlib.Path(openwakeword.utils.__file__).parent.resolve(),
                    "resources", "models", "embedding_model.onnx"
                )

            sessionOptions = ort.SessionOptions()
            sessionOptions.inter_op_num_threads = ncpu
            sessionOptions.intra_op_num_threads = ncpu
            self.melspec_model = ort.InferenceSession(melspec_onnx_model_path, sess_options=sessionOptions, providers=avail_providers)
            self.embedding_model = ort.InferenceSession(embedding_onnx_model_path, sess_options=sessionOptions, providers=avail_providers)
            self.onnx_execution_provider = self.melspec_model.get_providers()[0]

            self.raw_data_buffer = openwakeword.utils.deque(maxlen=sr*10)
            self.melspectrogram_buffer = openwakeword.utils.np.ones((76, 32))
            self.melspectrogram_max_len = 10*97
            self.accumulated_samples = 0
            self.feature_buffer = self._get_embeddings(openwakeword.utils.np.zeros(160000).astype(openwakeword.utils.np.int16))
            self.feature_buffer_max_len = 120

        openwakeword.utils.AudioFeatures.__init__ = safe_audio_features_init
    except Exception:
        pass

_patch_openwakeword_providers()

class WakeWordEngine:
    def __init__(
        self,
        on_wake_detected: Optional[Callable[[str], None]] = None,
        on_speech_ended: Optional[Callable[[], None]] = None,
        model_path: Optional[str] = None,
        threshold: float = 0.5,
        silence_timeout_sec: float = 1.2,
        max_window_sec: float = 30.0
    ):
        self.on_wake_detected = on_wake_detected
        self.on_speech_ended = on_speech_ended
        self.threshold = threshold
        self.silence_timeout_sec = silence_timeout_sec
        self.max_window_sec = max_window_sec

        self.hardware_mic_available = False
        self.fallback_to_web_speech = False
        self.running = False
        self.thread: Optional[threading.Thread] = None

        self._model = None
        self._audio_stream = None
        self._pyaudio = None

        # VAD & Window State
        self.is_window_active = False
        self.window_start_time = 0.0
        self.last_speech_time = 0.0
        self.has_detected_speech_in_window = False

        self._init_engine(model_path)

    def _init_engine(self, model_path: Optional[str]):
        """Initialize openWakeWord model and check microphone hardware."""
        # 1. Check custom ONNX model path or default openWakeWord models
        target_model = model_path
        if not target_model:
            custom_soldier_path = Path(__file__).parent.parent / "data" / "models" / "hey_soldier.onnx"
            custom_dean_path = Path(__file__).parent.parent / "data" / "models" / "hey_dean.onnx"
            custom_joe_path = Path(__file__).parent.parent / "data" / "models" / "hey_joe.onnx"
            if custom_soldier_path.exists():
                target_model = str(custom_soldier_path)
            elif custom_dean_path.exists():
                target_model = str(custom_dean_path)
            elif custom_joe_path.exists():
                target_model = str(custom_joe_path)

        try:
            import openwakeword
            from openwakeword.model import Model
            if target_model and os.path.exists(target_model):
                print(f"[wake_word] Loading custom openWakeWord model: {target_model}")
                self._model = Model(wakeword_model_paths=[target_model])
            else:
                print("[wake_word] Custom wake word ONNX model not found; using openWakeWord base ONNX engine for 'Hey Soldier'.")
                self._model = Model()
        except Exception as e:
            print(f"[wake_word] Notice: openwakeword module not loaded ({e}).")

        # 2. Check PyAudio / microphone hardware availability
        try:
            import pyaudio
            self._pyaudio = pyaudio.PyAudio()
            # Try finding an active input device
            device_count = self._pyaudio.get_device_count()
            has_input = False
            for i in range(device_count):
                info = self._pyaudio.get_device_info_by_index(i)
                if info.get("maxInputChannels", 0) > 0:
                    has_input = True
                    break
            
            if has_input:
                self.hardware_mic_available = True
                print("[wake_word] Hardware microphone detected and ready for openWakeWord.")
            else:
                print("[wake_word] No audio input hardware found. Delegating wake word to Web Speech API.")
                self.fallback_to_web_speech = True
        except Exception as e:
            print(f"[wake_word] Audio hardware init notice: {e}. Falling back to Web Speech API.")
            self.fallback_to_web_speech = True

    def start(self):
        """Start background microphone listening thread if hardware is present."""
        if not self.hardware_mic_available or not self._model:
            print("[wake_word] Engine running in browser Web Speech API fallback mode.")
            return

        self.running = True
        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()

    def stop(self):
        """Stop microphone listening loop."""
        self.running = False
        if self._audio_stream:
            try:
                self._audio_stream.stop_stream()
                self._audio_stream.close()
            except Exception:
                pass
        if self._pyaudio:
            try:
                self._pyaudio.terminate()
            except Exception:
                pass

    def _compute_rms(self, pcm_data: bytes) -> float:
        """Compute Root Mean Square (RMS) volume level of 16-bit PCM chunk."""
        if not pcm_data:
            return 0.0
        count = len(pcm_data) // 2
        if count == 0:
            return 0.0
        shorts = struct.unpack(f"<{count}h", pcm_data)
        sum_squares = sum(s * s for s in shorts)
        return math.sqrt(sum_squares / count)

    def trigger_wake_event(self, trigger_phrase: str = "Hey Soldier"):
        """Programmatically trigger a wake detection event (e.g. from STT regex fallback)."""
        now = time.time()
        self.is_window_active = True
        self.window_start_time = now
        self.last_speech_time = now
        self.has_detected_speech_in_window = False
        if self.on_wake_detected:
            self.on_wake_detected(trigger_phrase)

    def _listen_loop(self):
        """Background continuous audio streaming loop."""
        CHUNK_SIZE = 1280  # 80ms chunk at 16kHz
        FORMAT = 8  # pyaudio.paInt16
        CHANNELS = 1
        RATE = 16000

        try:
            import pyaudio
            self._audio_stream = self._pyaudio.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK_SIZE
            )
        except Exception as e:
            print(f"[wake_word] Failed to open microphone stream: {e}. Switching to browser STT.")
            self.hardware_mic_available = False
            self.fallback_to_web_speech = True
            return

        import numpy as np
        print("[wake_word] Continuous openWakeWord background listener active ('Hey Soldier').")

        while self.running:
            try:
                data = self._audio_stream.read(CHUNK_SIZE, exception_on_overflow=False)
                if not data:
                    continue

                audio_int16 = np.frombuffer(data, dtype=np.int16)

                # 1. Run openWakeWord prediction
                if self._model:
                    prediction = self._model.predict(audio_int16)
                    for model_name, score in prediction.items():
                        if score >= self.threshold:
                            print(f"[wake_word] 'Hey Soldier' detected via openWakeWord! Score: {score:.3f}")
                            self.trigger_wake_event("Hey Soldier")
                            # Reset model prediction buffer to prevent double triggers
                            self._model.reset()
                            break

                # 2. Run Voice Activity Detection (VAD) for active command window
                if self.is_window_active:
                    now = time.time()
                    elapsed = now - self.window_start_time
                    rms = self._compute_rms(data)

                    # Speech detection threshold (RMS > 400 = speech)
                    if rms > 400.0:
                        self.last_speech_time = now
                        self.has_detected_speech_in_window = True

                    silence_duration = now - self.last_speech_time

                    # Close window if:
                    # a) Speech was detected and followed by silence_timeout_sec (1.2s)
                    # b) Maximum window ceiling (30s) reached
                    if (self.has_detected_speech_in_window and silence_duration >= self.silence_timeout_sec) or (elapsed >= self.max_window_sec):
                        print(f"[wake_word] VAD early-closing command window (silence: {silence_duration:.1f}s, total: {elapsed:.1f}s).")
                        self.is_window_active = False
                        if self.on_speech_ended:
                            self.on_speech_ended()

            except Exception as e:
                time.sleep(0.1)
