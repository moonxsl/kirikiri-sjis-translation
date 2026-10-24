# -*- coding: utf-8 -*-
import struct, zlib, os

SRC_XP3 = r'D:\熟悉\data.xp3.bak'      # 原始主包（只读）
OUT_KS  = r'D:\熟悉\_work\new_ks'
OUT_XP3 = r'D:\熟悉\_work\data_new.xp3'

with open(SRC_XP3,'rb') as f:
    f.seek(0x20)
    index_offset = struct.unpack('<Q', f.read(8))[0]
    f.seek(index_offset+1)
    comp_size = struct.unpack('<Q', f.read(8))[0]
    uncomp_size = struct.unpack('<Q', f.read(8))[0]
    comp_data = f.read(comp_size)
    index_data = bytearray(zlib.decompress(comp_data))

    # 解析索引，记录每个 ks 条目位置
    pos = 0
    modified = {}   # xp3内部路径 -> info
    while pos < len(index_data):
        if index_data[pos:pos+4] != b'File': break
        data_size = struct.unpack('<Q', index_data[pos+4:pos+12])[0]
        data_start = pos+12; data_end = data_start+data_size
        sub = data_start
        filename=None; info_pos=segm_pos=adlr_pos=0
        while sub+12 <= data_end:
            sid = index_data[sub:sub+4]
            ssize = struct.unpack('<Q', index_data[sub+4:sub+12])[0]
            sd = sub+12
            if sid==b'info':
                info_pos = sd
                p = sd+4+8+8
                nl = struct.unpack('<H', index_data[p:p+2])[0]
                p+=2
                filename = index_data[p:p+nl*2].decode('utf-16-le')
            elif sid==b'segm':
                segm_pos = sd
            elif sid==b'adlr':
                adlr_pos = sd
            sub = sd+ssize
        if filename and filename.endswith('.ks'):
            base = os.path.basename(filename)
            new_ks = os.path.join(OUT_KS, base)
            if os.path.exists(new_ks):
                comp = open(new_ks,'rb').read()      # rewrite.py 已 zlib 压缩
                raw = zlib.decompress(comp)           # 明文(隧道编码后)
                modified[filename] = dict(
                    info_pos=info_pos, segm_pos=segm_pos, adlr_pos=adlr_pos,
                    raw_size=len(raw), comp=comp)
        pos = data_end

    print("待替换 ks:", len(modified))

    # 计算新偏移：从 index_offset 开始依次放替换后的数据
    cur = index_offset
    for fn,info in modified.items():
        # info: +4 uncomp, +12 comp
        struct.pack_into('<Q', index_data, info['info_pos']+4, info['raw_size'])
        struct.pack_into('<Q', index_data, info['info_pos']+12, len(info['comp']))
        # segm: +4 offset, +12 uncomp, +20 comp
        struct.pack_into('<Q', index_data, info['segm_pos']+4, cur)
        struct.pack_into('<Q', index_data, info['segm_pos']+12, info['raw_size'])
        struct.pack_into('<Q', index_data, info['segm_pos']+20, len(info['comp']))
        if info['adlr_pos']:
            struct.pack_into('<I', index_data, info['adlr_pos'],
                             zlib.adler32(info['comp']) & 0xFFFFFFFF)
        cur += len(info['comp'])

    new_index_comp = zlib.compress(bytes(index_data))

    with open(OUT_XP3,'wb') as out:
        # 1. 原样拷贝 [0, index_offset)
        f.seek(0); remain = index_offset
        while remain>0:
            chunk = f.read(min(1<<20, remain))
            if not chunk: break
            out.write(chunk); remain -= len(chunk)
        # 2. 追加替换后 ks 的压缩数据
        for info in modified.values():
            out.write(info['comp'])
        # 3. 写新索引块
        new_index_offset = out.tell()
        out.write(b'\x01')
        out.write(struct.pack('<Q', len(new_index_comp)))
        out.write(struct.pack('<Q', len(index_data)))
        out.write(new_index_comp)
        # 4. 写回索引偏移
        out.seek(0x20)
        out.write(struct.pack('<Q', new_index_offset))

print("输出:", OUT_XP3, os.path.getsize(OUT_XP3), "字节")
