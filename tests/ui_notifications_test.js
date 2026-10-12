// 执行真实业务函数，验证异步反馈进入统一 toast，卡片不再新增结果区。
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const settle = () => new Promise(resolve => setImmediate(resolve));
const elements = {}, timers = new Map();
let timerId = 0, response = () => ({success: true, message: '操作完成'});
function element() {
  const el = {value: '', textContent: '', className: '', style: {}, attrs: {}, children: [],
    appendChild(child) {this.children.push(child); if (child.id) elements[child.id] = child;},
    setAttribute(key, value) {this.attrs[key] = value;}};
  el.classList = {
    contains: value => el.className.split(' ').includes(value),
    remove: value => {el.className = el.className.split(' ').filter(item => item !== value).join(' ');},
    add: value => {el.className += ' ' + value;}
  };
  return el;
}
for (const id of ['pingUrl', 'pingBtn', 'pingResult', 'ussdCode', 'ussdResult', 'ntpBtn', 'ntpResult', 'otaFile', 'smsPhone', 'smsContent', 'smsSendResult']) elements[id] = element();
elements.pingUrl.value = 'https://example.com/payload';
elements.ussdCode.value = '*122#';
elements.otaFile.files = [];
const context = {console, Date, Promise, URLSearchParams,
  document: {body: element(), getElementById: id => elements[id] || null, createElement: element,
    querySelectorAll: () => [], addEventListener() {}},
  addEventListener() {},
  setTimeout(fn, delay) {const id = ++timerId; timers.set(id, {fn, delay}); return id;},
  clearTimeout(id) {timers.delete(id);}, setInterval() {}, clearInterval() {},
  fetch: async url => ({ok: true, json: async () => response(url)})};
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(__dirname, '../code/web_src/app.js'), 'utf8'), context);
function toast() {return elements.saveToast;}
(async () => {
  response = url => ({success: true, running: !url.includes('action=status'), message: '下载成功'});
  context.doPing();
  assert.equal(elements.pingResult.hidden, true);
  assert(toast().classList.contains('loading'));
  assert.equal(timers.size, 0, '执行中提示保持可见');
  await settle(); await settle();
  assert(toast().classList.contains('ok'));
  assert.match(toast()._message.textContent, /payload 下载完成/);
  assert.equal(toast().attrs.role, 'status');
  assert.equal(context.document.body.children.length, 1);
  Object.defineProperty(toast(), 'offsetWidth', {get() {throw new Error('toast 不应强制重排');}});
  response = () => ({success: false, message: '运营商拒绝查询'});
  context.sendUssd(); await settle();
  assert.equal(elements.ussdResult.hidden, true);
  assert(toast().classList.contains('err'));
  assert.equal(toast().attrs.role, 'alert');
  assert.equal(toast()._message.textContent, '运营商拒绝查询');
  assert.equal([...timers.values()][0].delay, 8000);
  response = () => ({success: true, message: '时间已同步'});
  context.ntpSync(); await settle();
  assert.equal(elements.ntpBtn.disabled, false);
  assert.equal(elements.ntpResult.hidden, true);
  assert.equal(toast()._message.textContent, '时间已同步');
  context.doOta();
  assert(toast().classList.contains('err'));
  assert.match(toast()._message.textContent, /选择 .bin/);
  context.sendSmsModal();
  assert.match(toast()._message.textContent, /请输入目标号码/);
  context.showSaved(true);
  assert(toast().classList.contains('ok'));
  assert.equal(toast()._message.textContent, '已保存');
  assert.equal(context.document.body.children.length, 1, '跨页面操作复用一个全局 toast');
  toast().children[2].onclick();
  assert.equal(toast().classList.contains('show'), false);
  assert.equal(timers.size, 0);
  console.log('global UI notification regressions passed');
})().catch(error => {console.error(error); process.exit(1);});
