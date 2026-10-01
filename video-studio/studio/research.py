"""Step 2: AI researcher. Claude searches the web to fact-check the script and find visual ideas."""
import anthropic

MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"

RESEARCH_PROMPT = """You are the research assistant for a YouTube channel.
Below is the script of an upcoming video. Use web search to:

1. Fact-check every claim. Flag anything wrong or outdated and give the correct version.
2. Find 3-6 extra facts, numbers or stories that would make the video stronger.
3. List what the viewer should SEE for each key topic (real places, objects, people,
   historical footage, maps, charts) so an editor can pick accurate visuals.
4. List the sources you used (title + URL).

Write plain Markdown with these headings: Fact check, Extra facts, Visual references, Sources.

<script>
{script}
</script>"""


def research(client: anthropic.Anthropic, script: str) -> str:
    messages = [{"role": "user", "content": RESEARCH_PROMPT.format(script=script)}]
    for _ in range(5):  # web search can pause long turns; resume up to a few times
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
            betas=[FALLBACK_BETA],
            fallbacks="default",
            tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 8}],
            messages=messages,
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("Research request was declined by the model.")
        if response.stop_reason != "pause_turn":
            break
        messages.append({"role": "assistant", "content": response.content})

    return "".join(b.text for b in response.content if b.type == "text").strip()
