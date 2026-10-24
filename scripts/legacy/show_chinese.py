# -*- coding: utf-8 -*-
import struct, zlib
sx = open(r'D:\熟悉\_work\sjis_ext.bin','rb').read()
chars = sx.decode('utf-16-le')
tunnel={}
idx=0
while idx < len(chars):
    hi = idx // 0x3A; lo = idx % 0x3A
    hb = 0x81+hi if hi < 0x1F else 0xE0+(hi-0x1F)
    lb = 1+lo
    for s in (0x09,0x0A,0x0D,0x20,0x2C):
        if lb>=s: lb+=1
    tunnel[(hb,lb)] = chars[idx]
    idx+=1

def dec(data):
    out=[]; i=0
    while i < len(data):
        b=data[i]
        if (0x81<=b<=0x9F or 0xE0<=b<=0xFC) and i+1<len(data):
            if (b,data[i+1]) in tunnel:
                out.append(tunnel[(b,data[i+1])]); i+=2; continue
            try:
                out.append(data[i:i+2].decode('cp932')); i+=2; continue
            except: pass
        try: out.append(bytes([b]).decode('cp932'))
        except: out.append('?')
        i+=1
    return ''.join(out)

f=open(r'D:\熟悉\_work\data_new.xp3','rb')
f.seek(0x20); io=struct.unpack('<Q',f.read(8))[0]
f.seek(io+1); cs=struct.unpack('<Q',f.read(8))[0]; f.read(8)
data=zlib.decompress(f.read(cs))
pos=0
while pos+12<=len(data):
    if data[pos:pos+4]!=b'File': break
    ds=struct.unpack('<Q',data[pos+4:pos+12])[0]; de=pos+12+ds; sub=pos+12
    fn=None; segs=[]
    while sub+12<=de:
        sid=data[sub:sub+4]; ss=struct.unpack('<Q',data[sub+4:sub+12])[0]; sd=sub+12
        if sid==b'info':
            nl=struct.unpack('<H',data[sd+20:sd+22])[0]
            fn=data[sd+22:sd+22+nl*2].decode('utf-16-le')
        elif sid==b'segm':
            cnt=struct.unpack('<I',data[sd:sd+4])[0]; p=sd+4
            for _ in range(cnt):
                o=struct.unpack('<Q',data[p:p+8])[0];u=struct.unpack('<Q',data[p+8:p+16])[0];c=struct.unpack('<Q',data[p+16:p+24])[0]
                segs.append((o,u,c));p+=24
        sub=sd+ss
    if fn=='scenario/scn_hyouka.ks':
        o,u,c=segs[0]; f.seek(o); raw=zlib.decompress(f.read(c))
        print(dec(raw))
    pos=de
