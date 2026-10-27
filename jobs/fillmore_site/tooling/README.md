# Fillmore publishing tooling (snapshot)

Copies of the session's working scripts, kept here so the documents can be rebuilt if the session's scratch space is lost.
The live copies run from the session scratchpad (`$S/fillmore/...`); paths inside the scripts point there.

- `build_fillmore.py` — every Fillmore document in one command (`--spec-dir=jobs`), see its docstring for the steps.
- `copy_fillmore.json` — the customer copy the build fills with engine facts.
- `hub_merge_fillmore.py` — merges the Fillmore section into the hub page.
- `build_schedule.py` — the schedule model; writes `jobs/fillmore_site/schedule.json` (the specs' `extras.timeline`).
- `build_spec.py` — the interactive 3D page from the specs.
- `render_final.sh`, `cameras.json` — the photoreal (Cycles) set and its camera stations.
- `make_variants.py` — the render variants `render_final.sh` builds from the specs at its start (louver angle, screen drop, the lit yard stairs 2 and 2B).
- `fillmore_section.html` — the hub section template `hub_merge_fillmore.py` fills (prices, links, the color study row).
- `urls.json` — the published links (3D, proposal, roof, internal, cost, Decks & Docks, permit, color study).
- `colorstudy/` — the exterior color study: `palettes.json` (the paints), `make_specs.py` (palette specs from the base spec),
  `render_palettes.py` (three.js stills), `run_photoreal.sh` (the Cycles stills, then `build_colorstudy.py` with the PDF).
