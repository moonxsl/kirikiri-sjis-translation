# -*- coding: utf-8 -*-
import os, re, json
SRC=r'D:\熟悉\_work\extracted\scenario'; GTI=r'D:\熟悉\文本\gt_input'; GTO=r'D:\熟悉\文本\gt_output'
MERGED=re.compile(r'^【[^】]*】\n')
kana=re.compile(r'[ぁ-んァ-ヶ]')

def peel_tags(b):
    while b.startswith('['):
        d=0;e=None
        for i,ch in enumerate(b):
            if ch=='[':d+=1
            elif ch==']':
                d-=1
                if d==0:e=i;break
        if e is None:break
        b=b[e+1:]
    while b.endswith(']'):
        d=0;s=None
        for i in range(len(b)-1,-1,-1):
            if b[i]==']':d+=1
            elif b[i]=='[':
                d-=1
                if d==0:s=i;break
        if s is None:break
        b=b[:s]
    return b

allgaps=0
for jf in sorted(f for f in os.listdir(GTO) if f.endswith('.json')):
    base=jf[:-5]
    if base=='mcr_add': continue
    text=open(os.path.join(SRC,base+'.ks'),'rb').read().decode('cp932')
    jp=json.load(open(os.path.join(GTI,jf),encoding='utf-8'))
    cn=json.load(open(os.path.join(GTO,jf),encoding='utf-8'))
    for i in range(min(len(jp),len(cn))):
        jn=MERGED.sub('',jp[i]['message'],count=1)
        cp=MERGED.sub('',cn[i]['message'],count=1)
        if jn==cp: continue
        nchar=[re.escape(c) for c in jn if c not in '\r\n']
        text=re.sub(r'(?:\[[^\[\]]*\]|\r?\n)*'.join(nchar), lambda m: cp, text, count=1)
    # scan leftover kana lines
    leftover=[]
    for ln in text.split('\n'):
        body=ln.rstrip('\r').strip()
        if not body or body.startswith(';') or body.startswith('*'): continue
        inner=peel_tags(body)
        if kana.search(inner) and len(inner.strip())>=6:
            leftover.append(inner.strip()[:50])
    if leftover:
        allgaps+=len(leftover)
        print(f"--- {base}: 残留 {len(leftover)} 行 ---")
        for l in leftover[:12]: print("   ", l)
print("\n残留日文行合计:", allgaps)
