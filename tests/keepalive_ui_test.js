// 执行实际网页脚本，验证状态回填、表单保存和重新加载不会改写 URL。
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const settle = () => new Promise(resolve => setImmediate(resolve));
function app(initialUrl, deferStatus = false) {
  let savedUrl = initialUrl;
  const posts = [], listeners = {}, pending = [];
  const elements = {};
  const input = () => ({ value: '', checked: false, dataset: {}, classList: { add() {}, remove() {}, toggle() {} } });
  for (const id of ['kaUrl', 'pingUrl', 'kaEnabled', 'kaIntervalDays', 'kaAction', 'kaTarget', 'kaCard']) elements[id] = input();
  elements.kaForm = {
    id: 'kaForm', dataset: {}, getAttribute: name => name === 'action' ? '/save' : null,
    querySelector: () => null,
    appendChild: child => { elements[child.id] = child; }
  };
  const context = {
    console, Date, Promise, URLSearchParams,
    document: {
      getElementById: id => elements[id] || null, querySelectorAll: () => [],
      createElement: () => input(), addEventListener: (name, callback) => { listeners[name] = callback; }
    },
    FormData: class {
      constructor(form) {
        assert.equal(form, elements.kaForm);
        this.values = new URLSearchParams({ kaForm: elements.kaFormFlag.value, kaUrl: elements.kaUrl.value });
      }
      forEach(callback) { this.values.forEach(callback); }
      get(key) { return this.values.get(key); }
    },
    addEventListener() {}, setTimeout: () => 1, clearTimeout() {}, setInterval() {}, clearInterval() {},
    fetch: async (url, options) => {
      if (deferStatus && url.startsWith('/keepalive')) return new Promise(resolve => pending.push(data => resolve({ok: true, json: async () => data})));
      if (url === '/save') {
        assert.equal(options.method, 'POST');
        const fields = new URLSearchParams(options.body.toString());
        assert.equal(fields.get('kaForm'), '1');
        savedUrl = fields.get('kaUrl');
        posts.push(savedUrl);
      }
      return { ok: true, json: async () => url.startsWith('/keepalive') ? { url: savedUrl } : {} };
    }
  };
  context.window = context;
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../code/web_src/app.js'), 'utf8'), context);
  return { context, elements, posts, listeners, pending };
}
(async () => {
  const urls = [
    'http://gg.incrafttime.top/api/payload?size=128684',
    'https://gg.incrafttime.top/api/payload?size=64342',
    'http://gg.incrafttime.top/api/payload?size=1286840',
    'http://gg.incrafttime.top/api/payload?x=a%2Fb&size=100000&x=z',
    'http://example.com/api/payload?size=128684',
    'http://example.com/gg.incrafttime.top/api/payload?size=128684',
    'http://gg.incrafttime.top.evil.test/api/payload?size=128684',
    'http://gg.incrafttime.top/'
  ];
  for (const url of urls) {
    const { context: c, elements: e, posts, listeners } = app(url);
    c.kaLoadStatus(); await settle();
    assert.equal(e.kaUrl.value, url);
    assert.equal(e.pingUrl.value, url);
    assert.ok(e.kaFormFlag);
    // 真实保存按钮事件，以及立即执行前的局部保存，均应提交用户输入。
    e.kaUrl.value = url;
    listeners.submit({ target: e.kaForm, preventDefault() {} });
    await settle();
    assert.equal(posts[0], url);
    e.kaUrl.value = ''; e.pingUrl.value = '';
    // 模拟重新打开页面：首次状态回填标志随旧 DOM 一起销毁。
    delete e.kaFormFlag;
    c.kaLoadStatus(); await settle();
    assert.equal(e.kaUrl.value, url);
    assert.equal(e.pingUrl.value, url);
    assert.equal(await c.kaSaveForm(), true);
    assert.equal(posts[1], url);
  }
  const {context: c, elements: e, pending, listeners} = app('https://example.com/payload', true);
  c.kaLoadStatus();
  e.kaEnabled.checked = true;
  e.kaUrl.value = 'https://example.com/edited';
  pending.shift()({enabled: false, intervalDays: 175, action: 1, target: 'saved-target', url: 'https://example.com/saved'});
  await settle();
  assert.equal(e.kaEnabled.checked, true, '迟到回填不能把用户开关改回去');
  assert.equal(e.kaUrl.value, 'https://example.com/edited');
  assert.equal(e.kaTarget.value, 'saved-target', '未编辑字段仍须完整回填');
  assert.equal(e.kaIntervalDays.value, 175);
  assert.ok(e.kaFormFlag);
  e.kaEnabled.checked = false;
  e.kaIntervalDays.value = 90;
  c.kaLoadStatus();
  pending.shift()({enabled: true, intervalDays: 175, url: 'https://example.com/saved'});
  await settle();
  assert.equal(e.kaEnabled.checked, false, '刷新执行状态不能覆盖未保存配置');
  assert.equal(e.kaIntervalDays.value, 90);
  c.kaLoadStatus();
  const previousRequest = pending.shift();
  c.kaLoadStatus();
  pending.shift()({url: 'https://example.com/latest'});
  await settle();
  previousRequest({url: 'https://example.com/stale'});
  await settle();
  assert.equal(e.pingUrl.value, 'https://example.com/latest', '旧请求不能覆盖新请求');
  delete e.kaFormFlag;
  c.kaLoadStatus();
  e.kaEnabled.checked = true; listeners.change({target: e.kaEnabled});
  e.kaEnabled.checked = false; listeners.change({target: e.kaEnabled});
  pending.shift()({enabled: true, url: 'https://example.com/saved'});
  await settle();
  assert.equal(e.kaEnabled.checked, false, '开关来回切换后仍须保留用户选择');
  console.log('keepalive save/reload and delayed status regressions passed');
})().catch(error => { console.error(error); process.exit(1); });
