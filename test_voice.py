import asyncio
import time
from pathlib import Path

import yaml
import sounddevice as sd

from openai import AsyncOpenAI
from cartesia import AsyncCartesia


# ============================================================
# CONFIG
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.yaml"

if not CONFIG_FILE.exists():
    raise FileNotFoundError(
        f"config.yaml not found:\n{CONFIG_FILE}"
    )

with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

if not isinstance(config, dict):
    raise RuntimeError("config.yaml is not a valid YAML object.")


# ============================================================
# API KEYS
# ============================================================

NVIDIA_API_KEY = config["nvidia_api_key"]
CARTESIA_API_KEY = config["CARTESIA_API_KEY"]

NVIDIA_MODEL = config["nvidia_model"]

VOICE_ID = config.get("cartesia_voice_id", "b1ce5126-4d08-42c3-adef-d3eb39e90c7a")

# ============================================================
# AUDIO
# ============================================================

SAMPLE_RATE = 16000
CHANNELS = 1


# ============================================================
# CONFIG CHECK
# ============================================================

print()
print("=" * 65)
print("CONFIGURATION")
print("=" * 65)

print(f"Config : {CONFIG_FILE}")
print(f"NVIDIA : {'FOUND' if NVIDIA_API_KEY else 'EMPTY'}")
print(f"Cartesia: {'FOUND' if CARTESIA_API_KEY else 'EMPTY'}")
print(f"Model  : {NVIDIA_MODEL}")
print(f"Voice  : {VOICE_ID}")

print("=" * 65)


# ============================================================
# CLIENTS
# ============================================================

nvidia = AsyncOpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=NVIDIA_API_KEY,
)

cartesia = AsyncCartesia(
    api_key=CARTESIA_API_KEY,
)


# ============================================================
# JARVIS
# ============================================================

async def jarvis(prompt: str):

    total_start = time.perf_counter()

    first_token_time = None
    first_audio_time = None

    print()
    print("=" * 65)
    print("JARVIS")
    print("=" * 65)

    print(f"User: {prompt}")
    print()

    # --------------------------------------------------------
    # Open Cartesia WebSocket
    # --------------------------------------------------------

    async with cartesia.tts.websocket_connect() as connection:

        # ----------------------------------------------------
        # Create TTS context
        # ----------------------------------------------------

        ctx = connection.context(

            model_id="sonic-3.5",

            voice={
                "mode": "id",
                "id": VOICE_ID,
            },

            output_format={
                "container": "raw",
                "encoding": "pcm_s16le",
                "sample_rate": SAMPLE_RATE,
            },

            language="en",
        )

        # ----------------------------------------------------
        # Start NVIDIA
        # ----------------------------------------------------

        llm_start = time.perf_counter()

        print("[NVIDIA] Starting request...")

        stream = await nvidia.chat.completions.create(

            model=NVIDIA_MODEL,

            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Joe Goldberg. Calm, soft-spoken, intensely observant, calculating, and psychologically insightful. "
                        "You speak in a slow, intimate, measured tone as if narrating your internal monologue directly to 'You'. "
                        "Do not speak like a fast or energetic assistant. Keep responses measured, deliberate, quiet, and concise. "
                        "Do not use markdown. Do not use bullet points."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],

            max_tokens=150,

            stream=True,

            extra_body={
                "chat_template_kwargs": {
                    "thinking": False
                }
            },
        )

        # ----------------------------------------------------
        # Open audio output
        # ----------------------------------------------------

        audio = sd.RawOutputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
        )

        audio.start()

        # ----------------------------------------------------
        # Receive Cartesia audio
        # ----------------------------------------------------

        async def receive_audio():

            nonlocal first_audio_time

            try:

                async for response in ctx.receive():

                    if response.type == "chunk":

                        if not response.audio:
                            continue

                        if first_audio_time is None:

                            first_audio_time = time.perf_counter()

                            print()
                            print(
                                f"[FIRST AUDIO] "
                                f"{first_audio_time - total_start:.3f}s"
                            )

                        audio.write(response.audio)

                    elif response.type == "error":

                        print()
                        print(
                            f"[CARTESIA ERROR] "
                            f"{response.message or response.title}"
                        )

            except Exception as e:

                print()
                print(
                    f"[CARTESIA RECEIVE ERROR] "
                    f"{type(e).__name__}: {e}"
                )

        # Start audio receiver
        audio_task = asyncio.create_task(
            receive_audio()
        )

        # ----------------------------------------------------
        # Stream Nemotron
        # ----------------------------------------------------

        buffer = ""

        print("Assistant: ", end="", flush=True)

        try:

            async for chunk in stream:

                if not chunk.choices:
                    continue

                token = chunk.choices[0].delta.content

                if not token:
                    continue

                # ------------------------------------------------
                # First token
                # ------------------------------------------------

                if first_token_time is None:

                    first_token_time = time.perf_counter()

                    print()
                    print(
                        f"[FIRST TOKEN] "
                        f"{first_token_time - llm_start:.3f}s"
                    )

                    print(
                        "Assistant: ",
                        end="",
                        flush=True
                    )

                # ------------------------------------------------
                # Print response
                # ------------------------------------------------

                print(
                    token,
                    end="",
                    flush=True
                )

                buffer += token

                # ------------------------------------------------
                # Send chunks to Cartesia
                # ------------------------------------------------

                stripped = buffer.rstrip()

                should_send = False

                # Sentence boundary
                if stripped.endswith(
                    (".", "!", "?", ";", ":")
                ):
                    should_send = True

                # Maximum buffer
                elif len(buffer) >= 100:
                    should_send = True

                if should_send:

                    text = buffer

                    buffer = ""

                    await ctx.push(text)

            # ----------------------------------------------------
            # Send remaining text
            # ----------------------------------------------------

            if buffer:

                await ctx.push(buffer)

            # ----------------------------------------------------
            # Tell Cartesia there is no more input
            # ----------------------------------------------------

            await ctx.no_more_inputs()

            # ----------------------------------------------------
            # Wait for all audio
            # ----------------------------------------------------

            await audio_task

        finally:

            try:
                audio.stop()
                audio.close()
            except Exception:
                pass

    # ========================================================
    # RESULTS
    # ========================================================

    total_end = time.perf_counter()

    print()
    print()
    print("=" * 65)
    print("LATENCY RESULTS")
    print("=" * 65)

    if first_token_time:

        print(
            f"LLM first token : "
            f"{first_token_time - llm_start:.3f}s"
        )

    else:

        print(
            "LLM first token : N/A"
        )

    if first_audio_time:

        print(
            f"First audio     : "
            f"{first_audio_time - total_start:.3f}s"
        )

    else:

        print(
            "First audio     : N/A"
        )

    print(
        f"Total response  : "
        f"{total_end - total_start:.3f}s"
    )

    print("=" * 65)


# ============================================================
# MAIN
# ============================================================

async def main():

    print()
    print("╔═══════════════════════════════════════════════════════════╗")
    print("║                    JARVIS VOICE TEST                     ║")
    print("╚═══════════════════════════════════════════════════════════╝")

    print()
    print(f"Model: {NVIDIA_MODEL}")
    print(f"Voice: {VOICE_ID}")

    print()
    print("Type 'exit' to quit.")

    while True:

        try:

            prompt = input("\nYou: ").strip()

            if prompt.lower() in {
                "exit",
                "quit",
                "q",
            }:

                print("\nGoodbye, sir.")
                break

            if not prompt:
                continue

            await jarvis(prompt)

        except KeyboardInterrupt:

            print("\n\nExiting...")
            break

        except Exception as e:

            print()
            print("=" * 65)
            print("ERROR")
            print("=" * 65)
            print(
                f"{type(e).__name__}: {e}"
            )
            print("=" * 65)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    asyncio.run(main())
