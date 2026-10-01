"""Step 3: AI director. Claude turns script + timing + research into a scene-by-scene edit plan."""
import json
from typing import Literal

import anthropic
from pydantic import BaseModel

from .research import FALLBACK_BETA, MODEL
from .transcribe import Segment


class Scene(BaseModel):
    number: int
    start: float
    end: float
    narration: str
    visual_source: Literal["ai_video", "stock", "text_card"]
    ai_video_prompt: str
    stock_search: str
    overlay_text: str
    overlay_position: Literal["top", "center", "bottom"]
    camera_and_edit_notes: str
    transition: str
    sfx_and_music: str
    fact_check_note: str


class VideoPlan(BaseModel):
    title_ideas: list[str]
    thumbnail_prompt: str
    music_mood: str
    hook_notes: str
    scenes: list[Scene]


STYLE = {
    "long": "Long-form YouTube video, 16:9. Scenes of about 4-8 seconds. Calm, documentary pacing.",
    "short": "YouTube Short, vertical 9:16, under 60s. Fast scenes of about 1.5-3 seconds. "
             "Strong hook in the first 2 seconds. Big, punchy overlay text.",
}

DIRECTOR_PROMPT = """You are the director and lead editor of a YouTube channel.
Format: {style}
Total audio length: {duration:.2f} seconds.

Turn the voiceover below into a shot list. Rules:
- Scenes must cover the whole audio with no gaps: the first starts at 0, each scene starts
  where the previous one ends, and the last ends at {duration:.2f}. Cut on the timestamps given.
- visual_source: "ai_video" for things stock footage can't show (history, concepts, the
  impossible), "stock" for real everyday footage, "text_card" for stats or lists.
- ai_video_prompt: a detailed text-to-video prompt (subject, action, setting, camera move,
  lighting, style). No on-screen text inside the prompt. Fill it for every scene.
- stock_search: 2-4 word search for a stock footage site. Fill it for every scene.
- overlay_text: short on-screen text (max ~6 words) or "" if the shot should be clean.
- camera_and_edit_notes / transition / sfx_and_music: concrete instructions a human editor
  can follow (zoom-ins, speed ramps, J-cuts, whooshes, music hits).
- fact_check_note: use the research; note anything the editor must verify or "".

<research>
{research}
</research>

<timed_voiceover>
{segments}
</timed_voiceover>"""


def direct(client: anthropic.Anthropic, segments: list[Segment], research: str,
           duration: float, fmt: str) -> VideoPlan:
    prompt = DIRECTOR_PROMPT.format(
        style=STYLE[fmt],
        duration=duration,
        research=research or "(no research)",
        segments="\n".join(f"[{s.start:.2f}-{s.end:.2f}] {s.text}" for s in segments),
    )
    with client.beta.messages.stream(
        model=MODEL,
        max_tokens=64000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        betas=[FALLBACK_BETA],
        fallbacks="default",
        output_format=VideoPlan,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        message = stream.get_final_message()

    if message.stop_reason == "refusal":
        raise RuntimeError("Director request was declined by the model.")
    if message.stop_reason == "max_tokens" or message.parsed_output is None:
        raise RuntimeError("Director plan was cut off. Try splitting the script into parts.")
    return fix_timeline(message.parsed_output, duration)


def offline_plan(segments: list[Segment], duration: float) -> VideoPlan:
    """Plan without AI (for testing the edit pipeline): one text card per segment."""
    scenes = [
        Scene(number=i + 1, start=s.start, end=s.end, narration=s.text,
              visual_source="text_card", ai_video_prompt="", stock_search="",
              overlay_text=" ".join(s.text.split()[:6]), overlay_position="center",
              camera_and_edit_notes="", transition="cut", sfx_and_music="", fact_check_note="")
        for i, s in enumerate(segments)
    ]
    plan = VideoPlan(title_ideas=[], thumbnail_prompt="", music_mood="", hook_notes="", scenes=scenes)
    return fix_timeline(plan, duration)


def fix_timeline(plan: VideoPlan, duration: float) -> VideoPlan:
    """Make scenes contiguous and exactly cover the audio, whatever the model returned."""
    scenes = sorted((s for s in plan.scenes if s.end > s.start), key=lambda s: s.start)
    if not scenes:
        raise RuntimeError("Plan has no scenes.")
    scenes[0].start = 0.0
    for prev, nxt in zip(scenes, scenes[1:]):
        prev.end = nxt.start
    scenes[-1].end = duration
    plan.scenes = [s for s in scenes if s.end - s.start >= 0.3]
    for i, s in enumerate(plan.scenes, 1):
        s.number = i
    # Re-stitch in case a too-short scene was dropped
    for prev, nxt in zip(plan.scenes, plan.scenes[1:]):
        prev.end = nxt.start
    plan.scenes[0].start, plan.scenes[-1].end = 0.0, duration
    return plan


def save(plan: VideoPlan, path: str) -> None:
    with open(path, "w") as f:
        json.dump(plan.model_dump(), f, indent=2)


def load(path: str) -> VideoPlan:
    with open(path) as f:
        return VideoPlan.model_validate(json.load(f))
