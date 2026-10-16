"""
High-Converting 16:9 YouTube Thumbnail Generator
================================================
Generates arresting 16:9 landscape thumbnails (1920x1080 / 1280x720)
combining photorealistic cinematic AI artwork with bold, click-compelling
typography overlays, pill badges, and drop shadows for standard YouTube videos.
"""

import logging
import os
import re
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont, ImageFilter

import config
from generator.image_generator import ImageGenerator, ImageSafetyScanner

logger = logging.getLogger("ThumbnailGenerator")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class ThumbnailGenerator:
    def __init__(self, api_key: Optional[str] = None):
        self.image_gen = ImageGenerator(api_key=api_key)

    def _get_font(self, size: int) -> ImageFont.FreeTypeFont:
        """Finds the best available bold font for thumbnail text."""
        candidates = [
            config.DEFAULT_FONT_PATH,
            Path("/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        ]
        for p in candidates:
            if p and Path(p).exists():
                try:
                    return ImageFont.truetype(str(p), size)
                except Exception:
                    pass
        return ImageFont.load_default()

    def generate_thumbnail(
        self,
        headline: str,
        visual_prompt: str,
        output_path: Path,
        category_label: str = "HIGH PERFORMANCE",
        category: Optional[str] = None,
        accent_phrase: Optional[str] = None,
    ) -> Path:
        """
        Creates a 1920x1080 high-CTR thumbnail:
        1. Generates 16:9 widescreen cinematic background artwork.
        2. Applies cinematic gradient darkening on the text side.
        3. Renders a bold, high-contrast headline with drop shadow & pill badge.
        """
        if category:
            category_label = category
        output_path.parent.mkdir(parents=True, exist_ok=True)
        raw_bg_path = output_path.parent / f"raw_thumb_{output_path.name}"

        # 1. Generate base 16:9 cinematic artwork
        logger.info(f"🎨 Generating 16:9 thumbnail base artwork for '{headline}'...")
        prompt = (
            f"{visual_prompt}, extreme emotional intensity, dramatic high-contrast ARRI Alexa cinematic lighting, "
            "striking subject centered or positioned with negative space, vivid color grading, 16:9 widescreen composition, "
            "award-winning commercial photography, 8k resolution, photorealistic, no text inside the image"
        )
        self.image_gen.generate_scene_image(
            prompt=prompt,
            output_path=raw_bg_path,
            aspect_ratio="16:9",
            width=1920,
            height=1080,
        )

        try:
            bg_image = Image.open(raw_bg_path).convert("RGBA")
        except Exception as e:
            logger.warning(f"Could not load raw thumbnail background ({e}). Using procedural fallback.")
            self.image_gen._generate_procedural_background(raw_bg_path, width=1920, height=1080)
            bg_image = Image.open(raw_bg_path).convert("RGBA")

        # 2. Add cinematic left-side or bottom gradient overlay for maximum text readability
        overlay = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
        draw_ov = ImageDraw.Draw(overlay)

        # Horizontal dark vignette on left side (where headline text will sit)
        for x in range(1100):
            progress = (1100 - x) / 1100.0
            alpha = int(220 * (progress ** 1.3))
            draw_ov.line([(x, 0), (x, 1080)], fill=(8, 12, 18, alpha))

        # Bottom subtle gradient
        for y in range(800, 1080):
            progress = (y - 800) / 280.0
            alpha = int(180 * progress)
            draw_ov.line([(0, y), (1920, y)], fill=(5, 8, 14, alpha))

        canvas = Image.alpha_composite(bg_image, overlay)
        draw = ImageDraw.Draw(canvas)

        # 3. Render Top Category Pill Badge
        badge_text = f"★ {category_label.upper()} ★"
        badge_font = self._get_font(36)
        bbox_b = draw.textbbox((0, 0), badge_text, font=badge_font)
        bw = bbox_b[2] - bbox_b[0]
        bh = bbox_b[3] - bbox_b[1]
        bx, by = 100, 140

        draw.rounded_rectangle(
            [(bx - 24, by - 14), (bx + bw + 24, by + bh + 14)],
            radius=16,
            fill=(255, 59, 48, 240),  # Vivid high-contrast red
            outline=(255, 255, 255, 200),
            width=2,
        )
        draw.text((bx, by), badge_text, fill=(255, 255, 255), font=badge_font)

        # 4. Render Headline Text (Word-wrapped, 3-5 words)
        clean_headline = re.sub(r"[#*_\"']", "", headline).strip().upper()
        words = clean_headline.split()

        # Split words into 2-3 lines max
        lines = []
        cur_line = []
        for w in words:
            cur_line.append(w)
            if len(" ".join(cur_line)) > 16:
                lines.append(" ".join(cur_line[:-1]))
                cur_line = [w]
        if cur_line:
            lines.append(" ".join(cur_line))

        font_size = 96 if len(lines) <= 2 else 80
        headline_font = self._get_font(font_size)

        text_y = by + bh + 60
        for i, line in enumerate(lines[:3]):
            # Accent coloring: 1st line Yellow, others White
            text_color = (255, 215, 0) if i == 0 else (255, 255, 255)
            tx = 100

            # Render dramatic multi-layer drop shadow
            for offset_x, offset_y in [(6, 6), (4, 4), (2, 2)]:
                draw.text((tx + offset_x, text_y + offset_y), line, fill=(0, 0, 0, 240), font=headline_font)

            draw.text((tx, text_y), line, fill=text_color, font=headline_font)
            text_y += font_size + 24

        # 5. Add Bottom Value Subtitle or Action Prompt
        sub_font = self._get_font(34)
        sub_text = accent_phrase or "WATCH BEFORE IT'S TOO LATE  ▶"
        draw.text((102, text_y + 20), sub_text, fill=(0, 0, 0, 220), font=sub_font)
        draw.text((100, text_y + 18), sub_text, fill=(57, 255, 20), font=sub_font)  # Neon green

        # Save finalized thumbnail
        final_thumb = canvas.convert("RGB")
        final_thumb.save(output_path, "JPEG", quality=95)
        logger.info(f"✅ High-CTR 16:9 Thumbnail saved: {output_path.name}")

        # Clean up raw temporary background
        if raw_bg_path.exists():
            try:
                raw_bg_path.unlink()
            except Exception:
                pass

        return output_path
