#!/usr/bin/env python3
"""Put the Fillmore section into the jobs hub ("GSX Deck Files", https://claude.ai/artifact/J81Bm9MuruFvPFDfcHhV2a) with the
published links and the prices the proposal prints — Prentice's hub_merge.py, for a job with options.

    python3 hub_merge_fillmore.py                 # strict: every {{KEY}} filled and every linked PDF delivered, else nothing is written
    python3 hub_merge_fillmore.py --preview       # fill what is there: a missing link -> "#", a missing number -> "—"; lists the gaps
    options: --urls=FILE (publish/urls.json) --prices=FILE (publish/prices.json, from build_fillmore.py prices)
             --manifest=FILE (publish/manifest.json, from build_fillmore.py deliver: which PDF each docs/... link is)
             --hub=FILE (the live hub page; default publish/hub_live/index.html, else $S/hub3/index_new.html)
             --section=FILE (publish/fillmore_section.html) --out=FILE (publish/hub_index_new.html) --date="October 28, 2026"

Writes hub_index_new.html (the hub with the section at the top, or replacing the previous Fillmore section between its
<!-- fillmore:start --> / <!-- fillmore:end --> markers; "current as of" moved to the date) and hub_files.json
({"docs/fillmore-*.pdf": the delivered PDF}). Publish: Artifact url=<the hub>, file_path=hub_index_new.html, files=hub_files.json
(the hub's other docs/ files stay as they are). Rows marked data-optional="1" drop out quietly when their link or PDF is missing."""
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

S = Path("/tmp/claude-0/-home-user-Decks-/3110cd41-980c-5ceb-b230-1490acc026a8/scratchpad")
PUB = S / "fillmore" / "publish"
HUB_URL = "https://claude.ai/artifact/J81Bm9MuruFvPFDfcHhV2a"
KEY_RE = re.compile(r"\{\{[A-Z0-9_]+\}\}")
START, END = "<!-- fillmore:start -->", "<!-- fillmore:end -->"


def jload(p, default=None):
    try:
        return json.load(open(p))
    except Exception:
        return default


def main(argv):
    o = {a[2:].split("=", 1)[0]: (a.split("=", 1)[1] if "=" in a else True) for a in argv if a.startswith("--")}
    if "help" in o:
        print(__doc__); return 0
    preview = bool(o.get("preview"))
    urls_p = Path(o.get("urls", PUB / "urls.json"))
    prices_p = Path(o.get("prices", PUB / "prices.json"))
    man_p = Path(o.get("manifest", PUB / "manifest.json"))
    hub_p = Path(o.get("hub", PUB / "hub_live" / "index.html"))
    if not hub_p.exists():
        hub_p = S / "hub3" / "index_new.html"
    sec_p = Path(o.get("section", PUB / "fillmore_section.html"))
    out_p = Path(o.get("out", PUB / "hub_index_new.html"))
    d = datetime.strptime(o["date"], "%B %d, %Y").date() if isinstance(o.get("date"), str) else date.today()

    urls = {k: v for k, v in (jload(urls_p, {}) or {}).items() if isinstance(v, str) and v.startswith("http")}
    prices = jload(prices_p, {}) or {}
    man = jload(man_p, {}) or {}
    vals = dict(prices.get("hub") or {})
    vals.update({"{{" + k + "}}": v for k, v in urls.items()})
    vals["{{PILL_DATE}}"] = f"{d:%b} {d.day}"
    pdf_of = {x.get("hub_doc"): x.get("pdf") for x in (man.get("documents") or []) if x.get("hub_doc")}
    problems, dropped = [], []
    if not prices:
        problems.append(f"no prices: run build_fillmore.py prices ({prices_p})")
    if prices.get("draft"):
        problems.append("prices.json was built from the DRAFT spec")
    if prices.get("estimates"):
        print("note: ESTIMATE in the prices (owner has not set it): " + "; ".join(prices["estimates"]))

    sec = sec_p.read_text()

    def fix_row(m):
        row = m.group(0)
        keys = set(KEY_RE.findall(row))
        miss = sorted(k for k in keys if k not in vals)
        docs = re.findall(r'href="(docs/[^"]+)"', row)
        nopdf = [x for x in docs if not (pdf_of.get(x) and Path(pdf_of[x]).exists())]
        if 'data-optional="1"' in row and (miss or nopdf):
            dropped.append(re.sub(r"<[^>]+>", " ", row).split("·")[0].strip()[:60])
            return ""
        for x in nopdf:
            problems.append(f"no delivered PDF for {x} (run build_fillmore.py deliver)")
            if preview:
                row = re.sub(r'<a href="' + re.escape(x) + r'" class="pdf">PDF</a>\s?', "", row)
        return row

    sec = re.sub(r"<tr\b[^>]*>.*?</tr>", fix_row, sec, flags=re.S)
    sec = sec.replace(' data-optional="1"', "")
    for k in sorted(set(KEY_RE.findall(sec))):
        if k in vals:
            sec = sec.replace(k, vals[k])
        else:
            problems.append(f"no value for {k}" + (" (urls.json)" if k.startswith("{{URL_") else " (prices.json — run build_fillmore.py prices)"))
            if preview:
                sec = sec.replace(k, "#" if k.startswith("{{URL_") else "—")
    problems = list(dict.fromkeys(problems))
    if problems and not preview:
        print("NOT WRITTEN — fill these first (or run with --preview):")
        for p in problems:
            print("  -", p)
        return 1

    h = hub_p.read_text()
    if START in h and END in h:
        h = h[:h.index(START)] + sec.strip() + h[h.index(END) + len(END):]
        how = "replaced the previous Fillmore section"
    else:
        assert "7303 S Fillmore" not in h, "the hub has a Fillmore section without the markers: merge by hand"
        i = h.index('<section class="job">')
        h = h[:i] + sec.strip() + "\n\n" + h[i:]
        how = "inserted at the top"
    h = re.sub(r"current as of [A-Z][a-z]+ \d{1,2}, \d{4}", f"current as of {d:%B} {d.day}, {d.year}", h)
    out_p.write_text(h)
    files = {x: pdf_of[x] for x in sorted(set(re.findall(r'href="(docs/fillmore[^"]+)"', sec))) if pdf_of.get(x) and Path(pdf_of[x]).exists()}
    json.dump(files, open(PUB / "hub_files.json", "w"), indent=1)
    left = KEY_RE.findall(sec)
    print(f"{'PREVIEW ' if preview else ''}ok: {out_p} ({len(h):,} bytes; {how}; base hub {hub_p})")
    print(f"hub_files.json: {len(files)} PDFs ({sum(Path(v).stat().st_size for v in files.values()) / 1e6:.1f} MB)")
    if dropped:
        print("optional rows left out:", "; ".join(dropped))
    if problems:
        print("gaps (preview only):")
        for p in problems:
            print("  -", p)
    if left:
        print("unfilled:", left)
    print(f"publish: Artifact url={HUB_URL} file_path={out_p} files=<hub_files.json> (read the hub first: action read, url)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
