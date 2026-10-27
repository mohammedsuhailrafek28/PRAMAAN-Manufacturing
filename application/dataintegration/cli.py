"""Command line: preview / import / demo.

  python -B -m application.dataintegration preview --source ERP=erp.csv --source MES=mes.csv [--mapping ERP=my_erp_mapping.json]
                                                    [--ledger L.sqlite --staging S.sqlite] [--create-units] [--historical-shipments] [--out DIR]
  python -B -m application.dataintegration import   (same, plus --ledger and --staging are required; writes the ledger and the staging store)
  python -B -m application.dataintegration demo     [--workdir DIR]     end-to-end demonstration with the bundled synthetic exports
"""
import argparse
import sys
from pathlib import Path

from .importer import DEFAULT_MAPPINGS, Source, run
from .planner import Options
from .report import render_text, write_reports


def _pairs(values, what):
    out = []
    for v in values or []:
        system, sep, rest = v.partition("=")
        if not sep or system.upper() not in DEFAULT_MAPPINGS:
            raise SystemExit(f"--{what} expects SYSTEM=path with SYSTEM one of {', '.join(DEFAULT_MAPPINGS)}; got {v!r}")
        out.append((system.upper(), Path(rest)))
    return out


def sources_from(args) -> list[Source]:
    mappings = dict(_pairs(args.mapping, "mapping"))
    sources = [Source(system, path, mappings.get(system)) for system, path in _pairs(args.source, "source")]
    if not sources:
        raise SystemExit("at least one --source SYSTEM=path is required")
    return sources


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="python -m application.dataintegration", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    for name in ("preview", "import"):
        p = sub.add_parser(name)
        p.add_argument("--source", action="append", help="SYSTEM=path of an export (repeatable)")
        p.add_argument("--mapping", action="append", help="SYSTEM=path of a mapping configuration (default: the bundled one)")
        p.add_argument("--ledger"); p.add_argument("--staging"); p.add_argument("--out")
        p.add_argument("--lot-registry", help="lot registry JSON (default: the bundled synthetic registry)")
        p.add_argument("--create-units", action="store_true", help="register motor serials the ledger does not know yet")
        p.add_argument("--historical-shipments", action="store_true", help="allow logistics records to become MOTOR_SHIPPED history")
    d = sub.add_parser("demo")
    d.add_argument("--workdir", default=None)
    args = ap.parse_args(argv)
    if args.command == "demo":
        from .demo import main as demo_main
        return demo_main(args.workdir)
    commit = args.command == "import"
    if commit and not (args.ledger and args.staging):
        raise SystemExit("import needs --ledger and --staging (use preview to see what would happen without writing)")
    report, plan, files = run(sources_from(args), ledger=args.ledger, staging=args.staging, commit=commit, lot_registry=args.lot_registry,
                              options=Options(create_units=args.create_units, historical_shipments=args.historical_shipments))
    print(render_text(report))
    if args.out:
        print("\nwritten:", ", ".join(write_reports(report, args.out).values()))
    print(f"\nreport digest {report.digest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
