"""
roboonto CLI
============

用法:
  roboonto pack migrate <legacy_dir> -o <robot.pack.yaml>
  roboonto pack validate <robot.pack.yaml>
  roboonto pack inspect <robot.pack.yaml> [--json]
  roboonto validate <ontology_dir>
  roboonto query   <ontology_dir> <query_kind> [args...]
  roboonto check-action <ontology_dir> <action_id> --params '{}' --state '{}'
  roboonto demo    <ontology_dir>
  roboonto import urdf <file> -o <dir>
  roboonto import sdk-code <dir> -o <dir>
  roboonto readiness <dir> [--profile customer_v1] [--json] [--require grade]
  roboonto build init/status/log/run <dir>
  roboonto serve --mcp [--dir robots/]
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path

import yaml

from .api.loader import OntologyLoader
from .api.query import Query, action_for_llm
from .api.action_validator import ActionValidator
from .api.capability_infer import infer_capability_drafts
from .framework.readiness import Readiness, GRADE_ORDER


def cmd_validate(args):
    _legacy_notice("validate")
    loader = OntologyLoader(Path(args.dir))
    loader.load()
    issues = loader.validate()
    print(loader.summary())
    errors = [i for i in issues if i.severity == "error"]
    if errors:
        print("\n=== ERRORS ===", file=sys.stderr)
        for e in errors:
            print(" ", e, file=sys.stderr)
        return 1
    return 0


def cmd_query(args):
    _legacy_notice("query")
    loader = OntologyLoader(Path(args.dir))
    ontology = loader.load()
    q = Query(ontology)

    kind = args.kind
    if kind == "objects":
        if not args.arg:
            print("query kind 'objects' requires an object type", file=sys.stderr)
            return 2
        out = q.objects_of_type(args.arg)
    elif kind == "actions-in-mode":
        if not args.arg:
            print("query kind 'actions-in-mode' requires a mode value", file=sys.stderr)
            return 2
        out = [{"id": a["type_id"], "safety": a.get("safety_class"),
                "desc": a.get("description")}
               for a in q.actions_allowed_in_mode(args.arg)]
    elif kind == "actions-affecting":
        if not args.arg:
            print("query kind 'actions-affecting' requires a target id", file=sys.stderr)
            return 2
        out = [a["type_id"] for a in q.actions_affecting(args.arg)]
    elif kind == "events-on":
        if not args.arg:
            print("query kind 'events-on' requires a hardware id", file=sys.stderr)
            return 2
        out = [e["id"] for e in q.events_indicating(args.arg)]
    elif kind == "bits":
        if not args.arg:
            print("query kind 'bits' requires a carrier field", file=sys.stderr)
            return 2
        out = q.status_bits_on_field(args.arg)
    elif kind == "action-spec":
        if not args.arg:
            print("query kind 'action-spec' requires an action id", file=sys.stderr)
            return 2
        a = ontology.actions_by_id.get(args.arg)
        out = action_for_llm(a) if a else None
    elif kind == "capabilities":
        out = q.list_capabilities()
    elif kind == "agent-affordances":
        out = q.agent_affordance_menu(capability_kind=args.arg)
    elif kind == "capabilities-for":
        if not args.arg:
            print("query kind 'capabilities-for' requires a requirement id", file=sys.stderr)
            return 2
        out = q.find_capabilities(requirement=args.arg)
    elif kind == "service-fit":
        if not args.arg:
            print("query kind 'service-fit' requires a requirement id", file=sys.stderr)
            return 2
        out = q.explain_service_fit(args.arg)
    else:
        print(f"unknown query kind: {kind}", file=sys.stderr)
        return 2

    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    return 0


def cmd_check_action(args):
    _legacy_notice("check-action")
    loader = OntologyLoader(Path(args.dir))
    ontology = loader.load()
    v = ActionValidator(ontology)
    params = json.loads(args.params) if args.params else {}
    state = json.loads(args.state) if args.state else {}
    report = v.check(args.action_id, params=params, state=state)
    print(report.summary())
    return 0 if report.ok else 1


def cmd_demo(args):
    _legacy_notice("demo")
    loader = OntologyLoader(Path(args.dir))
    ontology = loader.load()
    loader.validate()
    print(loader.summary())
    print("\n→ run `python examples/diagnosis_demo.py` for the full walkthrough")
    return 0


def cmd_readiness(args):
    r = Readiness(Path(args.dir), profile=args.profile)
    report = r.run()
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(report.to_text(color=sys.stdout.isatty()))
    if args.require:
        if args.require not in GRADE_ORDER:
            print(f"unknown grade '{args.require}', expected one of {GRADE_ORDER}", file=sys.stderr)
            return 2
        if GRADE_ORDER.index(report.grade) < GRADE_ORDER.index(args.require):
            print(f"\nFAIL: required '{args.require}', got '{report.grade}'", file=sys.stderr)
            return 1
    return 0 if report.grade != "fail" else 1


def cmd_infer_capabilities(args):
    _legacy_notice("infer-capabilities")
    loader = OntologyLoader(Path(args.dir))
    ontology = loader.load()
    draft = infer_capability_drafts(ontology)
    if args.yaml:
        print(yaml.dump(draft, allow_unicode=True, sort_keys=False))
    else:
        print(json.dumps(draft, indent=2, ensure_ascii=False, default=str))
    return 0


def cmd_import(args):
    if args.import_cmd == "urdf":
        return _cmd_import_urdf(args)
    elif args.import_cmd == "sdk-code":
        return _cmd_import_sdk(args)
    return 2


def _cmd_import_urdf(args):
    from .importers.urdf import URDFImporter
    from .pack import dump_pack

    robot_id = args.robot_id or Path(args.urdf_file).stem
    importer = URDFImporter(robot_id=robot_id, version=args.version)
    pack = importer.run(Path(args.urdf_file))
    output = _pack_output_path(args.output, robot_id, Path(args.urdf_file).parent)
    finalized = dump_pack(pack, output)
    counts = finalized.count()
    print(
        f"PackModule: {finalized.module.id}@{finalized.module.version}  "
        f"entities={counts['entities']}  relations={counts['relations']}"
    )
    print(f"  → {output}")
    return 0


def _cmd_import_sdk(args):
    from .importers.sdk_code import import_sdk_code
    sdk_dir = Path(args.sdk_dir)
    robot_id = args.robot_id or sdk_dir.name
    output = _pack_output_path(args.output, robot_id, Path.cwd())
    print(f"Importing SDK: {sdk_dir}")
    result = import_sdk_code(
        str(sdk_dir),
        str(output),
        robot_id=robot_id,
        version=args.version,
    )
    counts = result.count()
    print(
        f"PackModule: {result.module.id}@{result.module.version}  "
        f"entities={counts['entities']}  bindings={counts['bindings']}"
    )
    print(f"  → {output}")
    return 0


def cmd_pack(args):
    from .pack import load_pack

    if args.pack_cmd == "migrate":
        from .compat import LegacyPackMigrator
        from .pack import dump_pack

        result = LegacyPackMigrator(output_version=args.version).migrate(args.legacy_dir)
        output = Path(args.output)
        finalized = dump_pack(result.pack, output)
        blocking = [
            issue for issue in finalized.migration_issues if issue.blocks_execution
        ]
        print(
            f"已生成 {finalized.module.id}@{finalized.module.version}: "
            f"{output}"
        )
        print(
            f"源对象={result.source_counts['objects']} "
            f"源关系={result.source_counts['relations']} "
            f"源动作={result.source_counts['actions']}"
        )
        print(
            f"规范实体={len(finalized.entities)} "
            f"规范关系={len(finalized.relations)} "
            f"TargetAction={len(finalized.target_actions)} "
            f"阻塞项={len(blocking)}"
        )
        print(f"digest={finalized.module.content_digest}")
        if args.strict and blocking:
            for issue in blocking:
                print(f"  {issue.id}: {issue.message}", file=sys.stderr)
            return 1
        return 0

    pack = load_pack(args.path)
    if args.pack_cmd == "validate":
        print(
            f"有效 PackModule: {pack.module.id}@{pack.module.version} "
            f"{pack.module.content_digest}"
        )
        return 0
    if args.pack_cmd == "inspect":
        payload = {
            "module": pack.module.to_data(),
            "counts": pack.count(),
            "exports": {
                key: list(values) for key, values in sorted(pack.exports.items())
            },
            "migration": {
                "issues": len(pack.migration_issues),
                "blocking": sum(
                    1 for issue in pack.migration_issues if issue.blocks_execution
                ),
            },
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"{pack.module.id}@{pack.module.version}")
            for key, value in payload["counts"].items():
                print(f"  {key}: {value}")
            print(f"  digest: {pack.module.content_digest}")
            print(
                f"  migration: {payload['migration']['issues']} issues, "
                f"{payload['migration']['blocking']} blocking"
            )
        return 0
    return 2


def _pack_output_path(raw: str, robot_id: str, default_dir: Path) -> Path:
    if not raw:
        return default_dir / f"{robot_id}.pack.yaml"
    path = Path(raw)
    if path.suffix.lower() in {".json", ".yaml", ".yml"}:
        return path
    return path / f"{robot_id}.pack.yaml"


def _legacy_notice(command: str) -> None:
    print(
        f"提示：`roboonto {command}` 使用 0.9 compatibility 层；"
        "生产链路请使用 `roboonto pack ...`。",
        file=sys.stderr,
    )


def cmd_build(args):
    from .build.session import BuildSession
    sess = BuildSession(Path(args.dir))
    if args.build_cmd == "init":
        sess.init(operator=args.operator)
        print(f"Build session initialized in {sess.dir}")
        return 0
    if args.build_cmd == "status":
        if not sess.exists():
            print("no build session — run `roboonto build init`", file=sys.stderr)
            return 1
        print(json.dumps(sess.status(), indent=2, ensure_ascii=False, default=str))
        return 0
    if args.build_cmd == "log":
        if not sess.exists():
            print("no build session — run `roboonto build init`", file=sys.stderr)
            return 1
        for entry in sess.tail(args.limit):
            print(json.dumps(entry, ensure_ascii=False, default=str))
        return 0
    if args.build_cmd == "run":
        if not sess.exists():
            print("no build session — run `roboonto build init`", file=sys.stderr)
            return 1
        return sess.run_step(args.step, cmd=args.cmd, note=args.note)
    return 2


def cmd_serve(args):
    if not args.mcp:
        print("Use --mcp to start as MCP server", file=sys.stderr)
        return 1
    from .mcp_server import serve_mcp, _find_robots_dir
    robots_dir = Path(args.dir) if args.dir else _find_robots_dir()
    print(f"roboonto MCP server starting (robots: {robots_dir})", file=sys.stderr)
    serve_mcp(robots_dir)
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="roboonto")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_pack = sub.add_parser("pack", help="编译、验证和检查规范 PackModule")
    pack_sub = p_pack.add_subparsers(dest="pack_cmd", required=True)
    p_pm = pack_sub.add_parser("migrate", help="一次性迁移旧 RoboOnto 目录")
    p_pm.add_argument("legacy_dir")
    p_pm.add_argument("--output", "-o", required=True)
    p_pm.add_argument("--version", default="0.9.0")
    p_pm.add_argument(
        "--strict",
        action="store_true",
        help="存在阻塞执行的迁移项时返回非零状态",
    )
    p_pm.set_defaults(func=cmd_pack)
    p_pv = pack_sub.add_parser("validate", help="验证 Schema、静态语义和摘要")
    p_pv.add_argument("path")
    p_pv.set_defaults(func=cmd_pack)
    p_pi = pack_sub.add_parser("inspect", help="检查 PackModule 摘要")
    p_pi.add_argument("path")
    p_pi.add_argument("--json", action="store_true")
    p_pi.set_defaults(func=cmd_pack)

    p_v = sub.add_parser("validate", help="Load + validate an ontology directory")
    p_v.add_argument("dir")
    p_v.set_defaults(func=cmd_validate)

    p_q = sub.add_parser("query", help="Run a query against an ontology")
    p_q.add_argument("dir")
    p_q.add_argument("kind", choices=[
        "objects", "actions-in-mode", "actions-affecting",
        "events-on", "bits", "action-spec",
        "capabilities", "agent-affordances", "capabilities-for", "service-fit",
    ])
    p_q.add_argument("arg", nargs="?")
    p_q.set_defaults(func=cmd_query)

    p_c = sub.add_parser("check-action", help="Validate an Action call")
    p_c.add_argument("dir")
    p_c.add_argument("action_id")
    p_c.add_argument("--params", help="JSON for action parameters", default="{}")
    p_c.add_argument("--state", help="JSON for runtime state", default="{}")
    p_c.set_defaults(func=cmd_check_action)

    p_d = sub.add_parser("demo", help="Summarize the ontology")
    p_d.add_argument("dir")
    p_d.set_defaults(func=cmd_demo)

    # Import
    p_import = sub.add_parser("import", help="Import data into ontology")
    import_sub = p_import.add_subparsers(dest="import_cmd", required=True)
    p_urdf = import_sub.add_parser("urdf", help="URDF → PackModule")
    p_urdf.add_argument("urdf_file")
    p_urdf.add_argument("--output", "-o", default="")
    p_urdf.add_argument("--robot-id", default="")
    p_urdf.add_argument("--version", default="0.9.0")
    p_urdf.add_argument("--mesh-root", default="")
    p_urdf.set_defaults(func=cmd_import)
    p_sdk = import_sub.add_parser("sdk-code", help="SDK .msg/.srv → PackModule")
    p_sdk.add_argument("sdk_dir")
    p_sdk.add_argument("--output", "-o", default="")
    p_sdk.add_argument("--robot-id", default="")
    p_sdk.add_argument("--version", default="0.9.0")
    p_sdk.set_defaults(func=cmd_import)

    # Readiness
    p_r = sub.add_parser("readiness", help="Grade an ontology against a framework profile")
    p_r.add_argument("dir")
    p_r.add_argument("--profile", default="customer_v1")
    p_r.add_argument("--json", action="store_true")
    p_r.add_argument("--require", default="")
    p_r.set_defaults(func=cmd_readiness)

    p_ic = sub.add_parser("infer-capabilities", help="Infer a reviewable capabilities.yaml draft from actions/interfaces")
    p_ic.add_argument("dir")
    p_ic.add_argument("--yaml", action="store_true", help="Output YAML instead of JSON")
    p_ic.set_defaults(func=cmd_infer_capabilities)

    # Build
    p_b = sub.add_parser("build", help="Sessioned ontology build with audit log")
    build_sub = p_b.add_subparsers(dest="build_cmd", required=True)
    p_bi = build_sub.add_parser("init", help="Initialize a build session")
    p_bi.add_argument("dir")
    p_bi.add_argument("--operator", default="")
    p_bi.set_defaults(func=cmd_build)
    p_bs = build_sub.add_parser("status", help="Show current session state")
    p_bs.add_argument("dir")
    p_bs.set_defaults(func=cmd_build)
    p_bl = build_sub.add_parser("log", help="Tail the audit log")
    p_bl.add_argument("dir")
    p_bl.add_argument("--limit", type=int, default=50)
    p_bl.set_defaults(func=cmd_build)
    p_br = build_sub.add_parser("run", help="Run a build step under audit")
    p_br.add_argument("dir")
    p_br.add_argument("step")
    p_br.add_argument("--note", default="")
    p_br.add_argument("cmd", nargs=argparse.REMAINDER)
    p_br.set_defaults(func=cmd_build)

    # MCP server
    p_serve = sub.add_parser("serve", help="Start MCP server for AI agent integration")
    p_serve.add_argument("--mcp", action="store_true", help="Run as MCP stdio server")
    p_serve.add_argument("--dir", default="", help="Robots directory")
    p_serve.set_defaults(func=cmd_serve)

    return p


def main():
    args = build_parser().parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
