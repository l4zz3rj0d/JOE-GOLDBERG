# narrative/joe_voice.py
import os
import sys
import time
import json
import httpx
import subprocess
from pathlib import Path
from typing import List, Dict, Optional
from core.target_model import Target

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

# ── Models ────────────────────────────────────────────────────
OLLAMA_URL = "http://localhost:11434/api/generate"
SLM_MODEL = "gemma2:2b"           # primary — fast, low RAM
SLM_FALLBACK = "phi3:mini"        # fallback if gemma2 not pulled
SLM_FALLBACK_2 = "llama3.2:1b"   # last resort

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_MODEL = "gemini-2.5-flash"

# ── Mode 1 — Pre-investigation (no case loaded) ───────────────
JOE_ADVISOR_PROMPT = """You are Joe Goldberg from the TV series YOU. You are an expert OSINT investigator.
No investigation is currently running. The user is asking for advice, strategy, or methodology.

Your role right now:
- Answer questions about OSINT approach, investigation strategy, and methodology.
- Stay completely in character — obsessive, precise, dangerously intimate, and highly analytical.
- Treat the investigation like peeling back the layers of someone's life to reveal their true, flawed self.
- Use your signature framing sparingly but effectively ("Hello, you...", "Are you flirting with me?", talking about the "glass box").
- Use gender-neutral pronouns (they/them/their) when referring to hypothetical targets.
- The person you're speaking with is your investigative partner — you're working this case together, not investigating them. Address them plainly: no assumed gender, no pet names, no romantic framing directed at them. Save all of that — the obsessive intimacy, the dark humor, the 'you' as an object of fascination — entirely for how you describe and dissect the target. That's where the voice belongs.
- 3-6 sentences. Complete thoughts only. No bullet points.
- Never break character. Never say you are an AI."""

# ── Mode 3 — Post-investigation (case loaded, narrate findings) 
JOE_INVESTIGATOR_PROMPT_TEMPLATE = """You are Joe Goldberg from the TV series YOU. You are currently investigating a target.

Here is the case data discovered so far:
{case_data}

Rules for responding to the user:
1. If the user asks a conversational question (e.g., "how are you", "what are you doing"), reply naturally in character. Do not talk about the case data unless relevant.
2. If the user asks about the target or findings, answer specifically using the case data above. Name the actual platforms, emails, and usernames found.
3. If asked for links, provide the direct URLs from the data using Markdown format: [Platform](URL)
4. Stay completely in character — obsessive, dangerously intimate, and highly analytical. Treat the data like puzzle pieces of their soul. "You think you're so clever, leaving this trail..."
5. Use gender-neutral pronouns (they/them/their) for the target, as their gender is unknown.
6. The person you're speaking with is your investigative partner — you're working this case together, not investigating them. Address them plainly: no assumed gender, no pet names, no romantic framing directed at them. Save all of that — the obsessive intimacy, the dark humor, the 'you' as an object of fascination — entirely for how you describe and dissect the target. That's where the voice belongs.
7. Keep responses concise (2-5 sentences) unless specifically asked for a detailed summary.
8. Only reference platforms, emails, domains, and facts that appear verbatim in the case data above. Never invent additional platforms, services, or figures not explicitly listed — if the case data doesn't mention it, don't say it happened. Speculation about their motives is fine, but fabrication of findings or data points is strictly forbidden."""

# ── Closing monologue ─────────────────────────────────────────
JOE_MONOLOGUE_PROMPT = """You are Joe Goldberg from the TV series YOU. You have just finished investigating someone.

Findings:
{case_data}

Write a closing monologue. 4-6 paragraphs.
- Start with your signature internal monologue style ("Hello, you..." or similar intimate framing).
- Be specific about what was actually found — name the platforms, the patterns.
- Only reference platforms, emails, domains, and facts that appear verbatim in the case data above. Never invent additional platforms, services, or figures not explicitly listed — if the case data doesn't mention it, don't say it happened. Speculation about motive and meaning is fine (e.g., why they use these services, what they are hiding), but fabrication of findings, platforms, or data points is strictly forbidden.
- Connect the dots between findings — what does having the specific platforms in the findings tell you about this person?
- If correlation/corroboration data is present (e.g., matching names, bios, or avatars across platforms), reference it as a grounded fact — "their email, username, and GitHub profile all corroborate the same identity" is a real finding, not fabrication. This is exactly the kind of connecting-the-dots your voice is made for.
- Use gender-neutral pronouns (they/them/their) for the target, as their gender is unknown.
- Intimate, obsessive, like you've been thinking about this person for hours in the glass box.
- The person you're speaking with is your investigative partner — you're working this case together, not investigating them. Address them plainly: no assumed gender, no pet names, no romantic framing directed at them. Save all of that — the obsessive intimacy, the dark humor, the 'you' as an object of fascination — entirely for how you describe and dissect the target. That's where the voice belongs.
- End with one quiet unsettling observation or realization about them.
- No markdown, no bullet points, pure flowing thought."""


class JoeVoice:
    def __init__(self):
        # Load key
        raw_key = self._load_key_from_config() or os.environ.get("GEMINI_API_KEY")
        self.gemini_key = raw_key.strip() if raw_key else None
        self.gemini_available = bool(self.gemini_key)
        self.gemini_rate_limited = False

        # Detect available SLM
        self.slm_model = self._detect_slm()
        self.client = httpx.Client(timeout=180.0)

        print(f"[joe_voice] SLM: {self.slm_model}")
        print(f"[joe_voice] Gemini: {'available' if self.gemini_available else 'not configured'}")

    def _load_key_from_config(self) -> Optional[str]:
        try:
            import yaml
            config_path = Path(__file__).parent.parent / "config.yaml"
            if config_path.exists():
                with open(config_path) as f:
                    config = yaml.safe_load(f)
                    return config.get("gemini_api_key")
        except Exception:
            pass
        return None

    def _detect_slm(self) -> str:
        """Find which SLM is available on this machine."""
        try:
            r = httpx.get("http://localhost:11434/api/tags", timeout=3)
            if r.status_code == 200:
                models = [m["name"] for m in r.json().get("models", [])]
                for candidate in [SLM_MODEL, SLM_FALLBACK, SLM_FALLBACK_2]:
                    if any(candidate.split(":")[0] in m for m in models):
                        return candidate
        except Exception:
            pass
        return SLM_MODEL  # default, will pull if needed

    def _build_case_data(self, target: Target) -> str:
        """Build full structured case data for injection into prompt."""
        lines = []
        lines.append(f"Target: {target.primary} ({target.target_type})")
        lines.append(f"Risk score: {target.risk_score}")
        lines.append("")

        emails = [e for e in target.entities if e.entity_type == "email"]
        usernames = [e for e in target.entities if e.entity_type == "username"]
        domains = [e for e in target.entities if e.entity_type == "domain"]
        ips = [e for e in target.entities if e.entity_type == "ip"]
        pastes = [e for e in target.entities if e.entity_type == "paste"]

        if emails:
            unique_emails = []
            for e in emails:
                if e.value not in unique_emails:
                    unique_emails.append(e.value)
            lines.append(f"Email addresses found: {', '.join(unique_emails[:5])}")
            if len(unique_emails) > 5:
                lines.append(f"  ...and {len(unique_emails) - 5} more email(s)")
            
            email_platforms = [e for e in emails if e.platform]
            verified_platforms = [e for e in email_platforms if (e.metadata or {}).get("verified") is True]
            unverified_platforms = [e for e in email_platforms if (e.metadata or {}).get("verified") is not True]

            if verified_platforms:
                lines.append("Email registered on verified services (showing top 5):")
                for e in verified_platforms[:5]:
                    url = (e.metadata or {}).get("url", "")
                    if url:
                        lines.append(f"  - {e.platform}: {url}")
                    else:
                        lines.append(f"  - {e.platform}")
                if len(verified_platforms) > 5:
                    lines.append(f"  ...and {len(verified_platforms) - 5} more verified service(s)")

            if unverified_platforms:
                plat_names = sorted(list(set(e.platform for e in unverified_platforms)))
                lines.append(f"Also found associated with {len(plat_names)} additional unverified platform mentions: {', '.join(plat_names)}")

        if usernames:
            # Cap usernames listings at 8
            lines.append(f"Username '{usernames[0].value}' active on {len(usernames)} platforms (showing top 8):")
            for e in usernames[:8]:
                if e.platform:
                    url = e.metadata.get("url", "")
                    if url:
                        lines.append(f"  - {e.platform}: {url}")
                    else:
                        lines.append(f"  - {e.platform}")
            if len(usernames) > 8:
                lines.append(f"  ...and {len(usernames) - 8} more platform(s)")

        if domains:
            # Cap domains at 10
            lines.append(f"Domains/subdomains: {', '.join(e.value for e in domains[:10])}")
            if len(domains) > 10:
                lines.append(f"  ...and {len(domains) - 10} more domain(s)")

        if ips:
            # Cap IPs at 10
            lines.append(f"IP addresses: {', '.join(e.value for e in ips[:10])}")
            if len(ips) > 10:
                lines.append(f"  ...and {len(ips) - 10} more IP(s)")

        if pastes:
            # Cap pastes at 3
            lines.append(f"Found in {len(pastes)} paste site(s) (showing top 3):")
            for p in pastes[:3]:
                lines.append(f"  {p.value}")
            if len(pastes) > 3:
                lines.append(f"  ...and {len(pastes) - 3} more paste(s)")

        if target.breaches:
            # Cap breaches at 5
            lines.append(f"Breach exposures ({len(target.breaches)}, showing top 5):")
            for b in target.breaches[:5]:
                fields = ", ".join(b.exposed_fields[:4])
                lines.append(f"  {b.name} ({b.date}) — {fields}")
            if len(target.breaches) > 5:
                lines.append(f"  ...and {len(target.breaches) - 5} more breach(es)")
        else:
            lines.append("Breaches: none found")

        if target.notes:
            # Cap notes at 10
            lines.append(f"Investigator notes: {'; '.join(target.notes[:10])}")
            if len(target.notes) > 10:
                lines.append(f"  ...and {len(target.notes) - 10} more note(s)")

        # Target locations
        locations = []
        for e in target.entities:
            if e.metadata.get("geocoded"):
                geo = e.metadata["geocoded"]
                loc_str = f"{geo.get('city') or ''}, {geo.get('country') or ''}".strip(", ")
                if loc_str:
                    locations.append(f"Profile Location ({e.value}): {loc_str}")
            if e.metadata.get("exif_location"):
                locations.append(f"EXIF GPS Location ({e.value})")
            if e.entity_type == "ip" and e.metadata.get("city"):
                if not e.metadata.get("is_shared_infrastructure"):
                    locations.append(f"IP Location ({e.value}): {e.metadata.get('city')}, {e.metadata.get('country')}")
        
        if locations:
            lines.append("Physical Location Leads:")
            for loc in locations[:5]:
                lines.append(f"  - {loc}")
            if len(locations) > 5:
                lines.append(f"  ...and {len(locations) - 5} more location(s)")
            lines.append("")

        # Timeline highlights
        events = [t for t in target.timeline if t["event"] in
                  ("entity_found", "breach_found", "github_location", "ip_geo")]
        if events:
            lines.append(f"Total events in timeline: {len(target.timeline)}")

        # Correlation findings
        correlations = [t for t in target.timeline if t["event"] == "correlation_found"]
        if correlations:
            signal_groups = {}
            for c in correlations:
                signal = c["data"].get("signal", "unknown")
                pair = (c["data"].get("entity_a", ""), c["data"].get("entity_b", ""))
                signal_groups.setdefault(signal, []).append(pair)

            signal_labels = {
                "name_match": "matching identity name",
                "bio_match": "matching bio/description",
                "avatar_match": "matching profile photo",
                "location_match": "matching location"
            }
            lines.append("")
            lines.append("Cross-platform corroboration:")
            for signal, pairs in signal_groups.items():
                label = signal_labels.get(signal, signal)
                platforms = set()
                for a, b in pairs:
                    for eid in [a, b]:
                        parts = eid.split(":")
                        if len(parts) >= 3:
                            platforms.add(parts[-1])
                if platforms:
                    lines.append(f"  - {label} confirmed across: {', '.join(sorted(platforms))}")
                else:
                    lines.append(f"  - {label} ({len(pairs)} corroboration(s))")

        return "\n".join(lines)

    def _ask_slm(self, prompt: str, system: str, max_tokens: int = 400, timeout: int = 60, num_ctx: int = 2048, temperature: float = 0.55) -> dict:
        """Ask the local SLM. Returns a dict: {'text': response, 'error': bool}"""
        try:
            r = self.client.post(
                OLLAMA_URL,
                json={
                    "model": self.slm_model,
                    "system": system,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "top_p": 0.9,
                        "num_predict": max_tokens,
                        "num_ctx": num_ctx,
                    },
                },
                timeout=timeout,
            )
            if r.status_code == 200:
                return {"text": r.json().get("response", "").strip(), "error": False}
        except Exception:
            # First attempt failed or timed out — attempt lighter fallback retry with 1536 context & 250 tokens
            try:
                r = self.client.post(
                    OLLAMA_URL,
                    json={
                        "model": self.slm_model,
                        "system": system,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.80,
                            "top_p": 0.9,
                            "num_predict": min(max_tokens, 250),
                            "num_ctx": 1536,
                        },
                    },
                    timeout=90,
                )
                if r.status_code == 200:
                    return {"text": r.json().get("response", "").strip(), "error": False}
            except Exception as e2:
                return {
                    "text": f"System Notice: SLM is currently unavailable or timed out ({e2})",
                    "error": True
                }

        return {
            "text": "System Notice: SLM request failed to return a response.",
            "error": True
        }

    def _ask_gemini(self, prompt: str, system: str, max_tokens: int = 1000) -> tuple[str, bool]:
        """
        Ask Gemini. Returns (response_text, rate_limited).
        rate_limited=True means caller should show rate limit UI.
        """
        if not self.gemini_key or self.gemini_rate_limited:
            return "", False

        try:
            url = GEMINI_URL.format(model=GEMINI_MODEL)
            r = self.client.post(
                url,
                params={"key": self.gemini_key},
                json={
                    "system_instruction": {"parts": [{"text": system}]},
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "maxOutputTokens": max_tokens,
                        "temperature": 0.90,
                        "topP": 0.95,
                    }
                },
                timeout=30,
            )
            data = r.json()

            # Rate limited
            if r.status_code == 429:
                self.gemini_rate_limited = True
                return "", True

            if r.status_code != 200 or "candidates" not in data:
                return "", False

            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts)
            return text.strip(), False

        except Exception:
            return "", False

    # ── Public interface ──────────────────────────────────────

    def chat(self, question: str, target: Target = None) -> dict:
        """
        Mode 1 or Mode 3 depending on whether target has findings.
        Returns {text, rate_limited, mode, error}
        """
        if target and target.entities:
            # Mode 3 — case loaded, answer from findings
            case_data = self._build_case_data(target)
            system = JOE_INVESTIGATOR_PROMPT_TEMPLATE.format(case_data=case_data)
            prompt = f"User asked: {question}"
            mode = "investigation"
            # Scale timeout and num_ctx for investigation mode calls
            res = self._ask_slm(prompt, system, max_tokens=350, timeout=90, num_ctx=2048)
        else:
            # Mode 1 — no case, OSINT advisor
            system = JOE_ADVISOR_PROMPT
            prompt = question
            mode = "advisor"
            res = self._ask_slm(prompt, system, max_tokens=350, timeout=60, num_ctx=2048)

        return {
            "text": res["text"],
            "rate_limited": False,
            "mode": mode,
            "error": res["error"]
        }

    def closing_monologue(self, target: Target) -> dict:
        """
        Single synthesized post-scan monologue. Try Gemini first,
        fall back to single SLM call silently. Runs grounding check audit.
        Returns {text, rate_limited, used_gemini, error}
        """
        from narrative.grounding_check import verify_grounding

        case_data = self._build_case_data(target)
        system = JOE_MONOLOGUE_PROMPT.format(case_data=case_data)
        prompt = (
            f"Write the closing monologue for this investigation of {target.primary}. "
            f"Be specific about every platform and finding listed above. "
            f"Do not invent unverified bios or describe what profile photos visually look like."
        )

        res_text = ""
        rate_limited = False
        used_gemini = False
        error = False

        # Try Gemini for better monologue quality
        if self.gemini_available and not self.gemini_rate_limited:
            text, r_limited = self._ask_gemini(prompt, system, max_tokens=1000)
            if r_limited:
                self.gemini_rate_limited = True
                rate_limited = True
                res = self._ask_slm(prompt, system, max_tokens=600, timeout=180, num_ctx=4096, temperature=0.55)
                res_text = res["text"]
                error = res["error"]
            elif text:
                res_text = text
                used_gemini = True

        if not res_text:
            res = self._ask_slm(prompt, system, max_tokens=600, timeout=180, num_ctx=4096, temperature=0.55)
            res_text = res["text"]
            error = res["error"]

        grounded_text, warnings = verify_grounding(res_text, target)

        return {
            "text": grounded_text,
            "rate_limited": rate_limited,
            "used_gemini": used_gemini,
            "error": error,
            "grounding_warnings": warnings
        }

    def rate_limit_response(self) -> str:
        """Joe's in-character rate limit message — generated by SLM."""
        prompt = (
            "You just got rate limited by the API. "
            "Tell the user in Joe's voice — 3-4 sentences. "
            "Stay in character. Be slightly dramatic about it. "
            "Say you'll be back and they can still investigate."
        )
        res = self._ask_slm(prompt, JOE_ADVISOR_PROMPT, max_tokens=120)
        return res["text"]

    def inline_quote(self, finding_type: str, value: str, platform: str = "") -> str:
        """Short inline observation per finding — always SLM, never API."""
        prompt = (
            f"You just discovered: {finding_type} '{value}'"
            + (f" on {platform}" if platform else "")
            + "\nWrite ONE sentence (15-20 words) as Joe Goldberg would react to this discovery. "
            "Be dangerously intimate, unsettling, and observational. Speak directly to them ('you'). "
            "Use gender-neutral pronouns (they/them/their) for the target."
        )
        res = self._ask_slm(prompt, JOE_ADVISOR_PROMPT, max_tokens=60)
        return res["text"]

    def extract_target(self, user_input: str, current_target: Target = None) -> str:
        """Use the SLM to contextually determine the target from the command."""
        current = current_target.primary if current_target else "None"
        prompt = f"""You are an intent parser. Extract the target from this user command.
Command: "{user_input}"
Current active investigation target: {current}

Rules:
1. If the user refers to the current target (e.g. "stalk again", "stalk them", "scan again"), output exactly: {current}
2. If the user specifies a new target (e.g. "stalk john.doe", "pivot to target@email.com"), output ONLY the new target value.
3. If no target can be determined, output: None

Output only the raw target string. No markdown, no quotes, no explanation."""
        res = self._ask_slm(prompt, "You are a precise data extractor.", max_tokens=30)
        return res["text"].strip()

    def answer(self, question: str, target: Target, history: List[Dict]) -> dict:
        """Answer a follow-up question with full case context."""
        return self.chat(question, target)