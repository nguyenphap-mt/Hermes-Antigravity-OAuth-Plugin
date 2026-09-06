# 🌟 Hermes Antigravity OAuth & Google Flow Multi-Provider Suite

<div align="center">
  <img src="docs/assets/banner_mockup.jpg" alt="Hermes Antigravity OAuth & Google Flow Suite" width="100%" />
</div>

> **Premium extension suite for Hermes Agent**, delivering end-to-end integration of top-tier AI models from **Google Antigravity OAuth** (Gemini 2.5/3.7, Claude 3.5/3.7 Sonnet & Opus, GPT-OSS 120B), **AI Image Generation** (Gemini 3.1 Flash Image), and **Cinematic AI Video Generation** (Google Flow Veo 3.1 & Omni 1.1 Flash) into Hermes Agent — across CLI, Telegram, Discord, TUI, and Web Dashboard.

**Version:** `v3.1.0 (September 2026 - Production Ready)`  
**Author:** Nguyen Phap  
**License:** MIT / Apache 2.0  

> [!CAUTION]
> **DISCLAIMER & LIABILITY WAIVER:**  
> This project is an independent open-source tool built for educational and technical research purposes only and is neither affiliated with nor endorsed by Google LLC. Automating or accessing experimental endpoints carries inherent risks of violating Google's Terms of Service, which may lead to account suspension, restrictions, or termination. The developers and contributors **assume zero liability** for any actions taken or consequences to your Google accounts. Users are strongly advised to use dedicated secondary accounts. For full details, see [Disclaimer & Terms of Use](#-disclaimer--terms-of-use).

---

## 📌 Architectural Overview & Core Pillars

```
                  ┌──────────────────────────────────────────────┐
                  │          HERMES AGENT ECOSYSTEM              │
                  │   (CLI, Telegram, Discord, Web Dashboard)    │
                  └──────┬───────────────────┬───────────────────┘
                         │                   │
         ┌───────────────▼────────┐  ┌───────▼──────────────────┐
         │  Model Provider Plugin │  │ Image & Video Providers  │
         │ (plugins/model-prov...)│  │ (plugins/image_gen, ...) │
         └───────────────┬────────┘  └───────┬──────────────────┘
                         │                   │
                         ▼                   ▼
    ┌───────────────────────────────────────────────────────────────┐
    │              ANTIGRAVITY LOOPBACK BRIDGE ENGINE               │
    │                   (tools/antigravity_bridge)                  │
    ├───────────────────────────────┬───────────────────────────────┤
    │  • OAuth 2.0 PKCE Multi-Acc   │  • Camofox Browser Bridge     │
    │  • Credential Pool Strategies │  • reCAPTCHA Enterprise Token │
    │  • Token Auto-Refresh Daemon  │  • Google Flow Generator      │
    │  • 32+ Dynamic Model Catalog  │  • Local HTTP Proxy (v1 API)  │
    └───────────────────────────────┴───────────────────────────────┘
```

### 1. 🧠 LLM Chat & Code Assist (`plugins/model-providers/antigravity`)
- **OpenAI-Compatible Local Loopback**: Runs local HTTP proxy at `http://127.0.0.1:8100/v1` (`/v1/chat/completions`, `/v1/models`).
- **Dynamic Model Discovery (32+ Models)**: Automatically discovers available models from Google Cloud Code Assist based on active account entitlements (Gemini 3.7 Flash/Pro, Gemini 2.5 Flash/Pro, Claude 3.5/3.7 Sonnet, Claude 3.7 Sonnet Thinking, Claude Opus 4.6, GPT-OSS 120B).
- **Multi-Modal Vision**: Translates inline/URL images into Google API `inlineData` structure.
- **Native Structured Tool Calling**: Two-way schema translation between OpenAI JSON Schema and Google `functionDeclarations`, strictly honoring Hermes message role alternation rules.
- **Reasoning / Thinking Forwarding**: Full support for `thinking_config` on thinking-enabled models.
- **Daemon Auto-Wake**: Automatically checks and starts the background bridge server on-demand without manual intervention.

### 2. 🔑 OAuth 2.0 PKCE & Credential Pool (`tools/antigravity_bridge`)
- **1-Click Browser Login**: Standard OAuth 2.0 PKCE flow via desktop browser, obtaining and persisting refresh tokens.
- **Multi-Account Pool**: Run and balance multiple independent Google accounts within a single Hermes profile.
- **4 Load Balancing Strategies**:
  - `fill_first`: Exhaust current account's quota before rotating.
  - `round_robin`: Sequential round-robin rotation across calls.
  - `least_used`: Prioritize account with lowest invocation count.
  - `random`: Uniformly random distribution across active accounts.
- **Auto-Cooldown & Failover**: On `429 Too Many Requests` or quota exhaustion, automatically tags the account `COOLING_DOWN` and fails over to the next account immediately.
- **Background Token Refresh Daemon**: Silently renews expiring access tokens to eliminate `401 Unauthorized` errors.

### 3. 🖼️ AI Image Generation Backend (`plugins/image_gen/antigravity`)
- **Core Tool Integration**: Registers as a native `ImageGenProvider` under name `antigravity`.
- **Engine**: Powered by `gemini-3.1-flash-image` (or Imagen 3) via Google Antigravity endpoints.
- **Flexible Ratios**: Supports `1:1`, `16:9`, `9:16`, `4:3`, and `3:4` aspect ratios, Text-to-Image and Image-to-Image.
- **Auto-Healing**: Automatically re-establishes bridge runtime files if wiped during git updates.

### 4. 🎬 AI Video Generation - Google Flow Veo 3.1 (`plugins/video_gen/antigravity`)
- **Core Tool Integration**: Registers as an official `VideoGenProvider` under name `antigravity`.
- **Camofox Anti-Detection & Sandbox Bridge**:
  - Dynamically extracts valid `reCAPTCHA Enterprise` tokens to execute requests against `aisandbox-pa.googleapis.com` (completely resolves HTTP 403 Forbidden).
  - **Headless Auto-Refresh & Keep-Alive Daemon**: Maintains continuous 30-day rolling sessions in the background without needing Chrome tabs open.
- **5 Intent-Based Quality Tiers**:
  1. **Free 100% (0 credits)**: `veo-3.1-lite-free` (4s) — Previews, drafts, script experimentation.
  2. **Budget / Lite (5 credits)**: `veo-3.1-lite` (6s) — Ultra-fast rendering, minimal credit cost.
  3. **Standard (6 credits)**: `omni-1.1-flash` (10s) — **Default**, balanced quality with synchronized natural audio.
  4. **Fast / Premium (10 credits)**: `veo-3.1-fast` (10s) — Crisp motion physics, high definition.
  5. **Studio Quality (100 credits)**: `veo-3.1-quality` (10s) — Maximum cinematic detail, optical studio simulation.
- **Automatic Media Delivery**: Polls generation status, downloads `.mp4` video locally (`~/.hermes/media/flow/`), and delivers directly to Telegram/Discord.
- **Bundled Skill**: `skills/ai-video-generation` instructs the agent to invoke `video_generate` natively instead of writing ad-hoc FFmpeg scripts.

### 5. 🌐 Web Dashboard & Runtime Dynamic Injector (`injector.py`)
- **Zero Core Modifications Principle**: Leaves core Hermes repository files untouched.
- **In-Memory Dynamic Monkey-Patching**: Injects Antigravity management cards, model options, and API endpoints into FastAPI Web Dashboard during startup:
  - `/api/credentials/providers/antigravity/accounts`
  - `/api/credentials/providers/antigravity/oauth/start`
  - `/api/credentials/providers/antigravity/oauth/poll`

---

## 📂 Project Directory Structure

```
Hermes-Antigravity-OAuth-Plugin/
├── README.md                      # English Documentation (this file)
├── README_VN.md                   # Vietnamese Documentation
├── Login_Google_Flow.cmd          # 1-Click Interactive Google Flow Login Utility
├── install.py                     # 1-Click Multi-Profile & Multi-Workspace Installer
├── manage.py                      # CLI Management tool for Bridge, Accounts & Flow
│
├── plugin/                        # Hermes Model Provider Plugin
│   ├── plugin.yaml                # Provider metadata
│   ├── __init__.py                # ProviderProfile & Auto-wake bridge
│   └── injector.py                # Dynamic FastAPI Runtime Injector
│
├── bridge/                        # Antigravity Runtime Bridge Engine
│   ├── auth.py                    # OAuth PKCE Manager & Token Persistence
│   ├── account_pool.py            # Multi-account pool & 4 rotation strategies
│   ├── client.py                  # OpenAI ↔ Gemini Code Assist translator
│   ├── models.py                  # Live Discovery of 32+ Models & Caching
│   ├── server.py                  # Local HTTP Proxy server on port 8100
│   │
│   └── flow/                      # Google Flow Veo 3.1 Bridge
│       ├── camofox_bridge.py      # Camofox control & reCAPTCHA Enterprise extraction
│       ├── flow_refresh_daemon.py # Headless token auto-refresh daemon
│       ├── flow_auth_service.py   # Flow session manager
│       ├── account_pool.py        # Independent Flow account pool
│       ├── generators.py          # T2V and I2V generation endpoints
│       └── tools.py               # Model tool schemas
│
├── image_gen/antigravity/         # Image Generation Plugin
│   ├── plugin.yaml                # Image provider declaration
│   └── __init__.py                # ImageGenProvider & Auto-heal logic
│
├── video_gen/antigravity/         # Video Generation Plugin (Google Flow)
│   ├── plugin.yaml                # Video provider declaration
│   └── __init__.py                # VideoGenProvider (5 tiers & auto-routing)
│
├── dashboard/                     # Web Dashboard Assets
│   └── plugin_api.py              # Dashboard API handlers
│
└── skills/ai-video-generation/    # Specialized Agent Skill
    └── SKILL.md                   # Explicit directive for video_generate tool
```

---

## 📋 Prerequisites & Preparation Checklist

Before running the installer `install.py`, ensure your system meets the following prerequisites:

### 1. Runtime & Tools Prerequisites
- **Python:** Version `>= 3.10` (Recommended `3.11` – `3.12`, fully supports `3.14`).
- **Node.js & npm:** Version `18+` (Recommended `20+` or `22+`) — Required if operating Camofox browser server for Google Flow Video Generation.
- **Google Chrome:** Installed on desktop with your Google account logged in (used for 1-Click PKCE and Flow Handshake).
- **Hermes Agent:** Active `hermes-agent` checkout and initialized configuration directory `~/.hermes`.

### 2. Python Dependencies
Install the required packages in your Hermes Python environment or virtualenv:
```bash
# 1. Core libraries for Bridge Server, Model Discovery & Account Pool
pip install aiohttp httpx requests pyyaml

# 2. Browser automation (Required for Google Flow Video Generation)
pip install playwright
playwright install chromium
```
> [!NOTE]
> If you only intend to use **LLM Chat/Code Assist** and **Image Generation**, only Group 1 (`aiohttp httpx requests pyyaml`) is needed. `playwright` is required when using **Google Flow Video Generation** (`manage.py flow-login` / `flow-handshake`).

### 3. Google Accounts & Access Preparation
- **Google Antigravity Account:**
  - At least **1 Google Account** with access to Google Antigravity / Google Cloud Code Assist.
  - *Recommended:* Prepare **2–3 accounts** for the Multi-Account Pool (`python manage.py login`) to enable automatic failover and cooling down when hitting quota limits (`429 Too Many Requests`).
- **Google Flow Account (AI Video Generation):**
  - An account eligible to access [Google Flow Studio](https://labs.google/fx/tools/flow).
  - Verify remaining AI credits if targeting paid tiers (5 - 100 credits), or utilize the `veo-3.1-lite-free` (0 credit) tier.

### 4. Ports & Network Connectivity
- Ensure the following localhost loopback ports are free and unblocked by antivirus/firewalls:
  - `Port 8100`: Antigravity Local Reverse-Proxy Bridge (`http://127.0.0.1:8100/v1`).
  - `Port 51121`: OAuth 2.0 PKCE Callback Listener (`http://localhost:51121/oauth-callback`).
  - `Port 9377`: Camofox Browser Server (for Google Flow Sandbox API).
- Ensure unrestricted outbound connectivity to Google endpoints (`accounts.google.com`, `daily-cloudcode-pa.googleapis.com`, `cloudcode-pa.googleapis.com`, `labs.google`, `aisandbox-pa.googleapis.com`). If Google Flow is geo-restricted in your region, enable a suitable VPN/proxy before handshaking.

---

## 🚀 Installation & Usage

### Method 1: 1-Click Automated Installer (Recommended)

From the plugin directory, execute:
```bash
python install.py
```

**The installer automatically:**
1. Detects all Hermes homes (`~/.hermes`, `AppData/Local/hermes`, and profiles like `test-bot1`, `test-bot2`).
2. Detects all active local `hermes-agent` checkouts.
3. Installs Plugin, Bridge, Image Gen, Video Gen, and Dashboard components.
4. Sets up a git `post-merge` hook to automatically preserve and re-sync files upon `git pull`.
5. Clears stale model caches to make newly discovered models immediately accessible.

---

### Method 2: Management CLI (`manage.py`)

```bash
# Check status across Bridge, Account Pool, Camofox & Google Flow
python manage.py status

# Add a new Google Antigravity account via OAuth
python manage.py login

# Manage Credential Pool accounts and strategy
python manage.py pool list
python manage.py pool set-strategy round_robin

# 4. Inspect, refresh, and authenticate Google Flow
python manage.py flow-status       # Check status, email, ya29 token expiry & 30-day cookie
python manage.py flow-refresh      # Headless direct-endpoint session renewal
python manage.py flow-login        # Interactive browser login window (or click Login_Google_Flow.cmd)

# 5. Start / Stop Bridge daemon manually
python manage.py start
python manage.py stop
```

---

## 🛡️ Update Resilience Assessment (`git pull`)

| Component | Storage Location | Resilience | Protection Mechanism |
| :--- | :--- | :---: | :--- |
| **Tokens & Multi-Account Data** | `~/.hermes/auth/` | 🟢 **100% Resilient** | Outside git repository; never affected by `git pull` or resets. |
| **User Configuration (`config.yaml`)** | `~/.hermes/config.yaml` | 🟢 **100% Resilient** | Stored in user home, preserving all provider settings. |
| **User Plugins** | `~/.hermes/plugins/` | 🟢 **100% Resilient** | Discovered with priority by Hermes PluginManager. |
| **Bridge Runtime Engine** | `~/.hermes/bridge/` | 🟢 **100% Resilient** | Imported directly from user home if repo copy is missing. |
| **Workspace Bridge** | `tools/antigravity_bridge` | 🟢 **Self-Healing** | Automatically restored by `image_gen` auto-heal logic. |
| **Dashboard UI Injection** | In-Memory (RAM) | 🟢 **95% Resilient** | Uses dynamic runtime monkey-patching without touching core files. |
| **Core tool `video_generate`** | `toolsets.py` | 🟡 **Auto-Restored via Hook** | Automatically re-inserted into `toolsets.py` via Git post-merge hook or running `install.py` post-update. |

---

## 🔄 Authentication Lifecycle & Rolling Session Architecture (3-Tier Security)

To ensure Google Flow Veo 3.1 video generation remains continuously accessible 24/7 without repeatedly interrupting the user with login prompts, the system employs a robust 3-Tier Authentication Lifecycle combined with rolling session renewal:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      3-TIER AUTHENTICATION LIFECYCLE                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  [TIER 1]  Google Flow Access Token (Bearer ya29...)                    │
│            • Expiration: ~1 hour                                        │
│            • Scope: Direct API requests to aisandbox-pa.googleapis.com  │
│            • Storage: ~/.hermes/auth/flow_token.json                    │
│                 ▲                                                       │
│                 │ (Silently renewed before generation or on-demand)     │
│                 │                                                       │
│  [TIER 2]  NextAuth Session Cookie (__Secure-next-auth.session-token)   │
│            • Expiration: 30 days (ROLLING EXTENSION)                    │
│            • Mechanism: Every video request or flow-refresh call        │
│              AUTOMATICALLY EXTENDS this cookie by an additional 30 DAYS │
│              from the moment of invocation!                             │
│            • NO NEED to keep browser windows or tabs open.              │
│                 ▲                                                       │
│                 │ (Only re-authenticated if completely idle > 30 days)  │
│                 │                                                       │
│  [TIER 3]  Google Account SSO (Chrome Profile Session)                  │
│            • Storage: ~/.hermes/flow_browser_session/ (Chrome Profile 2)│
│            • Root fallback session if NextAuth cookie is invalidated.   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1. Do I need to keep `labs.google/fx/tools/flow` open in my browser?
> **ABSOLUTELY NOT.**  
> You do not need to keep Google Chrome open, nor keep any `labs.google` tab alive on your desktop.  
> Whenever you instruct Hermes to generate a video (or run `manage.py flow-refresh`), the background daemon spins up a headless browser instance in 2–3 seconds, extracts a freshly minted `ya29...` bearer token, and immediately shuts down. Everything occurs invisibly in the background.

### 2. Rolling Session Mechanism — Will I be logged out after 30 days?
> **NO, as long as you use Hermes periodically within each 30-day window.**  
> - **How it works:** NextAuth utilizes a **Rolling Session** model. Each time Hermes contacts the Google Flow session endpoint during generation or status checks, Google automatically rolls over the cookie expiration date to **30 days starting from that exact interaction**.  
> - **Real-world Example:** If you generate a video on Day 20, your session is renewed for another 30 days (extending your total validity to 50 days from your initial login).  
> - **When is re-login required?** You only need to log in again if:
>   1. You do not generate any videos or refresh tokens for more than 30 consecutive days.
>   2. You change your Google account password or revoke sessions via Google Security settings.

### 3. Stability Hardening & Error Protections (v3.1.0)
- **Direct Session Endpoint**: Google Flow currently redirects from `labs.google/fx/tools/flow` to `flow.google.com`. To eliminate CORS and 404 routing anomalies caused by client-side redirects, the refresh daemon accesses `https://labs.google/fx/api/auth/session` directly, delivering sub-1.5s token extraction.
- **Windows DPAPI Cookie Decryption**: Google Chrome on Windows protects SQLite cookies using OS-level DPAPI encryption. Playwright is configured with `channel="chrome"`, enabling native decryption of encrypted cookies from your local Chrome profile.
- **Test Pollution Guard (`is_prod`)**: Production credentials in `~/.hermes/auth/flow_token.json` are strictly shielded from `pytest` suites via destination path verification, guaranteeing test fixtures never overwrite real tokens.
- **Multi-Profile Synchronization**: `install.py` seamlessly propagates these security fixes across all 7 Hermes profile homes on your workstation.

### 4. Convenient Login & Maintenance Utilities
- **1-Click Interactive Login**: Double-click `Login_Google_Flow.cmd` in the plugin directory to launch the dedicated login browser window.
- **CLI Commands**:
  ```bash
  # Check bearer token validity, remaining minutes, and 30-day session cookie
  python manage.py flow-status

  # Perform headless token renewal on-demand
  python manage.py flow-refresh

  # Launch interactive browser session for login or re-authentication
  python manage.py flow-login
  ```

---

## ❓ Frequently Asked Questions (FAQ)

#### Q1: Why did the bot fall back to FFmpeg image stitching instead of using Google Flow?
> **A:** If a prior generation request encountered an error in the chat session, LLMs may latch onto conversational context and default to fallback scripts.  
> **Fix:** Run `/reset` or `/new` in your Telegram/Discord chat. This clears the historical context and enforces the `ai-video-generation` skill to invoke `video_generate` via Google Flow.

#### Q2: How can I check my remaining Google Flow AI credits?
> **A:** Execute `python manage.py flow-status`. It displays the authenticated email address, Camofox connection status, and remaining credit balance.

#### Q3: What should I do if `git pull` fails with "local changes would be overwritten"?
> **A:** Open your terminal inside `hermes-agent` and run:
> ```bash
> git stash
> git pull
> python install.py
> ```
> All custom providers, tools, and configurations will be cleanly restored.

#### Q4: Do I need to keep Chrome or a tab open for Flow to work?
> **A:** No. The headless daemon executes in the background only when generating media or refreshing tokens. Chrome does not need to be running.

#### Q5: Is re-login strictly required after 30 days?
> **A:** No. Thanks to the **Rolling Session** design, every video generation automatically resets the 30-day counter. As long as you generate at least one video every 30 days, your session remains permanently active.

#### Q6: Why does the system open an interactive browser window instead of automating password entry?
> **A:** Google's automated threat detection flags headless scripts attempting to submit passwords on `accounts.google.com` with *"This browser or app may not be secure"*. Launching an interactive browser once guarantees full 2FA compatibility and compliant session persistence without security triggers.

---

## ⚖️ Disclaimer & Terms of Use

Before installing and utilizing the **Hermes Antigravity OAuth & Google Flow Plugin**, users must read, understand, and agree to the following terms and disclaimers:

1. **Independent Educational & Technical Research Project:**
   - This plugin is developed strictly as an independent open-source project for educational research, software experimentation, and personal AI agent integration.
   - This project is **not affiliated with, endorsed, sponsored, or certified by Google LLC or Alphabet Inc.** All trademarks and brand names belong to their respective owners.

2. **Inherent Risks of Account Suspension or Termination:**
   - Google Flow (Labs FX), Google Antigravity (Code Assist), and Google Veo are experimental proprietary platforms governed by Google's Terms of Service and acceptable use policies.
   - Leveraging browser automation frameworks (Playwright/Camofox), local reverse proxies, cookie session extraction, or non-public endpoints may be detected by Google's automated threat detection and abuse-prevention systems.
   - Google reserves the right at its sole discretion to impose penalties, including but not limited to:
     - Demanding repeated CAPTCHA or identity verification.
     - Revocation of access to Google Flow / Google Labs preview features.
     - Forfeiture or resetting of available AI generation credits.
     - Temporary suspension or **permanent termination of your Google account** and associated services.

3. **Complete Waiver of Liability (Zero Liability Policy):**
   - The authors, maintainers, and contributors of this repository **EXPRESSLY DISCLAIM ALL WARRANTIES AND ASSUME ABSOLUTELY ZERO LIABILITY OR RESPONSIBILITY** for:
     - Any Google account suspension, ban, limitation, or flagging incurred directly or indirectly through the use of this software.
     - Any data loss, service interruption, or loss of access to associated Google services (Gmail, Google Drive, Google Photos, contacts, YouTube channels, etc.).
     - Any direct, indirect, incidental, special, or consequential financial damages or lost credits.
   - **You assume 100% of all risks, liabilities, and consequences** associated with deploying and executing this tool.

4. **Safe Usage Best Practices & Recommendations:**
   - 🛡️ **DO NOT USE YOUR PRIMARY PERSONAL ACCOUNT:** Never link a critical Google account that holds irreplaceable emails, work credentials, family photos, or business documents.
   - 🧪 **ALWAYS USE A DEDICATED SECONDARY / BURNER ACCOUNT:** Create and designate an independent Google account specifically for AI experimentation and media rendering.
   - ⏱️ **Avoid Aggressive Request Spikes (Rate Limiting):** Refrain from scripting rapid-fire generation requests that can trigger automated bot-detection tripwires.
   - 📜 **Abide by Platform Policies:** Respect AI safety guidelines and acceptable usage boundaries established by service providers.

---

## 📝 Changelog

### v3.1.0 (September 6, 2026) - Headless Rolling Session & Auth Hardening
- ✅ **3-Tier Auth Lifecycle & Rolling Session**: 30-day session cookies roll over upon every generation, enabling long-term persistence without open browser tabs.
- ✅ **Direct Session Endpoint**: Fast and resilient retrieval via `https://labs.google/fx/api/auth/session` bypassing domain redirects.
- ✅ **Windows DPAPI Cookie Decryption**: Configured `channel="chrome"` for Playwright to decrypt protected SQLite cookies on Windows.
- ✅ **Test Pollution Guard**: Enforced `is_prod` safety check to protect production `flow_token.json` from test runs.
- ✅ **1-Click Login Utility (`Login_Google_Flow.cmd`) & CLI `flow-refresh`**: Added interactive launcher and manual headless renewal commands.

### v3.0.0 (September 5, 2026) - The Unified AI Multi-Provider Release
- ✅ **Google Flow Veo 3.1 & Omni 1.1 Flash**: Integrated 5-tier video generation architecture with Text-to-Video and Image-to-Video support.
- ✅ **reCAPTCHA Enterprise Resolution**: Hardened Camofox script evaluation to eliminate HTTP 403 Forbidden on Google Sandbox calls.
- ✅ **Dynamic Model Discovery (32+ Models)**: Live catalog discovery for Claude 3.7 Thinking, Gemini 2.5/3.7, and GPT-OSS.
- ✅ **Dynamic Runtime Injector (`injector.py`)**: Zero-Core modification architecture for FastAPI Web Dashboard.
- ✅ **Multi-Home & Profile Installer**: Enhanced `install.py` with multi-profile and multi-workspace support.
- ✅ **Self-Healing Bridge Engine**: Automated restoration of bridge assets during git operations.

### v2.1.0 (August 31, 2026)
- ✅ Resolved `thoughtSignature` handling for Gemini 3 models.
- ✅ Fixed `ConnectionResetError` crashes on local bridge server.
- ✅ Added daemon auto-wake mechanism `ensure_antigravity_bridge_running()`.

### v2.0.0 (August 28, 2026)
- ✅ Initial release featuring OAuth 2.0 PKCE, Multi-Account Pool, and port 8100 Proxy.
