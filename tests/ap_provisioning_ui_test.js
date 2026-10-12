// 执行实际配网页脚本，验证名称回填、保存、连接反馈和断网重试。
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const settle = () => new Promise(resolve => setImmediate(resolve));
const source = fs.readFileSync(path.join(__dirname, '../code/web_src/ap.html'), 'utf8').match(/<script>([\s\S]*?)<\/script>/)[1];

function page({ host = 'existing-sms', deferInitial = false, failPoll = false, savedHost } = {}) {
  const elements = {}, posts = [], intervals = new Map();
  let nextId = 1, statusCalls = 0, resolveInitial;
  for (const id of ['sel', 'ssid', 'pass', 'passToggle', 'scanBtn', 'saveBtn', 'mdnsHost', 'mdnsPreview', 'msg']) {
    elements[id] = { value: '', disabled: false, textContent: '', focus() {}, setAttribute() {}, replaceChildren() {}, appendChild() {} };
  }
  elements.mdnsHost.value = 'sms';
  elements.sel.hidden = true;
  const context = {
    Date, Promise, encodeURIComponent,
    document: { getElementById: id => elements[id], createElement: () => ({}) },
    setInterval(fn, delay) { const id = nextId++; intervals.set(id, { fn, delay }); return id; },
    clearInterval(id) { intervals.delete(id); },
    fetch: async (url, options) => {
      if (url.startsWith('/wifiscan')) return { json: async () => [{ ssid: 'Home WiFi', rssi: -42, enc: true }] };
      if (url.startsWith('/apstatus')) {
        statusCalls++;
        if (statusCalls === 1 && deferInitial) return new Promise(resolve => { resolveInitial = data => resolve({ json: async () => data }); });
        if (statusCalls > 1 && failPoll) throw new Error('热点连接中断');
        return { json: async () => ({ mdnsHost: host, connected: posts.length > 0, ip: '192.168.1.50' }) };
      }
      assert.equal(url, '/wificonfig');
      assert.equal(options.headers['X-SMS-CSRF'], '1');
      const fields = new URLSearchParams(options.body);
      posts.push(fields);
      host = savedHost || fields.get('mdnsHost');
      return { json: async () => ({ success: true, mdnsHost: host }) };
    }
  };
  vm.createContext(context);
  vm.runInContext(source, context);
  return { context, elements, posts, resolveInitial: data => resolveInitial(data),
    async tick(delay) { for (const [id, timer] of [...intervals]) { if (timer.delay === delay && intervals.has(id)) timer.fn(); } await settle(); }
  };
}

(async () => {
  const p = page(); await settle();
  assert.equal(p.elements.mdnsHost.value, 'existing-sms');
  assert.match(p.elements.mdnsPreview.textContent, /existing-sms.local/);
  assert.equal(p.elements.sel.hidden, true);
  p.context.scan(); await settle();
  assert.equal(p.elements.sel.hidden, false);
  assert.equal(p.elements.scanBtn.disabled, false);
  p.elements.sel.value = 'Home WiFi'; p.elements.sel.onchange();
  assert.equal(p.elements.ssid.value, 'Home WiFi');
  p.elements.ssid.value = 'Home WiFi';
  p.elements.pass.value = 'test-password';
  p.elements.mdnsHost.value = 'Office-SMS';
  p.elements.mdnsHost.oninput();
  assert.match(p.elements.mdnsPreview.textContent, /office-sms.local/);
  p.context.save(); await settle();
  assert.equal(p.posts[0].get('mdnsHost'), 'office-sms');
  assert.equal(p.posts[0].get('ssid'), 'Home WiFi');
  assert.equal(p.posts[0].get('pass'), 'test-password');
  p.context.save(); assert.equal(p.posts.length, 1);
  await p.tick(1500);
  assert.equal(p.elements.saveBtn.textContent, '已连接');
  assert.match(p.elements.msg.textContent, /192\.168\.1\.50.*office-sms\.local/);
  for (let i = 0; i < 15; i++) await p.tick(1000);
  assert.match(p.elements.msg.textContent, /热点已关闭.*192\.168\.1\.50.*office-sms\.local/);

  for (const host of ['-bad', 'bad-', 'with space', '中文', 'sms.local', 'x'.repeat(33)]) {
    const invalid = page(); await settle();
    invalid.elements.ssid.value = 'WiFi'; invalid.elements.mdnsHost.value = host;
    invalid.context.save(); await settle();
    assert.equal(invalid.posts.length, 0);
    assert.match(invalid.elements.msg.textContent, /设备名称需/);
  }
  const empty = page({ savedHost: 'actual-name' }); await settle();
  empty.elements.ssid.value = 'WiFi'; empty.elements.mdnsHost.value = '';
  empty.context.save(); await settle();
  assert.equal(empty.posts[0].get('mdnsHost'), 'sms');
  await empty.tick(1500);
  assert.match(empty.elements.msg.textContent, /actual-name.local/);

  const edited = page({ deferInitial: true });
  edited.elements.mdnsHost.value = 'typing'; edited.elements.mdnsHost.oninput();
  edited.resolveInitial({ mdnsHost: 'old-name' }); await settle();
  assert.equal(edited.elements.mdnsHost.value, 'typing');
  const submitted = page({ deferInitial: true });
  submitted.elements.ssid.value = 'WiFi'; submitted.context.save(); await settle();
  submitted.resolveInitial({ mdnsHost: 'old-name' }); await settle();
  assert.equal(submitted.elements.mdnsHost.value, 'sms');

  const offline = page({ failPoll: true }); await settle();
  offline.elements.ssid.value = 'WiFi'; offline.context.save(); await settle();
  for (let i = 0; i < 24; i++) await offline.tick(1500);
  assert.equal(offline.elements.saveBtn.disabled, false);
  assert.match(offline.elements.msg.textContent, /连接超时/);
  console.log('AP mDNS prefill, validation, saving and connection feedback passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
