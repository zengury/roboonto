"""
roboonto.tools.generate_3d — Generate the 3D ontology-atlas HTML for a pack.

Injects GRAPH_DATA (built from the ontology) into the vendored, robot-agnostic
atlas template and fills the robot title/id placeholders.

Usage:
  python3 -m roboonto.tools.generate_3d robots/unitree_g1_edu
  python3 -m roboonto.tools.generate_3d robots/unitree_g1_edu -o output.html
"""
from __future__ import annotations
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REF_HTML = _HERE / "templates" / "ontology_atlas_3d.html"


def generate(ontology_dir: str, output_path: str, *, verify: bool = True) -> int:
    """Generate the atlas HTML from an ontology by injecting GRAPH_DATA."""
    from roboonto.core.graph_data import GraphData

    gd = GraphData.build(ontology_dir)

    if verify:
        issues = gd.validate()
        warnings = [i for i in issues if i.startswith("WARNING")]
        errors = [i for i in issues if not i.startswith("WARNING")]
        if warnings:
            print(f"Warnings ({len(warnings)}):", file=sys.stderr)
            for w in warnings[:10]:
                print(f"  {w}", file=sys.stderr)
        if errors:
            print(f"VALIDATION FAILED ({len(errors)} errors):", file=sys.stderr)
            for e in errors:
                print(f"  {e}", file=sys.stderr)
            return 1

    if not _REF_HTML.exists():
        print(f"Atlas template not found: {_REF_HTML}", file=sys.stderr)
        return 1
    ref = _REF_HTML.read_text(encoding="utf-8")

    # Replace the GRAPH_DATA object literal (brace-matched) with real data.
    decl = ref.find("const GRAPH_DATA = {")
    if decl < 0:
        print("Template missing 'const GRAPH_DATA = {'", file=sys.stderr)
        return 1
    jstart = ref.find("{", decl)
    brace = 0
    jend = -1
    for i in range(jstart, len(ref)):
        if ref[i] == "{":
            brace += 1
        elif ref[i] == "}":
            brace -= 1
            if brace == 0:
                jend = i
                break
    if jend < 0:
        print("Template GRAPH_DATA object not balanced", file=sys.stderr)
        return 1

    result = ref[:jstart] + gd.to_json() + ref[jend + 1:]

    # Fill robot placeholders.
    robot = gd.robot_meta
    vendor, model = robot.get("vendor", ""), robot.get("model", "")
    title = (f"{vendor} {model}".strip()) or gd.robot_id
    result = result.replace("__ROBOT_TITLE__", title)
    result = result.replace("__ROBOT_ID__", gd.robot_id)

    Path(output_path).write_text(result, encoding="utf-8")

    if verify:
        out = Path(output_path).read_text(encoding="utf-8")
        for needle, name in {
            "const GRAPH_DATA = {": "declaration",
            '"nodes"': "nodes",
            '"layer"': "layer field",
            '"stats"': "stats",
        }.items():
            if needle not in out:
                print(f"VERIFY FAILED: missing {name} in output", file=sys.stderr)
                return 1
        if "__ROBOT_TITLE__" in out or "__ROBOT_ID__" in out:
            print("VERIFY FAILED: unfilled placeholder remains", file=sys.stderr)
            return 1

    print(f"Generated: {output_path}  ({len(gd.nodes)} nodes, {len(gd.links)} links)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 -m roboonto.tools.generate_3d <ontology_dir> [-o output.html]")
        sys.exit(1)
    onto_dir = sys.argv[1]
    output = sys.argv[sys.argv.index("-o") + 1] if "-o" in sys.argv else f"{onto_dir}/roboonto_pack_3d.html"
    sys.exit(generate(onto_dir, output))
