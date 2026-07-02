"""
roboonto.tools.download_g1_meshes — Download G1 STL meshes and build 3D robot HTML.

Usage (when network is good):
  python3 roboonto/tools/download_g1_meshes.py
  
Downloads from unitree_ros/robots/g1_description/meshes,
gzip-compresses all STL files, base64 encodes, embeds into robot HTML template.
"""
from __future__ import annotations
import base64, gzip, io, json, os, re, sys, urllib.request
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_TEMPLATE = _HERE.parent.parent / "robots" / "agibot_x2" / "roboonto_pack_3d_robot.html"
_MESH_URL = "https://raw.githubusercontent.com/unitreerobotics/unitree_ros/master/robots/g1_description/meshes"
_OUTPUT = _HERE.parent.parent / "robots" / "unitree_g1_edu" / "roboonto_pack_3d_robot.html"

# Key body meshes (not hands/fingers/sensors — those add ~80MB)
KEY_MESHES = [
    "pelvis.STL", "torso_link.STL", "head_link.STL",
    "waist_yaw_link.STL", "waist_roll_link.STL",
    "left_hip_pitch_link.STL", "left_hip_roll_link.STL", "left_hip_yaw_link.STL",
    "left_knee_link.STL", "left_ankle_pitch_link.STL", "left_ankle_roll_link.STL",
    "right_hip_pitch_link.STL", "right_hip_roll_link.STL", "right_hip_yaw_link.STL",
    "right_knee_link.STL", "right_ankle_pitch_link.STL", "right_ankle_roll_link.STL",
    "left_shoulder_pitch_link.STL", "left_shoulder_roll_link.STL", "left_shoulder_yaw_link.STL",
    "left_elbow_link.STL",
    "right_shoulder_pitch_link.STL", "right_shoulder_roll_link.STL", "right_shoulder_yaw_link.STL",
    "right_elbow_link.STL",
]


def download_meshes(mesh_names: list[str], output_dir: Path) -> dict[str, bytes]:
    """Download meshes, return {name: binary_data}."""
    output_dir.mkdir(parents=True, exist_ok=True)
    meshes = {}
    for name in mesh_names:
        url = f"{_MESH_URL}/{name}"
        path = output_dir / name
        if path.exists():
            meshes[name] = path.read_bytes()
            print(f"  ✅ {name} (cached, {len(meshes[name])} bytes)")
            continue
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                data = resp.read()
                path.write_bytes(data)
                meshes[name] = data
                print(f"  ✅ {name} ({len(data)} bytes)")
        except Exception as e:
            print(f"  ❌ {name}: {e}")
    return meshes


def build_meshes_blob(meshes: dict[str, bytes]) -> str:
    """Combine meshes into gzip-compressed base64 blob (same format as X2 template)."""
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode='wb', compresslevel=9) as gz:
        # Write file count
        gz.write(len(meshes).to_bytes(2, 'little'))
        for name, data in sorted(meshes.items()):
            name_bytes = name.encode('utf-8')
            gz.write(len(name_bytes).to_bytes(2, 'little'))
            gz.write(name_bytes)
            gz.write(len(data).to_bytes(4, 'little'))
            gz.write(data)
    return base64.b64encode(buf.getvalue()).decode('ascii')


def generate(mesh_dir: str = "/tmp/g1_meshes") -> int:
    # Download
    meshes = download_meshes(KEY_MESHES, Path(mesh_dir))
    if not meshes:
        print("No meshes downloaded. Check network.", file=sys.stderr)
        return 1
    
    # Build blob
    print(f"\nCompressing {len(meshes)} meshes...")
    blob = build_meshes_blob(meshes)
    print(f"Blob size: {len(blob)} chars (base64)")

    # Read template
    html = _TEMPLATE.read_text(encoding="utf-8")

    # Replace MESHES_B64
    old_blob = re.search(r'const MESHES_B64\s*=\s*"[^"]*"', html)
    if old_blob:
        html = html.replace(old_blob.group(), f'const MESHES_B64 = "{blob}"')
    else:
        print("MESHES_B64 not found in template", file=sys.stderr)
        return 1

    # Replace title and robot name
    html = html.replace("X2 Ontology · 3D Robot", "G1 EDU · 3D Robot")
    html = html.replace("AgiBot X2 Ultra", "Unitree G1 EDU (23-DOF)")

    # Replace actions data
    from roboonto.api.loader import OntologyLoader
    loader = OntologyLoader(_HERE.parent.parent / "robots" / "unitree_g1_edu")
    ontology = loader.load()
    actions = [{"id": a["type_id"], "desc": a.get("description", ""),
                 "safety": a.get("safety_class", ""), "affects": a.get("affects", [])}
               for a in ontology.actions_by_id.values()]
    
    old_actions = re.search(r'const ACTIONS\s*=\s*\[.*?\];', html, re.DOTALL)
    if old_actions:
        actions_json = json.dumps(actions, ensure_ascii=False, indent=2)
        html = html.replace(old_actions.group(), f"const ACTIONS = {actions_json};")

    _OUTPUT.write_text(html, encoding="utf-8")
    print(f"\nGenerated: {_OUTPUT} ({len(html)} chars)")
    return 0


if __name__ == "__main__":
    mesh_dir = sys.argv[1] if len(sys.argv) > 1 else "/tmp/g1_meshes"
    sys.exit(generate(mesh_dir))
