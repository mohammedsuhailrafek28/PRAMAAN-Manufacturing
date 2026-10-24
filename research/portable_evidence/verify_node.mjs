// Independent verifier for PRAMAAN-EVIDENCE/1 written against RFC 9901 / RFC 8037 directly, using only Node's built-in `crypto` (OpenSSL Ed25519).
// It shares no code with application/evidence_verify.py.   usage: node verify_node.mjs corpus.json  -> JSON array of {name, accepted, failure, claims}
import { createHash, createPublicKey, verify } from 'node:crypto';
import { readFileSync } from 'node:fs';

const FINDINGS = ['AFFECTED', 'EXCLUDED_WITH_EVIDENCE', 'UNRESOLVED'];
const CUSTOMER = ['motorSerial', 'recallId', 'evidenceFinding', 'operationalAction'];
const PROFILES = {
  customer: CUSTOMER,
  supplier: ['recallId', 'part', 'lot', 'slot', 'supplierId', 'evidenceFinding', 'operationalAction'],
  auditor: [...CUSTOMER, 'part', 'lot', 'slot', 'supplierId', 'installEventId', 'decisionId', 'policyDigest', 'registryDigest', 'headHash', 'sequence', 'eventRow', 'eventRowIndex'],
};
const FIELDS = new Set(['iss', 'aud', 'iat', 'exp', 'jti', '_sd_alg', '_sd', 'format', 'profile', 'purpose', 'binding']);
const b64uRe = /^[A-Za-z0-9_-]*$/;
class Reject extends Error { constructor(code) { super(code); this.code = code; } }
const dec = (s) => {
  if (!b64uRe.test(s) || s.length % 4 === 1) throw new Reject('B64');
  const b = Buffer.from(s, 'base64url');
  if (b.toString('base64url') !== s) throw new Reject('B64');
  return b;
};
const json = (b) => { try { return JSON.parse(b.toString('utf8')); } catch { throw new Reject('JSON'); } };

function check(token, key, kid, recipient, now) {
  if (typeof token !== 'string' || !token.endsWith('~')) throw new Reject('SDJWT');
  const [jwt, ...discs] = token.slice(0, -1).split('~');
  const [h, p, s, extra] = jwt.split('.');
  if (p === undefined || s === undefined || extra !== undefined) throw new Reject('JWS');
  const header = json(dec(h));
  if (Object.keys(header).some((k) => !['alg', 'typ', 'kid'].includes(k)) || header.alg !== 'EdDSA' || header.typ !== 'pramaan-evidence+sd-jwt' || header.kid !== kid) throw new Reject('HEADER');
  const sig = dec(s);
  if (sig.length !== 64 || !verify(null, Buffer.from(`${h}.${p}`, 'ascii'), key, sig)) throw new Reject('SIG');
  const payload = json(dec(p));
  if (payload === null || typeof payload !== 'object' || Array.isArray(payload)) throw new Reject('PAYLOAD');
  const allNames = new Set(Object.values(PROFILES).flat());
  if (Object.keys(payload).some((k) => !FIELDS.has(k) || allNames.has(k))) throw new Reject('PAYLOAD_FIELD');
  const allowed = PROFILES[payload.profile];
  if (!allowed || payload._sd_alg !== 'sha-256' || !Array.isArray(payload._sd) || new Set(payload._sd).size !== payload._sd.length) throw new Reject('SD');
  const claims = {};
  const seen = new Set();
  for (const d of discs) {
    if (seen.has(d)) throw new Reject('DUP_DISC');
    seen.add(d);
    const item = json(dec(d));
    if (!Array.isArray(item) || item.length !== 3 || typeof item[0] !== 'string' || typeof item[1] !== 'string' || item[0].length < 16) throw new Reject('DISC');
    const [, name, value] = item;
    if (name === '_sd' || name === '...' || !allowed.includes(name) || name in claims) throw new Reject('NAME');
    if (!payload._sd.includes(createHash('sha256').update(d, 'ascii').digest('base64url'))) throw new Reject('UNCOMMITTED');
    claims[name] = value;
  }
  if (claims.operationalAction !== undefined && claims.operationalAction !== 'RECALL_HOLD') throw new Reject('ACTION');
  if (claims.evidenceFinding !== undefined && !FINDINGS.includes(claims.evidenceFinding)) throw new Reject('FINDING');
  if (recipient !== null && payload.aud !== recipient) throw new Reject('AUD');
  const { iat, exp } = payload;
  if (!Number.isInteger(iat) || !Number.isInteger(exp) || exp <= iat || exp - iat > 7 * 86400) throw new Reject('EXP');
  const at = now ?? Math.floor(Date.now() / 1000);
  if (at < iat - 60) throw new Reject('NYV');
  if (at >= exp) throw new Reject('EXPIRED');
  if (payload.binding?.state !== 'ANCHORED_CURRENT') throw new Reject('BINDING');
  return claims;
}

const corpus = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const key = createPublicKey({ key: { kty: 'OKP', crv: 'Ed25519', x: corpus.issuerKey.x }, format: 'jwk' });
const out = corpus.cases.map((c) => {
  try { return { name: c.name, accepted: true, failure: null, claims: check(c.token, key, corpus.issuerKey.kid, c.recipient, c.now) }; }
  catch (e) { return { name: c.name, accepted: false, failure: e instanceof Reject ? e.code : 'CRASH:' + e.message, claims: {} }; }
});
console.log(JSON.stringify(out));
