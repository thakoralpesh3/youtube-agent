"""
Creative Festival Marketing Engine for "Chamunda Automobile Parts & Services".
Specializes EXCLUSIVELY in Royal Enfield motorcycles.

Generates high-resolution branded festive posters (1080x1920) and vertical videos (Reels/Stories)
blending authentic Indian festive celebration with Royal Enfield motorcycling passion.
"""

import io
import json
import logging
import os
import random
import re
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageFilter

import config
from generator.audio_generator import AudioGenerator, create_word_highlight_ass
from generator.image_generator import ImageGenerator, ImageSafetyScanner
from generator.script_generator import validate_family_safe
from generator.video_assembler import VideoAssembler, get_ffmpeg_binary
from growth.model_resolver import get_candidate_models
from syndication.festival_detector import FestivalInfo

logger = logging.getLogger("festival_creator")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

FESTIVAL_OUTPUT_DIR = config.OUTPUT_DIR / "festivals"
FESTIVAL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Brand constants for Chamunda Automobile (Derived directly from official visiting card)
BRAND_NAME = "CHAMUNDA"
BRAND_SUBTITLE_GU = "ઓટો મોબાઇલ પાર્ટસ & સર્વિસ"
BRAND_SPECIALTY = "★ SPECIALIZES IN ROYAL ENFIELD ONLY ★"
BRAND_SERVICES = "GENUINE SPARE PARTS / ACCESSORIES & SERVICE"
BRAND_PILL_BADGES = "ACCESSORIES • MAINTENANCE • SERVICE • MODIFICATION"
BRAND_MODELS = "Bullet 350 • Classic 350 • Hunter • Meteor • Himalayan 450 • 650 Twins"
BRAND_ADDRESS = "Address: 4, Sanidhya Arcade, Opp. Sindbad Hotel, Kalol - 382721"
BRAND_CONTACTS = "Hitesh: 8490001582 | Alpesh: 7874719139"
DIVINE_BLESSING = "॥ જય શ્રી ચામુંડા માતાજી ॥"
VISITING_CARD_PATH = config.BASE_DIR / "assets" / "chamunda_visiting_card.jpg"

# Font paths
FONT_LATIN = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
FONT_DEVANAGARI = Path("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf")
FONT_GUJARATI = Path("/usr/share/fonts/truetype/noto/NotoSansGujarati-Bold.ttf")


def get_font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    try:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    except Exception:
        pass
    return ImageFont.load_default()


class ChamundaFestivalCreator:
    """
    Dedicated creative marketing generator for Chamunda Automobile Parts & Services (Royal Enfield Only).
    Produces branded festive posters and videos for Instagram, Facebook, and WhatsApp.
    """

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key or config.GEMINI_API_KEY
        self.model_name = model_name or config.GEMINI_MODEL
        self.image_gen = ImageGenerator(api_key=self.api_key)
        self.audio_gen = AudioGenerator()
        self.video_assembler = VideoAssembler()
        self.ffmpeg_bin = get_ffmpeg_binary()

    # --------------------------------------------------------------------------
    # 1. FESTIVE POSTER (IMAGE) GENERATION
    # --------------------------------------------------------------------------
    def _build_image_prompt(self, festival: FestivalInfo) -> str:
        """
        Engineers a prompt featuring living subjects (riders, celebrants) alongside
        a decorated Royal Enfield motorcycle harmonized with the specific festival theme.
        """
        re_models = [
            "Royal Enfield Classic 350 in gleaming chrome and maroon",
            "Royal Enfield Bullet 350 in iconic gloss black with hand-painted gold pinstripes",
            "Royal Enfield Himalayan 450 expedition motorcycle",
            "Royal Enfield Continental GT 650 twin cafe racer in chrome",
        ]
        chosen_bike = random.choice(re_models)

        living_subjects = [
            "a proud, passionate Indian Royal Enfield rider in festive traditional kurta standing respectfully beside the motorcycle with hands folded in namaste",
            "a focused, joyful rider admiring the machine with deep devotion and living festive warmth",
            "a spirited Indian family celebrating together in colorful festive attire beside the motorcycle",
            "a master Royal Enfield technician and a passionate rider standing proudly together beside the motorcycle outside the workshop in festive traditional attire",
            "a distinguished motorcyclist performing traditional festive pooja on the Royal Enfield with fresh marigolds and glowing diya",
        ]
        chosen_subject = random.choice(living_subjects)

        prompt = (
            f"Masterpiece cinematic portrait shot on Hasselblad H6D-100c medium format camera, 80mm prime lens, featuring {chosen_subject} and a {chosen_bike}, "
            f"exquisitely decorated for {festival.festival_name} with vibrant fresh orange and yellow marigold flower garlands draped over the chrome headlamp and fuel tank, "
            f"traditional auspicious Indian festive oil lamps (diyas) softly glowing with natural warm golden flame reflections on the polished motorcycle chrome and fuel tank paint, "
            f"authentic mechanical engine cooling fins, genuine leather saddle stitching, crisp metallic highlights, "
            f"subtle temple stone architecture and warm festive cultural bokeh in background, natural festive golden hour lighting, "
            f"strictly family-friendly, fully clothed in modest festive traditional Indian attire (royal sherwani, embroidered kurta), "
            f"respectful folded hands in namaste, all-ages safe, zero sexy elements, zero provocative clothing, zero revealing garments, no violence, no nudity, "
            f"hyper-realistic 8k resolution, natural human skin pores and warm joyful expressions, optical depth of field, vertical 9:16 framing, "
            f"no text, no watermark, commercial automotive photography masterpiece"
        )
        return prompt

    def generate_poster(
        self,
        festival: FestivalInfo,
        lang: str = "hi",
        output_dir: Optional[Path] = None,
    ) -> Path:
        """
        Generates a 1080x1920 vertical festive poster with Chamunda Automobile & Royal Enfield branding.
        """
        out_dir = output_dir or FESTIVAL_OUTPUT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", festival.festival_name).lower().strip("_")
        poster_filename = f"poster_{festival.date_str}_{slug}.jpg"
        raw_bg_path = out_dir / f"raw_{poster_filename}"
        final_poster_path = out_dir / poster_filename

        if final_poster_path.exists() and final_poster_path.stat().st_size > 10000:
            logger.info(f"⚡ Checkpoint found: Reusing existing festive poster {final_poster_path.name}")
            return final_poster_path

        # 1. Generate visual background
        prompt = self._build_image_prompt(festival)
        logger.info(f"🎨 Generating festive Royal Enfield artwork for {festival.festival_name}...")

        success = self.image_gen._generate_with_gemini_imagen(prompt, raw_bg_path)
        if not success:
            logger.info("Falling back to Pollinations Flux for festive motorcycle visual...")
            success = self.image_gen._generate_with_pollinations(prompt, raw_bg_path)

        if not success or not raw_bg_path.exists():
            # Create high-end dark maroon/gold gradient canvas if offline
            bg_image = Image.new("RGB", (config.VIDEO_WIDTH, config.VIDEO_HEIGHT), color=(25, 10, 15))
            draw_bg = ImageDraw.Draw(bg_image)
            for y in range(config.VIDEO_HEIGHT):
                r = int(35 + (y / config.VIDEO_HEIGHT) * 35)
                g = int(12 + (y / config.VIDEO_HEIGHT) * 10)
                b = int(20 + (y / config.VIDEO_HEIGHT) * 15)
                draw_bg.line([(0, y), (config.VIDEO_WIDTH, y)], fill=(r, g, b))
        else:
            bg_image = Image.open(raw_bg_path).convert("RGBA")
            bg_image = bg_image.resize((config.VIDEO_WIDTH, config.VIDEO_HEIGHT), Image.Resampling.LANCZOS)

        # 2. Add subtle vignette/dimming overlays for readability
        overlay = Image.new("RGBA", (config.VIDEO_WIDTH, config.VIDEO_HEIGHT), (0, 0, 0, 0))
        draw_ov = ImageDraw.Draw(overlay)

        # Top banner dark gradient
        for y in range(320):
            alpha = int(220 * (1 - (y / 320)))
            draw_ov.line([(0, y), (config.VIDEO_WIDTH, y)], fill=(10, 5, 8, alpha))

        # Bottom banner dark gradient for smooth contrast behind blessing & visiting card
        for y in range(config.VIDEO_HEIGHT - 750, config.VIDEO_HEIGHT):
            progress = (y - (config.VIDEO_HEIGHT - 750)) / 750
            alpha = int(245 * progress)
            draw_ov.line([(0, y), (config.VIDEO_WIDTH, y)], fill=(6, 12, 8, alpha))

        # Composite background + overlay
        canvas = Image.alpha_composite(bg_image.convert("RGBA"), overlay)
        draw = ImageDraw.Draw(canvas)

        # Fonts
        font_brand = get_font(FONT_LATIN, 42)
        font_badge = get_font(FONT_LATIN, 24)
        font_sub = get_font(FONT_LATIN, 22)
        font_headline = get_font(FONT_LATIN, 50)

        indic_font_path = FONT_GUJARATI if lang == "gu" else FONT_DEVANAGARI
        font_blessing = get_font(indic_font_path, 34)
        font_divine = get_font(FONT_GUJARATI, 30)
        font_addr = get_font(FONT_LATIN, 22)
        font_contact = get_font(FONT_LATIN, 20)

        W = config.VIDEO_WIDTH

        # -------------------------------------------------------------
        # TOP HEADER: Chamunda Automobile Branding (Visiting Card Style)
        # -------------------------------------------------------------
        pill_box = [45, 45, W - 45, 205]
        draw.rounded_rectangle(pill_box, radius=22, fill=(14, 25, 18, 235), outline=(225, 180, 50, 240), width=3)

        # Brand Name "CHAMUNDA"
        brand_bbox = draw.textbbox((0, 0), BRAND_NAME, font=font_brand)
        bw = brand_bbox[2] - brand_bbox[0]
        draw.text(((W - bw) / 2 + 2, 54 + 2), BRAND_NAME, fill=(130, 20, 25), font=font_brand)
        draw.text(((W - bw) / 2, 54), BRAND_NAME, fill=(255, 245, 235), font=font_brand)

        # Subtitle in Gujarati: "ઓટો મોબાઇલ પાર્ટસ & સર્વિસ"
        font_sub_gu = get_font(FONT_GUJARATI, 28)
        font_sub_lat = get_font(FONT_LATIN, 28)
        w1 = font_sub_gu.getbbox("ઓટો મોબાઇલ પાર્ટસ ")[2]
        w2 = font_sub_lat.getbbox("& ")[2]
        w3 = font_sub_gu.getbbox("સર્વિસ")[2]
        total_sub_w = w1 + w2 + w3
        start_x = (W - total_sub_w) / 2
        draw.text((start_x, 108), "ઓટો મોબાઇલ પાર્ટસ ", fill=(255, 255, 255), font=font_sub_gu)
        draw.text((start_x + w1, 108), "& ", fill=(255, 215, 60), font=font_sub_lat)
        draw.text((start_x + w1 + w2, 108), "સર્વિસ", fill=(255, 255, 255), font=font_sub_gu)

        # Specialty Badge: "★ SPECIALIZES IN ROYAL ENFIELD ONLY ★"
        badge_bbox = draw.textbbox((0, 0), BRAND_SPECIALTY, font=font_badge)
        badgew = badge_bbox[2] - badge_bbox[0]
        draw.text(((W - badgew) / 2, 156), BRAND_SPECIALTY, fill=(255, 205, 60), font=font_badge)

        # -------------------------------------------------------------
        # UPPER THIRD: Festive Greeting Headline
        # -------------------------------------------------------------
        greet_text = festival.greeting_headline.upper()
        head_size = 50
        while head_size >= 26:
            font_headline = get_font(FONT_LATIN, head_size)
            bbox = draw.textbbox((0, 0), greet_text, font=font_headline)
            if (bbox[2] - bbox[0]) <= (W - 120):
                break
            head_size -= 4

        gw = bbox[2] - bbox[0]
        # Text shadow
        draw.text(((W - gw) / 2 + 3, 248), greet_text, fill=(0, 0, 0, 240), font=font_headline)
        draw.text(((W - gw) / 2, 245), greet_text, fill=(255, 225, 90), font=font_headline)

        # -------------------------------------------------------------
        # LOWER PORTION: Festive Blessing
        # -------------------------------------------------------------
        blessing_text = (
            festival.blessing_message_gu
            if lang == "gu"
            else festival.blessing_message_hi
            if lang == "hi"
            else festival.blessing_message_en
        )

        # Word wrap blessing
        words = blessing_text.split()
        lines = []
        cur_line = []
        for word in words:
            cur_line.append(word)
            test_line = " ".join(cur_line)
            bbox = draw.textbbox((0, 0), test_line, font=font_blessing)
            if (bbox[2] - bbox[0]) > (W - 140):
                cur_line.pop()
                lines.append(" ".join(cur_line))
                cur_line = [word]
        if cur_line:
            lines.append(" ".join(cur_line))

        has_visiting_card = VISITING_CARD_PATH.exists()

        if has_visiting_card:
            # 1. Divine Blessing above visiting card
            div_bbox = draw.textbbox((0, 0), DIVINE_BLESSING, font=font_divine)
            dw = div_bbox[2] - div_bbox[0]
            draw.text(((W - dw) / 2 + 2, 1142), DIVINE_BLESSING, fill=(0, 0, 0, 230), font=font_divine)
            draw.text(((W - dw) / 2, 1140), DIVINE_BLESSING, fill=(255, 215, 0), font=font_divine)

            # 2. Render blessing text
            bless_y = 1190
            for line in lines[:2]:
                bbox = draw.textbbox((0, 0), line, font=font_blessing)
                lw = bbox[2] - bbox[0]
                draw.text(((W - lw) / 2 + 2, bless_y + 2), line, fill=(0, 0, 0, 230), font=font_blessing)
                draw.text(((W - lw) / 2, bless_y), line, fill=(255, 255, 255), font=font_blessing)
                bless_y += 46

            # 3. Composite Official Visiting Card at bottom
            vc_img = Image.open(VISITING_CARD_PATH).convert("RGBA")
            target_w = W - 70  # 1010px
            aspect = vc_img.height / vc_img.width
            target_h = int(target_w * aspect)  # ~550px
            vc_resized = vc_img.resize((target_w, target_h), Image.Resampling.LANCZOS)

            # Rounded corner mask
            mask = Image.new("L", (target_w, target_h), 0)
            d_mask = ImageDraw.Draw(mask)
            d_mask.rounded_rectangle([0, 0, target_w, target_h], radius=24, fill=255)

            # Gold border around visiting card
            border_card = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
            d_border = ImageDraw.Draw(border_card)
            d_border.rounded_rectangle([1, 1, target_w - 2, target_h - 2], radius=24, outline=(225, 180, 50, 255), width=3)

            rounded_card = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
            rounded_card.paste(vc_resized, (0, 0), mask)
            rounded_card = Image.alpha_composite(rounded_card, border_card)

            card_x = (W - target_w) // 2
            card_y = config.VIDEO_HEIGHT - target_h - 35
            canvas.paste(rounded_card.convert("RGB"), (card_x, card_y), mask)
        else:
            # Fallback vector card
            bless_y = config.VIDEO_HEIGHT - 540
            for line in lines[:3]:
                bbox = draw.textbbox((0, 0), line, font=font_blessing)
                lw = bbox[2] - bbox[0]
                draw.text(((W - lw) / 2 + 2, bless_y + 2), line, fill=(0, 0, 0, 220), font=font_blessing)
                draw.text(((W - lw) / 2, bless_y), line, fill=(255, 255, 255), font=font_blessing)
                bless_y += 46

            card_x1 = 35
            card_y1 = config.VIDEO_HEIGHT - 380
            card_x2 = W - 35
            card_y2 = config.VIDEO_HEIGHT - 40
            card_box = [card_x1, card_y1, card_x2, card_y2]

            draw.rounded_rectangle(
                card_box,
                radius=24,
                fill=(14, 25, 18, 235),
                outline=(225, 175, 50, 240),
                width=2,
            )

            div_bbox = draw.textbbox((0, 0), DIVINE_BLESSING, font=font_divine)
            dw = div_bbox[2] - div_bbox[0]
            draw.text(((W - dw) / 2, card_y1 + 18), DIVINE_BLESSING, fill=(255, 215, 0), font=font_divine)

            draw.line([(card_x1 + 35, card_y1 + 65), (card_x2 - 35, card_y1 + 65)], fill=(200, 160, 45, 160), width=1)

            mb_bbox = draw.textbbox((0, 0), BRAND_MODELS, font=font_sub)
            mw = mb_bbox[2] - mb_bbox[0]
            draw.text(((W - mw) / 2, card_y1 + 78), BRAND_MODELS, fill=(245, 240, 230), font=font_sub)

            spec_text = "★ Genuine RE Spare Parts • Expert Engine Tuning • Highway Servicing ★"
            sp_bbox = draw.textbbox((0, 0), spec_text, font=font_sub)
            sw = sp_bbox[2] - sp_bbox[0]
            draw.text(((W - sw) / 2, card_y1 + 122), spec_text, fill=(255, 205, 60), font=font_sub)

            addr_bbox = draw.textbbox((0, 0), BRAND_ADDRESS, font=font_addr)
            aw = addr_bbox[2] - addr_bbox[0]
            draw.text(((W - aw) / 2, card_y1 + 172), BRAND_ADDRESS, fill=(255, 255, 255), font=font_addr)

            cnt_bbox = draw.textbbox((0, 0), BRAND_CONTACTS, font=font_contact)
            cw = cnt_bbox[2] - cnt_bbox[0]
            draw.text(((W - cw) / 2, card_y1 + 224), BRAND_CONTACTS, fill=(255, 225, 75), font=font_contact)

            draw.line([(card_x1 + 45, card_y1 + 272), (card_x2 - 45, card_y1 + 272)], fill=(200, 160, 45, 120), width=1)

            tag_text = "PURE MOTORCYCLING • VISIT OUR KALOL WORKSHOP FOR FESTIVE SERVICE"
            tag_bbox = draw.textbbox((0, 0), tag_text, font=font_sub)
            tw = tag_bbox[2] - tag_bbox[0]
            draw.text(((W - tw) / 2, card_y1 + 288), tag_text, fill=(215, 200, 180), font=font_sub)

        # Save finalized poster
        final_img = canvas.convert("RGB")
        final_img.save(final_poster_path, "JPEG", quality=95)
        logger.info(f"✅ Branded Festive Poster saved: {final_poster_path.name}")

        # Clean up temporary raw background
        if raw_bg_path.exists():
            try:
                raw_bg_path.unlink()
            except Exception:
                pass

        return final_poster_path

    # --------------------------------------------------------------------------
    # 2. FESTIVE VIDEO (REEL / STORY) GENERATION
    # --------------------------------------------------------------------------
    def _generate_video_script(self, festival: FestivalInfo, lang: str = "hi") -> str:
        """
        Uses Gemini 4 Argon reasoning to generate a short, punchy 15-20s video narration script
        blending the festival spirit with the iconic thump and pride of Royal Enfield.
        """
        lang_name = "Gujarati (genuine Gujarati script)" if lang == "gu" else "Hindi (genuine Devanagari script)" if lang == "hi" else "English"
        prompt = f"""
You are Gemini 4 Argon, Google's flagship reasoning engine.
Write a high-energy, memorable 15 to 20 second festive video voiceover script for "Chamunda Auto Mobile Parts & Services" (ચામુંડા ઓટો મોબાઇલ પાર્ટસ & સર્વિસ) located at Kalol.
Business Profile: Chamunda Automobile specializes EXCLUSIVELY in Royal Enfield motorcycles (Bullet 350, Classic 350, Hunter, Meteor, Himalayan 450, 650 Twins). Offers genuine RE spare parts, accessories, periodic maintenance, expert engine tuning, and custom modification.
Location: 4, Sanidhya Arcade, Opp. Sindbad Hotel, Kalol.
Contacts: Hitesh (8490001582) and Alpesh (7874719139).

Target Festival: {festival.festival_name}
Cultural Significance: {festival.significance}
Motorcycle Theme: {festival.motorcycle_theme}
Target Language: {lang_name}

Reasoning Directives:
- Deep Cultural & Biker Resonance: Synthesize the spiritual energy of {festival.festival_name} with the legendary thump ("Dug-Dug") of Royal Enfield and Maa Chamunda's divine protection on every highway and mountain pass.
- Length: Exactly 35 to 55 words (fits 15-20 seconds spoken pace).
- Tone: Proud, celebratory, authoritative, passionate about the Royal Enfield heartbeat and rider safety.
- STRICT CONTENT SAFETY (ZERO 18+ TOLERANCE): 100% wholesome, family-friendly, all-ages safe (suitable for children, youth, and elders). Strictly NO 18+ adult themes, vulgarity, swearing, violence, or controversial topics.
- Mention Chamunda Auto Kalol for genuine Royal Enfield parts, service & modification, and wish all RE riders safe, powerful journeys.
- Do NOT include scene headers or stage directions. Output ONLY the spoken narration text in the requested native script.
"""
        from google import genai
        client = genai.Client(api_key=self.api_key)
        candidates = get_candidate_models(preferred=self.model_name, tier="argon")

        for model in candidates:
            try:
                res = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config={"temperature": 0.75},
                )
                text = res.text.strip().replace('"', "").replace("\n", " ")
                if len(text) > 30:
                    validate_family_safe(text)
                    return text
            except Exception as e:
                logger.debug(f"Script model {model} failed: {e}")

        # Fallback pre-written scripts
        if lang == "gu":
            return f"રોયલ એન્ફિલ્ડના તમામ રાઇડર્સને ચામુંડા ઓટો મોબાઇલ પાર્ટસ & સર્વિસ, કલોલ તરફથી {festival.festival_name} ની હાર્દિક શુભકામનાઓ! મા ચામુંડાના આશીર્વાદથી તમારી બુલેટનો અવાજ ગુંજતો રહે. જેન્યુઈન સ્પેરપાર્ટ્સ, એક્સેસરીઝ, સર્વિસ અને મોડિફિકેશન માટે પધારો સાનિધ્ય આર્કેડ, કલોલ. હેપી રાઇડિંગ!"
        elif lang == "hi":
            return f"रॉयल एनफील्ड के सभी राइडर्स को चामुंडा ऑटो मोबाइल पार्ट्स एंड सर्विसेज, कलोल की तरफ से {festival.festival_name} की हार्दिक शुभकामनाएं! मां चामुंडा की कृपा से आपकी बुलेट की धड़कन सदा गूंजती रहे। ओरिजिनल स्पेयर पार्ट्स, एसेसरीज, सर्विस और मॉडिफिकेशन के लिए पधारें सानिध्य आर्केड, कलोल।"
        else:
            return f"Wishing all Royal Enfield riders a blessed and joyous {festival.festival_name} from Chamunda Auto Mobile Parts & Services, Kalol! Trust only genuine RE parts, accessories, expert service, and custom modification for your machine. May Maa Chamunda protect every mile. Ride with pride!"

    def generate_video(
        self,
        festival: FestivalInfo,
        poster_path: Path,
        lang: str = "hi",
        output_dir: Optional[Path] = None,
    ) -> Path:
        """
        Renders a 1080x1920 vertical Reel/Story MP4 video with:
        - Festive background poster visual
        - Dynamic Edge-TTS neural speech in Hindi or Gujarati
        - Synchronized word-by-word karaoke highlight subtitles (.ass)
        - Ambient festive background audio with sidechain audio ducking
        """
        out_dir = output_dir or FESTIVAL_OUTPUT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", festival.festival_name).lower().strip("_")

        video_filename = f"video_{festival.date_str}_{slug}_{lang}.mp4"
        final_video_path = out_dir / video_filename

        if final_video_path.exists() and final_video_path.stat().st_size > 50000:
            logger.info(f"⚡ Checkpoint found: Reusing existing festive video {final_video_path.name}")
            return final_video_path

        audio_path = out_dir / f"audio_{festival.date_str}_{slug}_{lang}.mp3"
        srt_path = out_dir / f"subs_{festival.date_str}_{slug}_{lang}.srt"
        ass_path = out_dir / f"subs_{festival.date_str}_{slug}_{lang}.ass"

        script_text = self._generate_video_script(festival, lang=lang)

        # 1. Synthesize or reuse voiceover audio
        if audio_path.exists() and srt_path.exists() and audio_path.stat().st_size > 1000:
            logger.info(f"⚡ Checkpoint found: Reusing existing festive voiceover ({audio_path.name})")
        else:
            logger.info(f"🎙️ Generated festive voiceover script ({lang}): {script_text[:60]}...")
            voice = "gu-IN-NiranjanNeural" if lang == "gu" else "hi-IN-MadhurNeural" if lang == "hi" else "en-US-ChristopherNeural"
            logger.info(f"Synthesizing voiceover with {voice}...")
            self.audio_gen._generate_edge_tts(script_text, audio_path, srt_path, lang=lang)
            if not audio_path.exists() or audio_path.stat().st_size < 100:
                self.audio_gen._generate_gtts(script_text, audio_path, srt_path, lang=lang)

        # 3. Calculate duration & create ASS highlight subtitles
        import moviepy.editor as mp
        with mp.AudioFileClip(str(audio_path)) as aclip:
            duration = aclip.duration + 0.5  # add 0.5s pause at end

        create_word_highlight_ass(script_text, duration, ass_path, lang=lang)

        # 4. Background music ducking setup
        music_file = config.MUSIC_DIR / "stoic_ambient_focus.mp3"
        has_music = music_file.exists()

        logger.info(f"🎬 Assembling final festive video for Chamunda Automobile ({duration:.1f}s)...")

        d_frames = max(30, int((duration + 0.5) * 30))

        # Ultra-realistic cinematic camera motion + film grading for festival poster
        # Pre-scale to 2160x3840 for subpixel smoothness, Ken Burns slow push-in, warm festive color grading, optical lens vignette, organic 35mm film grain
        cinematic_filter = (
            f"scale=2160:3840,"
            f"zoompan=z='min(zoom+0.0007,1.08)':d={d_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"s={config.VIDEO_WIDTH}x{config.VIDEO_HEIGHT}:fps=30,"
            f"eq=contrast=1.08:brightness=0.01:saturation=1.12,"
            f"vignette=PI/5:mode=backward,"
            f"noise=c1s=3:c0f=u+t"
        )
        subtitle_filter = f"{cinematic_filter},ass='{ass_path.name}'"

        if has_music:
            # Sidechain compression / ducking filter: Speech attenuates music
            filter_complex = (
                f"[0:v]{subtitle_filter}[v];"
                f"[2:a]volume=0.18[bgm];"
                f"[bgm][1:a]sidechaincompress=threshold=0.08:ratio=8:attack=100:release=400[ducked_bgm];"
                f"[ducked_bgm][1:a]amix=inputs=2:duration=first:dropout_transition=2[a]"
            )
            cmd = [
                self.ffmpeg_bin,
                "-y",
                "-loop", "1",
                "-i", str(poster_path.resolve()),
                "-i", str(audio_path.resolve()),
                "-stream_loop", "-1",
                "-i", str(music_file.resolve()),
                "-filter_complex", filter_complex,
                "-map", "[v]",
                "-map", "[a]",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-c:a", "aac",
                "-b:a", "192k",
                "-t", f"{duration:.2f}",
                "-pix_fmt", "yuv420p",
                "-shortest",
                str(final_video_path.resolve()),
            ]
        else:
            cmd = [
                self.ffmpeg_bin,
                "-y",
                "-loop", "1",
                "-i", str(poster_path.resolve()),
                "-i", str(audio_path.resolve()),
                "-vf", subtitle_filter,
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-c:a", "aac",
                "-b:a", "192k",
                "-t", f"{duration:.2f}",
                "-pix_fmt", "yuv420p",
                str(final_video_path.resolve()),
            ]

        # Execute FFmpeg in working directory where ass file resides
        proc = subprocess.run(cmd, cwd=str(ass_path.parent), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            logger.warning(f"Kinetic FFmpeg render error, falling back to safe render: {proc.stderr.decode('utf-8', errors='ignore')[-300:]}")
            # Fallback with standard scaling and subtitles
            fallback_sub_filter = f"scale={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT},ass='{ass_path.name}'"
            if has_music:
                fallback_complex = (
                    f"[0:v]{fallback_sub_filter}[v];"
                    f"[2:a]volume=0.18[bgm];"
                    f"[bgm][1:a]sidechaincompress=threshold=0.08:ratio=8:attack=100:release=400[ducked_bgm];"
                    f"[ducked_bgm][1:a]amix=inputs=2:duration=first:dropout_transition=2[a]"
                )
                cmd_fb = [
                    self.ffmpeg_bin, "-y", "-loop", "1", "-i", str(poster_path.resolve()),
                    "-i", str(audio_path.resolve()), "-stream_loop", "-1", "-i", str(music_file.resolve()),
                    "-filter_complex", fallback_complex, "-map", "[v]", "-map", "[a]",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-b:a", "192k",
                    "-t", f"{duration:.2f}", "-pix_fmt", "yuv420p", "-shortest", str(final_video_path.resolve())
                ]
            else:
                cmd_fb = [
                    self.ffmpeg_bin, "-y", "-loop", "1", "-i", str(poster_path.resolve()),
                    "-i", str(audio_path.resolve()), "-vf", fallback_sub_filter,
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-b:a", "192k",
                    "-t", f"{duration:.2f}", "-pix_fmt", "yuv420p", str(final_video_path.resolve())
                ]
            subprocess.run(cmd_fb, cwd=str(ass_path.parent), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        logger.info(f"🎉 Branded Festive Reel / Video ready: {final_video_path.name}")
        return final_video_path

    # --------------------------------------------------------------------------
    # 3. SOCIAL CAPTION GENERATOR
    # --------------------------------------------------------------------------
    def generate_caption(self, festival: FestivalInfo, lang: str = "hi") -> str:
        """Generates an engaging, branded caption for Instagram, Facebook, and WhatsApp."""
        blessing = (
            festival.blessing_message_gu
            if lang == "gu"
            else festival.blessing_message_hi
            if lang == "hi"
            else festival.blessing_message_en
        )

        fest_clean = festival.festival_name.split("/")[0].strip()
        fest_tag = re.sub(r"[^a-zA-Z0-9]+", "", fest_clean)

        caption = f"""🚩 {festival.greeting_headline} 🚩

{blessing}

May Maa Chamunda bless your life with boundless prosperity, peak health, and unshakeable power on every journey!

🏍️ CHAMUNDA (ચામુંડા)
ઓટો મોબાઇલ પાર્ટસ & સર્વિસ
★ SPECIALIZES EXCLUSIVELY IN ROYAL ENFIELD ★
• GENUINE SPARE PARTS / ACCESSORIES & SERVICE
• ACCESSORIES • MAINTENANCE • SERVICE • MODIFICATION
• Bullet 350 • Classic 350 • Hunter • Meteor • Himalayan 450 • 650 Twins

📞 Contact:
• Hitesh: 8490001582
• Alpesh: 7874719139

📍 Address:
4, Sanidhya Arcade, Opp. Sindbad Hotel, Kalol - 382721

Ride safe, ride proud, and let the heartbeat of your Royal Enfield thump strong!

#ChamundaAutomobile #RoyalEnfield #Bullet350 #Classic350 #Himalayan450 #Meteor350 #Hunter350 #ContinentalGT650 #Interceptor650 #{fest_tag} #FestiveVibes #GujaratBikers #Kalol #MaaChamunda #PureMotorcycling #Story"""

        return caption.strip()
