const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function deferred() {
  let resolve, reject;
  const promise = new Promise((a, b) => { resolve = a; reject = b; });
  return { promise, resolve, reject };
}
function setup() {
  const elements = {}, requests = [], hooks = [], notices = [];
  class Element {
    constructor(tag) { this.tagName = tag; this.children = []; this.style = {}; this.classList = { add() {}, remove() {} }; }
    appendChild(child) {
      if (child.tagName === '#fragment') this.children.push(...child.children);
      else this.children.push(child);
    }
    set innerHTML(value) { this.html = value; this.children = []; }
    get innerHTML() { return this.html || ''; }
  }
  elements.panelHost = new Element('main');
  const c = {
    console, Date, Promise, URLSearchParams, AbortController,
    document: {
      hidden: false, querySelectorAll: () => [], querySelector: () => null, addEventListener() {},
      getElementById: id => elements[id] || null,
      createElement: tag => new Element(tag), createDocumentFragment: () => new Element('#fragment')
    },
    location: { hash: '#overview' }, addEventListener() {},
    setTimeout: () => 1, clearTimeout() {}, setInterval() {}, clearInterval() {},
    fetch(url, options) {
      const d = deferred(); requests.push({ url, options, ...d }); return d.promise;
    }
  };
  c.window = c;
  vm.createContext(c);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../code/web_src/app.js'), 'utf8'), c);
  c.panelHook = name => hooks.push(name);
  c.showToast = (message, kind) => notices.push({ message, kind });
  return { c, elements, requests, hooks, notices, Element };
}
const settle = () => new Promise(resolve => setImmediate(resolve));
const templateReply = text => ({ ok: true, text: () => Promise.resolve(text) });
const configReply = data => ({ ok: true, json: () => Promise.resolve(data) });

async function parallelLoad() {
  const { c, elements, requests, hooks } = setup();
  c.switchPanel('settings');
  assert.equal(requests.length, 2, '配置尚未返回时必须已经开始下载模板');
  const config = requests.find(r => r.url.startsWith('/config.json'));
  const template = requests.find(r => r.url.startsWith('/ui?'));
  assert.equal(template.options.cache, 'default');
  template.resolve(templateReply('<input value="%WEB_USER%">'));
  await settle();
  assert.equal(hooks.length, 0, '表单必须等配置返回后再渲染');
  config.resolve(configReply({ webUser: 'a&b', tzOffsetMin: 60 }));
  await settle();
  assert.equal(elements.panelHost.innerHTML, '<input value="a&amp;b">');
  assert.equal(c.devTz, 60);
  assert.deepEqual(hooks, ['settings']);
  c.switchPanel('settings');
  await settle();
  assert.equal(requests.length, 2, '再次进入应复用模板和配置');
}
async function independentPagesAndNavigationRace() {
  for (const name of ['overview', 'log', 'atterm']) {
    const { c, requests, hooks } = setup();
    c.switchPanel(name);
    assert.equal(requests.length, 1, name + ' 不应依赖配置接口');
    requests[0].resolve(templateReply('<div>ready</div>'));
    await settle();
    assert.deepEqual(hooks, [name]);
  }
  const { c, elements, requests, hooks } = setup();
  c.switchPanel('overview');
  c.switchPanel('log');
  assert.equal(requests[0].options.signal.aborted, true);
  requests[1].resolve(templateReply('new log'));
  await settle();
  requests[0].resolve(templateReply('old overview'));
  await settle();
  assert.equal(elements.panelHost.innerHTML, 'new log');
  assert.deepEqual(hooks, ['log']);
}
function lazyForms() {
  const { c } = setup();
  const calls = [];
  for (const name of ['buildPushChannels', 'buildWifiNetworks', 'buildSimCredentials', 'buildTzOptions', 'buildWifiTxPowerOptions']) {
    c[name] = () => { calls.push(name); return name; };
  }
  c.webConfig = { webUser: 'admin' };
  assert.equal(c.renderConfigTemplate('plain page'), 'plain page');
  assert.equal(c.renderConfigTemplate('%WEB_USER% %UNKNOWN_TOKEN%'), 'admin %UNKNOWN_TOKEN%');
  assert.equal(calls.length, 0, '普通页面不能生成无关表单');
  assert.equal(c.renderConfigTemplate('%PUSH_CHANNELS% %PUSH_CHANNELS%'), 'buildPushChannels buildPushChannels');
  assert.deepEqual(calls, ['buildPushChannels'], '同一表单只生成一次');
}
async function inboxRaceAndCopy() {
  const { c, elements, requests, Element } = setup();
  elements.inboxList = new Element('div');
  elements.smsSearch = { value: '' };
  c.currentPanel = 'inbox';
  c.loadMessages();
  c.loadMessages();
  assert.equal(requests[0].options.signal.aborted, true);
  const newer = [{ id: 2, sender: 'AUTH', text: 'Your verification code is 482913', recv: 1783056400, fwd: true }];
  requests[1].resolve(configReply(newer));
  await settle();
  requests[0].resolve(configReply([{ id: 1, text: 'old' }]));
  await settle();
  assert.equal(c.__msgFull[0].id, 2, '旧刷新不能覆盖最新收件箱');
  const otp = elements.inboxList.children[0].children[0].children[1].children[0];
  assert.equal(otp.textContent, '482913', '验证码应只显示数字');
  let copied = '', stopped = false;
  c.copyText = text => { copied = text; };
  otp.onclick({ stopPropagation() { stopped = true; } });
  assert.equal(copied, '482913');
  assert.equal(stopped, true);
  elements.smsSearch.value = 'no match';
  c.renderMessages();
  assert.equal(c.__msgCache.length, 0, '空搜索应清理抽屉查找缓存');
  c.loadMessages();
  c.cleanupPanelRuntime();
  requests[2].reject(new Error('offline'));
  await settle();
}
(async () => {
  lazyForms();
  await parallelLoad();
  await independentPagesAndNavigationRace();
  await inboxRaceAndCopy();
  console.log('web loading, lazy forms, navigation races and OTP copy regressions passed');
})().catch(e => { console.error(e); process.exitCode = 1; });
