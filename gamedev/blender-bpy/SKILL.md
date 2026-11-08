---
name: blender-bpy
description: High-performance Blender (bpy / bmesh) scripting rules and 3D asset optimization for game pipelines. Use when writing or reviewing Blender Python scripts (bpy, bmesh, headless `blender -b -P`), cleaning or decimating AI-generated meshes (TRELLIS, Hunyuan3D, SF3D .glb), smooth shading in Blender 4.1+, batch-processing assets in one Blender process, preparing concept images for image-to-3D models, or generating UCX_ convex collision hulls.
---

# LLM System Rules: High-Performance Blender (`bpy`) & 3D Asset Optimization

Advanced, non-obvious optimizations for Blender 4.x+ (`bpy`), `bmesh`, and generative 3D conditioning that LLMs typically get wrong by default.

## 1. The Golden Rule of `bpy`: Ban `bpy.ops` in Loops (10x–100x Speedup)

**What LLMs do wrong by default:**
LLMs default to using `bpy.ops.mesh.*` and `bpy.ops.object.*` because they mirror Blender's UI actions. Every single `bpy.ops` call forces Blender to re-evaluate the entire Scene Dependency Graph (`depsgraph`), checking constraints, modifiers, and view layers across the whole scene. Furthermore, `bpy.ops` relies on UI context (`bpy.context.active_object`), which frequently throws `RuntimeError: Operator bpy.ops...poll() failed, context is incorrect` in headless (`-b`) mode.

**The Mandatory Fix (Low-Level Data API & `bmesh`):**

1. **Never use `bpy.ops.transform.*`:** Directly multiply the object's or mesh's transformation matrix in C++ memory using `mesh.transform(matrix)` or `obj.matrix_world`.
2. **Never toggle Edit Mode (`bpy.ops.object.mode_set(mode='EDIT')`) just to edit geometry:** Load the mesh data directly into memory via `bmesh.new()`, run `bm.from_mesh(obj.data)`, perform all operations, and flush back once via `bm.to_mesh(obj.data)`.
3. **Use `foreach_get` and `foreach_set` with NumPy:** When reading or modifying thousands of vertices (e.g., finding bounding boxes, grounding pivots, or baking vertex colors), Python `for v in mesh.vertices:` loops are painfully slow on 200k-vertex AI meshes.

### Fast vs. Slow Vertex Grounding Pattern

```python
import bpy
import numpy as np

def fast_ground_and_center(obj):
    """
    100x faster than iterating vertices in Python or calling bpy.ops.object.origin_set.
    Operates directly on the underlying C-array buffer via NumPy.
    """
    mesh = obj.data
    vert_count = len(mesh.vertices)

    # Allocate flat numpy array and pull C-buffer directly
    coords = np.empty(vert_count * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", coords)
    coords = coords.reshape((vert_count, 3))

    # Compute bounds in microseconds
    min_bounds = coords.min(axis=0)
    max_bounds = coords.max(axis=0)

    # Center X/Y, place bottom-most vertex at Z = 0.0
    offset = np.array([
        (min_bounds[0] + max_bounds[0]) * 0.5,
        (min_bounds[1] + max_bounds[1]) * 0.5,
        min_bounds[2]
    ], dtype=np.float32)

    coords -= offset

    # Push modified buffer straight back to Blender C-data
    mesh.vertices.foreach_set("co", coords.ravel())
    mesh.update()
```

## 2. Preserving UV Seams & Textures When Decimating AI Meshes

**What LLMs do wrong by default:**
When decimating a raw `.glb` from TRELLIS or Hunyuan3D from 150,000 triangles down to 3,500 triangles, LLMs simply apply a standard `DECIMATE` modifier. This destroys the UV texture map along UV island borders, causing warped streaks and black seams on the final game asset.

**Traps that look like fixes but do nothing:**

- `DecimateModifier.delimit` is **ignored in `COLLAPSE` mode**. Blender only passes it to Planar (`DISSOLVE`) decimation. Setting `dec.delimit = {'UV', 'SEAM'}` on a collapse decimate protects nothing (tested on Blender 5.2: results with and without it differ no more than repeat runs with identical settings).
- `bmesh.ops.dissolve_degenerate` takes only `dist` and `edges`; it has no `delimit`. It dissolves zero-length edges and zero-area faces. It does **not** remove floating or interior junk geometry; drop small loose parts separately.
- Collapse decimation is **not deterministic**: the same mesh and settings can give a different face count (e.g. 381 vs 382) on each run. Never golden-test exact counts or vertex hashes; assert a range.

**The Mandatory Fix:**

1. **Weld first.** glTF stores one UV per vertex, so a `.glb` arrives with vertices split along every UV seam, and each UV island is a separate piece. Collapse decimation pulls those open borders apart into cracks. Blender stores UVs per loop, so welding with `remove_doubles` keeps the seam as a UV discontinuity on connected geometry.
2. **Protect seam vertices through the modifier's vertex group.** In collapse mode a lower vertex weight raises the cost of collapsing an edge. Put the seam and border vertices in a group and set `invert_vertex_group = True`, so they get weight 0 and the decimator spends its budget on the interior.
3. **For big reductions (e.g. 150k → 3.5k), rebake.** Protection keeps seams in place but still stretches texels inside islands. For hero assets: decimate, unwrap the low-poly mesh again, and bake the high-poly texture onto it.

```python
import bpy
import bmesh

def clean_and_decimate_preserve_uvs(obj, target_tris=3500, seam_strength=10.0):
    mesh = obj.data

    # Step 1: Pure BMesh cleanup (no Edit Mode switch)
    bm = bmesh.new()
    bm.from_mesh(mesh)

    # Weld the per-island vertex splits that glTF import leaves along every UV seam.
    # UVs live on loops, so the seam survives as a UV discontinuity, not an open border.
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0001)

    # Dissolves zero-length edges and zero-area faces only (not floating junk).
    bmesh.ops.dissolve_degenerate(bm, dist=0.0001, edges=bm.edges)

    # Seam vertices: their loops disagree on UV, or they sit on an open border.
    bm.verts.index_update()
    uv_layer = bm.loops.layers.uv.active
    seam_verts = []
    if uv_layer is not None:
        for v in bm.verts:
            uvs = {(round(l[uv_layer].uv.x, 5), round(l[uv_layer].uv.y, 5)) for l in v.link_loops}
            if len(uvs) > 1 or v.is_boundary:
                seam_verts.append(v.index)

    bm.to_mesh(mesh)  # writes verts in bmesh order, so seam_verts indices stay valid
    bm.free()
    mesh.update()

    # The collapse ratio counts triangles, not faces: on a quad mesh a face-based
    # ratio overshoots the target about 2x.
    mesh.calc_loop_triangles()
    current_tris = len(mesh.loop_triangles)
    if current_tris <= target_tris:
        return

    # Step 2: Collapse decimate. `delimit` does nothing here; the vertex group does the work.
    dec = obj.modifiers.new(name="UV_Safe_Decimate", type='DECIMATE')
    dec.decimate_type = 'COLLAPSE'
    dec.ratio = max(0.02, target_tris / current_tris)
    if seam_verts:
        group = obj.vertex_groups.new(name="_uv_seams")
        group.add(seam_verts, 1.0, 'REPLACE')
        dec.vertex_group = group.name
        dec.invert_vertex_group = True       # seam verts -> weight 0 -> expensive to collapse
        dec.vertex_group_factor = seam_strength  # protected seams resist collapse: expect ~10% over target

    # Evaluate the modifier via the depsgraph instead of the bpy.ops.object.modifier_apply operator
    depsgraph = bpy.context.evaluated_depsgraph_get()
    new_mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph))

    obj.modifiers.remove(dec)
    old_mesh = obj.data
    obj.data = new_mesh
    bpy.data.meshes.remove(old_mesh)
    leftover = obj.vertex_groups.get("_uv_seams")
    if leftover is not None:
        obj.vertex_groups.remove(leftover)
```

## 3. Blender 4.1+ / 4.3+ / 5.x API Deprecation Traps

**What LLMs do wrong by default:**
Almost every LLM still writes `mesh.use_auto_smooth = True` and `mesh.auto_smooth_angle = 1.047`. Blender 4.1+ completely removed `use_auto_smooth` from the Mesh data-block, causing scripts written by LLMs to crash immediately with `AttributeError: 'Mesh' object has no attribute 'use_auto_smooth'`.

**The Mandatory Fix:**
Use the Mesh data-API methods `shade_smooth()` and `set_sharp_from_angle(angle=...)`. They run in C, need no context, and work headless (tested on Blender 5.2). Do not use `bpy.ops.object.shade_smooth_by_angle`: it is an operator, so rule 1 applies. If a build lacks `set_sharp_from_angle`, use the `bmesh` fallback.

```python
import math
import bmesh

def set_modern_smooth_shading(obj, angle_degrees=35.0):
    mesh = obj.data
    angle_rad = math.radians(angle_degrees)
    if hasattr(mesh, "set_sharp_from_angle"):
        mesh.shade_smooth()                          # all faces smooth
        mesh.set_sharp_from_angle(angle=angle_rad)   # edges sharper than the angle -> sharp
        mesh.update()
        return

    # Fallback: faces smooth via foreach_set, sharp edges by angle in BMesh
    mesh.polygons.foreach_set("use_smooth", [True] * len(mesh.polygons))
    bm = bmesh.new()
    bm.from_mesh(mesh)
    for edge in bm.edges:
        if len(edge.link_faces) == 2:
            edge.smooth = edge.calc_face_angle() <= angle_rad
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
```

## 4. Persistent Blender Daemon vs. Cold-Starting `blender.exe`

**What LLMs do wrong by default:**
Spawning `blender.exe -b -P script.py` from scratch for every single asset incurs a 2.5 to 4.5 second OS & Python initialization penalty per asset. If generating 50 dungeon props, you waste nearly 4 minutes just opening and closing Blender.

**The Mandatory Fix:**

1. **Batch Processing in One Process:** Pass a JSON manifest of assets to a single headless Blender instance.
2. **Orphan Data-Block Purging:** Instead of calling `bpy.ops.wm.read_factory_settings(use_empty=True)` (which reloads internal startups), purge orphan meshes, materials, and images directly in memory between assets. Use the data-API `bpy.data.orphans_purge`, not the `bpy.ops.outliner.orphans_purge` operator (rule 1):

```python
import bpy

def fast_reset_scene():
    # Remove all objects in one call, without reloading the factory startup
    bpy.data.batch_remove(list(bpy.data.objects))
    # Purge the meshes, materials, textures and images that are now orphans
    bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
```

## 5. Pre-Conditioning Input Images for 2x Better 3D AI Topology

Generative 3D models (TRELLIS, Hunyuan3D-2, SF3D) are heavily sensitive to how the 2D concept image is framed and lit. Before passing an image to the 3D generator, the LLM orchestrator should enforce these rules:

1. **Prompt for "Orthographic / Isometric 3/4 View, Flat Albedo Lighting":**
   - *Why:* Hard drop-shadows or dramatic rim lighting in the 2D image get misinterpreted by 3D diffusion models as physical geometric dents or get permanently baked as black splotches into the diffuse texture. Always append: `"even studio lighting, ambient occlusion only, no cast shadows, 3/4 isometric view, isolated on solid neutral background"` to image generation prompts.
2. **Enforce an 85% Foreground Padding Ratio (Auto-Crop & Pad):**
   - *Why:* TRELLIS and Hunyuan3D normalize input images to `518x518` or `512x512`. If the object only occupies 40% of the canvas, you lose over half of the 3D voxel resolution. If it touches the edge of the canvas, the 3D mesh gets clipped flat at the borders.
   - *The Fix:* After running `rembg`, compute the alpha bounding box, crop tightly to the non-transparent pixels, and paste onto a square RGBA canvas such that the longest dimension occupies exactly 82%–88% of the image width/height.
3. **Alpha Thresholding (De-Haloing):**
   - *Why:* `rembg` leaves semi-transparent edge pixels (`alpha` between `10` and `200`). 3D models turn semi-transparent border pixels into jagged "crust" or floating geometry around the silhouette.
   - *The Fix:* Run a quick alpha erosion or hard threshold (`alpha = np.where(alpha > 160, 255, 0)`, the value the code below uses; tune between about 128 and 200) before feeding the PIL image into TRELLIS.

```python
import numpy as np
from PIL import Image

def optimize_image_for_3d(pil_rgba_img: Image.Image, canvas_size: int = 518, fill_ratio: float = 0.85) -> Image.Image:
    """
    Crops transparent borders, removes semi-transparent alpha halos that cause
    jagged 3D mesh edges, and centers the object at an optimal 85% voxel fill ratio.
    """
    pil_rgba_img = pil_rgba_img.convert("RGBA")  # an RGB input has no alpha channel to index
    arr = np.array(pil_rgba_img)
    alpha = arr[:, :, 3]

    # Hard-threshold alpha to prevent floating 'crust' vertices on silhouette
    alpha_clean = np.where(alpha > 160, 255, 0).astype(np.uint8)
    arr[:, :, 3] = alpha_clean

    # Find bounding box of foreground object
    coords = np.argwhere(alpha_clean > 0)
    if coords.size == 0:
        return pil_rgba_img.resize((canvas_size, canvas_size))

    y0, x0 = coords.min(axis=0)
    y1, x1 = coords.max(axis=0) + 1
    cropped = Image.fromarray(arr[y0:y1, x0:x1])

    # Scale longest side to target fill_ratio of canvas
    target_dim = int(canvas_size * fill_ratio)
    w, h = cropped.size
    scale = target_dim / max(w, h)
    new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
    resized = cropped.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # Paste centered onto clean transparent square canvas
    canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    paste_x = (canvas_size - new_w) // 2
    paste_y = (canvas_size - new_h) // 2
    canvas.paste(resized, (paste_x, paste_y))
    return canvas
```

## 6. Multi-Primitive Convex Decomposition vs. Single Hull (`UCX_`)

**What LLMs do wrong by default:**
A single convex hull (`bmesh.ops.convex_hull`) wraps the entire object like shrink-wrap. For an archway, a chair, or an L-shaped corner wall, a single `UCX_` hull blocks the player from walking through the arch or sitting in the chair.

**The Mandatory Fix:**
Instruct the LLM to check the Volumetric Concavity Ratio (comparing the volume of the mesh `bm.calc_volume()` against the volume of its single convex hull).

- If `hull_volume / mesh_volume < 1.35`: Use a single fast `UCX_SM_<Name>` hull (e.g., crates, barrels, rocks).
- If `hull_volume / mesh_volume >= 1.35`: The object is concave (e.g., archway, hollow pipe, furniture). Split the mesh by loose parts or voxel grid chunks (or run a convex decomposition library such as V-HACD or CoACD) and generate numbered hulls (`UCX_SM_<Name>_01`, `UCX_SM_<Name>_02`, etc.).

**`calc_volume()` needs a watertight mesh.** On a mesh with holes or non-manifold edges (common in raw AI output) the volume is meaningless, and so is the ratio. Check first; if the mesh is not watertight, fill holes on a copy (`bmesh.ops.holes_fill`) or skip the ratio and decompose by loose parts.

```python
import bmesh

def concavity_ratio(mesh):
    """hull_volume / mesh_volume, or None if the mesh is not watertight."""
    bm = bmesh.new()
    bm.from_mesh(mesh)
    watertight = all(e.is_manifold for e in bm.edges)  # boundary edges are not manifold
    mesh_volume = bm.calc_volume(signed=False)

    # Hull from the vertices alone: every face of `hull` is a hull face,
    # and leftover interior vertices are loose, so they add no volume.
    hull = bmesh.new()
    for v in bm.verts:
        hull.verts.new(v.co)
    bmesh.ops.convex_hull(hull, input=list(hull.verts))
    hull_volume = hull.calc_volume(signed=False)
    bm.free()
    hull.free()

    if not watertight or mesh_volume <= 1e-9:
        return None
    return hull_volume / mesh_volume
```

**Engine import: only Unreal reads `UCX_` names.**

- **Unreal:** the FBX importer turns `UCX_<RenderMeshName>_##` meshes into convex collision automatically. The name after `UCX_` must match the render mesh exactly (`UCX_SM_Crate_01` for `SM_Crate`).
- **Unity:** Unity does **not** do this. It imports `UCX_` meshes as ordinary visible meshes. Add an editor `AssetPostprocessor` (in an `Editor` folder) that turns them into convex `MeshCollider`s and removes their renderers. Keep each hull at or under 255 triangles: Unity's convex mesh colliders are limited to 255 polygons.

```csharp
using UnityEditor;
using UnityEngine;

public sealed class UcxColliderPostprocessor : AssetPostprocessor
{
    void OnPostprocessModel(GameObject root)
    {
        foreach (var filter in root.GetComponentsInChildren<MeshFilter>(true))
        {
            if (!filter.name.StartsWith("UCX_")) continue;

            var collider = filter.gameObject.AddComponent<MeshCollider>();
            collider.sharedMesh = filter.sharedMesh;
            collider.convex = true;

            var renderer = filter.GetComponent<MeshRenderer>();
            if (renderer != null) Object.DestroyImmediate(renderer);
            Object.DestroyImmediate(filter);
        }
    }
}
```
