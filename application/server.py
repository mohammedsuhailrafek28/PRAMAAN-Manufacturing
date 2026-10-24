"""Loopback-only local application. No external notification delivery or deployment."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import secrets
import threading
import time
import sys
from urllib.parse import urlsplit, unquote

from .service import Manufacturing, ValidationFailure, LedgerBlocked, ROOT


class LocalServer(ThreadingHTTPServer):
    # Concurrent browser assets and multiple review tabs must not exhaust the
    # stdlib's five-connection listen backlog, especially on Windows.
    request_queue_size = 128
    daemon_threads = True


def make_server(database, port=4173, seed=False, *, trusted_anchor=None, previous_anchor=None, lot_registry=None):
    database = Path(database).resolve()
    if lot_registry is not None:
        from . import service as _service
        _service.DEFAULT_LOT_REGISTRY = Path(lot_registry)   # synthetic, locally authored registry used by capture and by every read model
    from .anchors import TrustedAnchor
    anchor = TrustedAnchor(trusted_anchor,previous_anchor) if trusted_anchor else None
    database.parent.mkdir(parents=True, exist_ok=True)
    service = Manufacturing(database)
    try:
        if seed:
            service.seed_demo()
        service.audit.verify(copy_records=False)
        journal_cache=dict(key=service.audit.journal_bytes_key())
        # Explicit activation verifies the protected reference before serving.
        # Warm proofs remain tied to actual bytes on every subsequent request.
        if anchor:anchor.verify(service,deadline=float('inf'))
    finally:
        service.close()
    lock = threading.RLock()
    token = secrets.token_urlsafe(32)
    dist = (ROOT / "recall-ui" / "dist").resolve()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, status, payload, content_type="application/json"):
            data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass  # Browser navigated away; evidence writes remain durable.

        def guard(self):
            """Loopback-only request hygiene (not authentication): reject foreign Host headers (DNS rebinding)
            and browser-declared cross-site requests. Any local process can still call this API."""
            port = self.server.server_port
            if self.headers.get("Host") not in (f"127.0.0.1:{port}", f"localhost:{port}"):
                self.send(403, {"error": "HOST_NOT_ALLOWED"}); return False
            if self.headers.get("Sec-Fetch-Site") not in (None, "same-origin", "none"):
                self.send(403, {"error": "CROSS_SITE_REQUEST_REFUSED"}); return False
            return True

        def do_GET(self):
            if not self.guard():
                return
            path = unquote(urlsplit(self.path).path)
            if path == "/api/session":
                return self.send(200, {"token": token, "mode": "LOCAL_SYNTHETIC_DEMO"})
            if path.startswith("/api/"):
                return self.api(path)
            target = (dist / (path.lstrip("/") or "index.html")).resolve()
            if not target.is_relative_to(dist) or not target.is_file():
                return self.send(404, {"error": "Asset not found. Build recall-ui first."})
            return self.send(200, target.read_bytes(), mimetypes.guess_type(target)[0] or "application/octet-stream")

        def do_POST(self):
            if not self.guard():
                return
            origin = self.headers.get("Origin")
            port = self.server.server_port
            if self.headers.get("X-Pramaan-Token") != token or (origin and origin not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}")):
                return self.send(403, {"error": "Local session token and same origin required"})
            return self.api(unquote(urlsplit(self.path).path), mutate=True)

        def checkpoint_required(self, snap):
            """Decision sub-resources carry no current claims outside ANCHORED_CURRENT."""
            return self.send(409, {"error": "CHECKPOINT_REQUIRED", "state": snap["checkpoint"]["state"], "checkpoint": snap["checkpoint"], "decisionsUnavailable": True})

        def api(self, path, mutate=False):
            started = time.perf_counter()
            with lock:
                app = None
                try:
                    app = Manufacturing(database,journal_cache=journal_cache,verification_deadline=time.monotonic()+1.25)
                    if mutate:
                        if anchor is None:
                            raise LedgerBlocked('Trusted external anchor required for operational commands')
                        anchor.verify(app)
                        length = int(self.headers.get("Content-Length", "0"))
                        if length <= 0 or length > 1024*1024:
                            raise ValidationFailure("JSON body must be 1..1048576 bytes")
                        body = json.loads(self.rfile.read(length))
                        if not isinstance(body, dict):
                            raise ValidationFailure("JSON object required")
                        parts = path.strip("/").split("/")
                        if path == "/api/units":
                            app.create_unit(body.get("serial"), body.get("title", "IE3 11 kW electric motor"))
                        elif path == "/api/recalls":
                            if set(body)-{'lot','affectedSlots'} or ('affectedSlots' in body and body['affectedSlots'] is None):
                                raise ValidationFailure('Unsupported or contradictory recall scope fields')
                            app.announce(body.get("lot"), body.get('affectedSlots'))
                        elif len(parts) == 4 and parts[:2] == ["api", "units"]:
                            motor, action = parts[2:]
                            if action == "assemble":
                                app.assemble(motor, body.get("deLot"), body.get("ndeLot"), body.get("identity", "SERIAL"))
                            elif action == "ship":
                                app.ship(motor)
                            elif action == "replace":
                                app.replace(motor, body.get("lot"), body.get("slot", "DE"))
                            elif action == "observe":
                                app.observe(motor, body.get("lot"), body.get("slot", "DE"))
                            else:
                                return self.send(404, {"error": "Unknown command"})
                        else:
                            return self.send(404, {"error": "Unknown command"})
                        snap = app.snapshot(trusted_anchor=anchor)
                        return self.send(200, {"snapshot": snap, "captureToDecisionMs": (time.perf_counter()-started)*1000})
                    if anchor is None and path != '/api/snapshot':
                        raise LedgerBlocked('Trusted external anchor required; only historical snapshot envelope available')
                    snap = app.snapshot(trusted_anchor=anchor)
                    if path == "/api/snapshot":
                        return self.send(200, snap)
                    if path == "/api/motors":
                        return self.send(200, snap["units"])
                    if path == "/api/notifications":
                        return self.send(200, snap["notifications"])
                    parts = path.strip("/").split("/")
                    if len(parts) == 4 and parts[:2] == ["api", "motors"]:
                        motor, resource = parts[2:]
                        if not any(u["unitId"] == motor for u in snap["units"]):
                            return self.send(404, {"error": "Unknown motor"})
                        if resource in ("decisions",) and snap["checkpoint"]["state"] != "ANCHORED_CURRENT":
                            return self.checkpoint_required(snap)
                        if resource == "genealogy":
                            return self.send(200, {"checkpoint": snap["checkpoint"], "relationships": [c for c in snap["components"] if c["unitId"] == motor], "lineage": [l for l in snap["lineage"] if l["unitId"] == motor], "unit": next(u for u in snap["units"] if u["unitId"] == motor)})
                        if resource == "decisions":
                            # Policy ids remain top-level keys; trust state travels with every decision payload.
                            return self.send(200, dict(snap["decisions"][motor], checkpoint=snap["checkpoint"], eligibility=snap["eligibility"][motor]))
                        if resource == "provenance":
                            rows = app.db.execute("SELECT c.hash,c.raw,c.received,e.id,e.source,e.seq,e.hash AS event_chain_hash,e.epcis FROM captures c JOIN events e ON e.capture=c.hash WHERE e.motor=? ORDER BY e.ordinal", (motor,)).fetchall()
                            return self.send(200, [{k: r[k] for k in r.keys() if not isinstance(r[k], bytes)} for r in rows])
                    if len(parts) == 4 and parts[:2] == ["api", "lots"] and parts[3] == "investigation":
                        if snap["checkpoint"]["state"] != "ANCHORED_CURRENT":
                            return self.checkpoint_required(snap)
                        return self.send(200, {"components": [c for c in snap["components"] if c["lot"] == parts[2]], "decisions": snap["decisions"],
                                               "checkpoint": snap["checkpoint"], "eligibility": snap["eligibility"]})
                    return self.send(404, {"error": "Unknown resource"})
                except LedgerBlocked as exc:
                    code=getattr(exc,'code','INTEGRITY_UNAVAILABLE')
                    return self.send(503 if code=='VERIFYING' else 409, {"error": code, "state": 'VERIFYING' if code=='VERIFYING' else 'ANCHOR_INVALID', "decisionsUnavailable": True})
                except ValidationFailure:
                    return self.send(400, {"error": 'INVALID_REQUEST'})
                except (ValueError, KeyError, TypeError):
                    # Client-input faults are 400 only on commands; a read that fails internally is a server integrity/availability fault.
                    if mutate:
                        return self.send(400, {"error": 'INVALID_REQUEST'})
                    return self.send(500, {"error": 'SNAPSHOT_UNAVAILABLE', "decisionsUnavailable": True})
                except Exception:
                    return self.send(500, {"error": "Application operation failed; no decision fallback supplied"})
                finally:
                    if app:
                        app.close()
    return LocalServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=str(ROOT / ".local" / "manufacturing.sqlite"))
    parser.add_argument("--port", type=int, default=4173)
    parser.add_argument("--seed-demo", action="store_true")
    parser.add_argument("--trusted-anchor", type=Path, help="Owner-custodied external anchor; mandatory for current operational decisions")
    parser.add_argument('--previous-anchor',type=Path,help='Previous owner-custodied checkpoint for successor activation')
    parser.add_argument('--lot-registry', type=Path, help='Locally authored synthetic lot registry (default: bundled application/lot_registry.synthetic.json)')
    args = parser.parse_args()
    try:
        server = make_server(args.database, args.port, args.seed_demo, trusted_anchor=args.trusted_anchor,previous_anchor=args.previous_anchor, lot_registry=args.lot_registry)
    except Exception:
        print(json.dumps(dict(error='STARTUP_UNAVAILABLE',decisionsUnavailable=True)),file=sys.stderr)
        raise SystemExit(1)
    print(f"Manufacturing PRAMAAN: http://127.0.0.1:{server.server_port} (local synthetic demo)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
