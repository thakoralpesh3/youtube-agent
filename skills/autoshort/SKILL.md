---
name: autoshort
description: >-
  Autonomous end-to-end Short creation pipeline. Generates viral 9:16 vertical videos
  from raw prompt or trending topic: script generation, TTS voice synthesis,
  photorealistic AI imagery, dynamic subtitles, audio ducking, packaging checks, and multi-platform syndication.
---

# AutoShort Skill

AutoShort is the autonomous production pipeline that turns an idea, topic, or viral hook into a fully rendered, ready-to-publish 9:16 vertical Short in under 3 minutes with zero manual editing.

---

## ⚡ The 6-Stage Autonomous Pipeline

```mermaid
flowchart LR
    A["Topic / Hook"] --> B["Script Engine (21 Formulas)"]
    B --> C["TTS Synthesizer (Edge-TTS)"]
    C --> D["Visual Engine (ARRI 9:16)"]
    D --> E["FFmpeg Assembler (Captions & Ducking)"]
    E --> F["Packaging & Multi-Upload"]
```

### Stage 1: Topic & Hook Formulation
- Selects from high-performing pillars:
  - Neuroscience of Habits & Willpower
  - Stoic Equanimity & Emotional Resilience
  - Living Nature & Apex Predator Laws
  - Longevity, Hormesis & Peak Daily Discipline
- Validates the hook against `skills/yt-script/hookscore.py` (target score > 75).
- Validates title/thumbnail pairing against `skills/yt-package/title.py` (target score > 80).

### Stage 2: Script Synthesis
- Generates 4-6 timed scenes with exact spoken text.
- Word count: 115-145 words (strict 35-50 second ceiling).
- Embeds seamless loop point where the final sentence completes into the opening sentence.
- Generates localized native scripts for trilingual distribution (English, Hindi Devanagari, Gujarati).

### Stage 3: Neural Voice Synthesis
- Leverages Edge-TTS neural models for broadcast-quality narration:
  - 🇺🇸 English: `en-US-ChristopherNeural` or `en-US-GuyNeural` (Authoritative, calm, resonant).
  - 🇮🇳 Hindi: `hi-IN-MadhurNeural` (Authentic, commanding, natural cadence).
  - 🇮🇳 Gujarati: `gu-IN-NiranjanNeural` (Clear, respectful, engaging).
- Audio post-processing: Normalized to -1dB peak with gentle compression.

### Stage 4: Cinematic Visual Asset Generation
- 9:16 vertical resolution (1080x1920).
- Photorealistic cinematic prompt styling (ARRI Alexa LF, 35mm anamorphic, shallow depth of field, natural dramatic lighting, zero text overlay).
- Fallback chain: Google Imagen 3 ➔ Pollinations Flux / SDXL ➔ Local asset library.

### Stage 5: FFmpeg Motion Assembly & Subtitle Burn-In
- Motion: Dynamic subtle Ken Burns pan/zoom on each still to create lifelike cinematography.
- Subtitle Burn-In:
  - Word-level synchronization.
  - Large bold font (Montserrat Bold / Arial Black).
  - Bright Yellow (`#FFEB3B`) keyword highlights with solid black border.
  - Placed safely in middle-lower third (above Shorts title, below top header).
- Audio Ducking: Background music mixed at -20dB under voiceover, fading out smoothly over the final 0.5s.

### Stage 6: Multi-Platform Syndication & Metadata
- **YouTube Shorts:** Tags, category 27 (Education), pinned discussion comment.
- **Instagram Reels & Stories:** Aspect ratio check, mobile upload protocol.
- **Facebook Stories & Reels:** Graph API or browser profile fallback.
- **WhatsApp Status:** High-engagement status blast for direct audiences.

---

## 💻 CLI Usage: `autoshort_pipeline.py`

Run a quick autonomous Short generation directly:

```bash
# Generate a complete Short on a specific topic (English)
python3 skills/autoshort/autoshort_pipeline.py --topic "The 20-Second Rule That Beats Procrastination" --lang en

# Generate in trilingual mode (EN, HI, GU)
python3 skills/autoshort/autoshort_pipeline.py --topic "The Stoic Art of Emotional Control" --trilingual

# Dry run mode (generates assets without uploading)
python3 skills/autoshort/autoshort_pipeline.py --topic "Dopamine Reset" --dry-run
```
