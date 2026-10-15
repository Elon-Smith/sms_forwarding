const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('code/web_src/app.js','utf8');
const calls = [], navigations = [];
const context = { URL, URLSearchParams, location:{search:'?sim=2',href:'http://device/?sim=2',assign:url=>navigations.push(url)},
  document:{getElementById:()=>null},window:{fetch:(url,options)=>{calls.push({url,options});return Promise.resolve();}} };
vm.createContext(context);
vm.runInContext(source.slice(0,source.indexOf('// 主题固定')),context);
context.simFetch('/sendsms',{method:'POST',body:'phone=10086&content=test'});
context.selectSim(1);
context.simFetch('/keepalive'); // Already-created page/closures remain bound to SIM2.
context.simFetch('/schedtask?sim=1&action=run&index=0',{method:'POST'});
assert.equal(calls[0].url,'/sendsms?sim=2');
assert.equal(calls[1].url,'/keepalive?sim=2');
assert.equal(calls[2].url,'/schedtask?sim=1&action=run&index=0');
assert.equal(navigations[0],'http://device/?sim=1');
console.log('UI: submitted task target stays fixed; explicit scheduled target overrides page SIM');
