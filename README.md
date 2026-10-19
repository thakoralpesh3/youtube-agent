# 🚀 Autonomous AI YouTube Creator Agent

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/thakoralpesh3/youtube-agent/blob/main/YouTube_Agent_Colab.ipynb)

An end-to-end automated AI agent that daily generates viral **YouTube Shorts** (scripts, voiceovers, vertical 9:16 visuals, animated captions, titles, SEO descriptions, tags, and pinned comments) and automatically uploads them directly to your YouTube channel.

---

## 🌟 Key Features

- 🧠 **Gemini Powered Content Creation**: Generates viral hooks, high-retention 35–55s scripts, click-worthy titles, SEO descriptions, tags, and engagement-driving pinned comments.
- 🎙️ **Natural Neural TTS Voiceover**: Crystal-clear voiceovers with word-level subtitle alignment powered by Edge-TTS (free, no quota issues).
- 🎨 **Vertical 9:16 Visuals**: Automatically generates 1080x1920 vertical scenes using Gemini / Flux.
- 🎬 **Dynamic Video Assembly**: Ken Burns zoom/pan motion effects with high-contrast, viral yellow-and-black bordered animated subtitles.
- 📤 **Direct YouTube Upload**: Integrates with YouTube Data API v3 for unattended uploads (supports `public`, `unlisted`, or `private` status).
- ⏰ **Daily Automated Scheduling**: Built-in Python scheduler and cron-compatible commands for daily execution at your chosen time.

---

## 📁 Project Architecture

```
youtube-agent/
├── .env                  # API keys and channel preferences
├── config.py             # Global configuration & file path management
├── agent.py              # Central orchestrator CLI
├── scheduler.py          # Daily automation scheduler daemon
├── requirements.txt      # Python dependencies
├── generator/
│   ├── script_generator.py   # Gemini script, title, description & prompt generation
│   ├── audio_generator.py    # Edge-TTS voice synthesis & subtitle timestamps
│   ├── image_generator.py    # 9:16 AI image generation with fallback
│   └── video_assembler.py    # MoviePy vertical video rendering & animated captions
├── youtube/
│   ├── auth.py               # Google OAuth 2.0 authentication & token refresh
│   └── uploader.py           # Resumable video upload via YouTube Data API v3
├── assets/
│   ├── fonts/                # Subtitle typography (Montserrat Bold)
│   └── music/                # (Optional) Background music tracks
└── output/                   # Generated scripts, audios, images, and MP4 videos
```

---

## 🛠️ Step 1: Configuration (.env)

Edit the `.env` file in `/home/alpesh/youtube-agent/.env`:

```ini
# 1. Google Gemini API Key (Get from https://aistudio.google.com/)
GEMINI_API_KEY=your_gemini_api_key_here

# 2. YouTube Upload Privacy ("unlisted" recommended for testing, "public" for live channel)
YOUTUBE_PRIVACY_STATUS=unlisted

# 3. Channel Theme / Niche
DEFAULT_NICHE=High-Performance Adult Mindset, Stoicism, Health & Fitness Science, Mental Resilience, and Peak Daily Discipline
DAILY_UPLOAD_TIME=10:00

# 4. Voice Selection (e.g., en-US-ChristopherNeural, en-US-GuyNeural, en-US-BrianNeural)
TTS_VOICE=en-US-ChristopherNeural
```

---

## 🔑 Step 2: YouTube Channel Authorization (One-time)

To allow the agent to upload videos to your YouTube channel:

1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create a project and enable the **YouTube Data API v3** in **APIs & Services > Library**.
3. Go to **APIs & Services > OAuth consent screen**:
   - Choose **External**.
   - Add your Gmail account under **Test users**.
4. Go to **APIs & Services > Credentials**:
   - Click **Create Credentials > OAuth client ID**.
   - Application type: **Desktop app**.
   - Download the JSON file and save it as `/home/alpesh/youtube-agent/client_secret.json`.
5. Run the one-time authentication command:
   ```bash
   /home/alpesh/youtube-agent/.venv/bin/python agent.py --auth
   ```
   This will generate `token.json`, enabling future unattended daily uploads.

---

## 🚀 How to Run

### 1. Test Video Generation Locally (Dry Run - No Upload)
Generates the script, voiceover, images, and MP4 video in `output/` without uploading to YouTube:
```bash
/home/alpesh/youtube-agent/.venv/bin/python agent.py --dry-run
```

### 2. Generate and Upload Immediately
```bash
/home/alpesh/youtube-agent/.venv/bin/python agent.py --run-now
```

### 3. Generate on a Specific Topic
```bash
/home/alpesh/youtube-agent/.venv/bin/python agent.py --run-now --topic "Why Discipline Beats Motivation Every Single Time"
```

### 4. Run the Daily Scheduler (Daemon Mode)
Runs continuously in the background and generates/uploads every day at the time specified in `.env` (`DAILY_UPLOAD_TIME`):
```bash
/home/alpesh/youtube-agent/.venv/bin/python agent.py --schedule
```

---

## ⏰ Running via Linux Crontab (Optional)

If you prefer scheduling via system cron:
```bash
crontab -e
```
Add the following line to run daily at 10:00 AM:
```cron
0 10 * * * /home/alpesh/youtube-agent/.venv/bin/python /home/alpesh/youtube-agent/agent.py --run-now >> /home/alpesh/youtube-agent/output/cron.log 2>&1
```
