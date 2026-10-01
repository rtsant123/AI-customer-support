# AI Video Studio

Give it a **script** and a **voiceover**. It gives back a YouTube video in **parts**, ready for your editor to review.

```
script.txt + voice.mp3
   │
   ├─ 1. Whisper        → timed transcript (free, runs on your computer)
   ├─ 2. AI researcher  → Claude fact-checks the script on the web
   ├─ 3. AI director    → Claude plans every scene: AI-video prompt, stock search,
   │                      text overlay, cuts, transitions, SFX
   ├─ 4. Visuals        → AI-generated video (Replicate) → stock footage (Pexels)
   │                      → placeholder card with the prompt, if neither works
   └─ 5. Editor         → FFmpeg cuts each scene to the voiceover and adds the overlay
```

Works for **long videos (16:9)** and **Shorts (9:16)**.

## What you get (the `output/` folder)

| File | What it is |
|---|---|
| `parts/part_001.mp4 …` | One clip per scene: voiceover, visual and text overlay |
| `rough_cut.mp4` | All parts joined, for a quick watch |
| `edit_plan.md` | Director notes per part, written for your editor |
| `research.md` | Fact check, extra facts and sources |
| `captions.srt` | Subtitles, ready to upload to YouTube |
| `plan.json` | The full scene plan. Edit it and re-run with `--plan` |

## Setup (one time)

**Step 1.** Install Python 3.10+ and FFmpeg (`brew install ffmpeg`, `sudo apt install ffmpeg`, or ffmpeg.org on Windows).

**Step 2.** Install the packages:
```bash
cd video-studio
pip install -r requirements.txt
```

**Step 3.** Add your keys:
```bash
cp .env.example .env
```
Open `.env` and fill in:
- `ANTHROPIC_API_KEY`: **required**. Get it at console.anthropic.com.
- `PEXELS_API_KEY`: optional, free. Get it at pexels.com/api.
- `REPLICATE_API_TOKEN` + `REPLICATE_VIDEO_MODEL`: optional, for AI-generated clips (paid per clip). Use any text-to-video model on replicate.com.

## Make a video

**Long video (16:9):**
```bash
python make_video.py my_script.txt my_voice.mp3 --format long
```

**YouTube Short (9:16):**
```bash
python make_video.py my_script.txt my_voice.mp3 --format short --out output_short
```

**Test it with no API keys** (makes text cards only, to check that FFmpeg works):
```bash
python make_video.py examples/script.txt my_voice.mp3 --no-ai
```

## Change a scene after review

1. Open `output/plan.json` and edit a scene (overlay text, prompt, timing, or `visual_source`).
2. Delete that scene's clip from `output/clips/` if you want a new visual.
3. Re-run with your edited plan. Research and directing are skipped, and unchanged clips are reused (no extra cost):
```bash
python make_video.py my_script.txt my_voice.mp3 --plan output/plan.json
```

## Options

| Flag | Meaning |
|---|---|
| `--format long\|short` | 16:9 long video or 9:16 Short |
| `--out FOLDER` | Where to save (default `output`) |
| `--plan plan.json` | Re-render from an edited plan |
| `--no-research` | Skip web research (faster, cheaper) |
| `--no-whisper` | Estimate timing from the script instead of transcribing |
| `--whisper-model` | `tiny`, `base`, `small` (default), `medium`, `large-v3` |
| `--no-ai` | No API calls, for testing |
