"""Normalize one glTF asset and render deterministic catalog previews in Blender."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--source-relative", required=True)
    parser.add_argument("--source-pack", required=True)
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--output-glb", type=Path, required=True)
    parser.add_argument("--output-metadata", type=Path, required=True)
    parser.add_argument("--preview-dir", type=Path, required=True)
    return parser.parse_args(argv)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mesh_bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    points = [
        obj.matrix_world @ Vector(corner)
        for obj in objects
        if obj.type == "MESH"
        for corner in obj.bound_box
    ]
    if not points:
        raise RuntimeError("asset contains no mesh objects")
    return (
        Vector(
            (
                min(point.x for point in points),
                min(point.y for point in points),
                min(point.z for point in points),
            )
        ),
        Vector(
            (
                max(point.x for point in points),
                max(point.y for point in points),
                max(point.z for point in points),
            )
        ),
    )


def aim_camera(camera: bpy.types.Object, target: Vector) -> None:
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()


def add_material_plane(size: float) -> None:
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0.0, 0.0, -0.002))
    plane = bpy.context.object
    plane.name = "PreviewGround"
    material = bpy.data.materials.new("PreviewGroundMaterial")
    material.diffuse_color = (0.12, 0.14, 0.17, 1.0)
    plane.data.materials.append(material)


def render_previews(root: bpy.types.Object, dimensions: Vector, output_dir: Path) -> list[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 320
    scene.render.resolution_y = 320
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    if scene.world is None:
        scene.world = bpy.data.worlds.new("PreviewWorld")
    scene.world.color = (0.035, 0.04, 0.05)
    max_dim = max(*dimensions, 0.5)
    add_material_plane(max(20.0, max_dim * 8.0))

    bpy.ops.object.light_add(type="AREA", location=(3.0 * max_dim, -4.0 * max_dim, 5.0 * max_dim))
    bpy.context.object.data.energy = 900.0
    bpy.context.object.data.shape = "DISK"
    bpy.context.object.data.size = 5.0 * max_dim
    bpy.ops.object.light_add(type="SUN", location=(-2.0, 2.0, 5.0))
    bpy.context.object.data.energy = 2.0
    bpy.context.object.rotation_euler = (math.radians(25), math.radians(-20), math.radians(-35))
    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.data.lens = 58.0
    scene.camera = camera

    radius = max_dim * 2.8
    target = Vector((0.0, 0.0, dimensions.z * 0.45))
    views = {
        "front": (0.0, -radius, target.z),
        "back": (0.0, radius, target.z),
        "left": (-radius, 0.0, target.z),
        "right": (radius, 0.0, target.z),
        "top": (0.0, -0.01, radius + dimensions.z),
        "isometric": (radius * 0.72, -radius * 0.72, radius * 0.65),
    }
    rendered: list[str] = []
    root.hide_render = False
    for name, location in views.items():
        camera.location = location
        aim_camera(camera, target)
        path = output_dir / f"{name}.png"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        rendered.append(path.name)
    return rendered


def main() -> None:
    args = parse_args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    args.output_glb.parent.mkdir(parents=True, exist_ok=True)
    args.output_metadata.parent.mkdir(parents=True, exist_ok=True)
    args.preview_dir.mkdir(parents=True, exist_ok=True)

    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(args.source))
    imported = [obj for obj in bpy.data.objects if obj not in before]
    mesh_objects = [obj for obj in imported if obj.type == "MESH"]
    raw_min, raw_max = mesh_bounds(mesh_objects)
    center_x = (raw_min.x + raw_max.x) * 0.5
    center_y = (raw_min.y + raw_max.y) * 0.5

    root = bpy.data.objects.new(args.asset_id, None)
    bpy.context.scene.collection.objects.link(root)
    for obj in imported:
        if obj.parent is None:
            world = obj.matrix_world.copy()
            obj.parent = root
            obj.matrix_world = world
    translation = Vector((-center_x, -center_y, -raw_min.z))
    translation_matrix = Matrix.Translation(translation)
    for obj in imported:
        if obj.parent == root:
            obj.matrix_world = translation_matrix @ obj.matrix_world
    bpy.context.view_layer.update()
    canonical_min, canonical_max = mesh_bounds(mesh_objects)
    dimensions = canonical_max - canonical_min

    bpy.ops.object.select_all(action="DESELECT")
    root.select_set(True)
    for obj in imported:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = root
    bpy.ops.export_scene.gltf(
        filepath=str(args.output_glb),
        export_format="GLB",
        use_selection=True,
        export_animations=True,
    )

    clips = []
    for action in sorted(bpy.data.actions, key=lambda item: item.name):
        clips.append(
            {
                "name": action.name,
                "frame_start": float(action.frame_range[0]),
                "frame_end": float(action.frame_range[1]),
            }
        )
    preview_files = render_previews(root, dimensions, args.preview_dir)
    tags = [part.lower().replace(" ", "_") for part in Path(args.source_relative).parts[:-2]]
    metadata = {
        "schema_version": "1.0",
        "asset_id": args.asset_id,
        "source_pack": args.source_pack,
        "source_name": args.source.name,
        "source_relative_path": args.source_relative,
        "source_sha256": sha256_file(args.source),
        "normalized_glb_sha256": sha256_file(args.output_glb),
        "canonical_transform": {
            "translation": list(translation),
            "rotation_xyzw": [0.0, 0.0, 0.0, 1.0],
            "scale": [1.0, 1.0, 1.0],
        },
        "dimensions": list(dimensions),
        "bbox_min": list(canonical_min),
        "bbox_max": list(canonical_max),
        "ground_offset": 0.0,
        "animation_clips": clips,
        "tags_private": tags,
        "preview_files": preview_files,
    }
    args.output_metadata.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"asset_id": args.asset_id, "status": "ok"}))


if __name__ == "__main__":
    main()
