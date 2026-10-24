// Independent verifier for PRAMAAN-FED/1 envelopes using only Node's built-in `crypto` (OpenSSL Ed25519) and its own RFC 8785 canonicalisation for the value types used here
// (objects, arrays, strings, integers, booleans, null). Shares no code with application/federation/messages.py.
// usage: node verify_node.mjs corpus.json  -> JSON array of {name, accepted}
import { createPublicKey, verify } from 'node:crypto';
import { readFileSync } from 'node:fs';

const FORMAT = 'PRAMAAN-FED/1';
const ALERT = ['type', 'alertId', 'issuer', 'seq', 'prevHash', 'iat', 'exp', 'lot', 'affectedSlots', 'humanText', 'recipients'];
const ALERT_REQUIRED = ['type', 'alertId', 'issuer', 'seq', 'prevHash', 'iat', 'exp', 'lot', 'affectedSlots', 'humanText'];
const RESPONSE = ['type', 'responseId', 'alertId', 'alertHash', 'responder', 'seq', 'prevHash', 'iat', 'status', 'counts', 'asOfCheckpoint'];

function jcs(v) {
  if (v === null || typeof v === 'boolean' || typeof v === 'string') return JSON.stringify(v);
  if (typeof v === 'number') { if (!Number.isInteger(v)) throw new Error('non-integer'); return JSON.stringify(v); }
  if (Array.isArray(v)) return '[' + v.map(jcs).join(',') + ']';
  return '{' + Object.keys(v).sort().map((k) => JSON.stringify(k) + ':' + jcs(v[k])).join(',') + '}';
}
const same = (a, b) => a.length === b.length && a.every((x) => b.includes(x));

function check(c, now) {
  const env = c.envelope;
  if (env === null || typeof env !== 'object' || !same(Object.keys(env), ['format', 'kid', 'body', 'signature']) || env.format !== FORMAT) return false;
  const body = env.body;
  if (body === null || typeof body !== 'object' || Array.isArray(body) || body.type !== c.kind) return false;
  const who = c.kind === 'ALERT' ? body.issuer : body.responder;
  const peer = typeof who === 'string' ? c.pinned[who] : undefined;
  if (!peer || peer.role !== (c.kind === 'ALERT' ? 'supplier' : 'factory') || env.kid !== peer.kid) return false;
  if (typeof env.signature !== 'string' || !/^[A-Za-z0-9_-]*$/.test(env.signature)) return false;
  const sig = Buffer.from(env.signature, 'base64url');
  if (sig.length !== 64 || sig.toString('base64url') !== env.signature) return false;
  let message;
  try { message = Buffer.concat([Buffer.from(FORMAT + '\0', 'ascii'), Buffer.from(jcs(body), 'utf8')]); } catch { return false; }
  const key = createPublicKey({ key: { kty: 'OKP', crv: 'Ed25519', x: peer.x }, format: 'jwk' });
  if (!verify(null, message, key, sig)) return false;
  const keys = Object.keys(body);
  if (c.kind === 'ALERT') {
    if (keys.some((k) => !ALERT.includes(k)) || ALERT_REQUIRED.some((k) => !keys.includes(k))) return false;
    if (!Number.isInteger(body.iat) || !Number.isInteger(body.exp) || body.exp <= body.iat || body.exp - body.iat > 7 * 86400) return false;
    if (now < body.iat - 60 || now >= body.exp) return false;
  } else {
    if (!same(keys, RESPONSE)) return false;
    const { status, counts } = body;
    if (status === 'ANSWERED') {
      const by = counts && counts.heldByEvidenceFinding;
      if (counts === null || typeof counts !== 'object' || !same(Object.keys(counts), ['heldMotors', 'heldByEvidenceFinding', 'heldOnlyByIdentityGuard'])) return false;
      if (!by || !same(Object.keys(by), ['AFFECTED', 'UNRESOLVED', 'EXCLUDED_WITH_EVIDENCE']) || Object.values(by).some((n) => !Number.isInteger(n) || n < 0)) return false;
      if (!Number.isInteger(counts.heldMotors) || Object.values(by).reduce((a, b) => a + b, 0) !== counts.heldMotors) return false;
      if (!Number.isInteger(counts.heldOnlyByIdentityGuard) || counts.heldOnlyByIdentityGuard < 0 || counts.heldOnlyByIdentityGuard > counts.heldMotors) return false;
    } else if (counts !== null || body.asOfCheckpoint !== null) return false;
  }
  return true;
}

const corpus = JSON.parse(readFileSync(process.argv[2], 'utf8'));
console.log(JSON.stringify(corpus.cases.map((c) => { let ok = false; try { ok = check(c, corpus.now); } catch { ok = false; } return { name: c.name, accepted: ok }; })));
