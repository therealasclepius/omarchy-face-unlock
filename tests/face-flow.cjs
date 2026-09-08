const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const assert = require('node:assert/strict');
const source = fs.readFileSync(path.join(__dirname, '..', 'Service.qml'), 'utf8');
const functions = ['stopFace', 'startFace', 'handleFaceFinished'].map(name => {
  const start = source.indexOf('  function ' + name + '(');
  const end = source.indexOf('\n  }', start) + 4;
  assert(start > 0 && end > start);
  return source.slice(start, end);
}).join('\n');
function context() {
  const c = {
    lockRequested: true, sessionLock: {secure: true}, faceConfigured: true,
    authenticatingPassword: false, faceAuthenticating: false,
    failureMessage: '', faceMessage: '', enteredPassword: '', unlocked: false, starts: 0,
    faceTimeout: {stop() {}, restart() {}},
    runWake() {}, logEvent() {}, finishUnlock() { c.unlocked = true; },
    PamResult: {Success: 0},
    facePam: {active: false, abort() {this.active = false;}, start() {c.starts++; return true;}}
  };
  vm.createContext(c); vm.runInContext(functions, c); return c;
}
for (const patch of [{lockRequested:false}, {sessionLock:{secure:false}}, {faceConfigured:false}, {authenticatingPassword:true}]) {
  const c = Object.assign(context(), patch); c.startFace(); assert.equal(c.starts, 0);
}
{
  const c = context(); c.startFace(); c.startFace(); assert.equal(c.starts, 1);
  c.handleFaceFinished(1); assert.equal(c.unlocked, false); assert.equal(c.faceAuthenticating, false);
  c.startFace(); c.handleFaceFinished(0); assert.equal(c.unlocked, true);
}
{
  const c = context(); c.startFace(); c.stopFace(); c.handleFaceFinished(0);
  assert.equal(c.unlocked, false, 'cancelled success must be ignored');
}
{
  const c = context(); c.startFace(); c.lockRequested = false; c.handleFaceFinished(0);
  assert.equal(c.unlocked, false, 'late result after password unlock must be ignored');
}
{
  const c = context(); c.facePam.start = () => false; c.startFace();
  assert.equal(c.faceAuthenticating, false); assert.equal(c.unlocked, false);
  assert.match(c.faceMessage, /unavailable/);
}
{
  const c = context(); c.startFace(); c.failureMessage = 'Wrong password';
  c.authenticatingPassword = true; c.enteredPassword = 'still typing';
  c.handleFaceFinished(1);
  assert.equal(c.failureMessage, 'Wrong password', 'face failure must not overwrite password feedback');
  assert.equal(c.enteredPassword, 'still typing');
  assert.match(c.faceMessage, /did not pass/);
}
{
  const c = context(); c.startFace(); c.facePam.active = true;
  c.stopFace('Cancelled');
  assert.equal(c.facePam.active, false, 'Escape must abort the PAM scan');
  assert.equal(c.faceMessage, 'Cancelled');
  c.handleFaceFinished(0); assert.equal(c.unlocked, false);
  c.startFace(); assert.equal(c.faceMessage, '', 'retry clears old face feedback');
}
console.log('Face flow checks passed: guards, failure, retry, success, cancellation, late results, start failure, password independence, feedback.');
