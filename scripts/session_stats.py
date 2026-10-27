"""Token use and activity of one Claude Code session, from its log (~/.claude/projects/<dir>/<session-id>.jsonl).
usage: session_stats.py <session-id prefix | path.jsonl>"""
import collections, datetime as dt, glob, json, os, re, sys

arg = sys.argv[1]
path = arg if arg.endswith(".jsonl") else (glob.glob(os.path.expanduser(f"~/.claude/projects/*/{arg}*.jsonl")) or [None])[0]
if not path:
    sys.exit(f"no session log matching {arg}")
rows = [json.loads(line) for line in open(path) if line.strip()]
times = [dt.datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00")) for r in rows if r.get("timestamp")]
usage, seen, steps = collections.Counter(), set(), 0
tools, lp, failed = collections.Counter(), collections.Counter(), set()
for r in rows:
    m = r.get("message") or {}
    if r.get("type") == "assistant" and m.get("id") not in seen:  # one API response is logged once per content block
        seen.add(m.get("id"))
        steps += 1
        usage.update({k: v for k, v in (m.get("usage") or {}).items() if isinstance(v, int)})
    for b in m.get("content") if isinstance(m.get("content"), list) else []:
        if b.get("type") == "tool_use" and r.get("type") == "assistant":
            tools[b["name"]] += 1
            lp.update(re.findall(r"lp\.py (\w+)", (b.get("input") or {}).get("command", "")))
        if b.get("type") == "tool_result" and b.get("is_error"):
            failed.add(b["tool_use_id"])
ctx = (usage["cache_read_input_tokens"] + usage["cache_creation_input_tokens"] + usage["input_tokens"]) / max(steps, 1)
print(f"{os.path.basename(path)}\nwall time   {times[-1] - times[0]}\nsteps       {steps} model responses, "
      f"avg context {ctx / 1000:.0f}k tokens\noutput      {usage['output_tokens']:,} tokens\ninput       "
      f"{usage['input_tokens']:,} new, {usage['cache_creation_input_tokens']:,} cache write, "
      f"{usage['cache_read_input_tokens']:,} cache read\ntools       {dict(tools.most_common())}\nlp.py       {dict(lp)}\n"
      f"tool errors {len(failed)}")
