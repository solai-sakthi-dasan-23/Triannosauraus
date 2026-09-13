const fs = require("fs");
const js = fs.readFileSync("c:/Users/admin/Desktop/MS/Triannausauras/journal_ui/js/journal.js", "utf8");

// Set up mock DOM where every element exists
const elements = {};
function getEl(id) {
  if (!elements[id]) {
    elements[id] = {
      id,
      textContent: "",
      innerHTML: "",
      value: "",
      style: {},
      classList: {
        add: (...c) => {},
        remove: (...c) => {},
        contains: (c) => false
      },
      dataset: {},
      appendChild: () => {},
      querySelectorAll: () => [],
      addEventListener: () => {}
    };
  }
  return elements[id];
}

const mockWindow = {
  location: {
    hostname: "triannosaraus.vercel.app",
    host: "triannosaraus.vercel.app",
    protocol: "https:",
    port: "",
    hash: "",
    pathname: "/"
  },
  innerWidth: 1200,
  addEventListener: () => {},
  document: null
};

const mockDocument = {
  readyState: "loading",
  addEventListener: (event, cb) => {
    if (event === "DOMContentLoaded") {
      mockDocument._onDOMContentLoaded = cb;
    }
  },
  getElementById: getEl,
  querySelectorAll: () => [],
  createElement: (tag) => getEl("dyn_" + tag),
  body: getEl("body")
};
mockWindow.document = mockDocument;

const mockLocalStorage = {
  _data: {},
  getItem: (k) => mockLocalStorage._data[k] || null,
  setItem: (k, v) => { mockLocalStorage._data[k] = String(v); },
  removeItem: (k) => { delete mockLocalStorage._data[k]; }
};

const mockFetch = (url) => {
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve([])
  });
};

try {
  const runner = new Function("window", "document", "localStorage", "sessionStorage", "fetch", js);
  runner(mockWindow, mockDocument, mockLocalStorage, mockLocalStorage, mockFetch);
  console.log("1. Script evaluated without top-level syntax or ReferenceErrors.");

  if (mockDocument._onDOMContentLoaded) {
    console.log("2. Running DOMContentLoaded callback (initApp)...");
    mockDocument._onDOMContentLoaded();
    console.log("3. initApp() executed successfully!");
  } else {
    console.log("2. DOMContentLoaded was not registered, readyState was not loading.");
  }
} catch (e) {
  console.error("FATAL RUNTIME ERROR IN journal.js:", e);
}
