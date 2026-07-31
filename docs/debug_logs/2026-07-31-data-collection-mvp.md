# Data Collection MVP State

- Goal: deterministic asset -> Scene Program -> Blender -> MP4/GLB/GT dataset pipeline.
- Current evidence: Blender 4.5.12 headless EEVEE smoke passed on the KML development machine.
- Data placement: `/m2v_intern/xuboshen/zgw/Video2Scene`; code checkout remains under `/home`.
- Source: Quaternius Ultimate Platformer Pack, official Google Drive folder, CC0.
- Latest failure fingerprint: Level 1 QC rejected all attempts because the normalized GLB
  dropped the canonical translation stored on an outer Empty (`bbox_min_z=-0.2985`).
- Current fix: bake canonical translation into top-level imported nodes and rebuild with
  `assets normalize --force`; attempt directories now include the generator commit prefix so
  old Level 1 attempt results remain available but do not block a fixed-code replay.
- Follow-up evidence: `Character.gltf` contains an unrelated top-level `Icosphere` at Z=-1.
  Rig normalization now retains only armature ancestors/descendants and drops source helpers.
- `Icosphere` was also referenced by 29 pose-bone custom shapes, causing the exporter to restore
  it as a dependency. Normalization clears editor-only custom-shape links before removal.
- Blender 4.5 still restores that helper through the imported glTF rig extension after orphan
  cleanup. MVP manifest policy now excludes `Character/**`; 108 static glTF assets remain.
- Constraints: do not version Demo, raw assets, normalized assets, previews, or generated samples.
- Next: implement asset normalization; implement deterministic sampler/compiler; run local unit checks; validate Levels 1-3 on KML.
