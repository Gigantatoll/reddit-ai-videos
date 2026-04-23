#!/usr/bin/env python3
"""
Reddit Reading Video Pipeline
────────────────────────────────────────────────────────────────────────────────
Pipeline:
  1. Claude      → question + 3 unhinged Gen Z answers + voice script (w/ upvotes)
  2. Pexels      → active/dynamic portrait video background (parkour, sports, etc.)
  3. PIL         → proper Reddit dark-mode cards (rounded corners, profile circles,
                   upvote row, comment border — looks like the actual app)
  4. ElevenLabs  → one reactive MP3 per segment + ding + lo-fi music
  5. Tmpfiles    → upload everything for Shotstack
  6. Shotstack   → moving bg + transparent card overlays + synced voice + ding + music
  7. Save        → Reddit AI Videos/MM/DD/YYYY/

Usage:
  python3 make_reddit_video.py --topic "pettiest thing you've done to a neighbour"
"""

import os
import json
import time
import hashlib
import textwrap
import argparse
import requests
import anthropic
from pathlib import Path
from datetime import datetime
from mutagen.mp3 import MP3
from PIL import Image, ImageDraw, ImageFont
from elevenlabs.client import ElevenLabs

# ── Load .env file if running locally ────────────────────────────────────────
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        if "=" in _line and not _line.startswith("#"):
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

# ── API Keys — loaded from environment variables (set locally via .env or GitHub Secrets) ──
ANTHROPIC_KEY   = os.getenv("ANTHROPIC_KEY",  "")
ELEVENLABS_KEY  = os.getenv("ELEVENLABS_KEY", "")
SHOTSTACK_KEY   = os.getenv("SHOTSTACK_KEY",  "")
PEXELS_KEY      = os.getenv("PEXELS_KEY",     "")

SHOTSTACK_BASE      = "https://api.shotstack.io/edit/v1"
ELEVENLABS_VOICE_ID = "onwK4e9ZLuTAKqWW03F9"   # Daniel — British, dry, warm, natural
OUTPUT_FOLDER       = os.getenv("OUTPUT_FOLDER", "/Users/vincent/Desktop/Reddit AI Videos")
ASSETS_DIR          = Path(os.getenv("ASSETS_DIR", "/Users/vincent/Desktop/Reddit AI Videos/assets"))
TEMP_DIR            = Path("/tmp/reddit_video")
VIDEO_W, VIDEO_H    = 1080, 1920

# Active backgrounds that actually keep people watching
FALLBACK_SEARCHES = [
    "parkour free running",
    "skateboard tricks",
    "basketball freestyle",
    "bmx tricks extreme",
    "martial arts training",
    "cooking fast satisfying",
    "subway surfers gameplay",
    "minecraft parkour",
    "satisfying food compilation",
    "city street walking",
    "gym workout motivation",
]

ASSETS_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

costs = {
    "anthropic":  {"tokens": 0,    "usd": 0.0},
    "elevenlabs": {"chars":  0,    "usd": 0.0},
    "shotstack":  {"minutes": 0.0, "usd": 0.0},
}


# ══════════════════════════════════════════════════════════════════════════════
# SOUND ASSETS
# ══════════════════════════════════════════════════════════════════════════════
def ensure_sounds() -> tuple:
    ding_path  = ASSETS_DIR / "ding.mp3"
    music_path = ASSETS_DIR / "lofi_music.mp3"
    client     = ElevenLabs(api_key=ELEVENLABS_KEY)

    if not ding_path.exists():
        print("  Generating ding (one-time)...")
        ding_path.write_bytes(b"".join(client.text_to_sound_effects.convert(
            text="soft pleasant digital notification ding, single clear bell chime, clean UI sound",
            duration_seconds=1.2, prompt_influence=0.5,
        )))

    if not music_path.exists():
        print("  Generating lo-fi music (one-time)...")
        music_path.write_bytes(b"".join(client.text_to_sound_effects.convert(
            text="relaxing lo-fi hip hop background music, soft mellow piano chords, gentle drums, chill and smooth",
            duration_seconds=22.0, prompt_influence=0.4,
        )))

    print("  Sounds ready.")
    return str(ding_path), str(music_path)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — Claude: Gen Z Reddit content
# ══════════════════════════════════════════════════════════════════════════════
def generate_reddit_package(topic: str) -> dict:
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    prompt = f"""You are generating a viral TikTok Reddit reading video.

Topic hint: "{topic}"

━━ THE QUESTION — this is the most important part ━━
Study this example of a question that got millions of views:
  "What's the most unethical parenting hack you know?"

Why it works:
- "Unethical" signals the answers will be funny and slightly wrong
- Everyone either IS a parent or HAS parents — 100% universal
- "Hack" means real practical things people actually do
- It makes EVERYONE think of their own answer immediately → floods TikTok comments

Your question must follow this exact energy:
- Slightly taboo or edgy, but not offensive
- 100% universally relatable — every single person watching has experienced this
- Implies the answers will be surprising, funny, or slightly wrong
- Max 12 words. Short, punchy, impossible to scroll past.

GREAT question formats:
  "What's the most unethical [X] hack you know?"
  "What did your [parents/boss/school] do that was lowkey genius but wrong?"
  "What's the thing everyone does but nobody admits out loud?"
  "What rule exists that makes zero sense but everyone follows anyway?"
  "What's the most [taboo adjective] thing you've done that actually worked?"

- Body: empty string.
- Upvotes + fake timestamp (e.g. "38.4k", "6h")

━━ COMMENTS — 5 answers, real and blunt ━━
Generate FIVE comments. Each one is a real thing a real person did or knows.
NO fictional scenarios. NO abstract jokes. Just the thing, stated deadpan.

The humor comes from RECOGNITION — people laugh because it's true, not because it's clever.
Think: "oh my god my parents did this exact thing" or "I have literally done this."

RULES:
- MAX 20 words per comment. Under 15 is better.
- State the thing bluntly. No setup. No explanation. The content IS the joke.
- Must be specific. "Tell kids the ice cream truck plays music when it's out of ice cream" > "lie to your kids."
- Real > absurd. Grounded > random. Specific > vague.
- Each comment slightly more unhinged than the last.

PERFECT examples for "unethical parenting hack" topic:
  "Tell your kids the ice cream truck only plays music when it's sold out."
  "If they won't sleep, tell them their eyes will fall out if they stay awake too long."
  "My dad told me coffee stunts your growth. I'm 5'2 and he drank four cups a day."
  "Tell them the toy in the store is broken and the one at home works fine."
  "My parents said swearing causes cancer. I'm 28 and still flinch."

For YOUR topic, same energy — real, specific, slightly wrong, instantly recognisable.

Comment upvotes (use these): 34.2k / 18.7k / 9.1k / 4.3k / 1.8k
Timestamps: 5h / 4h / 3h / 2h / 1h

━━ VOICE SCRIPT — 6 segments total ━━
British male. Clean, dry, warm. Reads each answer like he's genuinely enjoying it.
NO over-the-top reactions. Just reads it, pauses, maybe ONE short dry comment per answer.

Segment 0 (hook): One sentence. Punchy. Makes it sound unmissable.
  e.g. "Someone asked Reddit: [question]. The answers are actually sending me."

Segments 1-5 (one per comment): Read the comment cleanly. Short natural pause. Then optionally ONE dry 4-6 word reaction that's specific to that comment — not generic.
  GOOD reactions: "...the music thing. Genius. Evil genius." / "...I'm 5'2. That's the whole joke." / "...still flinches at 28. Incredible."
  NO reactions needed if the comment is funny enough on its own — silence is fine.

Each segment MAX 25 words total. Use "..." for pauses.

━━ PEXELS SEARCH ━━
Pick the background that best matches the video's energy. Vary it.
Options: "parkour free running", "skateboard tricks", "basketball freestyle",
"bmx tricks extreme", "martial arts training", "cooking fast satisfying",
"satisfying food compilation", "city street walking", "gym workout motivation"

Return ONLY valid JSON:
{{
  "subreddit": "r/AskReddit",
  "post": {{
    "title": "...",
    "author": "u/...",
    "upvotes": "38.4k",
    "timestamp": "6h",
    "body": ""
  }},
  "comments": [
    {{ "author": "u/...", "upvotes": "34.2k", "timestamp": "5h", "text": "..." }},
    {{ "author": "u/...", "upvotes": "18.7k", "timestamp": "4h", "text": "..." }},
    {{ "author": "u/...", "upvotes": "9.1k",  "timestamp": "3h", "text": "..." }},
    {{ "author": "u/...", "upvotes": "4.3k",  "timestamp": "2h", "text": "..." }},
    {{ "author": "u/...", "upvotes": "1.8k",  "timestamp": "1h", "text": "..." }}
  ],
  "voice_segments": [
    "[hook sentence about the question]",
    "[read comment 1]...[optional short dry reaction]",
    "[read comment 2]...[optional short dry reaction]",
    "[read comment 3]...[optional short dry reaction]",
    "[read comment 4]...[optional short dry reaction]",
    "[read comment 5]...[optional short dry reaction]"
  ],
  "pexels_search": "parkour free running",
  "caption": "Viral TikTok caption. Hook must be ONE specific funny/shocking detail from the answers (not generic). Always include #reddit #askreddit. Add 2-3 relevant hashtags. Under 130 chars."
}}"""

    msg = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}]
    )

    costs["anthropic"]["tokens"] += msg.usage.input_tokens + msg.usage.output_tokens
    costs["anthropic"]["usd"]    += (msg.usage.input_tokens  / 1_000_000 * 15.0) + \
                                     (msg.usage.output_tokens / 1_000_000 * 75.0)

    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Pexels: active dynamic background video
# ══════════════════════════════════════════════════════════════════════════════
def fetch_pexels_video(search_term: str, min_dur: int = 45) -> str:
    headers  = {"Authorization": PEXELS_KEY}
    searches = [search_term] + [s for s in FALLBACK_SEARCHES if s != search_term]

    for term in searches:
        for orientation in ["portrait", "landscape"]:
            try:
                r = requests.get(
                    "https://api.pexels.com/videos/search",
                    headers=headers,
                    params={"query": term, "orientation": orientation,
                            "per_page": 15, "min_duration": min_dur},
                    timeout=10
                )
                if r.status_code != 200:
                    continue
                for video in r.json().get("videos", []):
                    mp4s = [f for f in video["video_files"]
                            if f.get("file_type") == "video/mp4"]
                    hd   = [f for f in mp4s if f.get("quality") == "hd"]
                    pick = max(hd or mp4s,
                               key=lambda f: f.get("height", 0)
                               if orientation == "portrait" else f.get("width", 0),
                               default=None)
                    if pick:
                        print(f"  Pexels: '{term}' [{orientation}] "
                              f"→ {pick.get('width')}×{pick.get('height')}, {video['duration']}s")
                        return pick["link"]
            except Exception as e:
                print(f"  Pexels '{term}' failed: {e}")

    raise RuntimeError("No Pexels video found.")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — PIL: proper Reddit dark-mode cards
# ══════════════════════════════════════════════════════════════════════════════

# Reddit dark-mode palette
R_BG        = (26,  26,  27,  255)   # page background
R_CARD      = (39,  39,  41,  248)   # card background
R_ORANGE    = (255, 69,  0,   255)   # subreddit / upvote orange
R_TEXT      = (215, 218, 220, 255)   # primary text
R_MUTED     = (129, 131, 132, 255)   # meta / muted text
R_DIVIDER   = (60,  60,  62,  255)   # divider line
R_BORDER    = (255, 69,  0,   200)   # comment left border

PROFILE_COLORS = [
    (255, 69,  0  ),
    (70,  130, 180),
    (60,  179, 113),
    (219, 112, 147),
    (148, 103, 189),
    (255, 165, 0  ),
    (32,  178, 170),
]

CARD_MARGIN = 36   # px from screen edge
CARD_RADIUS = 18
PAD         = 22   # inner card padding


def _profile_color(username: str) -> tuple:
    h = int(hashlib.md5(username.encode()).hexdigest()[:6], 16)
    return PROFILE_COLORS[h % len(PROFILE_COLORS)]


def _font(size: int) -> ImageFont.FreeTypeFont:
    for path in [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _rounded_rect(draw: ImageDraw.Draw, xy, radius: int, fill: tuple):
    try:
        draw.rounded_rectangle(xy, radius=radius, fill=fill)
    except AttributeError:
        x1, y1, x2, y2 = xy
        r = radius
        draw.rectangle([x1+r, y1, x2-r, y2], fill=fill)
        draw.rectangle([x1, y1+r, x2, y2-r], fill=fill)
        for cx, cy in [(x1, y1), (x2-2*r, y1), (x1, y2-2*r), (x2-2*r, y2-2*r)]:
            draw.ellipse([cx, cy, cx+2*r, cy+2*r], fill=fill)


def _profile_circle(draw: ImageDraw.Draw, x: int, y: int,
                    size: int, color: tuple, letter: str):
    draw.ellipse([x, y, x+size, y+size], fill=color + (255,))
    try:
        draw.text((x + size//2, y + size//2), letter.upper(),
                  fill=(255, 255, 255, 255), font=_font(size // 2), anchor="mm")
    except Exception:
        draw.text((x + size//3, y + size//4), letter.upper(),
                  fill=(255, 255, 255, 255), font=_font(size // 2))


def _on_frame(card: Image.Image, y_pos: str = "center") -> Image.Image:
    canvas = Image.new("RGBA", (VIDEO_W, VIDEO_H), (0, 0, 0, 0))
    cx = CARD_MARGIN
    if y_pos == "center":
        cy = max(0, (VIDEO_H - card.height) // 2)
    else:
        cy = max(0, (VIDEO_H - card.height) // 2)
    canvas.paste(card, (cx, cy), card)
    return canvas


def render_post_card(post: dict, subreddit: str) -> Image.Image:
    card_w = VIDEO_W - CARD_MARGIN * 2

    f_sub    = _font(28)
    f_meta   = _font(24)
    f_title  = _font(46)
    f_body   = _font(32)
    f_footer = _font(26)

    title_lines = textwrap.wrap(post["title"], width=26)
    body        = post.get("body", "").strip()
    body_lines  = textwrap.wrap(body, width=34) if body else []

    # Measure height
    header_h  = 52          # icon row
    title_h   = len(title_lines) * 56
    body_h    = len(body_lines) * 40 if body_lines else 0
    footer_h  = 38
    total_h   = (PAD + header_h + 18 + title_h
                 + (14 + body_h if body_h else 0)
                 + 18 + 1 + 14 + footer_h + PAD)

    card = Image.new("RGBA", (card_w, total_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(card)
    _rounded_rect(draw, [0, 0, card_w, total_h], CARD_RADIUS, R_CARD)

    y = PAD

    # ── Header: subreddit icon + name + meta ──
    circ = 38
    _profile_circle(draw, PAD, y + 4, circ, (255, 69, 0), "r")
    draw.text((PAD + circ + 12, y + 2),  subreddit, font=f_sub,  fill=R_ORANGE)
    draw.text((PAD + circ + 12, y + 30), f"Posted by {post['author']} · {post.get('timestamp','4h')}",
              font=f_meta, fill=R_MUTED)
    y += header_h + 18

    # ── Title ──
    for line in title_lines:
        draw.text((PAD, y), line, font=f_title, fill=R_TEXT)
        y += 56

    # ── Body ──
    if body_lines:
        y += 14
        for line in body_lines:
            draw.text((PAD, y), line, font=f_body, fill=R_MUTED)
            y += 40

    y += 18

    # ── Divider ──
    draw.rectangle([PAD, y, card_w - PAD, y + 1], fill=R_DIVIDER)
    y += 15

    # ── Footer: upvotes | comments | share ──
    draw.text((PAD,       y), f"▲  {post['upvotes']}  ▼", font=f_footer, fill=R_MUTED)
    draw.text((PAD + 180, y), "💬  Comments",              font=f_footer, fill=R_MUTED)
    draw.text((PAD + 360, y), "↗  Share",                  font=f_footer, fill=R_MUTED)

    return _on_frame(card)


def render_comment_card(comment: dict) -> Image.Image:
    card_w = VIDEO_W - CARD_MARGIN * 2

    f_author  = _font(30)
    f_meta    = _font(23)
    f_text    = _font(37)
    f_footer  = _font(25)

    text_lines = textwrap.wrap(comment["text"], width=27)

    BORDER = 5   # left orange border width
    INNER  = 16  # gap between border and content

    header_h = 44
    text_h   = len(text_lines) * 50
    footer_h = 34
    total_h  = PAD + header_h + 14 + text_h + 14 + footer_h + PAD

    card = Image.new("RGBA", (card_w, total_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(card)

    # Background
    _rounded_rect(draw, [0, 0, card_w, total_h], CARD_RADIUS, R_CARD)

    # Left orange border (inset from corners)
    draw.rectangle([0, CARD_RADIUS, BORDER, total_h - CARD_RADIUS], fill=R_BORDER)

    content_x = BORDER + INNER

    y = PAD

    # ── Header: profile circle + username + timestamp ──
    author = comment["author"]
    color  = _profile_color(author)
    circ   = 34
    _profile_circle(draw, content_x, y + 4, circ, color,
                    author[2] if len(author) > 2 else "u")

    draw.text((content_x + circ + 10, y + 2),  author,
              font=f_author, fill=R_ORANGE)
    draw.text((content_x + circ + 10, y + 28), f"· {comment.get('timestamp','3h')}",
              font=f_meta,   fill=R_MUTED)
    y += header_h + 14

    # ── Comment text ──
    for line in text_lines:
        draw.text((content_x, y), line, font=f_text, fill=R_TEXT)
        y += 50
    y += 14

    # ── Footer: upvotes | reply | share ──
    draw.text((content_x,       y), f"▲  {comment['upvotes']}  ▼", font=f_footer, fill=R_MUTED)
    draw.text((content_x + 170, y), "↩  Reply",                     font=f_footer, fill=R_MUTED)
    draw.text((content_x + 290, y), "↗  Share",                     font=f_footer, fill=R_MUTED)

    return _on_frame(card)


def save_card_png(card: Image.Image, index: int) -> str:
    out = str(TEMP_DIR / f"card_{index}.png")
    card.save(out, "PNG")
    return out


def render_outro_card() -> Image.Image:
    """Clean follow card shown during the outro — no Reddit card, just a simple CTA."""
    W, H   = 900, 220
    card   = Image.new("RGBA", (W, H), (39, 39, 41, 240))
    draw   = ImageDraw.Draw(card)

    try:
        font_big  = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 38)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 26)
    except Exception:
        font_big  = ImageFont.load_default()
        font_small = font_big

    # Orange accent line at top
    draw.rectangle([(0, 0), (W, 5)], fill=(255, 69, 0, 255))

    # Main text
    main_text = "Follow for a new video every day 🔔"
    sub_text  = "New Reddit question drops daily"

    # Center main text
    bbox = draw.textbbox((0, 0), main_text, font=font_big)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, 65), main_text, font=font_big, fill=(215, 218, 220, 255))

    # Center sub text
    bbox2 = draw.textbbox((0, 0), sub_text, font=font_small)
    tw2 = bbox2[2] - bbox2[0]
    draw.text(((W - tw2) // 2, 130), sub_text, font=font_small, fill=(129, 131, 132, 255))

    return card


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — ElevenLabs: per-segment MP3 with reactive voice settings
# ══════════════════════════════════════════════════════════════════════════════
def mp3_duration(path: str) -> float:
    return MP3(path).info.length


def generate_voice_segments(segments: list) -> list:
    client  = ElevenLabs(api_key=ELEVENLABS_KEY)
    results = []

    for i, seg in enumerate(segments):
        audio_gen = client.text_to_speech.convert(
            voice_id=ELEVENLABS_VOICE_ID,
            text=seg,
            model_id="eleven_multilingual_v2",  # higher quality than turbo
            voice_settings={
                "stability":         0.45,   # consistent but not robotic
                "similarity_boost":  0.80,
                "style":             0.55,   # natural, not over-dramatic
                "use_speaker_boost": True,
            }
        )
        audio_bytes = b"".join(audio_gen)
        path = str(TEMP_DIR / f"voice_{i}.mp3")
        with open(path, "wb") as f:
            f.write(audio_bytes)

        dur = mp3_duration(path)
        costs["elevenlabs"]["chars"] += len(seg)
        costs["elevenlabs"]["usd"]   += (len(seg) / 1000) * 0.30
        results.append({"path": path, "duration": dur})
        print(f"      Segment {i+1}: {dur:.1f}s")

    return results


# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 — Upload
# ══════════════════════════════════════════════════════════════════════════════
def upload(path: str, mime: str) -> str:
    with open(path, "rb") as f:
        r = requests.post(
            "https://tmpfiles.org/api/v1/upload",
            files={"file": (os.path.basename(path), f, mime)}
        )
    r.raise_for_status()
    return r.json()["data"]["url"].replace("tmpfiles.org/", "tmpfiles.org/dl/")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 6 — Shotstack timeline
# ══════════════════════════════════════════════════════════════════════════════
TRANSITIONS = [
    {"in": "fade", "out": "fade"},
    {"in": "zoom", "out": "fade"},
    {"in": "zoom", "out": "fade"},
    {"in": "fade", "out": "fade"},
]

MUSIC_VOLUME = 0.12
DING_VOLUME  = 0.75


def build_timeline(card_urls: list, audio_info: list,
                   ding_url: str, music_url: str, bg_video_url: str) -> dict:

    image_clips = []
    voice_clips = []
    cursor      = 0.0

    for i, (card_url, info) in enumerate(zip(card_urls, audio_info)):
        dur   = info["duration"]
        trans = TRANSITIONS[i] if i < len(TRANSITIONS) else {"in": "fade", "out": "fade"}

        image_clips.append({
            "asset":      {"type": "image", "src": card_url},
            "start":      round(cursor, 3),
            "length":     round(dur, 3),
            "fit":        "crop",
            "transition": trans,
        })
        voice_clips.append({
            "asset":  {"type": "audio", "src": info["url"], "volume": 1.0},
            "start":  round(cursor, 3),
            "length": round(dur, 3),
        })
        cursor += dur

    total = round(cursor, 3)

    # Background video — muted, crops to fill 9:16
    bg_clip = {
        "asset": {"type": "video", "src": bg_video_url, "volume": 0},
        "start": 0, "length": total, "fit": "crop",
    }

    # Lo-fi music loop
    music_dur   = mp3_duration(str(ASSETS_DIR / "lofi_music.mp3"))
    music_clips = []
    t = 0.0
    while t < total:
        music_clips.append({
            "asset":  {"type": "audio", "src": music_url, "volume": MUSIC_VOLUME},
            "start":  round(t, 3),
            "length": round(min(music_dur, total - t), 3),
        })
        t += music_dur

    # Ding at start of each comment
    ding_clips = []
    t = 0.0
    for i, info in enumerate(audio_info):
        if i > 0:
            ding_clips.append({
                "asset":  {"type": "audio", "src": ding_url, "volume": DING_VOLUME},
                "start":  round(t, 3), "length": 1.2,
            })
        t += info["duration"]

    return {
        "timeline": {
            "background": "#000000",
            "tracks": [
                {"clips": image_clips},
                {"clips": [bg_clip]},
                {"clips": voice_clips},
                {"clips": music_clips},
                {"clips": ding_clips},
            ]
        },
        "output": {
            "format": "mp4", "resolution": "hd",
            "aspectRatio": "9:16", "fps": 30,
        }
    }


# ══════════════════════════════════════════════════════════════════════════════
# STEP 7 — Render + download
# ══════════════════════════════════════════════════════════════════════════════
def shotstack_render(timeline: dict) -> str:
    r = requests.post(
        f"{SHOTSTACK_BASE}/render",
        headers={"x-api-key": SHOTSTACK_KEY, "Content-Type": "application/json"},
        json=timeline
    )
    r.raise_for_status()
    return r.json()["response"]["id"]


def shotstack_poll(render_id: str, timeout: int = 600) -> str:
    print("  Rendering", end="", flush=True)
    t0 = time.time()
    while time.time() - t0 < timeout:
        r    = requests.get(f"{SHOTSTACK_BASE}/render/{render_id}",
                            headers={"x-api-key": SHOTSTACK_KEY})
        data = r.json()["response"]
        if data["status"] == "done":
            print(" done!")
            costs["shotstack"]["minutes"] += 1.0
            costs["shotstack"]["usd"]     += 0.40
            return data["url"]
        if data["status"] == "failed":
            raise RuntimeError(f"Shotstack: {data.get('error')}")
        print(".", end="", flush=True)
        time.sleep(10)
    raise TimeoutError("Shotstack timed out")


def download_video(url: str, topic: str) -> str:
    now    = datetime.now()
    folder = os.path.join(OUTPUT_FOLDER, now.strftime("%m-%d-%Y"))
    os.makedirs(folder, exist_ok=True)
    ts     = now.strftime("%H%M%S")
    safe   = topic.replace(" ", "_").replace("/", "-")[:40]
    path   = os.path.join(folder, f"{ts}_reddit_{safe}.mp4")
    r      = requests.get(url, stream=True)
    r.raise_for_status()
    with open(path, "wb") as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)
    return path


def save_caption(video_path: str, caption: str, post_title: str):
    """Save caption + hashtags as a text file right next to the video."""
    txt_path = video_path.replace(".mp4", "_CAPTION.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
        f.write("  TIKTOK CAPTION — copy & paste\n")
        f.write("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n")
        f.write(caption + "\n\n")
        f.write("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
        f.write(f"  Reddit post: {post_title}\n")
        f.write("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
    print(f"  Caption saved → {txt_path}")


# ── Caption spell-check ───────────────────────────────────────────────────────
def fix_caption(caption: str) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    msg = client.messages.create(
        model="claude-haiku-4-5", max_tokens=120,
        messages=[{"role": "user", "content":
            f"Fix any spelling mistakes in this TikTok caption, especially inside hashtags. "
            f"Return ONLY the corrected caption.\n\nCaption: {caption}"}]
    )
    costs["anthropic"]["tokens"] += msg.usage.input_tokens + msg.usage.output_tokens
    costs["anthropic"]["usd"]    += (msg.usage.input_tokens  / 1_000_000 * 0.80) + \
                                     (msg.usage.output_tokens / 1_000_000 * 4.00)
    return msg.content[0].text.strip()


# ── Cost report ───────────────────────────────────────────────────────────────
def print_costs():
    total = sum(v["usd"] for v in costs.values())
    print("\n" + "═" * 54)
    print("  COST REPORT")
    print("═" * 54)
    print(f"  Anthropic    {costs['anthropic']['tokens']:,} tokens       ${costs['anthropic']['usd']:.4f}")
    print(f"  Pexels       free                       $0.0000")
    print(f"  ElevenLabs   {costs['elevenlabs']['chars']} chars          ${costs['elevenlabs']['usd']:.4f}")
    print(f"  Shotstack    {costs['shotstack']['minutes']:.1f} min              ${costs['shotstack']['usd']:.4f}")
    print("─" * 54)
    print(f"  TOTAL                                ${total:.4f}")
    print("═" * 54)


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════
def make_reddit_video(topic: str) -> str:
    print(f"\n  Making Reddit video: '{topic}'\n")

    print("[0/7] Sound assets...")
    ding_path, music_path = ensure_sounds()

    print("\n[1/7] Claude generating content...")
    pkg      = generate_reddit_package(topic)
    caption  = fix_caption(pkg["caption"])
    post     = pkg["post"]
    comments = pkg["comments"]
    segments = pkg["voice_segments"]
    search   = pkg["pexels_search"]

    print(f"      Post:    {post['title'][:60]}...")
    print(f"      Search:  {search}")
    print(f"      Caption: {caption}")

    all_segs = [
        {"type": "post",    "data": post},
        *[{"type": "comment", "data": c} for c in comments]
    ]

    print("\n[2/7] Rendering Reddit cards...")
    card_paths = []
    for i, s in enumerate(all_segs):
        card = render_post_card(s["data"], pkg["subreddit"]) \
               if s["type"] == "post" else render_comment_card(s["data"])
        card_paths.append(save_card_png(card, i))
        print(f"      Card {i+1}/{len(all_segs)} done.")

    MIN_DURATION = 62  # TikTok Creativity Program requires 60s+ to monetise

    print("\n[3/7] ElevenLabs voiceovers...")
    audio_info = generate_voice_segments(segments)
    total_dur  = sum(a["duration"] for a in audio_info)
    print(f"      Total: {total_dur:.1f}s")

    # ── Minimum duration check ────────────────────────────────────────────────
    # If video is under 62s, add a short outro so it always qualifies for
    # TikTok's Creativity Program (pays out on videos over 60 seconds only).
    if total_dur < MIN_DURATION:
        gap       = MIN_DURATION - total_dur
        outro_txt = "Follow for a new video every day."
        print(f"      ⚠️  {total_dur:.1f}s is under {MIN_DURATION}s — adding {gap:.1f}s outro to qualify for monetisation...")
        client    = ElevenLabs(api_key=ELEVENLABS_KEY)
        audio_gen = client.text_to_speech.convert(
            voice_id=ELEVENLABS_VOICE_ID,
            text=outro_txt,
            model_id="eleven_multilingual_v2",
            voice_settings={"stability": 0.45, "similarity_boost": 0.80,
                            "style": 0.55, "use_speaker_boost": True}
        )
        outro_bytes = b"".join(audio_gen)
        outro_path  = str(TEMP_DIR / "voice_outro.mp3")
        with open(outro_path, "wb") as f:
            f.write(outro_bytes)
        outro_dur = mp3_duration(outro_path)
        costs["elevenlabs"]["chars"] += len(outro_txt)
        costs["elevenlabs"]["usd"]   += (len(outro_txt) / 1000) * 0.30
        audio_info.append({"path": outro_path, "duration": outro_dur, "is_outro": True})
        # Render a dedicated follow card instead of repeating the last answer
        outro_card     = render_outro_card()
        outro_card_idx = len(card_paths)
        outro_card_path = save_card_png(outro_card, outro_card_idx)
        card_paths.append(outro_card_path)
        total_dur = sum(a["duration"] for a in audio_info)
        print(f"      ✅ New total: {total_dur:.1f}s")

    # Fetch Pexels AFTER we know the exact video duration so the background
    # is always long enough to cover the whole video (+ 10s safety buffer)
    print(f"\n[4/7] Fetching Pexels background video (min {int(total_dur) + 10}s)...")
    bg_video_url = fetch_pexels_video(search, min_dur=int(total_dur) + 10)

    print("\n[5/7] Uploading...")
    card_urls = []
    for i, cp in enumerate(card_paths):
        card_urls.append(upload(cp, "image/png"))
        print(f"      Card {i+1} uploaded.")
    for i, info in enumerate(audio_info):
        info["url"] = upload(info["path"], "audio/mpeg")
        print(f"      Voice {i+1} uploaded. ({info['duration']:.1f}s)")
    ding_url  = upload(ding_path,  "audio/mpeg")
    music_url = upload(music_path, "audio/mpeg")
    print("      Ding + music uploaded.")

    print("\n[6/7] Building timeline + rendering...")
    t = 0.0
    for i, info in enumerate(audio_info):
        if info.get("is_outro"):
            label = "Outro   "
            ding  = ""
        elif i == 0:
            label = "Question"
            ding  = ""
        else:
            label = f"Answer {i}"
            ding  = " ← ding"
        print(f"      {label}  {t:.1f}s – {t+info['duration']:.1f}s{ding}")
        t += info["duration"]

    timeline  = build_timeline(card_urls, audio_info, ding_url, music_url, bg_video_url)
    render_id = shotstack_render(timeline)
    final_url = shotstack_poll(render_id)

    print("\n[7/7] Downloading...")
    local = download_video(final_url, topic)

    save_caption(local, caption, post["title"])

    print(f"\n  ✅ DONE!")
    print(f"  Saved  → {local}")
    print(f"  Length → {total_dur:.1f}s")
    print(f"\n  TikTok Caption:")
    print(f"  {caption}")
    print_costs()

    # ── Push to GitHub dashboard ──────────────────────────────────────────────
    try:
        push_to_dashboard(local, topic, caption)
    except Exception as e:
        print(f"\n  ⚠️  Dashboard push failed (video still saved locally): {e}")

    return local


def push_to_dashboard(video_path: str, topic: str, caption: str):
    """Upload video to GitHub Releases and commit a markdown card to GitHub."""
    import base64
    from datetime import datetime, timezone

    GITHUB_TOKEN = os.getenv("BOT_PUSH_TOKEN", "")
    REPO = "Gigantatoll/reddit-ai-videos"
    GH_HEADERS = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

    # 1 — Upload video to GitHub Releases
    print("\n  📤 Uploading to GitHub Releases...")
    now = datetime.now(timezone.utc)
    tag = now.strftime("video-%Y-%m-%d-%H-%M-UTC")
    video_filename = os.path.basename(video_path)

    # Create the release
    release_resp = requests.post(
        f"https://api.github.com/repos/{REPO}/releases",
        headers=GH_HEADERS,
        json={
            "tag_name": tag,
            "name": f"Reddit Video — {now.strftime('%Y-%m-%d %H:%M UTC')}",
            "body": topic,
            "draft": False,
            "prerelease": False,
        },
        timeout=30
    )
    release_resp.raise_for_status()
    release_id = release_resp.json()["id"]

    # Upload the video as a release asset
    upload_headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Content-Type": "video/mp4",
    }
    with open(video_path, "rb") as f:
        upload_resp = requests.post(
            f"https://uploads.github.com/repos/{REPO}/releases/{release_id}/assets"
            f"?name={video_filename}",
            headers=upload_headers,
            data=f,
            timeout=300
        )
    upload_resp.raise_for_status()
    video_url = upload_resp.json()["browser_download_url"]
    print(f"  Hosted at: {video_url}")

    # 2 — Build markdown content
    filename = now.strftime("%Y-%m-%d_%H-%M-UTC") + ".md"
    md = f"""# Reddit Video — {now.strftime('%Y-%m-%d %H:%M UTC')}

**Topic:** {topic}

## Video Download Link
{video_url}

## Caption & Hashtags
```
{caption}
```

---
*Auto-generated by Reddit Video Bot*
"""

    # 3 — Commit to GitHub output/ folder
    encoded = base64.b64encode(md.encode()).decode()
    resp = requests.put(
        f"https://api.github.com/repos/{REPO}/contents/output/{filename}",
        headers=GH_HEADERS,
        json={"message": f"🎬 {topic[:60]}", "content": encoded},
        timeout=30
    )
    resp.raise_for_status()
    print(f"  ✅ Dashboard updated → https://gigantatoll.github.io/reddit-ai-videos/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", type=str,
                        default="pettiest thing you've ever done to a neighbour")
    parser.add_argument("--audience", type=str, default="general",
                        help="Audience tag from topics.json (e.g. work, school, dating)")
    args = parser.parse_args()
    make_reddit_video(args.topic)
