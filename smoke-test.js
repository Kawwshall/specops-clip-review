const fs = require("fs");
const vm = require("vm");

const ids = [
  "file", "drop", "empty", "frame", "activeTopic", "time", "prev", "play",
  "scrub", "next", "fileName", "fileSize", "messageCount", "chunkCount",
  "topics", "status"
];

function element(id) {
  return {
    id,
    textContent: "",
    className: "",
    value: "0",
    max: "0",
    disabled: false,
    style: {},
    files: [],
    children: [],
    classList: { add() {}, remove() {}, toggle() {} },
    append(child) { this.children.push(child); },
    replaceChildren() { this.children = []; },
    addEventListener() {},
    removeAttribute() {},
    pause() {},
    play: async () => {},
    querySelector() { return element(`${id}-child`); },
    set innerHTML(value) { this.html = value; },
    get innerHTML() { return this.html || ""; }
  };
}

const elements = Object.fromEntries(ids.map((id) => [id, element(id)]));
const context = {
  console,
  TextDecoder,
  Blob,
  URL: {
    createObjectURL() { return "blob:test"; },
    revokeObjectURL() {}
  },
  document: {
    getElementById(id) { return elements[id] || element(id); },
    createElement(tag) { return element(tag); }
  },
  window: {
    setInterval() { return 1; },
    clearInterval() {}
  },
  getComputedStyle(el) { return { display: el.style.display || "block" }; }
};
context.globalThis = context;

const html = fs.readFileSync("index.html", "utf8");
const script = html.match(/<script>([\s\S]*)<\/script>/)[1];
vm.runInNewContext(script, context);

const bytes = fs.readFileSync("sample.mcap");
context.loadFile({
  name: "sample.mcap",
  size: bytes.length,
  arrayBuffer: async () => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength)
}).then(() => {
  const result = {
    status: elements.status.textContent,
    topic: elements.activeTopic.textContent,
    messages: elements.messageCount.textContent,
    chunks: elements.chunkCount.textContent,
    frameDisplay: elements.frame.style.display,
    time: elements.time.textContent
  };
  console.log(JSON.stringify(result, null, 2));
  if (result.topic !== "/camera/image" || result.messages !== "3" || result.frameDisplay !== "block") {
    process.exitCode = 1;
  }
});
