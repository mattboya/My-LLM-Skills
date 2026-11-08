---
name: rtx3090-image-to-3d
description: Generate game-ready 3D assets (FBX/GLB with LODs, UCX_ collision, base-colour + normal textures) from a concept image using the local RTX 3090 pipeline at F:\Code\ai-3d-pipeline. Use when the user asks to create, generate or "make a 3D model / prop / mesh / game asset" from an image, sprite or concept art, or wants to batch-produce props for a game project.
---

# Local 3D asset pipeline (Hunyuan3D-2 on the RTX 3090 + headless Blender)

Built for, and tested on, one Windows PC with an NVIDIA RTX 3090 (24 GB VRAM). The paths and timings
below are that PC's. The skill only drives the pipeline: the server, client and Blender clean-up are a
separate project that must be installed on the computer that runs the job.

On another computer, two environment variables replace the built-in values (see the repo README):
- `ASSET_PIPELINE_HOME`: the pipeline folder. If it is set, use it in place of `F:\Code\ai-3d-pipeline`
  in every command below. Check it first (`echo $ASSET_PIPELINE_HOME` in bash,
  `$env:ASSET_PIPELINE_HOME` in PowerShell).
- `ASSET_PIPELINE_URL`: the server address. `asset_client.py` reads it on its own.

Service: `http://127.0.0.1:8000` (FastAPI). Pipeline home: `F:\Code\ai-3d-pipeline`.
Client: `F:\Code\ai-3d-pipeline\integrations\asset_client.py` (stdlib only; run it with any Python 3.8+).

## 1. Check the service
```bash
python F:/Code/ai-3d-pipeline/integrations/asset_client.py health
```
If it is down, start it (takes ~10 s; models load lazily on the first job):
```bash
cmd /c "F:\Code\ai-3d-pipeline\start_server.bat"   # long-running: launch it in the background
```
Only one GPU job runs at a time; extra jobs queue. Do not start a second server.

## 2. Prepare the input image
The image IS the spec, so its quality caps the asset's quality:
- one object, 3/4 view (slightly above), whole object in frame, nothing cropped
- flat, even lighting: no cast shadows, no dramatic rim light (they bake into geometry/texture)
- transparent PNG or a plain background (background is removed automatically)
- 1024 px square or larger
No local text-to-image model is installed. If the user only has a description, ask them for an image
or generate one with a tool they approve.

## 3. Submit and wait
```bash
python F:/Code/ai-3d-pipeline/integrations/asset_client.py build <image.png> <AssetName> \
    --out-dir <absolute path inside this project> --quality standard --tris 3000 --height <metres>
```
- `AssetName`: PascalCase, letters/digits/underscore. Output: `SM_<AssetName>.fbx/.glb`.
- Always pass `--out-dir` as an absolute path inside the current project (e.g. Unity `Assets/Art/Generated`,
  Unreal import folder, Godot `res://` folder on disk).
- Always pass `--height` with a real-world height (crate ~1.0, door ~2.1, barrel ~1.1, chest ~0.9);
  otherwise the asset comes out ~2 m tall.
- Quality presets: `draft` (~1 min, 1.5k tris), `standard` (~2 min, 3k tris, 2 LODs),
  `hero` (~6-10 min, 20k tris, 3 LODs, 2K normal map baked from a 150k-face high-poly).
- Runs take minutes. Run the command in the background; it prints stage/progress lines.

Python alternative (inside a project script):
```python
import sys; sys.path.insert(0, r"F:\Code\ai-3d-pipeline\integrations")
from asset_client import build_asset
job = build_asset("concept.png", "Barrel", out_dir=r"<abs out dir>", target_tris=3000, height=1.1)
```

## 4. Verify before reporting success
```bash
F:/Code/ai-3d-pipeline/venv/Scripts/python.exe F:/Code/ai-3d-pipeline/verify_assets.py <AssetName> <out-dir>
```
It must print `RESULT: PASS`. Report the FBX/GLB paths, triangle counts, and any warning
(e.g. `textured=False`). Look at the result (render or engine import) before calling it final quality.

## 5. Watching a job / the GPU
`F:\Code\ai-3d-pipeline\monitor.bat` (live dashboard) or `... monitor.py --once` (text snapshot):
stage, progress, ETA, VRAM, temperature, power, throttling, stalled-job alerts.
Status of one job: `asset_client.py status <job_id>`; cancel: `asset_client.py cancel <job_id>`.

## Output contract
| File | Use |
|---|---|
| `SM_<Name>.fbx` | LOD0 + `UCX_SM_<Name>[_NN]` convex collider(s); Unreal auto-uses UCX_ as collision |
| `SM_<Name>.glb` | LOD0 with PBR material (base colour, + normal map if baked); Godot/three.js/Unity glTFast |
| `SM_<Name>_LOD1..N.fbx` | each LOD halves the triangles |
| `textures/T_<Name>_BaseColor.png`, `T_<Name>_Normal.png` | 2048 px; metallic 0 / roughness 0.8 defaults |

Engine notes: Unity ignores `UCX_` names; add a MeshCollider (convex) using the UCX mesh, or a
primitive collider. Unreal: import with "Combine Meshes" off; collision is detected from UCX_. Godot:
prefer the GLB.

## Limits to tell the user about
Albedo-only material (no real metal/roughness maps), lighting removed by a de-light model,
triangulated decimated topology (not quad/edge-flow), one UV atlas with AI-inpainted seams, and
back/hidden sides are invented by the model. Great for props, kitbash, blockout and background assets.
Hero assets need an artist pass.
