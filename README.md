<p align="center">
  <img src="assets/soldier-banner.png" alt="Soldier Boy" width="100%"/>
</p>

<h1 align="center">SOLDIER BOY : AUTONOMOUS PERSONAL & OSINT ASSISTANT</h1>
<p align="center">
  <b>Autonomous Personal AI Assistant by Project Hellhound</b>
  <br>
  <i>Your all-in-one local personal assistant & OSINT intelligence powerhouse. From daily workflow automation, live web search, system task execution, and offline voice interaction to target enumeration, identity pivoting, multi-source username scans, email intelligence, and 2D/3D topology graphs.</i>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> ·
  <a href="#installation--setup">Installation & Setup</a> ·
  <a href="#ai-model-routing">AI Routing</a> ·
  <a href="#commands">Commands</a> ·
  <a href="#capabilities--arsenal">Capabilities</a> ·
  <a href="#wake-word--voice">Voice & Wake Word</a> ·
  <a href="#desktop-gui-app">Desktop GUI</a> ·
  <a href="#license">License</a>
</p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.10+-blue?style=flat-square&logo=python&logoColor=white" alt="Python Version"/></a>
  <a href="https://github.com/project-hellhound-org/SOLDIER-BOY/releases"><img src="https://img.shields.io/badge/Release-v2.0.0-red?style=flat-square" alt="Release Version"/></a>
  <img src="https://img.shields.io/badge/AI--Powered-Ollama%20%7C%20NVIDIA%20NIM%20%7C%20Gemini-red?style=flat-square" alt="AI Support"/>
  <img src="https://img.shields.io/badge/Wake%20Word-Hey%20Soldier%20(openWakeWord)-orange?style=flat-square" alt="Wake Word"/>
  <img src="https://img.shields.io/badge/Voice-Chatterbox%20Local%20Clone-brightgreen?style=flat-square" alt="Voice Synthesis"/>
  <img src="https://img.shields.io/badge/Platform-Linux%20%7C%20macOS-lightgrey?style=flat-square" alt="Platform"/>
  <img src="https://img.shields.io/badge/License-GPLv3-blue?style=flat-square" alt="License"/>
</p>

---

> [!NOTE]
> ### 🛡️ Persona & Privacy Notice
> **Soldier Boy** operates as your direct, autonomous personal assistant and security investigator. He manages daily queries, web research, system automation, and open-source intelligence gathering with an **unfiltered, commanding, and pragmatic tone**. All operations run locally or through encrypted API bridges with zero data leaving your machine without explicit permission.

---

## What Is This?

**Soldier Boy** is the next-generation autonomous personal AI assistant and OSINT intelligence framework developed by **Project Hellhound**. Transitioned from a pure reconnaissance tool into an **all-in-one personal assistant**, Soldier Boy handles everything—from everyday task automation, live web dorking, and system query resolution to deep target investigations, username cross-referencing, email metadata parsing, and network topology graphing.

It features **persistent memory and an automated case blackboard**—all personal tasks, research logs, discovered handles, email profiles, DNS records, IP locations, Wayback snapshots, and evidence notes are retained in isolated workspaces (`~/.soldierboy/cases/<target>/`) so your assistant workflows seamlessly resume across sessions.

Operate across three flexible interfaces:
- **Desktop GUI Application**: A dedicated PyWebView/FastAPI desktop interface featuring collapsible card modules, transparent eye API key toggles, 2D/3D radial topology graphs, and hands-free microphone input with trained `"Hey Soldier"` wake word detection (`soldierboy`).
- **Interactive Terminal**: An interactive terminal environment with real-time monologue streaming, live progress feedback, and inline command execution (`soldierboy --cli`).
- **Headless CLI Runner**: Direct one-line command execution for automated scripts and headless task triggers (`soldierboy investigate <target>`).

---

## How It Works

```
You ──> soldierboy ("Hey Soldier...") ──> Intent & Task Parser ──> Executive Assistant Core
                                                 │                           │
                                                 ▼                           ▼
                                      Personal Workflow Engine    OSINT & Recon Toolchain
                                      ├─ Live Web Research        ├─ Sherlock & Maigret
                                      ├─ System Automation        ├─ Holehe & Gravatar
                                      ├─ Local Voice Synthesis    ├─ GitHub & Breach Check
                                      └─ Case Memory Blackboard   └─ EXIF, WHOIS & DNS
                                                 │
                                                 ▼ (Populates Persistent Blackboard)
                                      Soldier Boy Voice Engine <── Grounding Guard
                                                 │                 (Chatterbox Zero-Shot)
                                                 ▼
                                      /export (Submission-Ready HTML Case & Task Reports)
```

- **All-in-One Personal Capabilities**: Ask general questions, perform live web extractions, summarize complex documents, run system audits, or launch target investigations.
- **Collapsible Card System**: Settings, ledgers, and maps render in responsive card components with collapsible header toggles (`▼` / `▶`) and real-time state badges.
- **Eye Toggle Security**: API key fields (Gemini, NVIDIA NIM) feature transparent eye buttons (`👁`) for password visibility control.
- **Hands-Free Speech Input**: Voice typing via microphone (`🎤`) paired with a custom-trained `hey_soldier.onnx` openWakeWord engine.
- **Interactive Topology Graphs**: 2D SVG radial network fallback + 3D WebGL graph populating entity connections alongside active skill nodes.

---

## AI Model Routing & Recommended Providers

Autonomous intelligence gathering and personal assistant reasoning utilize fast SLMs and frontier LLMs for intent parsing and monologue synthesis.

> [!TIP]
> ### 💡 Recommended AI Engines
> - **NVIDIA NIM (Strongly Recommended for Cloud)**: Use **NVIDIA NIM** (`meta/llama-3.3-70b-instruct` or `nvidia/nemotron-3-super-120b-a12b`). It is **instant, ultra-fast**, and provides generous free API credits for frontier-class 70B–120B reasoning at zero cost.
> - **Local Qwen (Strongly Recommended for Offline)**: Run **Qwen** (`qwen2.5:7b` or `qwen2.5:14b`) locally via Ollama. Delivers exceptional local reasoning, structured output adherence, and 100% offline privacy with zero data leaving your machine.

---

## 🎙️ Voice Intelligence & Wake Word Engine

Soldier Boy features real-time, low-latency conversational speech powered by 100% offline zero-shot voice cloning (**Chatterbox TTS** & reference audio fingerprinting).

### 🎧 Trained "Hey Soldier" Wake Word Model
- **Genuine openWakeWord Engine**: Uses a production-grade `hey_soldier.onnx` neural classifier trained on real synthesized speech datasets and openWakeWord feature embeddings.
- **Zero-False-Accept Discrimination**: Validated on real audio clips to achieve a 1.0 peak score on spoken `"Hey Soldier"` while maintaining 0.00 false accepts on non-target background speech.
- **Jarvis Search Protocol**: Speak `"Hey Soldier, search Google for [query]"` to activate live web extractions and trigger the holographic search overlay.
- **Muting Guard**: Ambient speech listening is automatically muted while Soldier Boy is speaking to prevent self-triggering audio loops.

---

## Installation & Setup

### 1. Requirements & Prerequisites
- **Operating System**: Linux (Ubuntu, Debian, Kali, Arch), macOS.
- **Python**: Version 3.10 or higher.
- **Dependencies**: `ffmpeg`, `espeak-ng` (optional for local voice dataset generation).

### 2. Fast Deploy

#### Option A: One-Line Remote Installer
```bash
curl -fsSL https://raw.githubusercontent.com/project-hellhound-org/SOLDIER-BOY/main/install.sh | bash
```

#### Option B: Standard Git Clone
```bash
git clone https://github.com/project-hellhound-org/SOLDIER-BOY.git
cd SOLDIER-BOY

# Initialize config from template
cp config.yaml.example config.yaml

# Run system installer
chmod +x install.sh
./install.sh
```

#### Reload Shell Environment
```bash
source ~/.bashrc   # or source ~/.zshrc
```

The automated installer will:
- Set up an isolated Python environment (`soldier-env`).
- Initialize `config.yaml` from template configuration.
- Install OSINT and personal assistant toolchains (`sherlock`, `maigret`, `holehe`, `chatterbox-tts`, `openwakeword`).
- Mount desktop application dependencies (`pywebview`).
- Register global `soldierboy` command integration.

---

## Quick Start

### 1. Native Desktop GUI App
Launch the desktop application with collapsible cards and interactive 2D/3D topology graph:
```bash
soldierboy
```

### 2. Interactive Terminal
Launch the interactive CLI interface:
```bash
soldierboy --cli
```

### 3. Headless Direct Command
Run a direct target investigation or assistant command:
```bash
soldierboy investigate target@email.com
soldierboy investigate johndoe_87
soldierboy investigate target.com
```

---

## Commands

All actions can be triggered via slash commands or natural language:

### Core Commands

| Command | Aliases | Description | Usage |
| :--- | :--- | :--- | :--- |
| `investigate` | `/investigate`, `stalk` | Run multi-pass OSINT sweep against a target | `investigate <target>` |
| `resume` | `/resume`, `load` | Open saved investigation case or task log | `resume <target>` |
| `pivot` | `/pivot`, `focus` | Pivot investigation on a discovered handle or IP | `pivot <entity>` |
| `cases` | `/cases`, `list` | List all archived cases and saved sessions | `cases` |
| `notes` | `/notes`, `add` | Append investigative note or task reminder | `notes <text>` |
| `export` | `/export`, `report` | Generate offline HTML investigation & task report | `export` |
| `help` | `/?`, `info` | Display command guide and available modules | `help` |
| `exit` | `quit` | Exit workspace | `exit` |

---

## Capabilities & Arsenal

Soldier Boy combines personal assistant capabilities with specialized OSINT tools:

| Module | Category | Description |
| :--- | :--- | :--- |
| `personal_assistant` | Workflow Core | General Q&A, system commands, document analysis, and daily task management. |
| `wake_word_engine` | Voice Trigger | Production openWakeWord `hey_soldier.onnx` classifier for background activation. |
| `local_voice_clone` | Audio Engine | Zero-shot local voice synthesis powered by Chatterbox TTS. |
| `sherlock` | Username Scan | Multi-source account discovery across 300+ platforms. |
| `maigret` | Deep Identity | Advanced profile harvesting and metadata extraction. |
| `holehe` | Email Intelligence | Checks registration status across 120+ web services. |
| `gravatar` | Profile & Avatar | Public profile image, display name, and bio extraction. |
| `github_recon` | Code Intel | Repository search, commit history, and README profile parsing. |
| `dns_whois` | Domain Recon | Pulls A, AAAA, MX, TXT, CNAME records, and WHOIS registration. |
| `wayback` | History Snapshots | Discovers archived URLs and historical domain snapshots. |
| `exif_geo` | Image Metadata | Extracts GPS coordinates and camera metadata from image files. |
| `breach_directory` | Leak Inspection | Checks exposed data breaches and compromised field types. |
| `abuse_ipdb` | IP Reputation | Evaluates IP threat score, ISP, and proxy/VPN status. |
| `2d_3d_graph` | Network Topology | Guaranteed 2D SVG radial fallback + 3D WebGL relationship graph. |

---

## Scope Policy & Legal Compliance

Soldier Boy is built for **personal productivity, authorized penetration testing, bug bounty programs, CTF challenges, and legitimate security research**.
- Always obtain explicit authorization before investigating external targets.
- Users are solely responsible for ensuring compliance with all applicable local and international laws.

---

## License

This project is licensed under the [GNU General Public License v3 (GPLv3)](LICENSE).

---

## Author

<p align="center">
  <a href="https://l4zz3rj0d.github.io">
    <img src="https://img.shields.io/badge/Founder-L4ZZ3RJ0D-c0392b?style=for-the-badge" alt="L4ZZ3RJ0D"/>
  </a>
</p>

<div align="center">
  <br/>
  <sub>Built with power and precision. The Soldier Boy way.</sub>
</div>
