"""ffmpeg video assembly — frames + voiceover + music + captions."""

from pathlib import Path

from .broll import animate_frame
from .config import MEDIA_DIR, run_cmd
from .log import log


def get_audio_duration(path: Path) -> float:
    """Get duration of an audio file in seconds."""
    import shutil
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        r = run_cmd(
            [ffprobe, "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)],
            capture=True,
        )
        return float(r.stdout.strip())
    # Fallback: use ffmpeg to detect duration
    r = run_cmd(
        ["ffmpeg", "-i", str(path), "-f", "null", "-"],
        capture=True,
    )
    # Parse duration from ffmpeg stderr output
    import re
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+)\.(\d+)", r.stderr or "")
    if match:
        h, m, s, cs = match.groups()
        return int(h) * 3600 + int(m) * 60 + int(s) + int(cs) / 100
    raise RuntimeError(f"Cannot determine audio duration for {path}")


def _trim_video_clip(clip: Path, out_path: Path, duration: float):
    """Trim/loop a Pexels video clip to exact duration, scale to 1080x1920 portrait.

    Strategy: first concat the clip with itself enough times to exceed
    the target duration (via concat demuxer), then trim + scale. This is
    more reliable than -stream_loop which can freeze on some codecs.
    """
    from .config import VIDEO_WIDTH, VIDEO_HEIGHT
    w, h = VIDEO_WIDTH, VIDEO_HEIGHT

    # Step 1: Figure out how many loops we need
    # Get source clip duration via ffmpeg
    import re
    r = run_cmd(
        ["ffmpeg", "-i", str(clip), "-f", "null", "-"],
        capture=True, check=False,
    )
    src_dur = 0.0
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+)\.(\d+)", r.stderr or "")
    if match:
        hh, mm, ss, cs = match.groups()
        src_dur = int(hh) * 3600 + int(mm) * 60 + int(ss) + int(cs) / 100

    # Step 2: Build concat list to guarantee enough footage
    concat_file = clip.parent / f"_loop_{clip.stem}.txt"
    loops_needed = max(1, int(duration / max(src_dur, 1)) + 2)
    escaped = str(clip).replace("'", "'\\''")
    concat_file.write_text(
        "\n".join(f"file '{escaped}'" for _ in range(loops_needed)),
        encoding="utf-8",
    )

    # Step 3: Concat-loop → trim → scale/crop → force 30fps → output
    # Use Baseline profile + faststart for maximum player compatibility (incl. Windows Media Player)
    run_cmd([
        "ffmpeg",
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-t", str(duration),
        "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps=30",
        "-r", "30",
        "-c:v", "libx264", "-profile:v", "baseline", "-level", "3.1",
        "-preset", "fast", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-an",
        str(out_path), "-y", "-loglevel", "quiet",
    ])

    # Clean up temp concat file
    concat_file.unlink(missing_ok=True)


def _compute_segment_durations(
    total_duration: float,
    num_segments: int,
    word_timestamps: list[dict] | None = None,
) -> list[float]:
    """Compute per-segment durations that align with speech content.

    If word_timestamps are provided, splits the voiceover into N equal-word
    segments and uses the actual spoken duration for each. This ensures
    clip transitions happen between spoken phrases, not mid-sentence.
    Falls back to equal splits if no timestamps.
    """
    if not word_timestamps or num_segments < 2:
        equal = total_duration / max(num_segments, 1)
        return [equal] * num_segments

    # Split words into N roughly equal groups
    words_per_seg = max(1, len(word_timestamps) // num_segments)
    durations = []
    for i in range(num_segments):
        start_idx = i * words_per_seg
        if i == num_segments - 1:
            # Last segment gets all remaining words
            end_idx = len(word_timestamps) - 1
        else:
            end_idx = min((i + 1) * words_per_seg - 1, len(word_timestamps) - 1)

        seg_start = word_timestamps[start_idx]["start"]
        seg_end = word_timestamps[end_idx]["end"]
        durations.append(seg_end - seg_start)

    # Ensure durations cover the full audio (adjust last segment)
    actual_sum = sum(durations)
    if actual_sum < total_duration:
        durations[-1] += (total_duration - actual_sum)

    # Minimum 4 seconds per segment so clips aren't too jumpy
    durations = [max(d, 4.0) for d in durations]

    return durations


def assemble_video(
    frames: list[Path],
    voiceover: Path,
    out_dir: Path,
    job_id: str,
    lang: str = "en",
    ass_path: str | None = None,
    music_path: str | None = None,
    duck_filter: str | None = None,
    word_timestamps: list[dict] | None = None,
) -> Path:
    """Assemble final video from frames, voiceover, captions, and music."""
    log("Assembling video...")
    duration = get_audio_duration(voiceover)
    effects = ["zoom_in", "pan_right", "zoom_out"]

    # Compute per-clip durations aligned with speech content
    seg_durations = _compute_segment_durations(duration, len(frames), word_timestamps)

    # Animate each frame: video clips get trimmed, images get Ken Burns
    animated = []
    for i, frame in enumerate(frames):
        seg_dur = seg_durations[i] + 0.1  # small buffer
        anim = out_dir / f"anim_{i}.mp4"
        if frame.suffix == ".mp4":
            log(f"  Trimming video clip {i+1} to {seg_dur:.1f}s...")
            _trim_video_clip(frame, anim, seg_dur)
        else:
            animate_frame(frame, anim, seg_dur, effects[i % len(effects)])
        animated.append(anim)

    # Concat animated segments (escape single quotes for ffmpeg concat demuxer)
    concat_file = out_dir / "concat.txt"
    def _esc(p):
        return str(p).replace("'", "'\\''" )
    concat_file.write_text("\n".join(f"file '{_esc(p)}'" for p in animated), encoding="utf-8")

    merged_video = out_dir / "merged_video.mp4"
    run_cmd([
        "ffmpeg", "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c:v", "libx264", "-profile:v", "baseline", "-level", "3.1",
        "-preset", "fast", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(merged_video), "-y", "-loglevel", "quiet",
    ])

    # Build the final ffmpeg command with optional captions + music
    out_path = MEDIA_DIR / f"verticals_{job_id}_{lang}.mp4"

    # Determine video filter (captions via ASS)
    vf_parts = []
    if ass_path and Path(ass_path).exists():
        # ffmpeg ASS filter has issues with absolute paths on Windows
        # Use just the filename and set cwd during ffmpeg execution
        import os
        ass_file = Path(ass_path)
        if os.name == "nt":
            # Just use the filename — we'll set cwd to the directory
            vf_parts.append(f"ass={ass_file.name}")
        else:
            escaped_ass = str(ass_path).replace("\\", "\\\\").replace(":", "\\:")
            escaped_ass = escaped_ass.replace("'", "\\'")
            vf_parts.append(f"ass={escaped_ass}")
    vf = ",".join(vf_parts) if vf_parts else None

    if music_path and Path(music_path).exists():
        # Three inputs: video, voiceover, music
        cmd = ["ffmpeg", "-i", str(merged_video), "-i", str(voiceover)]

        # Loop music to match video duration, apply ducking
        music_filter = f"[2:a]aloop=loop=-1:size=2e+09,atrim=0:{duration}"
        if duck_filter:
            music_filter += f",{duck_filter}"
        music_filter += "[music]"

        # Mix voiceover + ducked music
        audio_filter = f"{music_filter};[1:a][music]amix=inputs=2:duration=first:dropout_transition=2[aout]"

        cmd += [
            "-stream_loop", "-1", "-i", str(music_path),
            "-filter_complex", audio_filter,
        ]

        if vf:
            cmd += ["-vf", vf]

        cmd += [
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest",
            str(out_path), "-y", "-loglevel", "quiet",
        ]
    else:
        # Two inputs: video + voiceover (no music)
        cmd = ["ffmpeg", "-i", str(merged_video), "-i", str(voiceover)]

        if vf:
            cmd += ["-vf", vf]

        cmd += [
            "-c:v", "libx264", "-profile:v", "baseline", "-level", "3.1",
            "-preset", "fast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest",
            "-movflags", "+faststart",
            str(out_path), "-y", "-loglevel", "quiet",
        ]

    # On Windows, run from the ASS file's directory so relative paths work
    import os
    ffmpeg_cwd = str(out_dir) if os.name == "nt" and ass_path else None
    run_cmd(cmd, cwd=ffmpeg_cwd)
    log(f"Video assembled: {out_path}")
    return out_path
