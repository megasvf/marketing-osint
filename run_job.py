"""Headless runner: one command builds a company report with no human in the loop.

  python run_job.py example.com --brand Example --category "form builder" \
      [--alt "Old Name"] [--competitor "Rival" ...] [--comparator rival.com] [--relationship benchmark] \
      [--no-ahrefs] [--skip-collect] [--dry-run]

Steps (each logs to data/<domain>/_logs/; a failed step stops the run with its log path):
  1. script collectors (run_collectors.py, then ai_visibility.py with the competitors)
  2. agent collectors via `claude -p`: outside-in layer + ad libraries; Ahrefs + SEO + affiliates (unless --no-ahrefs)
  3. synthesis (prompts/synthesis.md + dossier keys)
  4. gate loop: factcheck.py --add-evidence --fix-quotes, then factcheck.py; a fix agent gets the issue list (max 3 rounds)
  5. LLM fact-check from factcheck.py --targets, then an edit agent applies every WRONG; the gate runs again
  6. build.py, monitor.py

Agents run with `claude -p`; each step's total_cost_usd goes to the run ledger (costs.py) as "Claude agents".
Ahrefs: a headless agent sees only MCP servers given to the CLI (--mcp-config in OSINT_CLAUDE_FLAGS); a claude.ai connector
is not visible there, so use --no-ahrefs or configure an Ahrefs MCP server with an API key. Models: env OSINT_MODEL_COLLECT (default sonnet), OSINT_MODEL_SYNTH (default opus),
OSINT_MODEL_CHECK (default sonnet). Permission flags: env OSINT_CLAUDE_FLAGS (default below). Run it in a sandbox
(container or VM): the agents read the web and write files in this repo.
"""
import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable
DEFAULT_FLAGS = ("--permission-mode acceptEdits --allowedTools Bash Read Write Edit Glob Grep WebSearch WebFetch "
                 "mcp__Ahrefs --output-format json")
MODELS = {"collect": os.environ.get("OSINT_MODEL_COLLECT", "sonnet"),
          "synth": os.environ.get("OSINT_MODEL_SYNTH", "opus"),
          "check": os.environ.get("OSINT_MODEL_CHECK", "sonnet")}
RULES = ("Run everything from the repo root. Read schema.json first: every collector file follows that contract. "
         "Public data only: no logins, no sign-ups, no form submissions, no CAPTCHA or bot-protection bypass. People by role. "
         "Never invent values, URLs, dates or quotes; quotes are verbatim page text of at most 25 words; no em dashes. "
         "A page you could not open is never cited. Write any script longer than a few lines to a file before running it. "
         "Touch only the files your task names. Your final message is the deliverable.")


class Job:
    def __init__(self, a):
        self.a, self.d = a, a.domain
        self.logs = ROOT / "data" / a.domain / "_logs"
        self.flags = shlex.split(os.environ.get("OSINT_CLAUDE_FLAGS", DEFAULT_FLAGS))

    def sh(self, name, cmd, timeout=3600):
        print(f"[{time.strftime('%H:%M:%S')}] {name}: {' '.join(cmd)[:160]}")
        if self.a.dry_run:
            return 0, ""
        self.logs.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
        (self.logs / f"{name}.log").write_text(r.stdout + "\n--- stderr ---\n" + r.stderr, encoding="utf-8")
        return r.returncode, r.stdout

    def agent(self, name, model, prompt, timeout=5400):
        code, out = self.sh(name, ["claude", "-p", prompt, "--model", MODELS[model], *self.flags], timeout)
        try:
            res = json.loads(out) if out.strip() else {}
        except ValueError:
            res = {"result": out}
        if code or res.get("is_error"):
            sys.exit(f"step {name} failed; see {self.logs / (name + '.log')}")
        usd = res.get("total_cost_usd")
        if usd and not self.a.dry_run:
            import costs
            costs.record(self.d, "Claude agents", round(float(usd), 4), "USD",
                         f"{name} ({MODELS[model]}, {res.get('num_turns', '?')} turns, {round((res.get('duration_ms') or 0) / 60000)} min)",
                         billing="pay per use")
        return res.get("result", "")

    def gate(self):
        self.sh("gate_fix", [PY, "factcheck.py", self.d, "--add-evidence", "--fix-quotes"])
        return self.sh("gate", [PY, "factcheck.py", self.d])

    # ---------------------------------------------------------------- steps
    def collect_scripts(self):
        alts = [x for v in self.a.alt for x in ("--alt", v)]
        comps = [x for v in self.a.competitor for x in ("--competitor", v)]
        self.sh("collect_scripts", [PY, "run_collectors.py", self.d, "--brand", self.a.brand, "--category", self.a.category, "--no-ai", *alts])
        self.sh("collect_ai", [PY, "collectors/ai_visibility.py", self.d, "--brand", self.a.brand, "--category", self.a.category,
                               *alts, *comps, "--retry-failed"])

    def collect_agents(self):
        d, a = self.d, self.a
        aliases = ", ".join(a.alt) or "none"
        outside = (f"{RULES}\nCompany {a.brand}, domain {d}, aliases {aliases}. Run prompts/collect_outside.md, then the review-site part "
                   f"of prompts/ad_libraries.md and the ad libraries with a headless browser if one is available (Playwright via Node is "
                   f"preinstalled in many sandboxes); a library that needs login or shows a challenge is recorded as blocked. Outputs: "
                   f"data/{d}/earned.json, marketplaces.json, email_archive.json, corporate.json, ad_libraries.json.")
        jobs = [("agent_outside", outside)]
        if not a.no_ahrefs:
            seo = (f"{RULES}\nCompany {a.brand}, domain {d}, siblings none, aliases {aliases}, category \"{a.category}\", comparator "
                   f"{a.comparator or 'the main organic competitor'}. Run prompts/collect_ahrefs.md, prompts/collect_seo.md and "
                   f"prompts/collect_affiliate_media.md in that order. Load Ahrefs tools with ToolSearch; call doc before a tool's first use. "
                   f"Sum units-cost-total-actual from each response and log it with costs.py per prompt file; stop at 35k units. "
                   f"Ahrefs keyword buckets 11+ can collapse from late 2025 (index change): sum only buckets you trust and say so.")
            jobs.append(("agent_seo", seo))
        if a.dry_run:
            for name, p in jobs:
                self.agent(name, "collect", p)
            return
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as ex:
            list(ex.map(lambda np: self.agent(np[0], "collect", np[1]), jobs))

    def synthesize(self):
        d, a = self.d, self.a
        self.agent("synthesis", "synth", (
            f"{RULES}\nCompany {a.brand}, domain {d}, category \"{a.category}\", compiled {time.strftime('%Y-%m-%d')}. "
            f"Relationships: [\"{a.relationship}\"]. Read prompts/synthesis.md and prompts/dossier_enrich.md fully and every collector file "
            f"in data/{d}/ (skip files starting with _ except _ai_raw.json). Write data/{d}/analysis.json in one pass with every section "
            f"of synthesis.md plus the dossier keys. Partial or unavailable sources go into gaps with their note as the reason. "
            f"Then run `python factcheck.py {d} --add-evidence --fix-quotes` and `python factcheck.py {d}` until it prints 0 issues, "
            f"and `python build.py {d}` until lint ok. Fix the analysis, never code."))

    def gate_loop(self):
        for i in range(3):
            code, out = self.gate()
            if code == 0 or self.a.dry_run:
                return
            self.agent(f"gate_round_{i + 1}", "synth", (
                f"{RULES}\nThe deterministic gate failed for data/{self.d}/analysis.json. Issues:\n{out[-6000:]}\n"
                f"Fix the analysis with targeted load-edit-dump (never the gate or code) until `python factcheck.py {self.d}` prints 0 issues."))
        sys.exit(f"gate still failing after 3 rounds; see {self.logs}")

    def factcheck(self):
        d = self.d
        self.sh("targets", [PY, "factcheck.py", d, "--targets"])
        report = self.agent("factcheck", "check", (
            f"{RULES}\nYou are the independent fact-checker. Follow prompts/factcheck.md exactly for data/{d}/analysis.json, starting from "
            f"data/{d}/_factcheck_targets.json. Do not edit files. Give copy-pasteable corrections, and for a fix that needs new evidence "
            f"the exact URL and verbatim quote you saw."))
        if not self.a.dry_run:
            (self.logs / "factcheck_report.md").write_text(report, encoding="utf-8")
        self.agent("factcheck_apply", "synth", (
            f"{RULES}\nApply this independent fact-check to data/{d}/analysis.json with targeted load-edit-dump. New evidence must be "
            f"fetched by you and appended as one item per page to the right collector file in data/{d}/ (meta added_by factcheck-fix) "
            f"before the analysis cites it; if you cannot open a page, use the cautious wording. Then gate (0 issues) and build (lint ok).\n\n"
            f"FACT-CHECK REPORT:\n{report[:30000]}"))
        self.gate_loop()

    def build(self):
        code, _ = self.sh("build", [PY, "build.py", self.d])
        if code and not self.a.dry_run:
            sys.exit(f"build failed; see {self.logs / 'build.log'}")
        self.sh("monitor", [PY, "monitor.py", self.d])
        self.sh("costs", [PY, "costs.py", self.d, "--show"])


def main():
    ap = argparse.ArgumentParser(description="Build one company report end to end, headless.")
    ap.add_argument("domain")
    ap.add_argument("--brand", required=True)
    ap.add_argument("--category", required=True)
    ap.add_argument("--alt", action="append", default=[])
    ap.add_argument("--competitor", action="append", default=[])
    ap.add_argument("--comparator", default="")
    ap.add_argument("--relationship", default="benchmark", choices=["competitor", "benchmark", "prospect", "partner", "self"])
    ap.add_argument("--no-ahrefs", action="store_true")
    ap.add_argument("--skip-collect", action="store_true", help="reuse data/<domain>/ collector files")
    ap.add_argument("--dry-run", action="store_true", help="print the steps and commands, run nothing")
    a = ap.parse_args()
    j = Job(a)
    t0 = time.time()
    if not a.skip_collect:
        j.collect_scripts()
        j.collect_agents()
    j.synthesize()
    j.gate_loop()
    j.factcheck()
    j.build()
    print(f"done in {(time.time() - t0) / 60:.0f} min: output/{a.domain}/index.html")


if __name__ == "__main__":
    main()
