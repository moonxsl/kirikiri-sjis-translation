import struct, zlib, os

XP3 = r'D:\熟悉\data.xp3'
OUT = r'D:\熟悉\_work\extracted'

with open(XP3, 'rb') as f:
    magic = f.read(7)
    print("magic:", magic)
    f.seek(0x20)
    index_offset = struct.unpack('<Q', f.read(8))[0]
    print("index_offset: 0x%X" % index_offset)

    f.seek(index_offset)
    flag = f.read(1)
    comp_size = struct.unpack('<Q', f.read(8))[0]
    uncomp_size = struct.unpack('<Q', f.read(8))[0]
    print("index flag:", flag, "comp_size:", comp_size, "uncomp_size:", uncomp_size)
    comp_data = f.read(comp_size)
    index_data = zlib.decompress(comp_data)
    print("index decompressed:", len(index_data))

    # parse entries
    pos = 0
    entries = []
    while pos + 12 <= len(index_data):
        if index_data[pos:pos+4] != b'File':
            print("stop at", pos, index_data[pos:pos+8]); break
        data_size = struct.unpack('<Q', index_data[pos+4:pos+12])[0]
        data_start = pos + 12
        data_end = data_start + data_size
        sub = data_start
        filename = None; flags = 0; usz=0; csz=0; segs=[]
        while sub + 12 <= data_end:
            sid = index_data[sub:sub+4]
            ssize = struct.unpack('<Q', index_data[sub+4:sub+12])[0]
            sdata = sub + 12
            if sid == b'info':
                p = sdata
                flags = struct.unpack('<I', index_data[p:p+4])[0]; p+=4
                usz = struct.unpack('<Q', index_data[p:p+8])[0]; p+=8
                csz = struct.unpack('<Q', index_data[p:p+8])[0]; p+=8
                nlen = struct.unpack('<H', index_data[p:p+2])[0]; p+=2
                filename = index_data[p:p+nlen*2].decode('utf-16-le')
            elif sid == b'segm':
                p = sdata
                cnt = struct.unpack('<I', index_data[p:p+4])[0]; p+=4
                for _ in range(cnt):
                    off = struct.unpack('<Q', index_data[p:p+8])[0]; p+=8
                    u = struct.unpack('<Q', index_data[p:p+8])[0]; p+=8
                    c = struct.unpack('<Q', index_data[p:p+8])[0]; p+=8
                    segs.append((off,u,c))
            sub = sdata + ssize
        entries.append(dict(filename=filename, flags=flags, usz=usz, csz=csz, segs=segs))
        pos = data_end

    print("total entries:", len(entries))
    ks = [e for e in entries if e['filename'] and e['filename'].lower().endswith('.ks')]
    print("ks files:", len(ks))
    for e in ks:
        print("  ", e['filename'], "flags=%d"%e['flags'], "usz=%d"%e['usz'], "csz=%d"%e['csz'], "segs=%s"%(e['segs'],))

    # extract
    os.makedirs(OUT, exist_ok=True)
    for e in entries:
        fn = e['filename']
        if not fn or not e['segs']: continue
        off,u,c = e['segs'][0]
        f.seek(off)
        raw = f.read(c)
        # this archive stores ks zlib-compressed regardless of flags bit
        if raw[:1] == b'\x78':
            try:
                raw = zlib.decompress(raw)
            except Exception as ex:
                print("decompress fail", fn, ex)
        outp = os.path.join(OUT, fn.replace('/', os.sep))
        os.makedirs(os.path.dirname(outp), exist_ok=True)
        with open(outp,'wb') as o:
            o.write(raw)
    print("extracted to", OUT)
