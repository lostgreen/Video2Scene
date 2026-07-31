# Data Collection MVP State

- Goal: deterministic asset -> Scene Program -> Blender -> MP4/GLB/GT dataset pipeline.
- Current evidence: Blender 4.5.12 headless EEVEE smoke passed on the KML development machine.
- Data placement: `/m2v_intern/xuboshen/zgw/Video2Scene`; code checkout remains under `/home`.
- Source: Quaternius Ultimate Platformer Pack, official Google Drive folder, CC0.
- Current result: Level 1 passed (1/1), Level 2 passed (4/4, one per template), and a
  512x512/24fps/72-frame production probe passed QC.
- Current source state: 30 eligible rigid glTF assets are indexed and normalized; six previews
  and a contact sheet are generated for each. Acquisition inventory/report are materialized.
- Current blocker: `/m2v_intern/xuboshen/zgw/Video2Scene` returns `Disk quota exceeded` on file
  writes. Final `.env.local` points there, but validation artifacts temporarily live under
  `/home/xuboshen/zgw/video2scene_integration_data`.
- Stale evidence: the first Character-based Level 1 attempts failed with
  `bbox_min_z=-0.2985`; they predate the rigid-only manifest policy and should not be reused.
- Decisions: exclude `Character/**` from the rigid MVP; acquire 30 eligible glTF assets plus
  support/license files; resume partial downloads with a 120-second per-file deadline.
- Constraints: do not version Demo, raw assets, normalized assets, previews, or generated samples.
- Latest checks: local Ruff/mypy/14 pytest pass; KML 14 pytest pass; dataset contract validators
  pass for Level 1 and Level 2.
- Next: restore write quota on `/m2v_intern`, run `make assets`, then `make dataset-mvp` and
  `make dataset-check` in the configured final data root.
