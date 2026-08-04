"""Compile Scene Program v0.1, render RGB frames, and extract dense ground truth."""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", type=Path, required=True)
    parser.add_argument("--asset-index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def set_transform(obj: bpy.types.Object, transform: dict[str, Any]) -> None:
    obj.location = transform["position"]
    x, y, z, w = transform["rotation"]
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = (w, x, y, z)
    obj.scale = transform["scale"]


def configure_world(scene: bpy.types.Scene, lighting: dict[str, Any]) -> None:
    world = bpy.data.worlds.new("Video2SceneWorld")
    scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background is not None:
        color = lighting["world"]["color"]
        background.inputs["Color"].default_value = (*color, 1.0)
        background.inputs["Strength"].default_value = lighting["world"]["strength"]
    for spec in lighting["lights"]:
        data = bpy.data.lights.new(spec["id"], type=spec["type"])
        data.energy = spec["energy"]
        if spec["type"] == "AREA":
            data.shape = "DISK"
            data.size = spec["size"]
        light = bpy.data.objects.new(spec["id"], data)
        bpy.context.scene.collection.objects.link(light)
        light.location = spec["position"]
        light.rotation_euler = spec["rotation"]


def add_ground() -> bpy.types.Object:
    bpy.ops.mesh.primitive_plane_add(size=30.0, location=(0.0, 0.0, -0.01))
    ground = bpy.context.object
    ground.name = "Ground"
    material = bpy.data.materials.new("GroundMaterial")
    material.diffuse_color = (0.16, 0.18, 0.21, 1.0)
    material.use_nodes = True
    shader = material.node_tree.nodes.get("Principled BSDF")
    if shader is not None:
        shader.inputs["Base Color"].default_value = (0.16, 0.18, 0.21, 1.0)
        shader.inputs["Roughness"].default_value = 0.82
    ground.data.materials.append(material)
    return ground


def import_instances(
    scene_program: dict[str, Any], asset_index: dict[str, Any]
) -> dict[str, bpy.types.Object]:
    asset_paths = {entry["asset_id"]: entry["glb_path"] for entry in asset_index["assets"]}
    roots: dict[str, bpy.types.Object] = {}
    specs = {item["id"]: item for item in scene_program["objects"]}
    for spec in scene_program["objects"]:
        try:
            glb_path = asset_paths[spec["asset_id"]]
        except KeyError as error:
            raise RuntimeError(f"asset not present in index: {spec['asset_id']}") from error
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=glb_path)
        imported = [obj for obj in bpy.data.objects if obj not in before]
        root = bpy.data.objects.new(spec["id"], None)
        bpy.context.scene.collection.objects.link(root)
        for obj in imported:
            if obj.parent is None:
                world = obj.matrix_world.copy()
                obj.parent = root
                obj.matrix_world = world
        roots[spec["id"]] = root
    for object_id, root in roots.items():
        spec = specs[object_id]
        parent_id = spec.get("parent_id")
        if parent_id is not None:
            root.parent = roots[parent_id]
        set_transform(root, spec["transform"])
    return roots


def create_camera(scene_program: dict[str, Any]) -> tuple[bpy.types.Object, bpy.types.Object]:
    spec = scene_program["camera"]
    data = bpy.data.cameras.new(spec["id"])
    data.type = "ORTHO" if spec["type"] == "orthographic" else "PERSP"
    data.lens = spec["focal_length_mm"]
    data.ortho_scale = spec["ortho_scale"]
    data.clip_start = spec["clip_start"]
    data.clip_end = spec["clip_end"]
    camera = bpy.data.objects.new(spec["id"], data)
    bpy.context.scene.collection.objects.link(camera)
    set_transform(camera, spec["transform"])
    target = bpy.data.objects.new("CameraLookAt", None)
    bpy.context.scene.collection.objects.link(target)
    target.location = spec["look_at"]
    constraint = camera.constraints.new(type="TRACK_TO")
    constraint.target = target
    constraint.track_axis = "TRACK_NEGATIVE_Z"
    constraint.up_axis = "UP_Y"
    bpy.context.scene.camera = camera
    return camera, target


def apply_animations(scene_program: dict[str, Any], targets: dict[str, bpy.types.Object]) -> None:
    for track in scene_program["animations"]:
        target = targets[track["target_id"]]
        property_name = "location" if track["property"] == "position" else "rotation_quaternion"
        if property_name == "rotation_quaternion":
            target.rotation_mode = "QUATERNION"
        for keyframe in track["keyframes"]:
            value = keyframe["value"]
            if property_name == "location":
                target.location = value
            else:
                x, y, z, w = value
                target.rotation_quaternion = (w, x, y, z)
            target.keyframe_insert(data_path=property_name, frame=keyframe["frame"])
        if target.animation_data is None or target.animation_data.action is None:
            continue
        for curve in target.animation_data.action.fcurves:
            for point in curve.keyframe_points:
                point.interpolation = "LINEAR"


def configure_render(scene: bpy.types.Scene, render: dict[str, Any], output: Path) -> None:
    scene.render.engine = render["engine"]
    scene.render.resolution_x = render["width"]
    scene.render.resolution_y = render["height"]
    scene.render.resolution_percentage = 100
    scene.render.fps = render["fps"]
    scene.render.fps_base = 1.0
    scene.frame_start = render["frame_start"]
    scene.frame_end = render["frame_end"]
    scene.render.filepath = str(output / "frames" / "frame_")
    scene.render.film_transparent = False
    scene.render.use_file_extension = True
    scene.render.use_overwrite = True
    scene.render.use_placeholder = False
    scene.render.use_stamp = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.image_settings.compression = 25
    if hasattr(scene, "eevee"):
        scene.eevee.taa_render_samples = render["samples"]
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass


def descendants(root: bpy.types.Object) -> list[bpy.types.Object]:
    return [root, *list(root.children_recursive)]


def evaluated_bounds(
    root: bpy.types.Object, depsgraph: bpy.types.Depsgraph
) -> tuple[Vector, Vector] | None:
    points: list[Vector] = []
    for obj in descendants(root):
        if obj.type != "MESH":
            continue
        evaluated = obj.evaluated_get(depsgraph)
        points.extend(evaluated.matrix_world @ Vector(corner) for corner in evaluated.bound_box)
    if not points:
        return None
    return (
        Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points))),
        Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points))),
    )


def evaluated_centroid(root: bpy.types.Object, depsgraph: bpy.types.Depsgraph) -> Vector | None:
    """Match the upstream scorer's mean-of-mesh-centroids layout representation."""
    centroids: list[Vector] = []
    for obj in descendants(root):
        if obj.type != "MESH":
            continue
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            if not mesh.vertices:
                continue
            total = Vector((0.0, 0.0, 0.0))
            for vertex in mesh.vertices:
                total += evaluated.matrix_world @ vertex.co
            centroids.append(total / len(mesh.vertices))
        finally:
            evaluated.to_mesh_clear()
    if not centroids:
        return None
    total = Vector((0.0, 0.0, 0.0))
    for centroid in centroids:
        total += centroid
    return total / len(centroids)


def bbox_corners(minimum: Vector, maximum: Vector) -> list[Vector]:
    return [
        Vector((x, y, z))
        for x in (minimum.x, maximum.x)
        for y in (minimum.y, maximum.y)
        for z in (minimum.z, maximum.z)
    ]


def extract_ground_truth(
    scene: bpy.types.Scene,
    roots: dict[str, bpy.types.Object],
    camera: bpy.types.Object,
    output: Path,
    sample_id: str,
) -> None:
    trajectories: dict[str, list[dict[str, Any]]] = {name: [] for name in roots}
    camera_frames: list[dict[str, Any]] = []
    visibility_frames: dict[str, list[dict[str, Any]]] = {name: [] for name in roots}
    layout_objects: list[dict[str, Any]] = []
    sceneact_camera: dict[str, Any] = {}
    width = scene.render.resolution_x
    height = scene.render.resolution_y
    for frame in range(scene.frame_start, scene.frame_end + 1):
        scene.frame_set(frame)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        camera_eval = camera.evaluated_get(depsgraph)
        matrix = camera_eval.matrix_world
        quaternion = matrix.to_quaternion()
        camera_frames.append(
            {
                "frame": frame,
                "position": list(matrix.translation),
                "rotation_xyzw": [quaternion.x, quaternion.y, quaternion.z, quaternion.w],
                "focal_length_mm": camera.data.lens,
                "type": camera.data.type,
            }
        )
        if frame == scene.frame_start:
            euler = matrix.to_euler("XYZ")
            sceneact_camera = {
                "name": camera.name,
                "type": camera.data.type,
                "location": list(matrix.translation),
                "rotation_euler_deg": [math.degrees(value) for value in euler],
                "lens_mm": camera.data.lens,
                "matrix_world": [list(row) for row in matrix],
                "note": "Video2Scene fixed platform-station camera",
            }
        for object_id, root in roots.items():
            evaluated = root.evaluated_get(depsgraph)
            object_matrix = evaluated.matrix_world
            rotation = object_matrix.to_quaternion()
            trajectories[object_id].append(
                {
                    "frame": frame,
                    "position": list(object_matrix.translation),
                    "rotation_xyzw": [rotation.x, rotation.y, rotation.z, rotation.w],
                    "scale": list(object_matrix.to_scale()),
                }
            )
            if frame == scene.frame_start:
                centroid = evaluated_centroid(root, depsgraph)
                if centroid is not None:
                    layout_objects.append({"name": object_id, "location": list(centroid)})
            bounds = evaluated_bounds(root, depsgraph)
            if bounds is None:
                visibility_frames[object_id].append(
                    {"frame": frame, "visible": False, "pixel_area": 0}
                )
                continue
            minimum, maximum = bounds
            projected = [
                world_to_camera_view(scene, camera_eval, point)
                for point in bbox_corners(minimum, maximum)
            ]
            in_front = any(point.z > 0 for point in projected)
            min_x = max(0.0, min(point.x for point in projected))
            max_x = min(1.0, max(point.x for point in projected))
            min_y = max(0.0, min(point.y for point in projected))
            max_y = min(1.0, max(point.y for point in projected))
            visible = in_front and max_x > min_x and max_y > min_y
            pixel_area = int((max_x - min_x) * width * (max_y - min_y) * height) if visible else 0
            camera_position = matrix.translation
            camera_inside = all(
                minimum[index] <= camera_position[index] <= maximum[index] for index in range(3)
            )
            visibility_frames[object_id].append(
                {
                    "frame": frame,
                    "visible": visible,
                    "pixel_area": pixel_area,
                    "pixel_ratio": pixel_area / float(width * height),
                    "screen_bbox": [min_x, min_y, max_x, max_y],
                    "world_bbox_min": list(minimum),
                    "world_bbox_max": list(maximum),
                    "camera_inside_bbox": camera_inside,
                }
            )
    visibility: dict[str, Any] = {}
    frame_count = scene.frame_end - scene.frame_start + 1
    for object_id, frames in visibility_frames.items():
        visible_frames = [item for item in frames if item["visible"]]
        visibility[object_id] = {
            "visible_frame_ratio": len(visible_frames) / frame_count,
            "max_pixel_ratio": max((item.get("pixel_ratio", 0.0) for item in frames), default=0.0),
            "min_visible_pixels": min((item["pixel_area"] for item in visible_frames), default=0),
            "frames": frames,
        }
    gt_dir = output / "gt"
    (gt_dir / "camera.json").write_text(
        json.dumps({"frames": camera_frames}, indent=2) + "\n", encoding="utf-8"
    )
    (gt_dir / "trajectories.json").write_text(
        json.dumps(trajectories, indent=2) + "\n", encoding="utf-8"
    )
    (gt_dir / "visibility.json").write_text(
        json.dumps(visibility, indent=2) + "\n", encoding="utf-8"
    )
    (gt_dir / "layout.json").write_text(
        json.dumps({"sample_id": sample_id, "objects": layout_objects}, indent=2) + "\n",
        encoding="utf-8",
    )
    (gt_dir / "camera_sceneact.json").write_text(
        json.dumps(sceneact_camera, indent=2) + "\n", encoding="utf-8"
    )


def render_frames(scene: bpy.types.Scene, scene_program: dict[str, Any], output: Path) -> None:
    """Render static programs once while preserving the dense frame contract."""
    if scene_program["animations"]:
        bpy.ops.render.render(animation=True)
        return
    first_frame_number = scene.frame_start
    first_frame = output / "frames" / f"frame_{first_frame_number:04d}.png"
    animation_path = scene.render.filepath
    scene.frame_set(first_frame_number)
    scene.render.filepath = str(first_frame)
    bpy.ops.render.render(write_still=True)
    if not first_frame.is_file():
        raise RuntimeError(f"static render did not produce {first_frame}")
    for frame in range(first_frame_number + 1, scene.frame_end + 1):
        destination = output / "frames" / f"frame_{frame:04d}.png"
        try:
            os.link(first_frame, destination)
        except OSError:
            shutil.copyfile(first_frame, destination)
    scene.render.filepath = animation_path


def main() -> None:
    args = parse_args()
    scene_program = read_json(args.scene)
    asset_index = read_json(args.asset_index)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "frames").mkdir(parents=True, exist_ok=True)
    (args.output / "gt").mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    configure_world(scene, scene_program["lighting"])
    ground = add_ground()
    roots = import_instances(scene_program, asset_index)
    camera, _target = create_camera(scene_program)
    targets = {**roots, scene_program["camera"]["id"]: camera}
    apply_animations(scene_program, targets)
    configure_render(scene, scene_program["render"], args.output)
    extract_ground_truth(
        scene, roots, camera, args.output, sample_id=str(scene_program["sample_id"])
    )
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output / "scene.blend"))
    ground.hide_set(True)
    bpy.ops.export_scene.gltf(
        filepath=str(args.output / "scene.glb"),
        export_format="GLB",
        export_animations=True,
        export_force_sampling=True,
        use_visible=True,
    )
    ground.hide_set(False)
    render_frames(scene, scene_program, args.output)
    print(json.dumps({"sample_id": scene_program["sample_id"], "status": "ok"}))


if __name__ == "__main__":
    main()
