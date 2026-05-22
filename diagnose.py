"""Dump every schema, channel, and first-message sample from an MCAP file."""
import sys, struct, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from pathlib import Path

MAGIC = b'\x89MCAP0\r\n'

def u8(d,p):  return d[p], p+1
def u16(d,p): return int.from_bytes(d[p:p+2],'little'), p+2
def u32(d,p): return int.from_bytes(d[p:p+4],'little'), p+4
def u64(d,p): return int.from_bytes(d[p:p+8],'little'), p+8
def str32(d,p):
    n,p = u32(d,p); return d[p:p+n].decode('utf-8','replace'), p+n
def bytes32(d,p):
    n,p = u32(d,p); return d[p:p+n], p+n
def bytes64(d,p):
    n,p = u64(d,p); return d[p:p+n], p+n
def strmap(d,p):
    end,p = u32(d,p); end += p; m={}
    while p < end:
        k,p = str32(d,p); v,p = str32(d,p); m[k]=v
    return m,p

def iter_records(data, start, end):
    p = start
    while p+9 <= end:
        op = data[p]; p+=1
        length = int.from_bytes(data[p:p+8],'little'); p+=8
        if p+length > end: break
        yield op, data[p:p+length], p
        p += length
        if op == 0x02: break

def diagnose(path):
    data = Path(path).read_bytes()
    if not data.startswith(MAGIC):
        print("NOT AN MCAP FILE"); return

    schemas  = {}   # id -> {name, encoding}
    channels = {}   # id -> {schema_id, topic, msg_encoding, meta}
    msg_counts = {} # channel_id -> count
    first_bytes = {}# channel_id -> first 32 bytes of payload
    chunks = 0
    compressed_chunks = 0
    total_messages = 0
    chunk_start_times = []
    chunk_end_times = []

    def handle(op, body):
        nonlocal chunks, compressed_chunks, total_messages
        p = 0
        if op == 0x03:  # Schema
            sid,p = u16(body,p)
            name,p = str32(body,p)
            enc,p  = str32(body,p)
            dat,p  = bytes32(body,p)
            schemas[sid] = {'name': name, 'encoding': enc, 'data_len': len(dat),
                            'data_preview': dat[:120].decode('utf-8','replace')}
        elif op == 0x04:  # Channel
            cid,p  = u16(body,p)
            sid,p  = u16(body,p)
            topic,p = str32(body,p)
            menc,p  = str32(body,p)
            meta,p  = strmap(body,p)
            channels[cid] = {'schema_id': sid, 'topic': topic,
                             'msg_encoding': menc, 'meta': meta}
            msg_counts[cid] = 0
        elif op == 0x05:  # Message
            total_messages += 1
            cid,p = u16(body,p)
            msg_counts[cid] = msg_counts.get(cid,0) + 1
            if cid not in first_bytes:
                first_bytes[cid] = body[p+16:p+16+64]  # skip sequence+timestamps
        elif op == 0x06:  # Chunk
            chunks += 1
            t_start = int.from_bytes(body[0:8],'little')
            t_end   = int.from_bytes(body[8:16],'little')
            if t_start > 1_000_000_000_000_000_000: chunk_start_times.append(t_start)
            if t_end   > 1_000_000_000_000_000_000: chunk_end_times.append(t_end)
            p = 24  # skip start,end,uncompressed_size
            _,p = u32(body,p)  # crc
            comp,p = str32(body,p)
            if comp:
                compressed_chunks += 1
                return
            recs,p = bytes64(body,p)
            for rop, rbody, _ in iter_records(recs, 0, len(recs)):
                handle(rop, rbody)

    for op, body, _ in iter_records(data, len(MAGIC), len(data)-len(MAGIC)):
        handle(op, body)

    print(f"\n{'='*60}")
    print(f"FILE: {path}")
    print(f"SIZE: {len(data):,} bytes  ({len(data)/1e6:.1f} MB)")
    print(f"CHUNKS: {chunks}  (compressed: {compressed_chunks})")
    print(f"TOTAL MESSAGES: {total_messages}")

    if chunk_start_times and chunk_end_times:
        t0 = min(chunk_start_times)/1e9
        t1 = max(chunk_end_times)/1e9
        import datetime
        print(f"TIME RANGE: {datetime.datetime.utcfromtimestamp(t0)} to {datetime.datetime.utcfromtimestamp(t1)} UTC")
        print(f"DURATION: {(t1-t0):.1f}s  ({(t1-t0)/60:.1f} min)")

    print(f"\n{'='*60}")
    print("SCHEMAS:")
    for sid, s in schemas.items():
        print(f"  [{sid}] name={s['name']!r}  encoding={s['encoding']!r}  data_len={s['data_len']}")
        if s['data_preview'].strip():
            preview = s['data_preview'].replace('\n',' ')[:100]
            print(f"       data_preview: {preview}")

    print(f"\n{'='*60}")
    print("CHANNELS / TOPICS:")
    for cid, ch in channels.items():
        sc = schemas.get(ch['schema_id'], {})
        count = msg_counts.get(cid, 0)
        print(f"  [{cid}] topic={ch['topic']!r}")
        print(f"       schema={sc.get('name','?')!r}  msg_encoding={ch['msg_encoding']!r}  messages={count}")
        if ch['meta']:
            print(f"       meta={ch['meta']}")
        # Show first payload hint
        fb = first_bytes.get(cid, b'')
        if fb:
            hex_preview = fb[:16].hex()
            # Try to detect image magic bytes
            hints = []
            if fb[:2] == b'\xff\xd8': hints.append('JPEG')
            if fb[:4] == b'\x89PNG': hints.append('PNG')
            if len(fb)>=4 and fb[:4] in (b'\x00\x00\x00\x01', b'\x00\x00\x01'): hints.append('NAL/H26x')
            # Try JSON
            try:
                sample = fb.decode('utf-8','replace')
                if sample.strip().startswith('{'): hints.append('JSON-like')
            except: pass
            print(f"       first_payload_hex: {hex_preview}  hints={hints or ['unknown']}")

    if compressed_chunks == chunks and chunks > 0:
        print(f"\n⚠️  ALL {chunks} CHUNKS ARE COMPRESSED — messages not readable without decompressor")
    print()

if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else r'F:\recordings\segment_0004.mcap'
    diagnose(path)
