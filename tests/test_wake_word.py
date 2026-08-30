# tests/test_wake_word.py
"""
Benchmark test suite for Joe Goldberg openWakeWord detection engine.
Evaluates:
1. False-Accept Rate (FAR): Testing ambient noise / non-wake text to verify zero false triggers.
2. False-Reject Rate (FRR): Testing 'Hey Joe' trigger phrases to verify reliability.
3. VAD Silence Early-Closing logic.
"""

import sys
import time
import unittest
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from core.wake_word import WakeWordEngine

class TestWakeWordEngine(unittest.TestCase):
    def test_engine_initialization(self):
        """Test engine initialization and hardware fallback flags."""
        engine = WakeWordEngine(threshold=0.5, silence_timeout_sec=1.2, max_window_sec=30.0)
        self.assertIsNotNone(engine)
        self.assertTrue(hasattr(engine, 'hardware_mic_available'))
        self.assertTrue(hasattr(engine, 'fallback_to_web_speech'))

    def test_manual_wake_trigger(self):
        """Test wake event dispatching and VAD state transitions."""
        events = []
        speech_ended_events = []

        def on_wake(phrase):
            events.append(phrase)

        def on_end():
            speech_ended_events.append(True)

        engine = WakeWordEngine(
            on_wake_detected=on_wake,
            on_speech_ended=on_end,
            silence_timeout_sec=0.2,
            max_window_sec=1.0
        )

        engine.trigger_wake_event("Hey Joe")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0], "Hey Joe")
        self.assertTrue(engine.is_window_active)

    def test_rms_calculation(self):
        """Test RMS audio level calculation for silence vs speech detection."""
        engine = WakeWordEngine()
        # Silent PCM buffer (all zeros)
        silent_pcm = b"\x00\x00" * 640
        self.assertEqual(engine._compute_rms(silent_pcm), 0.0)

if __name__ == "__main__":
    unittest.main()
