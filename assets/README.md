# Asset Data Contract

Only source manifests and documentation are tracked in Git. Materialized asset data lives
under `SMCB_ASSET_ROOT`:

```text
assets/
  raw/quaternius_platformer/     # untouched upstream files
  normalized/                    # one canonical GLB + JSON per asset
  previews/                      # six PNG views + contact sheets
  manifests/                     # tracked source declarations (repository copy)
```

The KML development-machine deployment uses
`/m2v_intern/xuboshen/zgw/Video2Scene/assets`. The code checkout stays at
`/home/xuboshen/zgw/Video2Scene`.

Raw files are never edited in place. `source_inventory.json` records a deterministic hash of
the downloaded file tree, and `normalized/index.json` is the compiler-facing asset index.
