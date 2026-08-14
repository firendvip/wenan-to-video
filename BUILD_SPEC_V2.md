# v2 改造规格：横屏 + 接入 guizang-ppt-skill 的 9 套风格

在现有 webapp 基础上改造。**保持已有架构与"锁定默认值/仅音色·语速·风格·输出可配置"不变**，只做下面两件大事。

## A. 视频整体改横屏 1920×1080
- 全链路尺寸从竖屏 1080×1920 改为**横屏 1920×1080 / 30fps / yuv420p / libx264 crf18**。
- 需改：`engine/config.py`(尺寸常量)、`engine/styles.py`/deck 生成(舞台 1920×1080)、`engine/render.py` 截图 viewport=1920×1080、`engine/assemble.py` build_silent 的 scale/pad=1920:1080、字幕 ASS 的 PlayResX/Y=1920/1080 与排版、finalize 不变(tpad+ass+loudnorm+立体声+faststart)。

## B. HTML 改用 `guizang-ppt-skill` 的风格（横屏），共 9 套可选
Skill 根目录：`/Users/Admin/.claude/skills/guizang-ppt-skill/`。**必须读它的文件拿确切颜色/字体/背景代码**：
- 风格 A(电子杂志)：模板 `assets/template.html`、主题 `references/themes.md`、布局 `references/layouts.md`。签名：**WebGL 流体背景**(`canvas.bg`，见 template.html 的 `/* WebGL 双背景 */` 段与其着色器 JS)、衬线标题(Playfair Display + Noto Serif SC)+ 无衬线正文 + IBM Plex Mono 元数据。
- 风格 B(瑞士国际主义)：模板 `assets/template-swiss.html`、主题 `references/themes-swiss.md`、布局 `references/layouts-swiss.md`。签名：**网格/点阵 WebGL 背景**、全程 Inter+Noto Sans SC、极致字号对比、单一强调色。

**9 套风格（style key → 名称，来源）**：
1. `ink`     🖋 墨水经典（A）  2. `indigo` 🌊 靛蓝瓷（A）  3. `forest` 🌿 森林墨（A）
4. `kraft`   🍂 牛皮纸（A）    5. `dune`   🌙 沙丘（A）
6. `ikb`     🔵 克莱因蓝 IKB（B） 7. `lemon` 🟡 柠檬黄（B） 8. `lemongreen` 🟢 柠檬绿（B） 9. `orange` 🟠 安全橙（B）
每套的确切 CSS 变量（`--ink/--paper/...` 或 `--accent/...`）**从 themes.md / themes-swiss.md 逐字取用**，不要自造颜色。

### 生成方式（自动化，无人工澄清）
Skill 本是人工逐页作 PPT；这里要**程序化生成**：`engine/styles.py` 针对任意文案的分章，产出一个**横屏 1920×1080 deck**，每章一屏"陈述式"版式（大标题 headline + 副文 sub + kicker/章节号/进度点），**采用所选风格的字体+主题色+签名背景**。为保真：
- **背景 WebGL 代码从对应 skill 模板里原样拷贝**（A 拷 template.html 的流体背景 canvas+着色器；B 拷 template-swiss.html 的网格/点阵背景），别自己重写。
- 字体沿用 skill 的 `<link>` Google Fonts（本机联网可加载）；截图前 `await document.fonts.ready` 再截。
- 版式尽量对齐 skill 的类型系统（kicker=mono 小字母距、标题超大、A 用衬线/B 用无衬线、B 可用强调色块/hairline）。不需要复刻 skill 的演讲者模式/翻页 UI/宫格等交互，只要**单屏静态视觉**达到 skill 质感。
- **底部约 15%(≈160px) 留白做字幕安全区**，画面内不写口播字幕。

### 逐屏截图契约（给 render 用）
deck 支持确定性出图：URL 参数 `deck.html?slide=C`（C=1..N）直接渲染第 C 屏**最终静止态**（背景已绘、字体已加载、入场动效已结束），并暴露 `window.showSlide(C)`。截图 viewport=1920×1080、deviceScaleFactor=1、clip 1920×1080。（可参考 skill 的 `__playSlide`，但这里做成静态一屏一截更简单。）

## C. 横屏字幕（`engine/subtitles.py`）
- PlayResX/Y=1920/1080；PingFang SC 加粗、白字+黑描边、**强制单行**、逐条无缝按语音时长比例（逻辑不变）。
- 横屏参数：字号约 **68px**、`MarginL/R≈160`、`MarginV≈90`、单行宽度预算按 (1920-320)/68 ≈ **23 全角单位**重算（横屏更宽，拆分更少）。Outline≈5、Shadow≈2。

## D. 前端
- 设置页风格从 6 改为 **9 张卡片**（上列 9 套，含中文名 + 缩略/说明；缩略可用各主题背景色+字体示意）。其余不变（音色上传、语速、视频生成路径）。
- 主页尺寸提示改"横屏 1920×1080"。

## E. 自测（必须）
- 用短文案跑完整流程，产出**横屏 1920×1080** h264+aac 视频、时长>0、字幕单行且在底部安全区。
- 对 **9 套风格各截一张 slide 图**（1920×1080），确认背景(WebGL 流体 / 网格点阵)、主题色、字体均正确加载、非空白、非模板脸。
- server `/`、`/settings`、`/api/settings`(含 9 styles) 200。
- 报告：改动文件、9 风格截图确认、冒烟视频的 ffprobe(尺寸/流/时长)、字幕单行确认、已知限制。不要贴代码/长日志/图。
