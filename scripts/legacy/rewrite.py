# -*- coding: utf-8 -*-
import os, re, json, zlib

SRC_KS = r'D:\熟悉\_work\extracted\scenario'
GT_IN  = r'D:\熟悉\文本\gt_input'
GT_OUT = r'D:\熟悉\文本\gt_output'
OUT_KS = r'D:\熟悉\_work\new_ks'
os.makedirs(OUT_KS, exist_ok=True)
SKIP_FILES = {'mcr_add'}   # UI/宏脚本，不译

class SjisTunnel:
    def __init__(self):
        self._mapping = {}
    def _get(self, ch):
        if ch in self._mapping: return self._mapping[ch]
        idx = len(self._mapping)
        if idx >= 0x3B * 0x3A:
            raise Exception("SJIS tunnel limit exceeded")
        hi = idx // 0x3A; lo = idx % 0x3A
        hb = 0x81 + hi if hi < 0x1F else 0xE0 + (hi - 0x1F)
        lb = 1 + lo
        for s in (0x09,0x0A,0x0D,0x20,0x2C):
            if lb >= s: lb += 1
        tc = chr((hb << 8) | lb)
        self._mapping[ch] = tc
        return tc
    def encode(self, text):
        out = bytearray()
        for ch in text:
            try:
                raw = ch.encode('cp932')
                if raw[0] >= 0xF0:
                    raise UnicodeEncodeError('cp932', ch, 0, 1, '')
                out.extend(raw)
            except UnicodeEncodeError:
                tc = ord(self._get(ch)); out.append(tc>>8); out.append(tc&0xFF)
        return bytes(out)
    def mapping_string(self):
        return ''.join(sorted(self._mapping.keys(), key=lambda c: self._mapping[c]))

MERGED_RE = re.compile(r'^【[^】]*】\n')

def tolerant_sub(text, needle, repl):
    # 在每个字符间允许夹任意 [...] 内联标签或换行，兼容 [ruby..]/[r]
    parts = [re.escape(ch) for ch in needle]
    pat = r'(?:\[[^\[\]]*\]|\r?\n)*'.join(parts)
    return re.sub(pat, lambda m: repl, text, count=1)

tunnel = SjisTunnel()
problems = []
total_replaced = 0

for jf in sorted(f for f in os.listdir(GT_OUT) if f.endswith('.json')):
    base = jf[:-5]
    if base in SKIP_FILES: continue
    ks_path = os.path.join(SRC_KS, base + '.ks')
    if not os.path.exists(ks_path):
        problems.append(f"{jf}: 找不到 ks"); continue
    jp = json.load(open(os.path.join(GT_IN, jf), encoding='utf-8'))
    cn = json.load(open(os.path.join(GT_OUT, jf), encoding='utf-8'))
    text = open(ks_path,'rb').read().decode('cp932')

    replaced = 0
    for i in range(min(len(jp), len(cn))):
        jm = jp[i]['message']; cm = cn[i]['message']
        jp_prose = MERGED_RE.sub('', jm, count=1)   # 剥掉开头 【名】\n
        cn_prose = MERGED_RE.sub('', cm, count=1)
        if jp_prose == cn_prose:
            replaced += 1; continue
        # 去掉换行：字符间容错组已能吃掉 [r] / CRLF
        nchar = [re.escape(c) for c in jp_prose if c not in '\r\n']
        new_text, n = re.subn(
            r'(?:\[[^\[\]]*\]|\r?\n)*'.join(nchar),
            lambda m: cn_prose, text, count=1)
        if n == 1:
            text = new_text; replaced += 1
        else:
            problems.append(f"{jf}[{i}]: 未找到日文 '{jp_prose[:40]}'")
    total_replaced += replaced
    enc = tunnel.encode(text)
    open(os.path.join(OUT_KS, base+'.ks'),'wb').write(zlib.compress(enc))
    print(f"{base:18s} 替换 {replaced:3d}/{min(len(jp),len(cn)):3d}  raw={len(enc):6d} comp={len(zlib.compress(enc)):6d}")

print("\n=== 汇总 ===")
print("总替换:", total_replaced, " 隧道汉字:", len(tunnel._mapping))
sx = tunnel.mapping_string().encode('utf-16-le')
open(r'D:\熟悉\_work\sjis_ext.bin','wb').write(sx)
print("sjis_ext.bin:", len(sx), "字节")
print("\n=== 未找到 (%d) ===" % len(problems))
for p in problems: print("  ", p)
