"""AI Video Studio: script + voiceover in, researched and edited YouTube video parts out.

    python make_video.py SCRIPT.txt VOICE.mp3 --format long
    python make_video.py SCRIPT.txt VOICE.mp3 --format short
"""
import argparse
import os
import sys

from dotenv import load_dotenv

from studio import director, editor, research, transcribe, visuals


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("script", help="Script text file")
    p.add_argument("audio", help="Voiceover audio (mp3/wav/m4a)")
    p.add_argument("--format", choices=["long", "short"], default="long", help="long = 16:9, short = 9:16")
    p.add_argument("--out", default="output", help="Output folder")
    p.add_argument("--plan", help="Re-render from an existing (edited) plan.json; skips research and directing")
    p.add_argument("--no-research", action="store_true", help="Skip web research")
    p.add_argument("--no-ai", action="store_true", help="No API calls: text-card plan, to test the pipeline")
    p.add_argument("--no-whisper", action="store_true", help="Estimate timing from the script instead of Whisper")
    p.add_argument("--whisper-model", default="small", help="tiny/base/small/medium/large-v3")
    args = p.parse_args()

    load_dotenv()
    for path in (args.script, args.audio):
        if not os.path.exists(path):
            sys.exit(f"File not found: {path}")
    if not args.no_ai and not args.plan and not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is missing. Put it in .env (see .env.example), or use --no-ai to test.")

    script = open(args.script, encoding="utf-8").read()
    out = args.out
    parts_dir, clips_dir = os.path.join(out, "parts"), os.path.join(out, "clips")
    os.makedirs(parts_dir, exist_ok=True)
    os.makedirs(clips_dir, exist_ok=True)

    print("1/5  Reading audio timing...")
    duration = transcribe.audio_duration(args.audio)
    if args.no_whisper:
        segments = transcribe.estimate_from_script(script, duration)
    else:
        segments = transcribe.transcribe(args.audio, args.whisper_model)
    transcribe.save(segments, os.path.join(out, "transcript.json"))
    editor.write_srt(segments, os.path.join(out, "captions.srt"))
    print(f"     {duration:.1f}s of audio, {len(segments)} lines")

    if args.plan:
        print("2/5  Research skipped (using existing plan)")
        print("3/5  Loading plan...")
        plan = director.fix_timeline(director.load(args.plan), duration)
    elif args.no_ai:
        print("2/5  Research skipped (--no-ai)")
        print("3/5  Making a simple text-card plan (--no-ai)...")
        plan = director.offline_plan(segments, duration)
    else:
        import anthropic
        client = anthropic.Anthropic()
        notes = ""
        if args.no_research:
            print("2/5  Research skipped (--no-research)")
        else:
            print("2/5  AI researcher is fact-checking the script on the web...")
            notes = research.research(client, script)
            with open(os.path.join(out, "research.md"), "w") as f:
                f.write(notes)
        print("3/5  AI director is planning scenes...")
        plan = director.direct(client, segments, notes, duration, args.format)
    director.save(plan, os.path.join(out, "plan.json"))
    print(f"     {len(plan.scenes)} scenes")

    print("4/5  Getting visuals and editing parts...")
    width, height = editor.SIZES[args.format]
    sources, parts = {}, []
    for scene in plan.scenes:
        clip, sources[scene.number] = visuals.get_clip(scene, clips_dir, args.format, width, height)
        part = os.path.join(parts_dir, f"part_{scene.number:03d}.mp4")
        editor.render_scene(scene, clip, args.audio, part, args.format)
        parts.append(part)
        print(f"     part {scene.number:03d}  {scene.end - scene.start:5.1f}s  [{sources[scene.number]}]")

    print("5/5  Building rough cut and edit plan...")
    editor.rough_cut(parts, args.audio, os.path.join(out, "rough_cut.mp4"))
    editor.write_edit_plan(plan, sources, args.format, os.path.join(out, "edit_plan.md"))

    print(f"\nDone. Send the '{out}/' folder to your editor:")
    print("  parts/          one MP4 per scene (voiceover + visual + overlay)")
    print("  rough_cut.mp4   all parts joined, for a quick watch")
    print("  edit_plan.md    director notes per part (prompts, cuts, SFX, fact checks)")
    print("  captions.srt    subtitles for YouTube")
    print("  plan.json       edit it and re-run with --plan to change scenes")


if __name__ == "__main__":
    main()
