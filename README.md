---
name: kirikiri-sjis-tunnel-guide
description: KiriKiri/吉里吉里引擎 Galgame 中文汉化回写方案（实战验证版）。当 UIF/winmm hook 崩溃、patch.xp3 不加载、引擎硬编码 CP932 时使用。适用 D3D9 渲染文字、自定义 KAG 方言的老 Krkr 游戏。完整流程：解包 XP3 → GalTransl 翻译 → 容错正则回写 → SJIS 隧道编码 → 单次 zlib 重打包 → d3d9.dll 代理部署。
---

# KiriKiri SJIS 隧道回写方案（实战验证版）

> 本方案在《えすえむ学園～豊島優里花～》（smg.exe，data.xp3）上完整跑通。
> 与纯理论版的区别：以下每一条都是实际踩坑后修正的结论，不要凭"应该这样"跳过任何一步。

---

## 🚀 使用方式

**把本文件整份复制，粘贴给任意一个 AI（Claude / GPT / 豆包 / 通义千问等），告诉它：**

> "按照这个 skill 的步骤，帮我汉化这个 KiriKiri 游戏，游戏目录在 `D:\xxx`，翻译好的文本在 `D:\xxx\gt_output`。"

AI 会按照本文档的完整流程（解包 → 回写 → 隧道编码 → 重打包 → 部署）自动执行。

---

## 适用场景

- 引擎：KiriKiri / KAG3（吉里吉里），data.xp3 打包
- 文字通过 **D3D9** 渲染（不是 GDI TextOut）
- 引擎硬编码 CP932（Shift_JIS），无视 UTF-8/UTF-16 BOM
- UIF winmm hook 崩溃或拦不到文字
- patch.xp3 不被自动加载（exe 写死只加载 data.xp3）

## 核心原理

1. **SJIS 隧道编码**：中文里不在 CP932 中的字，映射到 CP932 未分配双字节码位。游戏把这些字节当正常日文读入，不报错。
2. **VNTextProxy d3d9.dll**：代理 DLL hook D3D9 文字渲染，读 `sjis_ext.bin` 把隧道码位还原成真正的中文字符。
3. **直接改 data.xp3**：不做 patch.xp3，直接重打主包。

---

## 完整流程

### 第 0 步：备份

```powershell
Copy-Item "D:\游戏目录\data.xp3" "D:\游戏目录\data.xp3.bak"
```

### 第 1 步：解包 data.xp3

XP3 格式要点（实测）：
- 文件偏移 `0x20` 处是 uint64 LE，存索引块偏移
- 索引块 = `flag(1B, 通常0x01)` + `comp_size(8B LE)` + `uncomp_size(8B LE)` + zlib 压缩的索引数据
- 索引解压后是一连串 `File` 条目，每条：`'File'(4B) + data_size(8B LE) + data`
- 每个 File data 里有三个子块：`info` / `segm` / `adlr`
  - **info**: `flags(4B) + uncomp_size(8B) + comp_size(8B) + name_len(2B) + name(UTF-16LE)`
  - **segm**: `seg_count(4B) + 每个段: offset(8B) + uncomp_size(8B) + comp_size(8B)`
  - **adlr**: `adler32(4B)` 压缩数据校验和
- 注意：某些 ks 文件 flags=0 但实际数据仍是 zlib 压缩的（首字节 `0x78`），不要信 flags 字段

解包脚本核心：
```python
import struct, zlib
with open('data.xp3','rb') as f:
    f.seek(0x20)
    index_offset = struct.unpack('<Q', f.read(8))[0]
    f.seek(index_offset + 1)          # 跳过 flag 字节
    comp_size   = struct.unpack('<Q', f.read(8))[0]
    uncomp_size = struct.unpack('<Q', f.read(8))[0]
    index_data  = zlib.decompress(f.read(comp_size))
    # 然后遍历 File 条目，按 segm offset 读出每个文件的压缩数据，zlib.decompress
```

### 第 2 步：提取对白为 JSON（GalTransl 输入）

对白结构（实测）：
- 名单独行：`[locklink]【佐渡教官】[r]`
- 对白行：`[PV file=..]「…」[/PV][unlocklink]` 或 `「…」[PG]`
- 外层标签 `[tag]` 不要提取，中间正文才是 message
- 提取后喂给 GalTransl，输出 `gt_output/*.json`

### 第 3 步：容错正则回写（关键坑点）

**坑**：ks 原文里句子中间夹着 `[ruby text=とげ]` 注音标签和 `[r]` 强制换行标签。GalTransl 提取时把这些标签剥掉了，导致"日文子串"在 ks 里对不上——因为 ks 里标签还插在句子中间。

**正确做法**：用容错正则，允许两个字符之间夹任意 `[...]` 标签或换行：

```python
import re
def tolerant_sub(text, needle, repl):
    parts = [re.escape(ch) for ch in needle if ch not in '\r\n']
    # 字符间允许夹任意 [...] 标签或 CRLF
    pat = r'(?:\[[^\[\]]*\]|\r?\n)*'.join(parts)
    return re.subn(pat, lambda m: repl, text, count=1)
```

- 把 needle 里的 `\n` 去掉（因为标签/换行会被容错组吃掉）
- 名单独行前缀 `【名】\n` 用 `re.compile(r'^【[^】]*】\n')` 剥掉
- UI/宏脚本（如 `mcr_add.ks`，成就进度那种）跳过不译

### 第 4 步：SJIS 隧道编码

```python
class SjisTunnel:
    def __init__(self):
        self._mapping = {}
    def _get(self, ch):
        if ch in self._mapping: return self._mapping[ch]
        idx = len(self._mapping)
        hi = idx // 0x3A; lo = idx % 0x3A
        hb = 0x81+hi if hi < 0x1F else 0xE0+(hi-0x1F)
        lb = 1+lo
        for s in (0x09,0x0A,0x0D,0x20,0x2C):
            if lb >= s: lb += 1
        tc = chr((hb<<8)|lb)
        self._mapping[ch] = tc
        return tc
    def encode(self, text):
        out = bytearray()
        for ch in text:
            try:
                raw = ch.encode('cp932')
                if raw[0] >= 0xF0: raise UnicodeEncodeError
                out.extend(raw)
            except UnicodeEncodeError:
                tc = ord(self._get(ch))
                out.append(tc>>8); out.append(tc&0xFF)
        return bytes(out)
```

**sjis_ext.bin 格式**（关键坑点）：
```python
chars = sorted(tunnel._mapping.keys(), key=lambda c: tunnel._mapping[c])
open('sjis_ext.bin','wb').write(''.join(chars).encode('utf-16-le'))
```
- **必须是 UTF-16LE 原始汉字**，按隧道索引顺序排列
- **不是**隧道码位的字节对（写成字节对会导致字全错，如"脏"变"饭"）
- 文件大小 = 汉字数 × 2（例：612 汉字 = 1224 字节）

### 第 5 步：重打包（双重压缩坑点）

**最致命的坑**：如果第 4 步输出的 ks 文件已经是 `zlib.compress(隧道字节)`，第 5 步 **绝对不能再压一次**。否则游戏解压一次后得到的还是 zlib 流，整个文件全是乱码。

**正确流程**：
- 第 4 步：把每个 ks 的隧道编码字节 `zlib.compress()` 后写入 new_ks 文件（这是给游戏用的压缩态）
- 第 5 步：repack 时直接读 new_ks 的压缩字节作为 segm 数据，**usz 用解压后明文长度，csz 用压缩字节长度**，不要再 compress()

```python
# repack 核心
for filename in modified_files:
    comp = open(new_ks_path, 'rb').read()      # 已经是压缩好的
    raw  = zlib.decompress(comp)               # 只为拿长度
    info_usz = len(raw)
    info_csz = len(comp)
    segm_offset = current_offset                # 新位置
    segm_usz = len(raw)
    segm_csz = len(comp)
    adler    = zlib.adler32(comp) & 0xFFFFFFFF
    current_offset += len(comp)
```

新文件布局：
1. 原样拷贝原 xp3 的 `[0, index_offset)` 段
2. 追加所有修改后 ks 的压缩数据（按上面算好的 offset 顺序）
3. 写新索引块：`0x01` + `new_index_comp_size` + `new_index_uncomp_size` + `zlib.compress(新索引)`
4. 在文件 `0x20` 处写新索引块的偏移

### 第 6 步：部署代理 DLL（这次失败的直接原因）

**最大坑**：不要只按 `smg.exe` 静态导入表选 DLL！

KiriKiri 文字渲染走 D3D9，但 `d3d9.dll` 通常是**运行时 LoadLibrary 动态加载**的，静态导入表里看不到。我第一次只按导入表放了 `ddraw.dll` + `winmm.dll`，结果 hook 完全没拦到文字，隧道字节被游戏当日文直接画出来 = 满屏乱码。

**正确做法**：直接把 VNTextProxy 目录里这几个 DLL 全复制到游戏目录：

```powershell
Copy-Item "VNTextProxy\d3d9.dll"      "游戏目录\"   # 关键！hook D3D9 文字渲染
Copy-Item "VNTextProxy\winmm.dll"     "游戏目录\"   # 代理
Copy-Item "VNTextProxy\version.dll"   "游戏目录\"   # 备用加载入口
Copy-Item "VNTextProxy\ddraw.dll"     "游戏目录\"   # 如有导入
Copy-Item "sjis_ext.bin"              "游戏目录\"   # 隧道映射表
```

- `d3d9.dll` 是文字 hook 的核心，**必须放**，不要因为导入表里没有就不放
- `sjis_ext.bin` 必须和 d3d9.dll 同目录

### 第 7 步：运行验证

- 窗口/全屏均可运行（已验证全屏也正常显示中文）
- 标题菜单日文正常，进入对话后对白显示中文
- 如果对话还是乱码：
  - 全是奇怪日文/符号 → d3d9.dll 没加载，检查 DLL 位数是否和 exe 匹配
  - 能看出中文但字错/顺序乱 → sjis_ext.bin 编码错（检查是否 UTF-16LE、顺序）
  - 中文位置是豆腐块 □ → 字体缺字

---

## 死路（不要重复试）

| 方案 | 结果 |
|---|---|
| UTF-8 BOM / UTF-16LE BOM | 引擎无视 BOM，乱码 |
| GBK 全量转换 | 引擎强制 CP932，乱码 |
| UIF winmm + TextOutA/W | D3D9 绕过 GDI，拦不到 |
| UIF + ExtTextOutW / GetGlyphOutlineW | EAccessViolation 崩溃 |
| UIF tunnel_decoder hook MultiByteToWideChar | EAccessViolation 崩溃 |
| patch.xp3 补丁包 | 此游戏 exe 写死只加载 data.xp3 |
| scenario/ 散文件 | 此游戏不读散文件 |
| 只按静态导入表放 DLL | d3d9.dll 动态加载，导入表看不到，hook 失效（本次实战踩坑） |
| repack 时对已压缩 ks 再 zlib.compress | 双层压缩，游戏解压一次后还是压缩流，全乱码（本次实战踩坑） |

## 验证清单

- [ ] data.xp3.bak 已备份
- [ ] new_ks 解压后明文长度 == 索引 info.usz
- [ ] sjis_ext.bin 大小 == 汉字数 × 2，UTF-16LE
- [ ] d3d9.dll 已放入游戏目录（不要管静态导入表）
- [ ] 运行窗口/全屏均可，不需要 Locale Emulator
- [ ] 标题菜单日文正常，对白中文正常
