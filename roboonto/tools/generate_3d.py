"""
roboonto.tools.generate_3d — Generate 3D ontology visualization HTML.

Single module. Uses GraphData schema. Renders via proven reference template.

Usage:
  python3 roboonto/tools/generate_3d.py robots/unitree_g1_edu
  python3 roboonto/tools/generate_3d.py robots/unitree_g1_edu -o output.html
"""
from __future__ import annotations
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REF_HTML = Path("/Users/ZQ/Downloads/runtime-console-package/ontology_3d.html")


def generate(ontology_dir: str, output_path: str, *, verify: bool = True) -> int:
    """Generate 3D HTML from ontology. Replaces JSON data in working reference template."""
    from roboonto.core.graph_data import GraphData

    gd = GraphData.build(ontology_dir)

    # Validate before writing (warnings are logged, errors fail)
    if verify:
        issues = gd.validate()
        errors = [i for i in issues if not i.startswith("WARNING")]
        warnings = [i for i in issues if i.startswith("WARNING")]
        if warnings:
            print(f"Warnings ({len(warnings)}):", file=sys.stderr)
            for w in warnings[:10]:
                print(f"  {w}", file=sys.stderr)
        if errors:
            print(f"VALIDATION FAILED ({len(errors)} errors):", file=sys.stderr)
            for e in errors:
                print(f"  {e}", file=sys.stderr)
            return 1

    # Read working reference template
    if not _REF_HTML.exists():
        print(f"Reference template not found: {_REF_HTML}", file=sys.stderr)
        print("Expected at: ~/Downloads/runtime-console-package/ontology_3d.html", file=sys.stderr)
        return 1

    ref = _REF_HTML.read_text(encoding="utf-8")

    # Find GRAPH_DATA JSON boundaries
    decl = ref.find("const GRAPH_DATA = {")
    jstart = ref.find("{", decl)
    # Find matching closing brace
    brace = 0
    for i in range(jstart, len(ref)):
        if ref[i] == "{":
            brace += 1
        elif ref[i] == "}":
            brace -= 1
            if brace == 0:
                jend = i
                break

    # Replace JSON content only; keep const GRAPH_DATA = {}; structure intact
    graph_json = gd.to_json()
    result = ref[:jstart] + graph_json + ref[jend + 1:]

    # Replace title
    robot = gd.robot_meta
    vendor, model = robot.get("vendor", ""), robot.get("model", "")
    result = result.replace("AgiBot X2 Ontology Atlas", f"{vendor} {model} Ontology Atlas")
    result = result.replace("AgiBot X2", f"{vendor} {model}")
    result = result.replace("agibot_x2", gd.robot_id)

    Path(output_path).write_text(result, encoding="utf-8")

    if verify:
        # Quick sanity: check key strings in output
        with open(output_path) as f:
            out = f.read()
        checks = {
            "const GRAPH_DATA = {": "declaration",
            '"nodes"': "data",
            '"category_colors"': "category_colors",
            '"stats"': "stats",
        }
        for needle, name in checks.items():
            if needle not in out:
                print(f"VERIFY FAILED: missing {name} in output", file=sys.stderr)
                return 1

    print(f"Generated: {output_path}  ({len(gd.nodes)} nodes, {len(gd.links)} links)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 roboonto/tools/generate_3d.py <ontology_dir> [-o output.html]")
        sys.exit(1)
    onto_dir = sys.argv[1]
    output = sys.argv[sys.argv.index("-o") + 1] if "-o" in sys.argv else f"{onto_dir}/roboonto_pack_3d.html"
    sys.exit(generate(onto_dir, output))
