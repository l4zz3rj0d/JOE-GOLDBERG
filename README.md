<p align="center">
  <img src="assets/joegui.png" alt="Joe Goldberg" width="100%"/>
</p>

<h1 align="center">JOE GOLDBERG : OSINT INVESTIGATOR</h1>
<p align="center">
  <b>Autonomous OSINT Investigator & Ethical Stalker Workspace by Project Hellhound</b>
  <br>
  <i>Target enumeration, identity pivoting, multi-source username scans, email intelligence, internal voice monologue synthesis, interactive 2D/3D correlation topology graphs, collapsible card UI, and zero-leak privacy — from initial handle to evidence report.</i>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> ·
  <a href="#installation--setup">Installation & Setup</a> ·
  <a href="#ai-model-routing--voice-synthesis">AI & Voice Routing</a> ·
  <a href="#commands">Commands</a> ·
  <a href="#the-osint-arsenal">Arsenal</a> ·
  <a href="#what-it-finds">What It Finds</a> ·
  <a href="#desktop-gui-app">Desktop GUI</a> ·
  <a href="#license">License</a>
</p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.10+-blue?style=flat-square&logo=python&logoColor=white" alt="Python Version"/></a>
  <a href="https://github.com/project-hellhound-org/JOE-GOLDBERG/releases"><img src="https://img.shields.io/badge/Release-v2.0.0-red?style=flat-square" alt="Release Version"/></a>
  <img src="https://img.shields.io/badge/AI--Powered-Ollama%20%7C%20NVIDIA%20NIM%20%7C%20Gemini-red?style=flat-square" alt="AI Support"/>
  <img src="https://img.shields.io/badge/Voice-Fish%20Audio%20TTS-orange?style=flat-square" alt="Voice Engine"/>
  <img src="https://img.shields.io/badge/Recon-Sherlock%20%7C%20Maigret%20%7C%20Holehe%20%7C%20DNS%20%7C%20Wayback%20%7C%20EXIF-red?style=flat-square" alt="Recon Toolchain"/>
  <img src="https://img.shields.io/badge/Platform-Linux%20%7C%20macOS-lightgrey?style=flat-square" alt="Platform"/>
  <img src="https://img.shields.io/badge/License-GPLv3-blue?style=flat-square" alt="License"/>
</p>

---

> [!NOTE]
> ### 👁️ Persona & Privacy Notice
> **Joe Goldberg** operates as an autonomous OSINT stalker and investigator. He gathers open-source intelligence, connects target identity webs, and narrate findings in his signature **internal monologue voice**. All requests run locally or through encrypted API bridges with zero data leaving your machine without explicit permission.

---

## What Is This?

**Joe Goldberg** is the autonomous OSINT investigation and ethical stalking framework developed by **Project Hellhound**. Built for security researchers, penetration testers, bug bounty hunters, and CTF practitioners, Joe Goldberg autonomously maps digital footprints, verifies identity handles, extracts email profiles, pulls domain infrastructure, captures EXIF geolocation metadata, visualizes entity networks, and synthesizes internal monologue observations in real time.

It features **persistent target memory and an automated case blackboard**—discovered handles, emails, domain DNS records, IP locations, Wayback snapshots, profile screenshots, and notes are automatically retained in isolated per-target workspaces (`~/.joe/cases/<target>/`) so investigations seamlessly resume across sessions.

Works across three flexible interfaces:
- **Interactive Terminal**: An interactive terminal environment with real-time monologue streaming, live progress feedback, and inline command execution (`joe --cli`).
- **Headless CLI Runner**: Direct one-line command execution for automated scripts (`joe stalk <target>`).
- **Desktop GUI Application**: A dedicated pywebview/fastapi desktop application featuring collapsible card modules, transparent eye API toggles, 2D/3D radial topology graphs, and live Fish Audio TTS voice narration (`joe`).

---

## How It Works

```
You ──> joe stalk <target> ──> Input Parser ──> Scope & Entity Resolver
                                     │                     │
                                     ▼                     ▼
                           Active OSINT Modules     Reconnaissance Toolchain
                           ├─ Sherlock & Maigret   (Sherlock, Maigret, Holehe)
                           ├─ Holehe & Gravatar    (WHOIS, DNS, Wayback, EXIF)
                           ├─ GitHub & Mentions    (BreachDirectory, AbuseIPDB)
                           └─ GeoIP & Wayback      
                                     │
                                     ▼ (Populates Non-Prunable Case Blackboard)
                           Narrator Engine <── NLP Stage-Direction Filter
                                     │            (Fish Audio TTS / Gemma2 Local)
                                     ▼
                           /export (Submission-Ready HTML Case Report)
```

- **Collapsible Card System**: Settings, ledgers, and maps render in responsive card components with collapsible header toggles (`▼` / `▶`) and real-time state badges.
- **Eye Toggle Security**: API key fields (Gemini, NVIDIA NIM, Fish Audio) feature transparent eye buttons (`👁`) for password visibility control.
- **Filtered Voice Monologue**: Fish Audio TTS integration with an NLP filter that strips stage directions, keeping Joe's voice strictly in character.
- **Guaranteed Graph Topology**: 2D SVG radial network fallback + 3D WebGL graph populating target connections alongside active OSINT skill nodes.

---

## AI Model Routing & Recommended Providers

Autonomous intelligence gathering and multi-pass identity pivoting utilize fast SLMs and frontier LLMs for intent parsing and monologue synthesis.

> [!TIP]
> ### 💡 Recommended AI Providers (Free & Paid)
> - **For Local Users (100% Offline)**: Run **gemma2:2b** or **qwen2.5:3b** locally via Ollama. Zero cost and complete privacy.
> - **For Free Cloud Inference**: Use **Google Gemini 2.5 Flash** or **NVIDIA NIM** (`meta/llama-3.3-70b-instruct`) for rapid monologue synthesis and deep context handling.
> - **For Voice Synthesis**: Use **Fish Audio TTS** with custom reference models (`s2.1-pro-free`).

---

## Installation & Setup

Everything you need to install, configure AI backends, and run Joe Goldberg in one unified workflow.

### 1. Requirements & Prerequisites
- **Operating System**: Linux (Ubuntu, Debian, Kali, Arch), macOS.
- **Python**: Version 3.10 or higher.
- **Git & Curl**: Required for installation and updates.
- **Ollama**: (Installed automatically for local SLM fallback).

### 2. Fast Deploy

#### Standard Git Clone
```bash
git clone https://github.com/project-hellhound-org/JOE-GOLDBERG.git
cd JOE-GOLDBERG
chmod +x install.sh
./install.sh
```

#### Reload Shell Environment
```bash
source ~/.bashrc   # or source ~/.zshrc
```

The automated installer will:
- Set up an isolated Python environment.
- Install OSINT tools (Sherlock, Maigret, Holehe, etc.).
- Mount the desktop application dependencies (`pywebview`).
- Create global `joe` command integration.

---

## Quick Start

### 1. Native Desktop GUI App
Launch the desktop application with collapsible cards and interactive 2D/3D topology graph:
```bash
joe
```

### 2. Interactive Terminal
Launch the interactive CLI interface:
```bash
joe --cli
```

### 3. Headless Direct Command
Run a direct target investigation:
```bash
joe stalk target@email.com
joe stalk johndoe_87
joe stalk target.com
```

---

## Commands

All actions can be triggered via slash commands or natural language:

### Core Commands

| Command | Aliases | Description | Usage |
| :--- | :--- | :--- | :--- |
| `stalk` | `/stalk`, `investigate` | Run multi-pass OSINT sweep against a target | `stalk <target>` |
| `resume` | `/resume`, `load` | Open saved investigation case file | `resume <target>` |
| `pivot` | `/pivot`, `focus` | Pivot investigation on a discovered handle or IP | `pivot <entity>` |
| `cases` | `/cases`, `list` | List all archived investigation cases | `cases` |
| `notes` | `/notes`, `add` | Append investigative note to active case | `notes <text>` |
| `export` | `/export`, `report` | Generate offline HTML investigation report | `export` |
| `help` | `/?`, `info` | Display command guide and available modules | `help` |
| `exit` | `quit` | Exit workspace | `exit` |

---

## The OSINT Arsenal

Joe Goldberg coordinates specialized OSINT modules into a unified execution pipeline:

| Module | Category | Engine | Description |
| :--- | :--- | :--- | :--- |
| `sherlock` | Username Enumeration | Sherlock Engine | Multi-source account discovery across 300+ platforms. |
| `maigret` | Deep Identity | Maigret Engine | Advanced profile harvesting and metadata extraction. |
| `holehe` | Email Intelligence | Holehe Engine | Checks registration status across 120+ web services. |
| `gravatar` | Profile & Avatar | Gravatar API | Public profile image, display name, and bio extraction. |
| `github_recon` | Code Intel | GitHub API / Scraper | Repository search, commit history, and README profile parsing. |
| `dns_whois` | Domain Recon | WHOIS & DNS Resolver | Pulls A, AAAA, MX, TXT, CNAME records, and WHOIS registration. |
| `wayback` | History Snapshots | Wayback Machine API | Discovers archived URLs and historical domain snapshots. |
| `exif_geo` | Image Metadata | ExifTool Engine | Extracts GPS coordinates and camera metadata from image files. |
| `breach_directory` | Leak Inspection | BreachDirectory API | Checks exposed data breaches and compromised field types. |
| `abuse_ipdb` | IP Reputation | AbuseIPDB Scraper | Evaluates IP threat score, ISP, and proxy/VPN status. |
| `dork_fallback` | Search Dorking | Google Dork Engine | Automated search dorking fallback for untracked targets. |
| `grounding_auditor` | Anti-Hallucination | Verification Engine | Validates narration statements against verified entity data. |
| `2d_3d_graph` | Network Topology | D3 / Three.js Engine | Guaranteed 2D SVG radial fallback + 3D WebGL relationship graph. |
| `eye_toggle_security`| UI Security | HTML5 / JS Gate | Transparent eye buttons (`👁`) for secure API key visibility control. |
| `collapsible_cards` | UI Architecture | Responsive CSS Grid | Collapsible card modules with header badges and chevron toggles (`▼`). |

---

## What It Finds

### 1. Digital Footprint & Identity Mapping
- **Usernames**: 300+ platform scans (`sherlock`, `maigret`), identity pivoting across handles, and profile picture extraction.
- **Email Intelligence**: Account registration status (`holehe`), Gravatar profiles, and email-to-username linkage.
- **Code & Social Mentions**: GitHub commits, repositories, README profiles, and paste site mentions (`psbdmp`).

### 2. Infrastructure & Historical Assets
- **Domain & IP Footprints**: DNS records, WHOIS data, IP Geolocation, proxy/VPN detection, and AbuseIPDB scoring.
- **Archived History**: Historical Wayback Machine snapshots and endpoint discovery.
- **Media Intel**: EXIF metadata and embedded GPS coordinates.

---

## Desktop GUI App

Joe Goldberg features a native desktop interface built with **pywebview** and **FastAPI**:

```bash
joe
```

- **Collapsible Cards System**: Declutter your workspace by expanding or collapsing Settings, Evidence Ledgers, and Location Maps (`▼` / `▶`).
- **Transparent Eye API Key Toggles**: Securely view or hide API keys (Gemini, NVIDIA, Fish Audio) with dynamic input masking (`👁`).
- **Guaranteed Topology Graph**: 2D SVG radial network fallback + WebGL 3D relationship graph populated with active OSINT skill nodes.
- **Filtered Voice Transcript**: Real-time Fish Audio narration with an NLP filter removing stage directions for a true internal monologue.

---

## Scope Policy & Legal Compliance

Joe Goldberg is built strictly for **authorized penetration testing, bug bounty programs, CTF challenges, and legitimate security research**.
- Always obtain explicit authorization before investigating any target.
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
  <sub>Built with obsession. Like Joe would.</sub>
</div>
