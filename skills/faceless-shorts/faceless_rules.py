#!/usr/bin/env python3
"""
faceless_rules.py - Lint and score a faceless Short script against viral retention mechanics.

Usage:
    python3 faceless_rules.py --script path/to/script.json
    python3 faceless_rules.py --text "Script voiceover text..."
    python3 faceless_rules.py --json path/to/script.json
"""

import argparse
import json
import re
import sys
from pathlib import Path

def lint_faceless_script(data: dict) -> dict:
    issues = []
    strengths = []
    score = 100

    title = data.get("title", "")
    target = data.get("english") or data.get("hindi") or data.get("gujarati") or data
    scenes = target.get("scenes", [])
    voiceover = target.get("voiceover_script", "")

    # If voiceover is not given, compile from scenes
    if not voiceover and scenes:
        voiceover = " ".join([s.get("narration", "") for s in scenes])

    words = re.findall(r"[a-zA-Z0-9']+", voiceover)
    word_count = len(words)

    # 1. Total Duration & Word Count Pacing (Target: 35-55s, ~110-150 words)
    if word_count < 80:
        issues.append(("too-short", f"Script has only {word_count} words. Ideal is 110-145 words for a 40-50s Short."))
        score -= 15
    elif word_count > 165:
        issues.append(("too-long", f"Script has {word_count} words. Exceeds 60-second limit at natural speech rates (>160 WPM). Cut to under 145 words."))
        score -= 20
    else:
        strengths.append(f"Optimal word count: {word_count} words (~35-50 seconds at 140 WPM)")

    # 2. Scene Pacing & Cuts (< 4.5s per scene)
    if scenes:
        num_scenes = len(scenes)
        if num_scenes < 4:
            issues.append(("slow-pacing", f"Only {num_scenes} scenes. Faceless shorts require at least 4-6 scene cuts to maintain retention."))
            score -= 15
        elif num_scenes >= 4:
            strengths.append(f"Fast visual pacing: {num_scenes} distinct scene cuts")

        for idx, sc in enumerate(scenes, 1):
            dur = sc.get("estimated_duration_sec", 0.0)
            if dur > 5.0:
                issues.append(("long-scene", f"Scene {idx} duration ({dur:.1f}s) is too long. Keep each clip under 4.5s for visual dopamine."))
                score -= 10
            
            # Check visual prompt
            vp = sc.get("visual_prompt", "")
            if vp:
                if "9:16" not in vp and "vertical" not in vp.lower():
                    issues.append(("orientation", f"Scene {idx} prompt missing 9:16 vertical composition cue."))
                    score -= 5
                if "no text" not in vp.lower() and "text overlay" in vp.lower():
                    issues.append(("ai-text-leak", f"Scene {idx} prompt might cause AI to render garbled text overlay."))
                    score -= 5
    else:
        issues.append(("no-scenes", "No individual scene visual breakdowns provided."))
        score -= 20

    # 3. Hook Analysis (First 15 words)
    first_words = " ".join(words[:12]).lower() if words else ""
    weak_starters = ["hello", "hey guys", "welcome", "in this video", "today we", "let's talk"]
    for w in weak_starters:
        if w in first_words:
            issues.append(("weak-hook", f"Hook opens with low-retention filler: '{w}'. Open with immediate stakes or contrarian fact."))
            score -= 25
            break

    # 4. Seamless Loop Point Check
    if words:
        first_sentence = voiceover.split(".")[0].strip().lower()
        last_sentence = voiceover.split(".")[-2].strip().lower() if len(voiceover.split(".")) > 1 else voiceover.strip().lower()
        
        loop_connectors = ["because", "why", "reason", "rule", "this is", "secret", "remember", "how to", "is why"]
        has_loop_connector = any(c in last_sentence for c in loop_connectors)
        if has_loop_connector:
            strengths.append("Seamless loop potential: ending sets up the opening line.")
        else:
            issues.append(("no-loop", "Last sentence ends on a hard stop. Consider a loop connector that flows back into the opening hook."))
            score -= 10

    score = max(0, min(100, score))
    return {
        "score": score,
        "word_count": word_count,
        "scene_count": len(scenes),
        "issues": issues,
        "strengths": strengths
    }

def main():
    parser = argparse.ArgumentParser(description="Lint and score a faceless Short script.")
    parser.add_argument("--script", type=str, help="Path to script.json or package.json")
    parser.add_argument("--text", type=str, help="Raw voiceover text")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    args = parser.parse_args()

    data = {}
    if args.script:
        p = Path(args.script)
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"Error reading JSON: {e}", file=sys.stderr)
                sys.exit(1)
        else:
            print(f"File not found: {args.script}", file=sys.stderr)
            sys.exit(1)
    elif args.text:
        data = {"voiceover_script": args.text}
    else:
        parser.print_help()
        sys.exit(1)

    result = lint_faceless_script(data)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    print("=" * 60)
    print(f"🎬 FACELESS SHORTS RETENTION AUDIT | SCORE: {result['score']}/100")
    print("=" * 60)
    print(f"📊 Stats: {result['word_count']} words | {result['scene_count']} scenes")
    
    if result["strengths"]:
        print("\n✅ Strengths:")
        for s in result["strengths"]:
            print(f"   • {s}")

    if result["issues"]:
        print("\n⚠️ Fixes Required:")
        for code, msg in result["issues"]:
            print(f"   [{code.upper()}] {msg}")
    else:
        print("\n✨ Script is 100% compliant with viral faceless retention standards!")
    print("=" * 60)

if __name__ == "__main__":
    main()
