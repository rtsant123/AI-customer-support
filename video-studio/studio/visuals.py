"""Step 4: get a clip for every scene (AI-generated video, stock footage, or a text card)."""
import os
import subprocess

import requests

from .director import Scene


def _download(url: str, path: str, headers: dict | None = None) -> str:
    with requests.get(url, headers=headers, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    return path


def ai_video(prompt: str, path: str, fmt: str) -> str:
    """Text-to-video on Replicate. Pick any model with REPLICATE_VIDEO_MODEL."""
    import replicate

    output = replicate.run(
        os.environ["REPLICATE_VIDEO_MODEL"],
        input={"prompt": prompt, "aspect_ratio": "9:16" if fmt == "short" else "16:9"},
    )
    if isinstance(output, list):
        output = output[0]
    if hasattr(output, "read"):
        with open(path, "wb") as f:
            f.write(output.read())
        return path
    return _download(str(output), path)


def stock_video(query: str, path: str, fmt: str, target_height: int) -> str:
    """Free stock footage from Pexels."""
    r = requests.get(
        "https://api.pexels.com/videos/search",
        headers={"Authorization": os.environ["PEXELS_API_KEY"]},
        params={"query": query, "per_page": 5,
                "orientation": "portrait" if fmt == "short" else "landscape"},
        timeout=30,
    )
    r.raise_for_status()
    videos = r.json().get("videos", [])
    if not videos:
        raise RuntimeError(f"No stock results for '{query}'")
    files = [f for f in videos[0]["video_files"] if f.get("height") and f.get("file_type") == "video/mp4"]
    best = min(files, key=lambda f: abs(f["height"] - target_height))
    return _download(best["link"], path)


def placeholder(scene: Scene, path: str, width: int, height: int) -> str:
    """Dark card with the prompt on it, so the editor knows exactly what goes here."""
    fontsize = height // 36
    chars = int(width * 0.8 / (fontsize * 0.6))
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
           "-i", f"color=c=0x1e1e28:s={width}x{height}:d=2:r=30"]
    txt = path + ".txt"
    if scene.visual_source != "text_card":  # text cards stay clean; the overlay is the content
        label = scene.ai_video_prompt or scene.stock_search or scene.narration
        with open(txt, "w") as f:
            f.write(f"SCENE {scene.number} - {scene.visual_source.upper()}\n\n{_wrap(label, chars)}")
        cmd += ["-vf", f"drawtext=textfile='{txt}':fontcolor=0x9aa0b4:fontsize={fontsize}"
                       ":x=(w-tw)/2:y=h*0.06:line_spacing=10"]
    subprocess.run(cmd + ["-c:v", "libx264", "-pix_fmt", "yuv420p", path], check=True)
    if os.path.exists(txt):
        os.remove(txt)
    return path


def _wrap(text: str, width: int) -> str:
    lines, line = [], ""
    for word in text.split():
        if len(line) + len(word) + 1 > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    lines.append(line)
    return "\n".join(lines[:10])


def get_clip(scene: Scene, clips_dir: str, fmt: str, width: int, height: int) -> tuple[str, str]:
    """Return (clip_path, where_it_came_from). Reuses clips already downloaded."""
    path = os.path.join(clips_dir, f"scene_{scene.number:03d}_source.mp4")
    tag = path + ".source"
    if os.path.exists(path):
        return path, open(tag).read() if os.path.exists(tag) else "existing clip"

    attempts = []
    if scene.visual_source == "ai_video" and os.getenv("REPLICATE_API_TOKEN") and os.getenv("REPLICATE_VIDEO_MODEL"):
        attempts.append(("ai_video", lambda: ai_video(scene.ai_video_prompt, path, fmt)))
    if scene.visual_source != "text_card" and os.getenv("PEXELS_API_KEY") and scene.stock_search:
        attempts.append(("stock", lambda: stock_video(scene.stock_search, path, fmt, height)))

    for name, fn in attempts:
        try:
            fn()
            _tag(tag, name)
            return path, name
        except Exception as e:  # one bad clip should never stop the whole video
            print(f"   ! scene {scene.number}: {name} failed ({e}), trying next option")
            if os.path.exists(path):
                os.remove(path)
    placeholder(scene, path, width, height)
    _tag(tag, "placeholder")
    return path, "placeholder"


def _tag(path: str, source: str) -> None:
    with open(path, "w") as f:
        f.write(source)
