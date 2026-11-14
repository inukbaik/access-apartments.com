"""Ask the listing screener a question. An LLM agent plans the tool calls; our checks give the
verdicts; if the LLM is unavailable you still get the measurement-based ranking. Run from the repo root:
  .venv/bin/python -m finder.ask --lat 34.0242 --lon -118.2991 --radius-km 1.5 --limit 10 \\
      "I use a power wheelchair and need a roll-in shower"
"""
import argparse
import os

from finder.agent import answer
from finder.llm import DEFAULT_BASE_URL, DEFAULT_MODEL, OpenAICompatBackend


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("request", help="what the user needs, in plain words")
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--radius-km", type=float, default=2)
    ap.add_argument("--limit", type=int, default=15)
    ap.add_argument("--refresh", action="store_true", help="ignore the cache and re-fetch")
    ap.add_argument("--out-dir", default="out/finder")
    ap.add_argument("--base-url", default=os.environ.get("FINDER_LLM_BASE_URL", DEFAULT_BASE_URL))
    ap.add_argument("--model", default=os.environ.get("FINDER_LLM_MODEL", DEFAULT_MODEL))
    ap.add_argument("--api-key-env", default="FINDER_LLM_API_KEY",
                    help="name of the environment variable holding the API key (default FINDER_LLM_API_KEY)")
    ap.add_argument("--no-llm", action="store_true", help="skip the agent: measurement-based results only")
    ap.add_argument("--max-steps", type=int, default=12)
    ap.add_argument("--time-budget", type=float, default=120, help="seconds for the whole agent run")
    ap.add_argument("--call-timeout", type=float, default=45, help="seconds per LLM call")
    args = ap.parse_args()

    backend = None
    if not args.no_llm:
        backend = OpenAICompatBackend(args.base_url, args.model, os.environ.get(args.api_key_env, ""),
                                      args.call_timeout)
    answer(args.request, args.lat, args.lon, args.radius_km, args.limit, backend, args.refresh,
           args.max_steps, args.time_budget, args.call_timeout, args.out_dir)


if __name__ == "__main__":
    main()
