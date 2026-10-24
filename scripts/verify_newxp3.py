# -*- coding: utf-8 -*-
import struct, zlib, os
XP3=r'D:\熟悉\_work\data_new.xp3'
f=open(XP3,'rb')
magic=f.read(7); print("magic:",magic)
f.seek(0x20); io=struct.unpack('<Q',f.read(8))[0]
print("index_offset: 0x%X"%io)
f.seek(io+1); cs=struct.unpack('<Q',f.read(8))[0]; us=struct.unpack('<Q',f.read(8))[0]
idx=zlib.decompress(f.read(cs))
print("index decompressed:",len(idx))
pos=0; found=0
while pos+12<=len(idx):
    if idx[pos:pos+4]!=b'File': break
    ds=struct.unpack('<Q',idx[pos+4:pos+12])[0]; de=pos+12+ds; sub=pos+12
    fn=None; info_off=info_usz=info_csz=0; segs=[]
    while sub+12<=de:
        sid=idx[sub:sub+4]; ss=struct.unpack('<Q',idx[sub+4:sub+12])[0]; sd=sub+12
        if sid==b'info':
            info_usz=struct.unpack('<Q',idx[sd+4:sd+12])[0]
            info_csz=struct.unpack('<Q',idx[sd+12:sd+20])[0]
            nl=struct.unpack('<H',idx[sd+20:sd+22])[0]
            fn=idx[sd+22:sd+22+nl*2].decode('utf-16-le')
        elif sid==b'segm':
            cnt=struct.unpack('<I',idx[sd:sd+4])[0]; p=sd+4
            for _ in range(cnt):
                o=struct.unpack('<Q',idx[p:p+8])[0];u=struct.unpack('<Q',idx[p+8:p+16])[0];c=struct.unpack('<Q',idx[p+16:p+24])[0]
                segs.append((o,u,c)); p+=24
        sub=sd+ss
    if fn=='scenario/scn_hyouka.ks':
        found+=1
        o,u,c=segs[0]
        f.seek(o); raw=f.read(c)
        data=zlib.decompress(raw)
        print(f"\nscn_hyouka.ks: info_usz={info_usz} actual={len(data)} match={info_usz==len(data)} segm_u={u} segm_c={c}")
        txt=data.decode('cp932',errors='replace')
        # 找对白行
        for ln in txt.split('\n'):
            if 'PV' in ln or 'はいっ' in ln or '炮' in ln or '不错' in ln:
                print("  行:",ln.strip()[:60])
    pos=de
print("\n校验完成，找到 hyouka:",found)
