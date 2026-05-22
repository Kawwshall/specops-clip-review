const fs = require("fs");

const magic = Buffer.from([0x89, 0x4d, 0x43, 0x41, 0x50, 0x30, 0x0d, 0x0a]);
const pngs = [
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADUlEQVR42mP8z8BQDwAFgwJ/l7q99gAAAABJRU5ErkJggg==",
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
].map((s) => Buffer.from(s, "base64"));

function u8(value) {
  return Buffer.from([value]);
}

function u16(value) {
  const b = Buffer.alloc(2);
  b.writeUInt16LE(value);
  return b;
}

function u32(value) {
  const b = Buffer.alloc(4);
  b.writeUInt32LE(value);
  return b;
}

function u64(value) {
  const b = Buffer.alloc(8);
  b.writeBigUInt64LE(BigInt(value));
  return b;
}

function str(value) {
  const data = Buffer.from(value, "utf8");
  return Buffer.concat([u32(data.length), data]);
}

function map(entries) {
  const body = Buffer.concat(Object.entries(entries).flatMap(([k, v]) => [str(k), str(v)]));
  return Buffer.concat([u32(body.length), body]);
}

function record(op, body) {
  return Buffer.concat([u8(op), u64(body.length), body]);
}

function cdrCompressedImage(png, stampNs) {
  const chunks = [Buffer.from([0x00, 0x01, 0x00, 0x00])];
  let pos = 4;

  function pad(size) {
    const mod = pos % size;
    if (!mod) return;
    const n = size - mod;
    chunks.push(Buffer.alloc(n));
    pos += n;
  }

  function add(buffer) {
    chunks.push(buffer);
    pos += buffer.length;
  }

  function addU32(value) {
    pad(4);
    add(u32(value));
  }

  function addI32(value) {
    pad(4);
    const b = Buffer.alloc(4);
    b.writeInt32LE(value);
    add(b);
  }

  function addString(value) {
    const bytes = Buffer.from(`${value}\0`, "utf8");
    addU32(bytes.length);
    add(bytes);
  }

  addI32(Number(stampNs / 1_000_000_000n));
  addU32(Number(stampNs % 1_000_000_000n));
  addString("camera");
  addString("png");
  addU32(png.length);
  add(png);
  return Buffer.concat(chunks);
}

const header = record(0x01, Buffer.concat([str("mcap-video-viewer"), str("synthetic")]));
const schema = record(0x03, Buffer.concat([
  u16(1),
  str("sensor_msgs/msg/CompressedImage"),
  str("ros2msg"),
  u32(0)
]));
const channel = record(0x04, Buffer.concat([
  u16(1),
  u16(1),
  str("/camera/image"),
  str("cdr"),
  map({})
]));

const startTime = 1_779_174_000_000_000_000n;
const messages = pngs.map((png, i) => record(0x05, Buffer.concat([
  u16(1),
  u32(i + 1),
  u64(startTime + BigInt(i) * 100_000_000n),
  u64(startTime + BigInt(i) * 100_000_000n),
  cdrCompressedImage(png, startTime + BigInt(i) * 100_000_000n)
])));

const footer = record(0x02, Buffer.concat([u64(0), u64(0), u32(0)]));
fs.writeFileSync("sample.mcap", Buffer.concat([magic, header, schema, channel, ...messages, footer, magic]));
console.log("sample.mcap written");
