---
name: faceless-shorts
description: >-
  Create high-retention, viral faceless YouTube Shorts and Instagram Reels.
  Covers the 0-3s visual pattern interrupt, 2.5-4s scene cut pacing,
  seamless infinite loops, high-contrast subtitle styling, and cinematic 9:16 visual prompt engineering.
---

# Faceless Shorts Skill

Faceless Shorts succeed or fail on three non-negotiable metrics: **Viewed vs. Swiped Away (>75% Viewed)**, **Average Percentage Viewed (>100% via seamless loops)**, and **Visual Pacing (scene cuts every 2.5 to 4 seconds)**.

Without an on-camera personality, the visual momentum, sound design, and narrative velocity must carry 100% of the retention.

---

## 🎯 The Faceless Shorts Architecture

```
00:00 - 00:03 ➔ THE VISUAL PATTERN INTERRUPT (Hook + On-Screen Contrast Text)
00:03 - 00:15 ➔ THE MECHANISM / PROBLEM (Fast cuts, 2.5-3.5s per scene)
00:15 - 00:35 ➔ THE COUNTER-INTUITIVE SOLUTION (Rule #1, Proof, Concrete Fact)
00:35 - 00:50 ➔ THE PAYOFF / TAKEAWAY (Actionable protocol, high stakes)
00:50 - 00:55 ➔ THE SEAMLESS LOOP CONNECTOR (Last line sets up Line 1)
```

---

## 🔑 Core Rules for Faceless Content

### 1. The 0-3 Second Pattern Interrupt
- Never open with an introduction, greeting ("Hey guys"), or channel name.
- First 3 seconds must combine:
  1. A **bold contrarian audio hook** scored with `skills/yt-script/hookscore.py`.
  2. A **high-contrast on-screen text badge** (different words than the spoken audio).
  3. A **dynamic visual with motion** (e.g. predatory wildlife, crashing waves, deep space, high-speed macro cinematography).

### 2. Scene Pacing & Cut Velocity
- **No static image or clip may stay on screen for longer than 4.5 seconds.**
- Target: 4 to 6 distinct visual scenes for a 35–50 second Short.
- Every cut must change either:
  - Subject distance (macro close-up ➔ wide establishing ➔ medium action).
  - Angle or lighting direction.
  - Motion direction (Ken Burns zoom-in ➔ pan-right ➔ slow pull-back).

### 3. The Seamless Infinite Loop (>100% APV)
- The algorithm rewards Shorts that loop without the viewer noticing where it ended.
- **Rule:** The final sentence must be syntactically or conceptually completed by the first sentence.
  - *Example End Line:* `"And that is the exact reason why..."`
  - *Loops back to Line 1:* `"...99% of people fail their morning routine."`
  - *Example End Line:* `"All you have to remember is..."`
  - *Loops back to Line 1:* `"...the 4-second rule that resets your nervous system."`

### 4. High-Contrast Subtitle Discipline
- 70%+ of mobile viewers watch Shorts with low volume or muted audio initially.
- **Subtitle Styling:**
  - 1 to 3 words on screen at a time (karaoke / rapid-fire word sync).
  - High-visibility font: Bold Sans-Serif (Montserrat, Roboto Bold, Arial Black).
  - Colors: Bright Yellow (`#FFEB3B`) or Neon Green (`#00E676`) for keywords, Crisp White (`#FFFFFF`) for base text.
  - Strong drop-shadow or 2px black outline (`#000000`) for legibility over any background.
  - Safe margins: Positioned centrally at 60-70% from top (avoiding YouTube Shorts UI icons on the right and title/audio text at the bottom).

### 5. Sound Design & Audio Ducking
- **Voice Track:** Authoritative, resonant, normalized to -1dB peak, speech pace 135–155 WPM.
- **Background Music:** Atmospheric, tension-building, or lo-fi track ducked to -18dB to -24dB beneath the voiceover.
- **Sound Effects (SFX):** Subtle whooshes or deep cinematic risers on scene cuts.

---

## 🎨 Cinematic 9:16 Visual Prompt Formulas

When generating AI imagery for faceless shorts, use photorealistic documentary camera specs:

```text
Cinematic 9:16 vertical composition, shot on ARRI Alexa LF, 35mm anamorphic prime lens,
T1.5 shallow depth of field, authentic natural dramatic lighting, photorealistic documentary realism,
hyper-detailed textures, volumetric atmospheric dust, 8k resolution, no text overlay, no watermark.
```

### Visual Themes by Niche:
- **Stoicism & Mindset:** Ancient marble statues weathering harsh storms, stormy northern seas, solo hooded figures on mountain ridges at dusk, ancient candlelit study.
- **Biology & Health:** High-resolution cellular visualization, glowing neural pathways, human eye iris macro shot, cold thermal waters, red blood cells flowing through vessels.
- **Apex Nature & Wildlife:** Golden eagle diving through cloud mist, gray wolf in snowstorm locking eyes with lens, lion maintaining calm vigilance at twilight, ancient redwood canopy.
- **Discipline & Deep Work:** Precision clockwork mechanisms, minimalist dark aesthetic desk under single tungsten lamp, runner in dense fog at 5 AM.

---

## 🛠️ The Linter Tool: `faceless_rules.py`

Run the faceless script linter to score a script before assembly:

```bash
python3 skills/faceless-shorts/faceless_rules.py --script path/to/script.json
```
