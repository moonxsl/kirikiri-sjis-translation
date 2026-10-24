# -*- coding: utf-8 -*-
"""KiriKiri XP3 + SJIS tunnel pipeline (KAG3, CP932-hardcoded engines).

Standard-library only. Every step is idempotent and reads/writes only the
paths you pass; nothing touches the game directory until `deploy`.

Typical run:

    python krr.py analyze --game "D:\\Game"
    python krr.py all     --game "D:\\Game" --text "D:\\Game\\文本"
    python krr.py deploy  --game "D:\\Game" --text "D:\\Game\\文本"

Steps:
    analyze  - dump the XP3 index (entries, ks files, sizes) and translation counts
    unpack   - extract *.ks from the archive (zlib-magic based, ignores flags)
    extract  - pull dialogue out of the extracted ks as GalTransl gt_input JSON
    rewrite  - tolerant-regex replace + SJIS tunnel encode -> _work/new_ks
    repack   - rebuild the XP3 with the new ks (no double compression)
    verify   - re-read the new XP3 and check usz/csz + decode a few lines
    deploy   - back up data.xp3, write the new archive, drop sjis_ext.bin + proxy DLLs

Layout of the working directory (default _work):
    extracted/scenario/*.ks   unpacked scripts
    new_ks/<name>.ks          zlib-compressed tunnel text, ready for repack
    sjis_ext.bin              tunnel map for VNTextProxy (UTF-16LE, 2 bytes/char)
    data_new.xp3              rebuilt archive
"""
import argparse
import glob
import json
import os
import re
import shutil
import struct
import sys
import zlib

for _s in (sys.stdout, sys.stderr):          # keep CJK output from dying on a GBK console
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# ---------------------------------------------------------------- XP3 helpers

def u64(b, o):
    return struct.unpack('<Q', b[o:o + 8])[0]


def read_index(path):
    with open(path, 'rb') as f:
        magic = f.read(11)
        f.seek(0x20)
        index_offset = u64(f.read(8), 0)
        f.seek(index_offset)
        flag = f.read(1)
        comp_size = u64(f.read(8), 0)
        uncomp_size = u64(f.read(8), 0)
        index_data = bytearray(zlib.decompress(f.read(comp_size)))
    return dict(magic=magic, index_offset=index_offset, flag=flag,
                comp_size=comp_size, uncomp_size=uncomp_size, index=index_data)


def parse_entries(index):
    entries, pos = [], 0
    while pos + 12 <= len(index):
        if index[pos:pos + 4] != b'File':
            break
        data_size = u64(index, pos + 4)
        data_start = pos + 12
        data_end = data_start + data_size
        sub = data_start
        e = dict(name=None, info_off=None, segm_off=None, adlr_off=None,
                 usz=0, csz=0, segs=[])
        while sub + 12 <= data_end:
            sid = index[sub:sub + 4]
            ssize = u64(index, sub + 4)
            sd = sub + 12
            if sid == b'info':
                e['info_off'] = sd
                e['usz'] = u64(index, sd + 4)
                e['csz'] = u64(index, sd + 12)
                nlen = struct.unpack('<H', index[sd + 20:sd + 22])[0]
                e['name'] = index[sd + 22:sd + 22 + nlen * 2].decode('utf-16-le')
            elif sid == b'segm':
                e['segm_off'] = sd
                p = sd + 4
                for _ in range(struct.unpack('<I', index[sd:sd + 4])[0]):
                    e['segs'].append((u64(index, p), u64(index, p + 8), u64(index, p + 16)))
                    p += 24
            elif sid == b'adlr':
                e['adlr_off'] = sd
            sub = sd + ssize
        entries.append(e)
        pos = data_end
    return entries


def script_entries(entries, ext):
    return [e for e in entries if e['name'] and e['name'].lower().endswith(ext)]


# ------------------------------------------------------------- tunnel encoder

class SjisTunnel:
    """Map non-CP932 characters onto byte pairs that normal text never produces.

    Lead byte 0x81-0x9F / 0xE0-0xEF, trail byte 0x01-0x3F (skipping controls and
    ASCII whitespace/delimiters). Those pairs are not valid CP932, but the engine
    treats them as one double-width character and passes them through; VNTextProxy
    swaps them back to real characters before drawing.
    """

    SKIP_TRAIL = (0x09, 0x0A, 0x0D, 0x20, 0x2C)
    TRAIL_COUNT = 0x3A
    LEAD_COUNT = 47          # 0x81-0x9F (31) + 0xE0-0xEF (16)

    def __init__(self):
        self._mapping = {}

    @classmethod
    def codepoint(cls, idx):
        hi, lo = idx // cls.TRAIL_COUNT, idx % cls.TRAIL_COUNT
        hb = 0x81 + hi if hi < 0x1F else 0xE0 + (hi - 0x1F)
        lb = 1 + lo
        for s in cls.SKIP_TRAIL:
            if lb >= s:
                lb += 1
        return (hb << 8) | lb

    def _get(self, ch):
        if ch in self._mapping:
            return self._mapping[ch]
        idx = len(self._mapping)
        if idx >= self.LEAD_COUNT * self.TRAIL_COUNT:
            raise RuntimeError('SJIS tunnel capacity exceeded (%d chars)' % idx)
        self._mapping[ch] = chr(self.codepoint(idx))
        return self._mapping[ch]

    def encode(self, text):
        out = bytearray()
        for ch in text:
            try:
                raw = ch.encode('cp932')
                if len(raw) == 2 and raw[0] >= 0xF0:      # CP932 user-defined area
                    raise UnicodeEncodeError('cp932', ch, 0, 1, '')
                out.extend(raw)
            except UnicodeEncodeError:
                tc = ord(self._get(ch))
                out.append(tc >> 8)
                out.append(tc & 0xFF)
        return bytes(out)

    def mapping_string(self):
        return ''.join(sorted(self._mapping, key=lambda c: self._mapping[c]))


def decode_tunnel(data, chars):
    table = {}
    for idx, ch in enumerate(chars):
        cp = SjisTunnel.codepoint(idx)
        table[(cp >> 8, cp & 0xFF)] = ch
    out, i = [], 0
    while i < len(data):
        b = data[i]
        if (0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC) and i + 1 < len(data):
            pair = (b, data[i + 1])
            if pair in table:
                out.append(table[pair])
                i += 2
                continue
            try:
                out.append(data[i:i + 2].decode('cp932'))
                i += 2
                continue
            except Exception:
                pass
        try:
            out.append(bytes([b]).decode('cp932'))
        except Exception:
            out.append('?')
        i += 1
    return ''.join(out)


# ------------------------------------------------------------ tolerant replace

MERGED = re.compile(r'^【[^】]*】\n')


def tolerant_sub(text, needle, repl):
    """Replace `needle` even when [tags] or line breaks sit between its chars."""
    parts = [re.escape(ch) for ch in needle if ch not in '\r\n']
    if not parts:
        return text, 0
    pat = r'(?:\[[^\[\]]*\]|\r?\n)*'.join(parts)
    return re.subn(pat, lambda m: repl, text, count=1)


# ------------------------------------------------------------------- commands

def cmd_analyze(c):
    size = os.path.getsize(c.xp3)
    meta = read_index(c.xp3)
    entries = parse_entries(meta['index'])
    print('file size      :', size)
    print('magic          :', meta['magic'])
    print('index_offset   : 0x%X (tail %d bytes)' % (meta['index_offset'],
                                                    size - meta['index_offset']))
    print('index flag     :', meta['flag'])
    print('index comp/unc :', meta['comp_size'], meta['uncomp_size'])
    print('entries        :', len(entries))
    ks = script_entries(entries, c.ext)
    print('%s entries   : %d' % (c.ext, len(ks)))
    for e in sorted(ks, key=lambda x: x['name']):
        print('   %-34s usz=%7d csz=%7d segs=%d'
              % (e['name'], e['usz'], e['csz'], len(e['segs'])))
    probed = None
    for e in ks:
        if not e['segs']:
            continue
        with open(c.xp3, 'rb') as f:
            off, usz, csz = e['segs'][0]
            f.seek(off)
            blob = f.read(csz)
        if blob[:1] == b'\x78':
            try:
                blob = zlib.decompress(blob)
            except Exception:
                pass
        try:
            blob.decode('cp932')
            probed = True
        except UnicodeDecodeError:
            probed = False
        break
    if probed is False:
        print('WARNING: the first script does not decode as CP932 - this archive looks '
              'already patched. Point --xp3 at data.xp3.bak.')
    multi = [e['name'] for e in ks if len(e['segs']) > 1]
    if multi:
        print('WARNING multi-segment scripts (repack only rewrites segment 0):', multi)


def cmd_unpack(c):
    entries = parse_entries(read_index(c.xp3)['index'])
    out_root = os.path.join(c.work, 'extracted')
    n = 0
    with open(c.xp3, 'rb') as f:
        for e in script_entries(entries, c.ext):
            off, usz, csz = e['segs'][0]
            f.seek(off)
            raw = f.read(csz)
            if raw[:1] == b'\x78':                 # flags lie; trust the zlib magic
                try:
                    raw = zlib.decompress(raw)
                except Exception as ex:
                    print('  decompress fail', e['name'], ex)
            dst = os.path.join(out_root, e['name'].replace('/', os.sep))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, 'wb') as o:
                o.write(raw)
            n += 1
    print('extracted %d script(s) -> %s' % (n, out_root))


def cmd_rewrite(c):
    os.makedirs(c.new_ks, exist_ok=True)
    tunnel = SjisTunnel()
    problems, stats = [], []
    for base, jp, cn in iter_pairs(c):
        ks_path = os.path.join(c.work, 'extracted', 'scenario', base + c.ext)
        if not os.path.exists(ks_path):
            problems.append('%s: script not found' % base)
            continue
        raw_ks = open(ks_path, 'rb').read()
        try:
            text = raw_ks.decode('cp932')
        except UnicodeDecodeError as ex:
            sys.exit('%s is not CP932 (%s).\\n'
                     'If you are re-running on an already patched archive, point --xp3 at '
                     'data.xp3.bak instead.' % (ks_path, ex))
        replaced, total = 0, min(len(jp), len(cn))
        for i in range(total):
            jprose = MERGED.sub('', jp[i]['message'], count=1)
            cprose = MERGED.sub('', cn[i]['message'], count=1)
            if jprose == cprose:
                replaced += 1
                continue
            text, n = tolerant_sub(text, jprose, cprose)
            if n == 1:
                replaced += 1
            else:
                problems.append('%s[%d]: not found %r' % (base, i, jprose[:40]))
        enc = tunnel.encode(text)
        comp = zlib.compress(enc)
        with open(os.path.join(c.new_ks, base + c.ext), 'wb') as f:
            f.write(comp)
        stats.append((base, replaced, total, len(enc), len(comp)))

    chars = tunnel.mapping_string()
    with open(os.path.join(c.work, 'sjis_ext.bin'), 'wb') as f:
        f.write(chars.encode('utf-16-le'))

    print('%-16s %-12s %-9s %-9s %s' % ('script', 'replace', 'raw', 'comp', 'ratio'))
    tr = ta = 0
    for b, r, t, raw, comp in stats:
        tr += r
        ta += t
        print('%-16s %-12s %-9d %-9d %.2f' % (b, '%d/%d' % (r, t), raw, comp,
                                              comp / max(raw, 1)))
    print('\ntotal %d/%d replaced, tunnel chars %d, sjis_ext.bin %d bytes'
          % (tr, ta, len(chars), len(chars) * 2))
    print('misses:', len(problems))
    for p in problems[:40]:
        print('   ', p)
    with open(os.path.join(c.work, 'rewrite_report.json'), 'w', encoding='utf-8') as f:
        json.dump(dict(stats=stats, problems=problems, tunnel=chars), f,
                  ensure_ascii=False, indent=1)


def cmd_repack(c):
    meta = read_index(c.xp3)
    index = meta['index']
    plan = {}
    for e in script_entries(parse_entries(index), c.ext):
        new_ks = os.path.join(c.new_ks, os.path.basename(e['name']))
        if os.path.exists(new_ks):
            comp = open(new_ks, 'rb').read()       # already compressed: never recompress
            plan[e['name']] = dict(comp=comp, raw=len(zlib.decompress(comp)), e=e)
    print('scripts to replace:', len(plan))

    cur = meta['index_offset']
    for info in plan.values():
        e = info['e']
        raw_size, comp_size = info['raw'], len(info['comp'])
        struct.pack_into('<Q', index, e['info_off'] + 4, raw_size)
        struct.pack_into('<Q', index, e['info_off'] + 12, comp_size)
        struct.pack_into('<Q', index, e['segm_off'] + 4, cur)
        struct.pack_into('<Q', index, e['segm_off'] + 12, raw_size)
        struct.pack_into('<Q', index, e['segm_off'] + 20, comp_size)
        if e['adlr_off']:
            struct.pack_into('<I', index, e['adlr_off'], zlib.adler32(info['comp']) & 0xFFFFFFFF)
        cur += comp_size

    new_index_comp = zlib.compress(bytes(index))
    with open(c.xp3, 'rb') as src, open(c.new_xp3, 'wb') as out:
        remain = meta['index_offset']
        src.seek(0)
        while remain > 0:
            chunk = src.read(min(1 << 20, remain))
            if not chunk:
                break
            out.write(chunk)
            remain -= len(chunk)
        for info in plan.values():
            out.write(info['comp'])
        new_index_offset = out.tell()
        out.write(b'\x01')
        out.write(struct.pack('<Q', len(new_index_comp)))
        out.write(struct.pack('<Q', len(index)))
        out.write(new_index_comp)
        out.seek(0x20)
        out.write(struct.pack('<Q', new_index_offset))
    print('output:', c.new_xp3, os.path.getsize(c.new_xp3), 'bytes')


def cmd_verify(c):
    entries = {e['name']: e for e in parse_entries(read_index(c.new_xp3)['index'])}
    chars = open(os.path.join(c.work, 'sjis_ext.bin'), 'rb').read().decode('utf-16-le')
    kana = re.compile(r'[\u3041-\u3096\u30a1-\u30f6]')
    tag = re.compile(r'\[[^\[\]]*\]')
    checked = bad = leftover = 0
    samples = []
    for name, e in entries.items():
        if not name or not name.lower().endswith(c.ext):
            continue
        if not os.path.exists(os.path.join(c.new_ks, os.path.basename(name))):
            continue
        off, usz, csz = e['segs'][0]
        with open(c.new_xp3, 'rb') as f:
            f.seek(off)
            raw = zlib.decompress(f.read(csz))
        checked += 1
        if not (len(raw) == e['usz'] == usz and csz == e['csz']):
            bad += 1
            print('  MISMATCH', name, len(raw), e['usz'], usz)
        txt = decode_tunnel(raw, chars)
        for ln in txt.split('\n'):
            body = ln.strip()
            if not body or body.startswith(';') or body.startswith('*'):
                continue
            if kana.search(tag.sub('', body)) and len(tag.sub('', body).strip()) >= 6:
                leftover += 1
        if len(samples) < 6:
            for ln in txt.split('\n'):
                if '「' in ln and re.search(r'[\u4e00-\u9fff]', ln):
                    samples.append('%s: %s' % (os.path.basename(name), ln.strip()[:60]))
                    break
    print('checked %d script(s), size/compression mismatches: %d' % (checked, bad))
    print('lines still containing kana: %d' % leftover)
    for s in samples:
        print('  ', s)


def cmd_deploy(c):
    bak = os.path.join(c.game, 'data.xp3.bak')
    if not os.path.exists(bak):
        shutil.copy2(c.xp3, bak)
        print('backup ->', bak)
    else:
        print('backup already exists:', bak)
    shutil.copy2(c.new_xp3, c.xp3)
    print('replaced', c.xp3)
    shutil.copy2(os.path.join(c.work, 'sjis_ext.bin'), os.path.join(c.game, 'sjis_ext.bin'))
    print('copied sjis_ext.bin')
    if not c.proxy_dir:
        print('no --proxy-dir given; copy d3d9.dll/winmm.dll/version.dll yourself')
        return
    for name in ('d3d9.dll', 'winmm.dll', 'version.dll', 'ddraw.dll'):
        src = os.path.join(c.proxy_dir, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(c.game, name))
            print('copied', name, os.path.getsize(src))


# ------------------------------------------------------------------- plumbing

def iter_pairs(c):
    gi = os.path.join(c.text, 'gt_input')
    go = os.path.join(c.text, 'gt_output')
    if not os.path.isdir(go):
        sys.exit('missing %s' % go)
    for jf in sorted(f for f in os.listdir(go) if f.endswith('.json')):
        base = jf[:-5]
        if base in c.skip:
            continue
        jp_path = os.path.join(gi, jf)
        if not os.path.exists(jp_path):
            print('  no gt_input for', jf)
            continue
        yield (base,
               json.load(open(jp_path, encoding='utf-8')),
               json.load(open(os.path.join(go, jf), encoding='utf-8')))


def build_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('step', choices=['analyze', 'unpack', 'rewrite', 'repack',
                                    'verify', 'deploy', 'all'])
    p.add_argument('--game', required=True, help='game directory (holds data.xp3)')
    p.add_argument('--text', help='translation root containing gt_input/ and gt_output/ '
                                  '(default: <game>/文本)')
    p.add_argument('--work', help='working directory (default: <game>/_work)')
    p.add_argument('--xp3', help='archive to read (default: <game>/data.xp3)')
    p.add_argument('--ext', default='.ks', help='script extension (default: .ks)')
    p.add_argument('--skip', default='', help='comma separated script stems to skip, e.g. mcr_add')
    p.add_argument('--proxy-dir', default='', help='folder holding VNTextProxy dlls (deploy only)')
    c = p.parse_args(argv)
    c.text = c.text or os.path.join(c.game, '文本')
    c.work = c.work or os.path.join(c.game, '_work')
    c.xp3 = c.xp3 or os.path.join(c.game, 'data.xp3')
    c.new_ks = os.path.join(c.work, 'new_ks')
    c.new_xp3 = os.path.join(c.work, 'data_new.xp3')
    c.skip = {s.strip() for s in c.skip.split(',') if s.strip()}
    return c


def main(argv=None):
    c = build_args(argv)
    steps = ['analyze', 'unpack', 'rewrite', 'repack', 'verify'] if c.step == 'all' else [c.step]
    table = dict(analyze=cmd_analyze, unpack=cmd_unpack, rewrite=cmd_rewrite,
                 repack=cmd_repack, verify=cmd_verify, deploy=cmd_deploy)
    for s in steps:
        print('=== %s ===' % s)
        table[s](c)
        print()


if __name__ == '__main__':
    main()
