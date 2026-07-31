# Data Collection MVP State

- Goal: deterministic asset -> Scene Program -> Blender -> MP4/GLB/GT dataset pipeline.
- Current evidence: Blender 4.5.12 headless EEVEE smoke passed on the KML development machine.
- Data placement: `/m2v_intern/xuboshen/zgw/Video2Scene`; code checkout remains under `/home`.
- Source: Quaternius Ultimate Platformer Pack, official Google Drive folder, CC0.
- Current failure: none; implementation is in progress.
- Constraints: do not version Demo, raw assets, normalized assets, previews, or generated samples.
- Next: implement asset normalization; implement deterministic sampler/compiler; run local unit checks; validate Levels 1-3 on KML.
