# GSX deck packages — latest versions

One place for every job document. Each folder is the built page with its renders (open `index.html`); the live copies
are the links. The hub page that lists all of them is `hub.html` here and https://claude.ai/artifact/J81Bm9MuruFvPFDfcHhV2a live.
Current as of September 17, 2026. Prices are cash / financed / monthly.

| Job | Package | Folder | Live | Cash | Financed | Monthly |
|---|---|---|---|---|---|---|
| Glengarry Pl, Castle Rock | 1 · Fulton rail · existing columns and caissons | `glengarry-1-fulton-existing/` | [V6](https://claude.ai/artifact/9MKSuUHXTxWqYcCtVLsT2E) | $127,893 | $137,519 | $1,596 |
| | 2 · Fulton rail · new caissons and 8x8 DF posts | `glengarry-2-fulton-new/` | [V6](https://claude.ai/artifact/X3cCKDXYSK6zos4kSP8zCx) | $139,327 | $149,814 | $1,739 |
| | 3 · stucco parapet stays · existing columns and caissons | `glengarry-3-parapet-existing/` | [V5](https://claude.ai/artifact/8Rd9mqBfq4aaujNvE9JW2c) | $118,896 | $127,845 | $1,484 |
| | 4 · stucco parapet stays · new caissons and 8x8 DF posts | `glengarry-4-parapet-new/` | [V5](https://claude.ai/artifact/V7vb6joT4ESHyZXLAv7ZeW) | $130,330 | $140,140 | $1,626 |
| | Lower deck · 2'4" in the alcove · parapet walls, no rail | `glengarry-lower/` | [V2](https://claude.ai/artifact/PNtja4QkwJMeAaj8tRC32J) | $37,866 | $40,716 | $473 |
| Center Ave, Lakewood (Alan) | 12 x 20 deck with landing and stair — proposal + PDF | `center-ave-proposal/` | [V6](https://claude.ai/artifact/CcGknredfUyG8ZHCuiQuDV) | $59,790 | $63,975 | $742 |
| Summit Point Ct | Main deck + porch cover + the 10 x 10, permit package | `summit-point-package/` | [V15](https://claude.ai/artifact/4SzpniuvUQKA6JjHkLQX27) | $133,429 | $143,472 | $1,665 |
| Eagle's Nest, Silverthorne | Takeoff + build set (the template) | `eagles-nest/` | [V1](https://claude.ai/artifact/3L81czJeCf3UBor7LWfPF9) | $122,615 | $131,844 | $1,530 |

The September 13 page https://claude.ai/artifact/LWbS2wTYKKY7x57pRZUfw4 is Eagle's Nest in the earlier layout, kept for reference.

## Open items

- Glengarry stair rise: 13 risers reach 8'4"; the deck is 12' and the lower level was drawn at 2'4" (9'8" between). The pages run 7 + 6 as drawn.
- Glengarry 3 and 4 put Fulton rail on the new stair and landings; if the stucco stair parapet stays, it comes out.
- County records tag the Glengarry lot 164 Glengarry Place; the pages carry 166 as given.
- Glengarry lower deck footings: Diamond Piers as priced, or the existing caissons.

## Rebuilding a package

```
python -m decktakeoff jobs/glengarry_2_fulton_new.json --page internal --key gl2 --out out/gl2
```

Then copy `out/<key>/page.html` to the folder as `index.html` and the renders it lists in `files.json` to `r/`.
