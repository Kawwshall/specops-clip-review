from __future__ import annotations

import base64, hashlib, json, mimetypes, os, platform, shutil, struct, subprocess, sys, tempfile, uuid, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import imageio_ffmpeg

# When frozen by PyInstaller: static files live in sys._MEIPASS (temp bundle dir),
# mutable data (cache, uploads) lives in ~/.specops so it survives across runs.
if getattr(sys, 'frozen', False):
    ROOT   = Path(sys._MEIPASS)
    _data  = Path.home() / '.specops'
else:
    ROOT   = Path(__file__).resolve().parent
    _data  = ROOT

EPOCH_SANITY_NS = 1_000_000_000_000_000_000  # 2001-09-09, filter obviously wrong timestamps
CACHE   = _data / 'converted'
UPLOADS = _data / 'uploads'
# Ensure data directories exist on every start
CACHE.mkdir(parents=True, exist_ok=True)
UPLOADS.mkdir(parents=True, exist_ok=True)
MAGIC   = b'\x89MCAP0\r\n'

_activity_cache: dict = {}  # path str -> score dict

class Reader:
    def __init__(self, data: bytes): self.data, self.pos = data, 0
    def remaining(self): return len(self.data) - self.pos
    def u8(self): v = self.data[self.pos]; self.pos += 1; return v
    def u16(self): v = int.from_bytes(self.data[self.pos:self.pos+2], 'little'); self.pos += 2; return v
    def u32(self): v = int.from_bytes(self.data[self.pos:self.pos+4], 'little'); self.pos += 4; return v
    def u64(self): v = int.from_bytes(self.data[self.pos:self.pos+8], 'little'); self.pos += 8; return v
    def take(self, n): v = self.data[self.pos:self.pos+n]; self.pos += n; return v
    def bytes32(self): return self.take(self.u32())
    def bytes64(self): return self.take(self.u64())
    def string32(self): return self.bytes32().decode('utf-8', errors='replace')
    def skip_string_map(self):
        end = self.pos + self.u32()
        while self.pos < end: self.string32(); self.string32()

def iter_records(data: bytes, start: int, end: int):
    r = Reader(data[start:end])
    while r.remaining() > 9:
        op, length = r.u8(), r.u64()
        if length > r.remaining(): break
        yield op, r.take(length)
        if op == 0x02: break

def read_varint(data: bytes, pos: int):
    shift = value = 0
    while pos < len(data):
        byte = data[pos]; pos += 1; value |= (byte & 0x7f) << shift
        if not byte & 0x80: return value, pos
        shift += 7
    raise ValueError('invalid protobuf varint')

def proto_fields(data: bytes):
    fields, pos = {}, 0
    while pos < len(data):
        key, pos = read_varint(data, pos); field, wire = key >> 3, key & 7
        if wire == 0: fields[field], pos = read_varint(data, pos)
        elif wire == 2:
            length, pos = read_varint(data, pos); fields[field] = data[pos:pos+length]; pos += length
        elif wire == 5: fields[field] = data[pos:pos+4]; pos += 4
        elif wire == 1: fields[field] = data[pos:pos+8]; pos += 8
        else: break
    return fields

def parse_video(data: bytes, encoding: str):
    if encoding.lower() == 'protobuf':
        fields = proto_fields(data); packet, fmt = fields.get(3), fields.get(4)
        if isinstance(packet, bytes) and packet:
            fmt_text = fmt.decode('utf-8', errors='replace') if isinstance(fmt, bytes) else ''
            return fmt_text.lower(), packet
    if encoding.lower() == 'json':
        msg = json.loads(data); raw = msg.get('data')
        packet = bytes(raw) if isinstance(raw, list) else base64.b64decode(raw or '')
        return str(msg.get('format', '')).lower(), packet
    return None

def extract_video_packets(data: bytes, topic: str):
    if not data.startswith(MAGIC): raise ValueError('not an MCAP file')
    schemas, channels, packets, fmt = {}, {}, [], ''
    def handle(op, body):
        nonlocal fmt
        if op == 0x03:
            r = Reader(body); sid = r.u16(); name = r.string32(); r.string32()
            schemas.setdefault(sid, name)
        elif op == 0x04:
            r = Reader(body); cid, sid = r.u16(), r.u16(); t, enc = r.string32(), r.string32(); r.skip_string_map()
            if cid not in channels:
                channels[cid] = (schemas.get(sid, ''), t, enc)
        elif op == 0x05:
            r = Reader(body); cid = r.u16(); r.u32(); r.u64(); r.u64(); payload = r.take(r.remaining())
            schema, t, enc = channels.get(cid, ('', '', ''))
            if t == topic and 'compressedvideo' in schema.lower():
                parsed = parse_video(payload, enc)
                if parsed:
                    packet_format, packet = parsed; fmt = packet_format or fmt; packets.append(packet)
        elif op == 0x06:
            r = Reader(body); r.u64(); r.u64(); r.u64(); r.u32(); compression = r.string32(); records = r.bytes64()
            if compression: raise ValueError(f'compressed MCAP chunks are not supported yet: {compression}')
            for cop, cbody in iter_records(records, 0, len(records)): handle(cop, cbody)
    for op, body in iter_records(data, len(MAGIC), len(data) - len(MAGIC)): handle(op, body)
    return fmt, packets


def inspect_local_mcap(relative_path: str, root_path: str = ""):
    path = find_recording(relative_path, root_path)
    if not path:
        raise ValueError(f"could not find recording on disk: {relative_path}")
    data = path.read_bytes()
    if not data.startswith(MAGIC):
        raise ValueError("not an MCAP file")
    schemas, channels = {}, {}
    messages = 0
    chunks = 0

    def handle(op, body):
        nonlocal messages, chunks
        if op == 0x03:
            r = Reader(body); sid = r.u16(); name = r.string32(); r.string32()
            schemas.setdefault(sid, name)  # summary section repeats these — don't overwrite
        elif op == 0x04:
            r = Reader(body); cid, sid = r.u16(), r.u16(); topic, enc = r.string32(), r.string32(); r.skip_string_map()
            # summary section repeats channel records after messages are counted — don't reset
            if cid not in channels:
                channels[cid] = {"schema": schemas.get(sid, ""), "topic": topic, "encoding": enc, "messages": 0, "format": ""}
        elif op == 0x05:
            messages += 1
            r = Reader(body); cid = r.u16(); r.u32(); r.u64(); r.u64(); payload = r.take(r.remaining())
            channel = channels.get(cid)
            if not channel:
                return
            channel["messages"] += 1
            if "compressedvideo" in channel["schema"].lower():
                parsed = parse_video(payload, channel["encoding"])
                if parsed and parsed[0] and not channel["format"]:
                    channel["format"] = parsed[0]
        elif op == 0x06:
            chunks += 1
            r = Reader(body); r.u64(); r.u64(); r.u64(); r.u32(); compression = r.string32(); records = r.bytes64()
            if compression:
                return
            for cop, cbody in iter_records(records, 0, len(records)):
                handle(cop, cbody)

    for op, body in iter_records(data, len(MAGIC), len(data) - len(MAGIC)):
        handle(op, body)

    topics = [{
        "topic": c["topic"],
        "format": c["format"] or "",
        "messages": c["messages"],
        "schema": c["schema"],
    } for c in channels.values() if "compressedvideo" in c["schema"].lower() and c["messages"]]
    return {
        "name": path.name,
        "relativePath": relative_path,
        "size": path.stat().st_size,
        "messages": messages,
        "chunks": chunks,
        "topics": topics,
    }

def _is_translocated():
    """True when macOS App Translocation is active (app not moved to /Applications)."""
    try:
        return 'AppTranslocation' in str(Path(sys.executable).resolve())
    except OSError:
        return False

def find_recording(relative_path: str, root_path: str = ""):
    cleaned = relative_path.replace('\\', '/').lstrip('/'); name = Path(cleaned).name
    candidates = []
    root = resolve_root(root_path) if root_path else None
    if root:
        candidates.append(root / cleaned)
    candidates.extend([ROOT / cleaned, ROOT.parent / cleaned, ROOT.parent.parent / cleaned, Path.home() / cleaned, Path.home() / 'Documents' / cleaned])
    # Glob inside ROOT.parent can raise ERANGE under macOS App Translocation — skip safely
    if not _is_translocated():
        try:
            candidates.extend(ROOT.parent.glob(f'**/{name}'))
        except OSError:
            pass
    for p in candidates:
        try: r = p.resolve()
        except OSError: continue
        if r.exists() and r.is_file() and r.suffix.lower() == '.mcap': return r
    return None


def _parse_vector3(data: bytes):
    """Parse a protobuf Vector3 message and return (x, y, z) as floats."""
    f = proto_fields(data)
    x = struct.unpack('<d', f[1])[0] if isinstance(f.get(1), bytes) and len(f[1]) == 8 else 0.0
    y = struct.unpack('<d', f[2])[0] if isinstance(f.get(2), bytes) and len(f[2]) == 8 else 0.0
    z = struct.unpack('<d', f[3])[0] if isinstance(f.get(3), bytes) and len(f[3]) == 8 else 0.0
    return x, y, z


def _imu_scan_window(data: bytes, schemas: dict, channels: dict, accels: list, n: int):
    """Scan raw MCAP bytes for IMU acceleration messages, appending to accels."""
    cp = 0
    while cp + 9 <= len(data) and len(accels) < n:
        op   = data[cp]
        clen = int.from_bytes(data[cp + 1: cp + 9], 'little')
        cs   = cp + 9
        if cs + clen > len(data):
            break
        body = data[cs: cs + clen]
        r    = Reader(body)
        try:
            if op == 0x03:
                sid = r.u16(); name = r.string32()
                schemas.setdefault(sid, name)
            elif op == 0x04:
                cid, sid = r.u16(), r.u16(); t, enc = r.string32(), r.string32()
                if cid not in channels:
                    channels[cid] = (schemas.get(sid, ''), t, enc)
            elif op == 0x05:
                cid = r.u16(); r.u32(); r.u64(); r.u64()
                payload = r.take(r.remaining())
                schema, t, _enc = channels.get(cid, ('', '', ''))
                if 'imu' in t.lower() and 'zed' in schema.lower():
                    fields = proto_fields(payload)
                    if isinstance(fields.get(5), bytes):
                        x, y, z = _parse_vector3(fields[5])
                        mag = (x*x + y*y + z*z) ** 0.5
                        if 1.0 < mag < 50.0:
                            accels.append(mag)
        except Exception:
            pass
        cp = cs + clen
        if op == 0x02:
            break


def _scan_chunk_window(raw: bytes, schemas: dict, channels: dict, accels: list, n: int):
    """Walk top-level MCAP records in raw bytes, descending into uncompressed chunks."""
    pos = 0; limit = len(raw)
    while pos + 9 <= limit and len(accels) < n:
        op        = raw[pos]
        body_len  = int.from_bytes(raw[pos + 1: pos + 9], 'little')
        body_start = pos + 9
        available  = min(body_len, limit - body_start)
        if op == 0x06:  # Chunk
            r = Reader(raw[body_start: body_start + available])
            try:
                r.u64(); r.u64(); r.u64(); r.u32()
                if not r.string32():           # no compression
                    r.u64()
                    _imu_scan_window(raw[body_start + r.pos: body_start + available],
                                     schemas, channels, accels, n)
            except Exception:
                pass
        if body_start + body_len > limit:
            break
        pos = body_start + body_len
        if op == 0x02:
            break


def extract_imu_accels(path: Path, n: int = 300):
    """Return up to N IMU linear-acceleration magnitudes sampled from across the
    full recording (start, middle, end) for accurate whole-shift activity scoring.

    Strategy:
      1. Read schema/channel definitions from the first 128 KB.
      2. Use ChunkIndex records (from the MCAP summary) to locate chunks spread
         evenly across the timeline; read 512 KB windows around each.
      3. Fall back to a single head-only scan if no summary is available.
    """
    READ_SIZE = 512 * 1024
    schemas: dict = {}
    channels: dict = {}
    accels: list  = []

    # ── Step 1: bootstrap schema/channel map from file header ────────────────
    try:
        with path.open('rb') as f:
            head = f.read(READ_SIZE)
    except OSError:
        return []
    if not head.startswith(MAGIC):
        return []
    _scan_chunk_window(head[len(MAGIC):], schemas, channels, [], n)  # collect defs only

    # ── Step 2: locate chunks via ChunkIndex records in the summary ───────────
    summary = _read_mcap_summary(path, max_bytes=262144)  # 256 KB
    chunk_locs: list[tuple[int, int, int]] = []  # (start_ns, offset, length)
    if summary:
        sp = 0
        while sp + 9 <= len(summary):
            sop  = summary[sp]
            sbln = int.from_bytes(summary[sp + 1: sp + 9], 'little')
            sbs  = sp + 9
            if sop == 0x0A and sbln >= 32 and sbs + 32 <= len(summary):  # ChunkIndex
                r = Reader(summary[sbs: sbs + sbln])
                sn = r.u64(); r.u64()          # start/end time
                offset = r.u64(); length = r.u64()
                chunk_locs.append((sn, offset, length))
            if sop == 0x02 or sbln == 0 or sbs + sbln > len(summary):
                break
            sp = sbs + sbln
        chunk_locs.sort()  # sort by start_ns

    if chunk_locs:
        # Pick up to 5 evenly-spaced chunks: beginning, quarters, end
        total  = len(chunk_locs)
        picks  = sorted({0, total // 4, total // 2, 3 * total // 4, total - 1})
        try:
            with path.open('rb') as f:
                for idx in picks:
                    if len(accels) >= n:
                        break
                    _, offset, length = chunk_locs[idx]
                    f.seek(offset)
                    window = f.read(min(length, READ_SIZE))
                    _scan_chunk_window(window, schemas, channels, accels, n)
        except OSError:
            pass
    else:
        # Fallback: head-only scan (original behaviour)
        _scan_chunk_window(head[len(MAGIC):], schemas, channels, accels, n)

    return accels


def compute_activity_score(path: Path) -> dict:
    """Compute activity score from IMU linear-acceleration variance (0–100).
    0 = stationary/idle; 100 = highly active operator."""
    key = str(path)
    if key in _activity_cache:
        return _activity_cache[key]

    accels = extract_imu_accels(path)
    if len(accels) < 10:
        result = {'score': -1, 'reason': f'only {len(accels)} IMU samples found'}
        _activity_cache[key] = result
        return result

    mean = sum(accels) / len(accels)
    variance = sum((a - mean) ** 2 for a in accels) / len(accels)
    stddev = variance ** 0.5
    # At rest: stddev ≈ 0.05–0.3 m/s²  Walking: 1–4  Active: 4–10+
    score = round(min(100.0, stddev * 12.5), 1)
    result = {'score': score, 'samples': len(accels), 'stddev': round(stddev, 3)}
    _activity_cache[key] = result
    return result


def _read_mcap_summary(path: Path, max_bytes: int = 131072) -> bytes | None:
    """Read the MCAP summary section by parsing the file footer.
    Returns raw summary bytes, or None if the file has no summary / can't be read."""
    _HDR = 9    # op(1) + length(8)
    _FOOTER_BODY = 20  # summary_start(8) + summary_offset_start(8) + summary_crc(4)
    try:
        with path.open('rb') as f:
            # Verify trailing MAGIC
            f.seek(-len(MAGIC), 2)
            if f.read(len(MAGIC)) != MAGIC:
                return None
            # Footer record sits immediately before trailing MAGIC
            f.seek(-(len(MAGIC) + _HDR + _FOOTER_BODY), 2)
            raw = f.read(_HDR + _FOOTER_BODY)
        if len(raw) < _HDR + _FOOTER_BODY or raw[0] != 0x02:
            return None
        summary_start = int.from_bytes(raw[_HDR: _HDR + 8], 'little')
        if not summary_start:
            return None
        with path.open('rb') as f:
            f.seek(summary_start)
            return f.read(max_bytes)
    except OSError:
        return None


def quick_scan_mcap(path: Path):
    """Return timing dict with ACTUAL start/end/duration by reading the MCAP
    Statistics record from the summary section.  Falls back to a 32 KB header
    scan (returning a 3-minute estimate) if the summary can't be parsed."""
    # ── Primary path: footer → Statistics record ─────────────────────────────
    summary = _read_mcap_summary(path)
    if summary:
        pos = 0
        while pos + 9 <= len(summary):
            op  = summary[pos]
            bln = int.from_bytes(summary[pos + 1: pos + 9], 'little')
            bs  = pos + 9
            if op == 0x0D:  # Statistics
                # layout: msg_count(8) schema(2) chan(2) attach(4) meta(4) chunks(4)
                #         message_start_time(8) message_end_time(8)  = 40 bytes min
                if bln >= 40 and bs + 40 <= len(summary):
                    r = Reader(summary[bs: bs + bln])
                    r.u64(); r.u16(); r.u16(); r.u32(); r.u32(); r.u32()
                    s_ns, e_ns = r.u64(), r.u64()
                    if s_ns > EPOCH_SANITY_NS and e_ns > s_ns:
                        return {
                            'start_ms':   s_ns / 1e6,
                            'end_ms':     e_ns / 1e6,
                            'duration_s': (e_ns - s_ns) / 1e9,
                        }
                break  # found Statistics but couldn't parse — fall through
            if op == 0x02 or bln == 0 or bs + bln > len(summary):
                break
            pos = bs + bln

    # ── Fallback: scan first 32 KB for a chunk header ────────────────────────
    try:
        with path.open('rb') as f:
            head = f.read(32768)
        pos = len(MAGIC); limit = len(head); start_ns = None
        while pos + 9 <= limit:
            op       = head[pos]
            body_len = int.from_bytes(head[pos + 1: pos + 9], 'little')
            body_start = pos + 9
            if op in (0x06, 0x0A) and body_len >= 16 and body_start + 16 <= limit:
                s = int.from_bytes(head[body_start:     body_start + 8], 'little')
                if s > EPOCH_SANITY_NS:
                    start_ns = s; break
            if body_start + body_len > limit: break
            pos = body_start + body_len
            if op == 0x02: break
        if start_ns:
            return {'start_ms': start_ns / 1e6,
                    'end_ms':   (start_ns + 180_000_000_000) / 1e6,
                    'duration_s': 180.0}
    except OSError:
        pass
    return None


def list_drives():
    """Enumerate drives/volumes instantly — Windows (ctypes) and macOS (/Volumes)."""
    os_name = platform.system()
    if os_name == 'Windows':
        try:
            import ctypes, string
            k32 = ctypes.windll.kernel32
            mask = k32.GetLogicalDrives()
            drives = []
            for i, letter in enumerate(string.ascii_uppercase):
                if not (mask & (1 << i)):
                    continue
                path = f'{letter}:\\'
                dtype = k32.GetDriveTypeW(path)
                if dtype not in (2, 3):  # 2=removable, 3=fixed
                    continue
                vol = ctypes.create_unicode_buffer(261)
                k32.GetVolumeInformationW(path, vol, 261, None, None, None, None, 0)
                drives.append({'path': path, 'label': vol.value or letter, 'removable': dtype == 2})
            return drives
        except Exception:
            return []
    elif os_name == 'Darwin':
        drives = []
        try:
            for vol in Path('/Volumes').iterdir():
                if vol.is_dir() and not vol.name.startswith('.'):
                    drives.append({'path': str(vol) + '/', 'label': vol.name, 'removable': True})
        except Exception:
            pass
        return drives
    return []


def auto_detect_recordings():
    """Find drives that contain a recordings folder with MCAP files."""
    results = []
    for drive in list_drives():
        for folder in ('recordings', 'Recordings', 'RECORDINGS'):
            rec = Path(drive['path']) / folder
            try:
                if rec.is_dir():
                    count = sum(1 for _ in rec.rglob('*.mcap'))
                    if count:
                        results.append({
                            'path': str(rec),
                            'drive': drive['path'],
                            'label': drive['label'],
                            'mcap_count': count,
                            'removable': drive['removable'],
                        })
                    break
            except PermissionError:
                continue
    return results


def list_recordings(root_path: str):
    root = resolve_root(root_path)
    if not root:
        raise ValueError(f"could not access folder: {root_path}")
    files = sorted(root.rglob("*.mcap"))
    items = []
    for path in files:
        rel = path.relative_to(root).as_posix()
        parts = rel.split("/")
        device = parts[0] if len(parts) > 1 else "root"
        item = {
            "name": path.name,
            "relativePath": rel,
            "device": device,
            "size": path.stat().st_size,
        }
        timing = quick_scan_mcap(path)
        if timing:
            item["startMs"] = timing["start_ms"]
            item["endMs"] = timing["end_ms"]
            item["durationS"] = round(timing["duration_s"], 1)
        items.append(item)
    return {"root": str(root), "count": len(items), "items": items}


def resolve_root(root_path: str):
    if not root_path:
        return None
    candidate = Path(root_path).expanduser()
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    if resolved.exists() and resolved.is_dir():
        return resolved
    return None

def normalize_packet(packet: bytes):
    if packet.startswith(b'\x00\x00\x01') or packet.startswith(b'\x00\x00\x00\x01'): return packet
    out, pos = bytearray(), 0
    while pos + 4 <= len(packet):
        length = int.from_bytes(packet[pos:pos+4], 'big'); pos += 4
        if length <= 0 or pos + length > len(packet): return packet
        out.extend(b'\x00\x00\x00\x01'); out.extend(packet[pos:pos+length]); pos += length
    return bytes(out) if pos == len(packet) and out else packet

def split_stream(raw: bytes):
    if raw.startswith(b'\x00\x00\x01') or raw.startswith(b'\x00\x00\x00\x01'): return [raw]
    packets, pos = [], 0
    while pos + 4 <= len(raw):
        length = int.from_bytes(raw[pos:pos+4], 'big'); pos += 4
        if length <= 0 or pos + length > len(raw): return [raw]
        packets.append(raw[pos:pos+length]); pos += length
    return packets if pos == len(raw) and packets else [raw]

def convert_packets(packets, fmt, mode, cache_key):
    CACHE.mkdir(exist_ok=True); digest = hashlib.sha256(cache_key + mode.encode()).hexdigest()[:16]; out = CACHE / f'{digest}.mp4'
    if out.exists(): return result_for(out, mode)
    kind = 'hevc' if any(x in fmt for x in ('265', 'hevc', 'h265')) else 'h264'; ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / f'input.{kind}'; raw.write_bytes(b''.join(normalize_packet(p) for p in packets))
        if mode == 'compat':
            cmd = [ffmpeg, '-y', '-fflags', '+genpts', '-r', '24', '-f', kind, '-i', str(raw), '-an', '-vf', 'scale=min(960\\,iw):-2', '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency', '-crf', '30', '-profile:v', 'baseline', '-level', '3.1', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(out)]
        else:
            cmd = [ffmpeg, '-y', '-fflags', '+genpts', '-r', '30', '-f', kind, '-i', str(raw), '-an', '-c:v', 'copy', '-tag:v', 'hvc1' if kind == 'hevc' else 'avc1', '-movflags', '+faststart', str(out)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if proc.returncode: raise ValueError(proc.stderr[-2000:] or 'ffmpeg conversion failed')
    return result_for(out, mode)

def result_for(out, mode):
    poster = make_poster(out)
    return {'url': f'/converted/{out.name}', 'poster': f'/converted/{poster.name}' if poster else '', 'cached': True, 'size': out.stat().st_size, 'mode': mode}

def make_poster(mp4):
    poster = mp4.with_suffix('.jpg')
    if poster.exists(): return poster
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe(); proc = subprocess.run([ffmpeg, '-y', '-ss', '1', '-i', str(mp4), '-frames:v', '1', '-update', '1', str(poster)], capture_output=True, text=True, timeout=120)
    return poster if proc.returncode == 0 and poster.exists() and poster.stat().st_size else None

def convert_mcap_bytes(data, topic, mode):
    fmt, packets = extract_video_packets(data, topic)
    if not packets: raise ValueError(f'no compressed video packets found for topic {topic}')
    return convert_packets(packets, fmt, mode, data + topic.encode())

def convert_local(rel, topic, mode, root_path = ""):
    p = find_recording(rel, root_path)
    if not p: raise ValueError(f'could not find recording on disk: {rel}')
    res = convert_mcap_bytes(p.read_bytes(), topic, mode); res['source'] = str(p); return res

class Handler(BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*'); self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS'); self.send_header('Access-Control-Allow-Headers', 'Content-Type'); super().end_headers()
    def do_OPTIONS(self): self.send_response(204); self.end_headers()
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)
        if path == '/api/health': return self.send_json({'ok': True, 'service': 'mcap-video-helper', 'translocated': _is_translocated()})
        if path == '/api/clear-cache':
            count = 0
            for f in CACHE.iterdir():
                try: f.unlink(); count += 1
                except Exception: pass
            _activity_cache.clear()
            return self.send_json({'cleared': count})
        if path == '/api/list-drives':
            return self.send_json({'drives': list_drives()})
        if path == '/api/auto-detect':
            return self.send_json({'results': auto_detect_recordings()})
        if path == '/api/activity':
            q = urllib.parse.parse_qs(parsed.query)
            p = find_recording(q.get('path', [''])[0], q.get('root', [''])[0])
            if not p:
                return self.send_json({'error': 'file not found'}, 404)
            return self.send_json(compute_activity_score(p))
        if path == '/api/list-recordings':
            q = urllib.parse.parse_qs(parsed.query)
            try:
                return self.send_json(list_recordings(q.get('root', [''])[0]))
            except Exception as exc:
                return self.send_json({'error': str(exc)}, 500)
        if path == '/api/inspect-local':
            q = urllib.parse.parse_qs(parsed.query)
            try:
                return self.send_json(inspect_local_mcap(q.get('path', [''])[0], q.get('root', [''])[0]))
            except Exception as exc:
                return self.send_json({'error': str(exc)}, 500)
        if path.startswith('/api/'): return self.send_json({'error': f'unknown API endpoint: {path}'}, 404)
        if path == '/': return self.send_file(ROOT / 'index.html')
        if path.startswith('/converted/'): return self.send_file(CACHE / Path(path).name)
        return self.send_file(ROOT / path.lstrip('/'))
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(parsed.query); mode = q.get('mode', ['fast'])[0]
        if mode not in {'fast', 'compat'}: mode = 'fast'
        try:
            if parsed.path == '/api/convert-local': return self.send_json(convert_local(q.get('path', [''])[0], q.get('topic', [''])[0], mode, q.get('root', [''])[0]))
            if parsed.path == '/api/upload-start': return self.upload_start()
            if parsed.path == '/api/upload-chunk': return self.upload_chunk(q)
            if parsed.path == '/api/upload-finish': return self.upload_finish(q, mode)
            body = self.rfile.read(int(self.headers.get('content-length', '0')))
            if parsed.path == '/api/convert-stream': return self.send_json(convert_packets(split_stream(body), q.get('format', [''])[0], mode, body + q.get('format', [''])[0].encode()))
            if parsed.path == '/api/convert': return self.send_json(convert_mcap_bytes(body, q.get('topic', [''])[0], mode))
            return self.send_json({'error': f'unknown API endpoint: {parsed.path}'}, 404)
        except Exception as exc: return self.send_json({'error': str(exc)}, 500)
    def upload_start(self):
        UPLOADS.mkdir(exist_ok=True); uid = uuid.uuid4().hex; (UPLOADS / f'{uid}.stream').write_bytes(b''); return self.send_json({'uploadId': uid})
    def upload_chunk(self, q):
        uid = q.get('id', [''])[0]; p = UPLOADS / f'{uid}.stream'
        if not uid.isalnum() or not p.exists(): return self.send_json({'error': 'unknown upload id'}, 404)
        with p.open('ab') as f: f.write(self.rfile.read(int(self.headers.get('content-length', '0'))))
        return self.send_json({'ok': True, 'received': p.stat().st_size})
    def upload_finish(self, q, mode):
        uid = q.get('id', [''])[0]; p = UPLOADS / f'{uid}.stream'
        if not p.exists(): return self.send_json({'error': 'unknown upload id'}, 404)
        return self.send_json(convert_packets(split_stream(p.read_bytes()), q.get('format', [''])[0], mode, p.read_bytes() + q.get('format', [''])[0].encode()))
    def send_file(self, path):
        if not path.exists() or not path.is_file(): self.send_error(404); return
        ctype = 'video/mp4' if path.suffix.lower() == '.mp4' else mimetypes.guess_type(path.name)[0] or 'application/octet-stream'; size = path.stat().st_size; rng = self.headers.get('Range')
        if rng and rng.startswith('bytes='):
            a, _, b = rng.removeprefix('bytes=').partition('-'); start = int(a or '0'); end = min(int(b) if b else size - 1, size - 1)
            self.send_response(206); self.send_header('Content-Type', ctype); self.send_header('Accept-Ranges', 'bytes'); self.send_header('Content-Range', f'bytes {start}-{end}/{size}'); self.send_header('Content-Length', str(end - start + 1)); self.end_headers()
            with path.open('rb') as f: f.seek(start); self.wfile.write(f.read(end - start + 1)); return
        self.send_response(200); self.send_header('Content-Type', ctype); self.send_header('Accept-Ranges', 'bytes'); self.send_header('Content-Length', str(size)); self.end_headers()
        with path.open('rb') as f: shutil.copyfileobj(f, self.wfile)
    def send_json(self, payload, status=200):
        data = json.dumps(payload).encode(); self.send_response(status); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
    def log_message(self, fmt, *args): print(fmt % args)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', '8765')); print(f'MCAP video helper running at http://127.0.0.1:{port}'); ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()

