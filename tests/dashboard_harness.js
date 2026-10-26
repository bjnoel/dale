// Runs static/dashboard.js under node against a stub DOM and prints what the
// results area would show. Driven by tests/test_dashboard_sold_out_fallback.py.
//
// Usage: node dashboard_harness.js <dashboard.js> <query string> <data.json>
// Prints JSON: {"count": <#resultCount text>, "html": <#results innerHTML>,
//               "url": <URL after syncURL()>}
//
// The stub is deliberately permissive: any element, any method, always present.
// It exists to exercise the filtering and render logic, not the page layout.
const fs = require('fs');
const vm = require('vm');

const [jsPath, search, dataPath] = process.argv.slice(2);

function el() {
  const store = {
    value: '', checked: false, innerHTML: '', textContent: '', innerText: '', placeholder: '',
    style: {}, dataset: {},
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
  };
  return new Proxy(store, {
    get(t, k) {
      if (k in t) return t[k];
      if (typeof k === 'symbol') return undefined;
      if (k === 'querySelectorAll') return () => [];
      return () => el();
    },
  });
}

const byId = {};
const document = {
  getElementById: id => (byId[id] = byId[id] || el()),
  querySelector: () => el(),
  querySelectorAll: () => [],
  createElement: () => el(),
  addEventListener() {},
};

let url = '/' + search;
const ctx = {
  window: {
    __DATA: JSON.parse(fs.readFileSync(dataPath, 'utf8')),
    location: { search, pathname: '/', hash: '' },
    history: { replaceState(_s, _t, u) { url = u; } },
    addEventListener() {},
  },
  document,
  localStorage: { getItem() { return null; }, setItem() {} },
  CSS: { escape: s => s },
  URLSearchParams,
  setTimeout() {},
  fetch() { return Promise.reject(new Error('no network in tests')); },
  console,
};
ctx.window.document = document;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(jsPath, 'utf8'), ctx, { filename: jsPath });

process.stdout.write(JSON.stringify({
  count: byId.resultCount.textContent,
  html: byId.results.innerHTML,
  url,
}));
