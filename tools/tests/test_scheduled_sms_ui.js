// 直接执行实际网页脚本，覆盖任务切换、删除和重新添加时的字段状态。
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const elements = {};
function element() { return {style: {}, classList: {toggle() {}}, value: '', checked: false, appendChild() {}}; }
elements.stForm = element();
const document = {
  getElementById: id => elements[id] || null,
  querySelectorAll: () => [], querySelector: () => null, addEventListener() {},
  createElement: () => element()
};
const context = {document, window: {addEventListener() {}}, location: {hash: ''},
  localStorage: {getItem: () => null}, setTimeout: () => 0, clearTimeout() {},
  setInterval: () => 0, clearInterval() {}, confirm: () => true, console};
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(__dirname, '../../code/web_src/app.js'), 'utf8'), context);
for (let i = 0; i < 6; i++) {
  const card = context.stBuildCard(i);
  elements['stTask' + i] = card;
  const html = card.innerHTML;
  for (const suffix of ['Time', 'Sys', 'Reply', 'Sender', 'Body', 'Timeout']) {
    assert(html.includes('name="st' + i + suffix + '"'));
    assert(html.includes('id="st' + i + suffix + '"'));
  }
  for (const match of html.matchAll(/id="([^"]+)"/g)) elements[match[1]] = element();
  elements['st' + i + 'Act'].value = '2';
  elements['st' + i + 'Sys'].checked = true;
  elements['st' + i + 'Reply'].checked = true;
  context.stSyncAction(i);
  assert.equal(elements['st' + i + 'Health'].style.display, '');
  assert.equal(elements['st' + i + 'Reply'].checked, true);
  elements['st' + i + 'Act'].value = '0';
  context.stSyncAction(i);
  assert.equal(elements['st' + i + 'Health'].style.display, 'none');
  assert.equal(elements['st' + i + 'Sys'].checked, false);
  assert.equal(elements['st' + i + 'Reply'].checked, false);
  elements['st' + i + 'Sender'].value = '^10086$';
  elements['st' + i + 'Body'].value = '余额为.*元';
  elements['st' + i + 'Time'].value = '08:00';
  elements['st' + i + 'Timeout'].value = 60;
  context.stRemove(i);
  for (const suffix of ['Sender', 'Body', 'Time']) assert.equal(elements['st' + i + suffix].value, '');
  assert.equal(elements['st' + i + 'Timeout'].value, 300);
  assert.equal(elements['st' + i + 'Reply'].checked, false);
  assert.equal(card.style.display, 'none');
}
assert.equal(elements.stForm.hidden, false, '删除最后一个任务后仍可保存空配置');
context.stDirty = false;
context.stShow(0, false);
assert.equal(elements.stForm.hidden, true, '没有任务或待保存删除时隐藏空表单');
// 首次加载完成前禁止添加；后续状态刷新只更新执行状态，保留未保存编辑。
const settle = () => new Promise(resolve => setImmediate(resolve));
(async () => {
  const pending = [];
  context.stBuilt = true;
  context.currentPanel = 'keepalive';
  elements.stAddBtn = element();
  elements.stAddBtn.disabled = true;
  elements.stForm.appendChild = child => {elements[child.id] = child;};
  context.fetch = url => url.startsWith('/schedtask')
    ? new Promise(resolve => pending.push(data => resolve({ok: true, json: async () => data})))
    : Promise.resolve({ok: true, json: async () => ({profiles: []})});
  context.stAddTask();
  assert.equal(elements.stTask0.style.display, 'none');
  context.stLoadStatus();
  pending.shift()({tasks: [{enabled: true, name: '已保存任务', intervalDays: 30, action: '0', switchBack: true}], timeValid: true});
  await settle();
  assert.equal(elements.st0Name.value, '已保存任务');
  assert.equal(elements.stAddBtn.disabled, false);
  assert.ok(elements.stFormFlag);
  elements.st0Name.value = '用户新名称';
  elements.st0En.checked = false;
  context.stLoadStatus();
  pending.shift()({tasks: [{enabled: true, name: '服务端旧名称', intervalDays: 30, action: '0'}], timeValid: true});
  await settle();
  assert.equal(elements.st0Name.value, '用户新名称');
  assert.equal(elements.st0En.checked, false);
  console.log('scheduled SMS UI regressions passed (6 slots, loading guard and preserved edits)');
})().catch(error => {console.error(error); process.exit(1);});
