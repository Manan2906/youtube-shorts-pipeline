"""B-roll generation: Giphy memes/GIFs, Pexels video/image, Gemini Imagen, Ken Burns animation."""

import base64
import random
from pathlib import Path

import requests
from PIL import Image

from .config import VIDEO_WIDTH, VIDEO_HEIGHT, get_gemini_key, get_pexels_key, extract_keywords, run_cmd
from .log import log
from .retry import with_retry

# Giphy public API key (free, 100 req/hour — sufficient for video generation)
GIPHY_API_KEY = "GlVGYHkr3WSBnllca54iNt0yFbjz7L65"


# ─────────────────────────────────────────────────────
# Gemini Imagen (original provider)
# ─────────────────────────────────────────────────────
@with_retry(max_retries=3, base_delay=2.0)
def _generate_image_gemini(prompt: str, output_path: Path, api_key: str):
    """Generate image via Gemini native image generation (free tier compatible)."""
    url = (
        "https://generativelanguage.googleapis.com/v1beta"
        "/models/gemini-2.0-flash-exp-image-generation:generateContent"
    )
    body = {
        "contents": [{"parts": [{"text": f"Generate an image: {prompt}"}]}],
        "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]},
    }
    r = requests.post(
        url, json=body, timeout=90,
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
    )
    if r.status_code != 200:
        try:
            detail = r.json().get("error", {}).get("message", r.text[:200])
        except Exception:
            detail = r.text[:200]
        raise RuntimeError(f"Gemini API {r.status_code}: {detail}")
    data = r.json()
    for part in data.get("candidates", [{}])[0].get("content", {}).get("parts", []):
        if "inlineData" in part:
            img_b64 = part["inlineData"]["data"]
            output_path.write_bytes(base64.b64decode(img_b64))
            return
    raise RuntimeError("No image in Gemini response")


# ─────────────────────────────────────────────────────
# Pexels stock video & image
# ─────────────────────────────────────────────────────
def _prompt_to_search_query(prompt: str) -> str:
    """Convert a long LLM b-roll prompt into a short Pexels search query."""
    keywords = extract_keywords(prompt)       # returns top 4 keywords
    words = keywords.split()[:3]              # Pexels works best with 2-3 words
    return " ".join(words)


@with_retry(max_retries=2, base_delay=1.0)
def _download_pexels_video(query: str, output_path: Path, api_key: str) -> Path:
    """Search Pexels Videos API and download the best portrait HD clip."""
    url = "https://api.pexels.com/videos/search"
    headers = {"Authorization": api_key}

    # Try with full query first, then shorter if no results
    for q in [query, " ".join(query.split()[:2])]:
        r = requests.get(
            url,
            params={"query": q, "per_page": 15, "orientation": "portrait", "size": "medium"},
            headers=headers,
            timeout=30,
        )
        if r.status_code == 429:
            raise RuntimeError("Pexels rate limit hit — retry later")
        if r.status_code != 200:
            raise RuntimeError(f"Pexels Videos API {r.status_code}: {r.text[:200]}")

        data = r.json()
        videos = data.get("videos", [])
        if videos:
            break
    else:
        raise RuntimeError(f"No Pexels videos found for query: {query}")

    if not videos:
        raise RuntimeError(f"No Pexels videos found for query: {query}")

    # Pick the best video file: prefer HD, width closest to 1080
    best_file = None
    best_score = float("inf")
    for video in videos[:5]:
        for vf in video.get("video_files", []):
            w = vf.get("width", 0)
            h = vf.get("height", 0)
            quality = vf.get("quality", "")
            # Prefer portrait (h > w), HD quality, close to 1080 width
            if h >= w and quality in ("hd", "sd"):
                score = abs(w - 1080) + (0 if quality == "hd" else 500)
                if score < best_score:
                    best_score = score
                    best_file = vf

    # If no portrait found, accept any HD file
    if not best_file:
        for video in videos[:5]:
            for vf in video.get("video_files", []):
                if vf.get("quality") == "hd":
                    best_file = vf
                    break
            if best_file:
                break

    if not best_file:
        raise RuntimeError(f"No suitable video file found for query: {query}")

    # Download the video clip
    download_url = best_file["link"]
    log(f"  Downloading Pexels video ({best_file.get('width', '?')}x{best_file.get('height', '?')})...")
    resp = requests.get(download_url, timeout=60, stream=True)
    resp.raise_for_status()
    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    return output_path


@with_retry(max_retries=2, base_delay=1.0)
def _download_pexels_image(query: str, output_path: Path, api_key: str) -> Path:
    """Search Pexels Photos API and download the best portrait image."""
    url = "https://api.pexels.com/v1/search"
    headers = {"Authorization": api_key}

    for q in [query, " ".join(query.split()[:2])]:
        r = requests.get(
            url,
            params={"query": q, "per_page": 5, "orientation": "portrait", "size": "medium"},
            headers=headers,
            timeout=30,
        )
        if r.status_code == 429:
            raise RuntimeError("Pexels rate limit hit — retry later")
        if r.status_code != 200:
            raise RuntimeError(f"Pexels Photos API {r.status_code}: {r.text[:200]}")

        photos = r.json().get("photos", [])
        if photos:
            break
    else:
        raise RuntimeError(f"No Pexels photos found for query: {query}")

    if not photos:
        raise RuntimeError(f"No Pexels photos found for query: {query}")

    # Download the portrait-oriented image
    photo = photos[0]
    img_url = photo.get("src", {}).get("portrait") or photo.get("src", {}).get("large2x") or photo["src"]["large"]
    log(f"  Downloading Pexels image...")
    resp = requests.get(img_url, timeout=30)
    resp.raise_for_status()
    output_path.write_bytes(resp.content)
    return output_path


# ─────────────────────────────────────────────────────
# Giphy — memes, reaction GIFs, topical content
# ─────────────────────────────────────────────────────
@with_retry(max_retries=2, base_delay=1.0)
def _download_giphy_gif(query: str, output_path: Path, offset: int = 0) -> Path:
    """Search Giphy for memes/GIFs and download as MP4.

    Giphy is ideal for: people, memes, reactions, pop culture, politics,
    celebrities, trending topics — everything Pexels can't do.
    """
    url = "https://api.giphy.com/v1/gifs/search"
    r = requests.get(
        url,
        params={
            "api_key": GIPHY_API_KEY,
            "q": query,
            "limit": 10,
            "offset": offset,
            "rating": "pg-13",
            "lang": "en",
        },
        timeout=15,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Giphy API {r.status_code}: {r.text[:200]}")

    data = r.json()
    gifs = data.get("data", [])
    if not gifs:
        raise RuntimeError(f"No Giphy results for: {query}")

    # Pick a random GIF from top results for variety
    gif = random.choice(gifs[:min(5, len(gifs))])

    # Prefer MP4 (smaller, better quality than GIF)
    mp4_url = (
        gif.get("images", {}).get("original_mp4", {}).get("mp4")
        or gif.get("images", {}).get("looping", {}).get("mp4")
        or gif.get("images", {}).get("downsized", {}).get("url", "")
    )

    if not mp4_url:
        # Fallback to GIF URL and convert
        mp4_url = gif.get("images", {}).get("original", {}).get("url", "")

    if not mp4_url:
        raise RuntimeError(f"No downloadable media for Giphy result: {gif.get('title', '')}")

    log(f"  Downloading Giphy: \"{gif.get('title', '')[:40]}\"...")
    resp = requests.get(mp4_url, timeout=30)
    resp.raise_for_status()
    output_path.write_bytes(resp.content)
    return output_path


# ─────────────────────────────────────────────────────
# Fallback + portrait crop
# ─────────────────────────────────────────────────────
def _fallback_frame(i: int, out_dir: Path) -> Path:
    """Solid colour fallback frame if all providers fail."""
    colors = [(20, 20, 60), (40, 10, 40), (10, 30, 50)]
    img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), colors[i % len(colors)])
    path = out_dir / f"broll_{i}.png"
    img.save(path)
    return path


def _crop_to_portrait(img_path: Path):
    """Resize and center-crop an image to 1080x1920 portrait."""
    img = Image.open(img_path).convert("RGB")
    target_w, target_h = VIDEO_WIDTH, VIDEO_HEIGHT
    orig_w, orig_h = img.size
    scale = max(target_w / orig_w, target_h / orig_h)
    new_w, new_h = int(orig_w * scale), int(orig_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    img = img.crop((left, top, left + target_w, top + target_h))
    img.save(img_path)


# ─────────────────────────────────────────────────────
# Main entry: generate b-roll with full fallback chain
# ─────────────────────────────────────────────────────
def generate_broll(prompts: list, out_dir: Path, search_terms: list | None = None, giphy_terms: list | None = None) -> list[Path]:
    """Generate b-roll with fallback chain:
       Giphy memes/GIFs → Pexels video → Pexels image → Gemini → solid color.

    Giphy is tried FIRST because it has topical content (people, memes,
    politics, pop culture) that Pexels stock footage completely lacks.

    Args:
        prompts: Detailed b-roll prompts (for Gemini image generation).
        out_dir: Directory to save frames.
        search_terms: LLM-generated Pexels search queries (stock footage).
        giphy_terms: LLM-generated Giphy search queries (memes, people, reactions).
    """
    gemini_key = get_gemini_key()
    pexels_key = get_pexels_key()

    sources = ["Giphy (memes/GIFs)"]
    if pexels_key:
        sources.append("Pexels Video")
    if gemini_key:
        sources.append("Gemini AI")
    sources.append("fallback")
    log(f"B-roll sources: {', '.join(sources)}")

    frames = []
    giphy_offset = 0  # avoid duplicate GIFs across frames

    for i, prompt in enumerate(prompts):
        # Get search queries for this frame
        pexels_q = search_terms[i] if search_terms and i < len(search_terms) else _prompt_to_search_query(prompt)
        giphy_q = giphy_terms[i] if giphy_terms and i < len(giphy_terms) else pexels_q
        acquired = False

        # ── 1. Try Giphy (memes, reactions, topical — BEST for people/politics) ──
        if not acquired:
            out_path = out_dir / f"broll_{i}.mp4"
            log(f"Searching Giphy for: \"{giphy_q}\"...")
            try:
                _download_giphy_gif(giphy_q, out_path, offset=i * 3)
                frames.append(out_path)
                acquired = True
                log(f"  Giphy clip saved: {out_path.name}")
            except Exception as e:
                log(f"  Giphy failed: {e}")

        # ── 2. Try Pexels Video (stock footage — good for abstract/scenic) ──
        if pexels_key and not acquired:
            out_path = out_dir / f"broll_{i}.mp4"
            log(f"Searching Pexels for: \"{pexels_q}\"...")
            try:
                _download_pexels_video(pexels_q, out_path, pexels_key)
                frames.append(out_path)
                acquired = True
                log(f"  Pexels video saved: {out_path.name}")
            except Exception as e:
                log(f"  Pexels video failed: {e}")

        # ── 3. Try Gemini Imagen (AI generation) ──
        if gemini_key and not acquired:
            out_path = out_dir / f"broll_{i}.png"
            log(f"Generating via Gemini Imagen...")
            try:
                _generate_image_gemini(prompt, out_path, gemini_key)
                _crop_to_portrait(out_path)
                frames.append(out_path)
                acquired = True
            except Exception as e:
                log(f"  Gemini failed: {e}")

        # ── 4. Try Pexels Image (static photo fallback) ──
        if pexels_key and not acquired:
            out_path = out_dir / f"broll_{i}.png"
            try:
                _download_pexels_image(pexels_q, out_path, pexels_key)
                _crop_to_portrait(out_path)
                frames.append(out_path)
                acquired = True
            except Exception as e:
                log(f"  Pexels image failed: {e}")

        # ── 5. Solid color fallback ──
        if not acquired:
            log(f"  Frame {i+1}: all providers failed — using solid color fallback")
            frames.append(_fallback_frame(i, out_dir))

    return frames


# ─────────────────────────────────────────────────────
# Ken Burns animation for static images
# ─────────────────────────────────────────────────────
def animate_frame(img_path: Path, out_path: Path, duration: float, effect: str = "zoom_in"):
    """Ken Burns animation on a single frame."""
    fps = 30
    frames = int(duration * fps)
    w, h = VIDEO_WIDTH, VIDEO_HEIGHT

    if effect == "zoom_in":
        vf = (
            f"scale={int(w * 1.12)}:{int(h * 1.12)},"
            f"zoompan=z='1.12-0.12*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={frames}:s={w}x{h}:fps={fps}"
        )
    elif effect == "pan_right":
        vf = (
            f"scale={int(w * 1.15)}:{int(h * 1.15)},"
            f"zoompan=z=1.15:x='0.15*iw*on/{frames}':y='ih*0.075'"
            f":d={frames}:s={w}x{h}:fps={fps}"
        )
    else:  # zoom_out
        vf = (
            f"scale={int(w * 1.12)}:{int(h * 1.12)},"
            f"zoompan=z='1.0+0.12*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={frames}:s={w}x{h}:fps={fps}"
        )

    run_cmd([
        "ffmpeg", "-loop", "1", "-i", str(img_path),
        "-vf", vf, "-t", str(duration), "-r", str(fps),
        "-pix_fmt", "yuv420p", str(out_path), "-y", "-loglevel", "quiet",
    ])
