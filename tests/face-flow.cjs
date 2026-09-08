const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const assert = require('node:assert/strict');
const source = fs.readFileSync(path.join(__dirname, '..', 'Service.qml'), 'utf8');
const functions = ['stopFace', 'startFace', 'handleFaceFinished', 'scheduleAutoFace', 'handleUserWake'].map(name => {
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
    autoFacePending: true, displayBlanked: false,
    autoFaceTimer: {running: false, start() {this.running = true;}, stop() {this.running = false;}},
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

for (const patch of [{lockRequested:false}, {sessionLock:{secure:false}}, {faceConfigured:false}, {authenticatingPassword:true}, {enteredPassword:'typing'}, {displayBlanked:true}, {autoFacePending:false}]) {
  const c = Object.assign(context(), patch); c.scheduleAutoFace();
  assert.equal(c.autoFaceTimer.running, false, 'automatic scan must honor readiness, cancellation, blanking and password guards');
}
{
  const c = context(); c.scheduleAutoFace(); assert.equal(c.autoFaceTimer.running, true);
  c.startFace(); assert.equal(c.starts, 1); assert.equal(c.autoFacePending, false);
  c.handleFaceFinished(1); c.scheduleAutoFace(); assert.equal(c.autoFaceTimer.running, false, 'no endless retries');
}
{
  const c = context(); c.scheduleAutoFace(); c.stopFace('Cancelled'); c.scheduleAutoFace();
  assert.equal(c.autoFaceTimer.running, false, 'Escape cancels a queued scan');
  c.displayBlanked = true; c.handleUserWake();
  assert.equal(c.displayBlanked, false); assert.equal(c.autoFaceTimer.running, true, 'waking blanked display schedules a fresh scan');
}
{
  const c = context(); c.stopFace('Cancelled'); c.handleUserWake();
  assert.equal(c.autoFaceTimer.running, false, 'ordinary mouse movement cannot undo cancellation');
}
console.log('Automatic scan checks passed: readiness, password typing, cancellation, wake and bounded attempts.');
