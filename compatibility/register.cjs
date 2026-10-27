// Node-only resolution of the stable frontend's existing @/ imports after test compilation.
// This does not participate in the Next application or change its bundler/alias configuration.
const Module = require('node:module');
const path = require('node:path');
const original = Module._resolveFilename;
Module._resolveFilename = function (request, parent, ...args) {
  const resolved = request.startsWith('@/')
    ? path.resolve(__dirname, '../.local/frontend-compat-compiled/src', request.slice(2)) : request;
  return original.call(this, resolved, parent, ...args);
};
