---
name: kirikiri-sjis-tunnel-guide
description: KiriKiri/吉里吉里（KAG3）Galgame 中文汉化回写方案（实战验证版）。当 UIF/winmm hook 崩溃、patch.xp3 不加载、引擎硬编码 CP932 时使用。含适用性判定、失败症状速查、SJIS 隧道编码、单次 zlib 重打包与代理 DLL 部署。适用于 D3D9/GDI 渲染文字、自定义 KAG 方言的老 Krkr 游戏。
---

# KiriKiri SJIS 隧道回写方案（实战验证版）

> 本方案在《えすえむ学園～豊島優里花～》（`smg.exe` + `data.xp3`）上完整跑通，并在 2026-10 复现。
> 与纯理论版的区别：下面每一条都是踩坑后修正的结论。
> 但它同时是一个**单案例**文档：凡是标注「本作专属」的结论，换游戏必须重新验证。

**一句话**：不改引擎、不改 exe、不换字体，把中文塞进 CP932 里"正常文本永远不会生成"的字节对，再用一个代理 DLL 在绘制前把它们换回真汉字。

**边界**：这套方案只治**对白文字**。图片里的文字（标题、按钮、CG）治不了；没翻译的脚本（菜单、UI）也不会自动变中文。

---

## 🚦 先判定，再动手

照着做之前先确认这 5 条。任何一条不成立，后面的流程就会在错误的方向上消耗几小时。

| # | 检查 | 怎么查 | 不成立怎么办 |
|---|---|---|---|
| 1 | 归档能解开 | `python scripts/krr.py analyze --game <目录>` | 索引不是 zlib 明文（加密 XP3）→ 先解决解密（GARbro / KrkrExtract），本方案不涉及 |
| 2 | 脚本真的是 CP932 | 解包出的 `.ks` 能用 `cp932` 解码 | 已经是 UTF-8/UTF-16 的引擎，**不要用隧道**，直接写 Unicode 更省事 |
| 3 | 绘制出口能被代理拦到 | 塞 3 个隧道汉字跑一次 | 见下方「30 分钟试跑」 |
| 4 | 容量够 | 预计不重复汉字数 < **2726** | 长篇作品可能不够；扩第二字节区间或换方案 |
| 5 | 文字不是画在图片里 | 打开游戏看菜单/标题 | 是图片 → 这套方案完全无效，得改图 |

### 30 分钟试跑（换新游戏必做）

1. `krr.py analyze` 确认 XP3 明文可解析、`.ks` 条目正常。
2. `krr.py unpack`，随手挑一个脚本，把其中一句日文换成两三个中文汉字（手动改，不用走全流程）。
3. 用 `krr.py` 的编码逻辑打包，或者干脆手工按隧道规则替换，塞回 `data.xp3`（先备份！）。
4. 放上 `d3d9.dll` + `sjis_ext.bin`，启动游戏，看到那句对白。
5. 按「失败症状速查表」判读结果：

| 看到什么 | 说明 | 下一步 |
|---|---|---|
| 正常中文 | 全链路通了 | 可以跑全量 |
| 满屏奇怪日文/符号 | 隧道生效，但代理没 hook 到 | 换 `winmm.dll` / `version.dll` / `ddraw.dll` 逐个试；确认 DLL 位数与 exe 一致 |
| 豆腐块 □ | 代理通了，字体缺字 | 换字体或补字 |
| 直接崩溃/报错 | 引擎不容忍这些字节 | 这条路堵死，考虑改 exe 的 codepage 调用 |
| 显示成正常日文里的生僻字 | 隧道没生效，字节被当合法 CP932 解了 | 检查首/末字节规则，或换一段不冲突的码位 |

只有第 1 行才值得继续。

---

## 🚀 使用方式

**方式 A：把本文件整份丢给 AI**，说：

> "按照这个 skill 帮我汉化这个 KiriKiri 游戏，游戏目录在 `<游戏目录>`，翻译好的文本在 `<游戏目录>\gt_output`。"

**方式 B：自己跑脚本**（`scripts/`，纯标准库，Python 3）：

```powershell
python scripts/krr.py analyze --game "D:\Game"                 # 看索引和条目
python scripts/krr.py unpack  --game "D:\Game"                 # 解出 *.ks
python scripts/extract.py     --game "D:\Game" --dry-run       # 看提取效果
python scripts/extract.py     --game "D:\Game"                 # 生成 gt_input
#   ……把 gt_input 交给 GalTransl（或手工翻译），产出 gt_output……
python scripts/krr.py all     --game "D:\Game" --skip mcr_add  # 回写+打包+校验
python scripts/krr.py deploy  --game "D:\Game" --proxy-dir "D:\VNTextProxy"
```

`--work` 默认 `<游戏目录>\_work`，所有中间产物都在里面；`deploy` 之前不会动游戏目录。

---

## 🔧 环境准备

| 工具 | 用途 | 下载链接 |
|---|---|---|
| **VNTextProxy**（VNTranslationTools） | 代理 DLL，把隧道字节还原成中文 | https://github.com/arcusmaximus/VNTranslationTools/releases |
| **Python 3** | 跑脚本（仅标准库，无需装包） | https://www.python.org/downloads/ |
| **GalTransl** | 日文剧本批量翻译（也可手工翻） | https://github.com/HIllya51/GalTransl |

**代理 DLL 部署要点**：把 `d3d9.dll`、`winmm.dll`、`version.dll` 复制到游戏目录，`sjis_ext.bin` 必须和它们同级。
「放哪几个」取决于引擎从哪条路加载——**本作**实测必须放 `d3d9.dll`（详见第 6 步）。

---

## 适用场景

以下条件**同时**成立时最顺：

- 引擎：KiriKiri / KAG3，`data.xp3` 打包，索引是明文 zlib
- 引擎硬编码 CP932，无视 UTF-8/UTF-16 BOM
- 文字经 D3D9（或代理能拦到的 GDI 路径）渲染
- 补丁机制不可用（本作 `patch.xp3` 不加载、也不读散文件）
- 没有更便宜的入口（引擎不开源、不值得改 exe）

反过来，碰到下面这些**不要用本方案**：引擎原生 UTF-16/UTF-8、能打 `patch.xp3`、能读散文件、文字在图片里、商业引擎有一键汉化工具。

## 核心原理

1. **SJIS 隧道编码**：CP932 是双字节编码，首字节 `0x81–0x9F` / `0xE0–0xEF` 时引擎会再吃一个字节，当成**一个全角字符**。正常日文的第二字节只落在 `0x40–0x7E` / `0x80–0xFC`，所以 `0x01–0x3F` 这一段是"文本里永远不会出现"的空档。把中文放进这些空档，引擎照单全收，宽度按全角算，排版逻辑完全不用改。
2. **VNTextProxy 代理 DLL**：它在文字绘制出口截获字节对，查 `sjis_ext.bin` 换回真汉字，再交给真实绘制函数。因为游戏看到的是"合法双字节"，所以不报错、不崩溃。
3. **直接改 `data.xp3`**：不做 `patch.xp3`（本作 exe 写死只加载主包），只重打主包。

> ⚠️ 准确地说，隧道用的字节对**不是合法的 CP932 字符**，而是"CP932 解码器不会正常产出的组合"。引擎能不能容忍、会不会在解码阶段就把它们吞掉，**因引擎而异**——这就是为什么必须先做 30 分钟试跑。

**容量**：首字节 47 个（`0x81–0x9F` 31 个 + `0xE0–0xEF` 16 个），第二字节 58 个（`0x01–0x3F` 去掉 5 个控制符），合计 **2726** 个不同汉字。

---

## 完整流程

### 第 0 步：备份

```powershell
Copy-Item "<游戏目录>\data.xp3" "<游戏目录>\data.xp3.bak"
```

### 第 1 步：解包 data.xp3

XP3 结构（实测）：

- 偏移 `0x20`：uint64 LE，索引块偏移
- 索引块：`flag(1B, 通常0x01)` + `comp_size(8B LE)` + `uncomp_size(8B LE)` + zlib 数据
- 索引解压后是一串 `File` 条目：`'File'(4B) + data_size(8B LE) + data`
- 每个 File 含三个子块：
  - **info**：`flags(4B) + usz(8B) + csz(8B) + name_len(2B) + name(UTF-16LE)`
  - **segm**：`seg_count(4B) + 每段 offset(8B) + usz(8B) + csz(8B)`
  - **adlr**：`adler32(4B)`
- 注意：某些 ks 的 `flags=0`，数据其实仍是 zlib 压缩的（首字节 `0x78`）。**不要信 flags，看魔数**。

`krr.py analyze` / `unpack` 已经实现这些；加密索引不在覆盖范围内。

### 第 2 步：提取对白

对白结构（本作实测）：

- 名单独行：`[locklink]【佐渡教官】[r]`
- 对白行：`[PV file=..]「…」[/PV][unlocklink]` 或 `「…」[PG]`
- 外层标签不要，中间正文才是 message

`extract.py` 会剥掉所有 `[tag]`、把 `【名字】` 单独放进 `name` 字段，输出 GalTransl 的 `gt_input/*.json`。**这是启发式提取**：只认"可选名字行 + 一行正文"这种形状，多行拼接、选项分支、`[ruby]` 之类需要按游戏补规则。

两个必用的自检开关：

- `--dry-run`：只打印不落盘，先抽查前几条
- `--compare <已有 gt_input 目录>`：逐脚本对比条数，差得多的脚本说明提取规则不适配

> 本作实测：38 个剧情脚本**逐条数量全部一致**（2450 句），只有被跳过的 UI 宏脚本 `mcr_add` 多提取了 6 条——它本来就不参与回写。

### 第 3 步：容错正则回写（关键坑点）

**坑**：ks 原文里句子中间夹着 `[ruby text=とげ]`、`[r]` 之类的标签，而 GalTransl 提取时把它们剥掉了，导致"日文子串"在 ks 里对不上。

**做法**：字符之间允许夹任意标签或换行。

```python
def tolerant_sub(text, needle, repl):
    parts = [re.escape(ch) for ch in needle if ch not in '\r\n']
    pat = r'(?:\[[^\[\]]*\]|\r?\n)*'.join(parts)
    return re.subn(pat, lambda m: repl, text, count=1)
```

- needle 里的 `\n` 要去掉（容错组会吃掉换行）
- 名字前缀 `【名】\n` 用 `re.compile(r'^【[^】]*】\n')` 剥掉
- UI/宏脚本（如 `mcr_add.ks`，成就进度那种）跳过不译（`--skip mcr_add`）
- 注意：匹配到的整段（含内联标签）会被替换掉，被吃掉的 `[ruby]` 不会保留——对本作无影响，介意就逐句核

### 第 4 步：SJIS 隧道编码

```python
class SjisTunnel:
    def _get(self, ch):
        idx = len(self._mapping)
        hi, lo = idx // 0x3A, idx % 0x3A
        hb = 0x81 + hi if hi < 0x1F else 0xE0 + (hi - 0x1F)
        lb = 1 + lo
        for s in (0x09, 0x0A, 0x0D, 0x20, 0x2C):   # 跳过控制符/空白/逗号
            if lb >= s: lb += 1
        return chr((hb << 8) | lb)
```

- 只对 `cp932` 编不出来的字（含 `0xF0+` 用户定义区）走隧道
- 原样能编的字保持原样，避免体积膨胀
- **`sjis_ext.bin` 格式**：按隧道索引顺序排列的**原始汉字**，UTF-16LE，大小 = 汉字数 × 2
  （例：612 汉字 = 1224 字节）
- **不是**码位字节对。写成字节对会导致整体错位，症状是"字全错"，比如「脏」变「饭」
- 映射顺序必须和编码时一致：它是按**首次出现顺序**分配的，同一次翻译结果可复现

### 第 5 步：重打包（双重压缩坑点）

**最致命的坑**：第 4 步输出的 ks 已经是 `zlib.compress(隧道字节)`，第 5 步**绝对不能再压**。否则游戏解压一次拿到的还是 zlib 流，整篇乱码，而且症状像编码错误，会把人带偏。

正确做法：直接拿压缩字节当 segm 数据，`usz` 用解压后长度，`csz` 用压缩长度，`adler32` 算在**压缩数据**上。

```python
comp = open(new_ks_path, 'rb').read()
raw  = zlib.decompress(comp)          # 只为取长度
info_usz, info_csz = len(raw), len(comp)
segm_offset, segm_usz, segm_csz = cur, len(raw), len(comp)
adler = zlib.adler32(comp) & 0xFFFFFFFF
```

新文件布局：

1. 原样拷贝原 xp3 的 `[0, index_offset)` 段（旧 ks 变死数据，浪费空间但无害）
2. 追加所有新 ks 的压缩数据
3. 写新索引块：`0x01` + `comp_size` + `uncomp_size` + `zlib.compress(索引)`
4. 回到 `0x20` 回填新索引偏移

> 多段文件（`seg_count > 1`）我的实现只重写第 0 段，`analyze` 会告警。真遇到要先扩展。

### 第 6 步：部署代理 DLL

**最大的坑（本作专属，但教训通用）**：不要只按 exe 的静态导入表选 DLL。KiriKiri 的文字渲染走 D3D9，而 `d3d9.dll` 往往是**运行时 `LoadLibrary`** 加载的，导入表里看不到。只放 `ddraw.dll` + `winmm.dll` 的结果是 hook 完全没生效、满屏乱码。

本作实测有效的最小集合：

```powershell
Copy-Item "<代理目录>\d3d9.dll"    "<游戏目录>\"   # 关键
Copy-Item "<代理目录>\winmm.dll"   "<游戏目录>\"   # 备用入口
Copy-Item "<代理目录>\version.dll" "<游戏目录>\"   # 备用入口
Copy-Item "<代理目录>\ddraw.dll"   "<游戏目录>\"   # 如有导入
Copy-Item "_work\sjis_ext.bin"     "<游戏目录>\"   # 隧道映射表
```

- `d3d9.dll` 是文字 hook 的核心，**不要因为导入表里没有就不放**
- `sjis_ext.bin` 必须与 DLL 同目录
- DLL 位数必须和 exe 一致（32 位游戏配 32 位 DLL）

### 第 7 步：运行验证

- 窗口/全屏都应正常，不需要 Locale Emulator
- 标题菜单仍是日文（没翻译的脚本/图片），进入对话后对白应为中文
- 异常判读见前面「失败症状速查表」

---

## 死路（不要重复试）

| 方案 | 结果 | 适用范围 |
|---|---|---|
| UTF-8 BOM / UTF-16LE BOM | 引擎无视 BOM，乱码 | 通用（CP932 硬编码的引擎） |
| GBK 全量转换 | 引擎强制 CP932，乱码 | 通用 |
| 换字体补字 | 只解决"豆腐块"，不解决编码 | 通用 |
| UIF winmm + TextOutA/W | D3D9 绕过 GDI，拦不到 | 通用 |
| UIF + ExtTextOutW / GetGlyphOutlineW | EAccessViolation 崩溃 | 本作实测 |
| UIF tunnel_decoder hook MultiByteToWideChar | EAccessViolation 崩溃 | 本作实测 |
| `patch.xp3` 补丁包 | 本作 exe 写死只加载 `data.xp3` | **本作专属**（多数游戏反而优先用它） |
| `scenario/` 散文件 | 本作不读散文件 | **本作专属** |
| 只按静态导入表放 DLL | `d3d9.dll` 动态加载，hook 失效 | 通用教训（凡动态加载的引擎） |
| repack 时对已压缩 ks 再 `zlib.compress` | 双层压缩，全乱码 | 通用 |

---

## 本方案治不了什么

| 范围 | 说明 |
|---|---|
| 图片文字 | 标题、按钮、CG 里的字是像素，只能改图 |
| 未覆盖的脚本 | 只替换 `gt_output` 里有译文的脚本；菜单/UI 脚本（`pge_*.ks`、`lay_conf.ks`、`first.ks`…）要单独提取翻译 |
| 引擎层文字（`tjs` 里写死的） | 不在 `.ks` 里，本流程不处理 |
| 字体级排版 | 个别字在三字节/全角宽度假设下可能错位，极少见 |

---

## 验证清单

- [ ] `data.xp3.bak` 已备份
- [ ] `analyze` 无 "multi-segment" 告警
- [ ] 回写报告：未找到条目 = 0
- [ ] `new_ks` 解压后明文长度 == 索引 `info.usz`
- [ ] `sjis_ext.bin` 大小 == 汉字数 × 2，UTF-16LE，顺序与编码一致
- [ ] `verify` 报告：长度/压缩不一致 = 0，残留假名行 = 0
- [ ] `d3d9.dll` 已放入游戏目录（不要管静态导入表）
- [ ] 实机跑过：对白中文正常（窗口/全屏都试）

---

## 环境记录

- 验证环境：Windows x64，Python 3（仅标准库），VNTextProxy 的 `d3d9/winmm/version/ddraw`（版本未记录，2023-02 构建）
- 案例：`data.xp3` 490 MB / 911 条目 / 59 个 `.ks` / 38 组译文 / 2450 句 / 612 个隧道汉字
- 复现结果：同一份译文两次生成的 `sjis_ext.bin` 哈希一致（`52D1DE44…`），可复现
