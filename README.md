# 灵灵 · 桌面 AI 助理桌宠

> 一只住在桌面角落的小宠物，也是一个能帮你干活的助理。
> 现在她会聊天、会看你在忙什么；接下来的方向是**办公技能**：找文件、整理文件、转格式、读文档、看代码——把文件拖到她身上就能开工。

<p align="center">
  <img src="docs/screenshots/icon.png" width="120" alt="灵灵">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-7c3ddb" alt="License">
  <img src="https://img.shields.io/badge/python-3.9%2B-7c3ddb" alt="Python">
  <img src="https://img.shields.io/badge/platform-Windows-7c3ddb" alt="Platform">
  <img src="https://img.shields.io/badge/status-WIP-orange" alt="Status">
</p>

<p align="center">
  <img src="docs/screenshots/pet.png" width="260" alt="桌宠">
  <img src="docs/screenshots/chat.png" width="260" alt="聊天">
</p>

---

## 现在能做什么

- **桌面住客**：无边框、不占任务栏、置顶、可拖动、位置记忆，拖到屏幕外能一键叫回；单实例，不会开出第二只
- **会聊天**：接任意 OpenAI 兼容服务（DeepSeek / 豆包 / 硅基流动 / Kimi / 智谱 / 通义 / OpenRouter / 本地 Ollama），流式逐字回复；没配 Key 时只说自己内置的台词
- **记得你**：每聊 8 轮提炼一次「关于你的事」，存成本地事实卡，下次聊天会想起来
- **看屏幕**：右键「看看我在干什么」，截一张屏让视觉模型随口点评一句；**窗口标题命中密码 / 银行 / 支付 / 验证码等词时连截图都不截**
- **有脾气**：回复里带 `<mood:开心>` 这类情绪标记，会自动切到对应动作，标记本身不显示
- **省心**：设置原子写、程序异常有日志、断网自动退回离线台词

<p align="center">
  <img src="docs/screenshots/settings.png" width="420" alt="设置">
</p>

---

## 正在做：从「宠物」变成「办公助理」

路线见 [ROADMAP.md](ROADMAP.md)。核心是三件事：**技能框架**、**文件入口**、**安全边界**。

| 能力 | 设想 | 状态 |
|---|---|---|
| 技能框架 | 每个技能一份 `skill.json`（触发方式、参数、权限）+ 一个处理函数，菜单/拖拽/对话都能调起 | 规划中 |
| 拖文件到她身上 | 从资源管理器把文件/文件夹拖到桌宠，弹出可用技能列表（比如「总结这份文档」「转成 PDF」） | 规划中 |
| 本地文件搜索 / 整理 | 按名字、类型、时间、内容找文件；批量重命名、归档、去重 | 规划中 |
| 文件格式转换 | 文档、表格、图片、PDF 之间互转（走本地 LibreOffice / Pillow） | 规划中 |
| 文档分析 | 长文档摘要、要点提取、针对内容提问、跨文档对比 | 规划中 |
| 代码分析 | 目录结构梳理、依赖检查、单个文件的解释与风险提示 | 规划中 |
| 安全边界 | 只读优先、写操作二次确认、可配置授权目录、全程本地日志 | 规划中 |

> 这些是**规划**，仓库里还没有实现。已实现的能力只在上面的「现在能做什么」里，不做夸大。

---

## 快速开始

### 方式一：直接用 exe（推荐给不想装 Python 的人）

到 Releases 下载 `灵灵.exe`，双击即可。首次启动会解压运行时并切帧，约 3–5 秒。

运行数据在：

```
%LOCALAPPDATA%\灵灵\
├── lines.json     台词库（可改）
├── persona.json   人设（可改）
├── settings.json  位置、模型配置
├── memory.json    记忆
└── _frames.pkl    切帧缓存（可删）
```

想变成绿色便携版：在 exe 同目录建一个 `data` 文件夹，程序会优先用它。

### 方式二：源码运行

```bash
pip install -r requirements.txt
pythonw 灵灵.pyw              # 启动
python  灵灵.pyw --selftest   # 自检：打印帧数后退出
python  灵灵.pyw --settings   # 启动并直接打开设置窗口
```

需要 Python 3.9+（tkinter 是标准库自带的）。

---

## 接大模型

右键灵灵 →「设置…」，选服务商 → 填 Key →「测试连接」→ 成功会自动保存。

| 服务商 | 接口地址 | 备注 |
|---|---|---|
| DeepSeek | `https://api.deepseek.com` | Key 是 `sk-` 开头、35 位左右 |
| 豆包（火山方舟） | `https://ark.cn-beijing.volces.com/api/v3` | 模型填 **Model ID**（如 `doubao-seed-2-1-turbo-260628`） |
| 硅基流动 / Kimi / 智谱 / 通义 / OpenAI / OpenRouter | 内置预设 | 选好自动填地址和模型 |
| 本地 Ollama | `http://127.0.0.1:11434/v1` | 不用 Key、不出网，先 `ollama pull qwen2.5:7b` |

- **不知道 Key 是哪家的**：粘进去点「自动匹配服务商」，会并行试常见服务商，认出来就自动填好地址和模型并保存
- **视觉模型**（看屏幕用）单独一栏，留空就用对话模型（需支持图片）
- 豆包默认关掉了「深度思考」（开着首字要 20 秒），想开就在 `settings.json` 的 `llm` 里加 `"thinking": "enabled"`

---

## 怎么玩

| 操作 | 反应 |
|---|---|
| 单击 | 摸头：压扁弹回 + 冒心心 + 说一句话 |
| 双击 | 打开聊天窗口（贴在灵灵左侧，拖动她时会一起走） |
| 拖动 | 跟着鼠标跑，松手记住位置、靠近边缘吸附 |
| 右键 | 聊天 / 看屏幕 / 逗一下 / 心情 / 投喂 / 换动作 / 窗口搬回来 / 设置 / 回到右下角 / 退出 |
| 托盘 | 显示隐藏、设置、叫回屏幕、退出 |

---

## 项目结构

```
.
├── 灵灵.pyw              入口（很薄，只负责开窗口）
├── ling/                 本体
│   ├── paths.py          路径 + 原子写
│   ├── frames.py         切帧 + 磁盘缓存
│   ├── anim.py           帧动画 / 摸头压扁
│   ├── bubble.py         气泡（文字永远在框里）
│   ├── mood.py           情绪标记解析
│   ├── behavior.py       行为决策（纯逻辑）
│   ├── persona.py        人设 + 时间上下文 + 系统提示
│   ├── memory.py         事实卡与关键词检索
│   ├── llm.py            OpenAI 兼容 / Ollama / 多模态
│   ├── vision.py         看屏幕：截屏、隐私过滤
│   ├── config.py         设置读写
│   ├── settings_ui.py    设置窗口
│   ├── tray.py           托盘图标
│   └── pet.py            窗口、交互、聊天接线
├── tests/test_ling.py    39 个单元测试（不弹窗、不联网）
├── assets/               精灵图、帧配置、图标
├── data/                 默认台词与人设
└── docs/screenshots/     截图
```

跑测试：

```bash
python -m unittest discover -s tests -v
```

---

## 打包成 exe

```bash
pyinstaller --onefile --windowed --name 灵灵 --icon assets/app.ico ^
  --add-data "assets;assets" ^
  --add-data "data/lines.json;data" ^
  --add-data "data/persona.json;data" ^
  灵灵.pyw
```

---

## 隐私

- 不联网也能完整使用；只有你填了 Key 并发消息 / 点「看屏幕」时才会请求你配置的那个接口
- Key 只存在本机 `settings.json`，没有遥测、没有默认上传
- 看屏幕前会检查前台窗口标题，命中隐私词直接放弃，截图不落盘
- 聊天记录和记忆都在本地，可以随时删除

---

## 已知限制

- 素材一帧只有约 112×198 像素，放大后会偏软；边缘有轻微锯齿，因为 tkinter 的透明是「色键」方案（每个像素只能全透明或全不透明），做不出半透明过渡
- 办公技能还没实现，见 [ROADMAP.md](ROADMAP.md)
- 语音合成 / 语音识别还没做
- 只在 Windows 上测过

---

## 致谢

- 情绪解析的思路来自 [luna-desktop-pet](https://github.com/Elysia20230/luna-desktop-pet)（MIT）
- 漫游节奏与插件化设计参考了 [jarvis](https://github.com/ynnyh/jarvis)（MIT）

## 素材版权

- **代码**（`ling/`、`灵灵.pyw`、`tests/`）采用 [MIT](LICENSE)，可自由使用、修改、商用
- **角色立绘与图标**（`assets/spritesheet.webp`、`assets/app*.ico/png`）**不是本项目原创**，
  来自 [Petdex](https://petdex.dev/zh) 的用户投稿宠物包，**不在 MIT 授权范围内**

> Petdex 官方 FAQ：*Pets are user-submitted fan art. Petdex does not claim rights to any underlying IP.*
> *Every pet on Petdex is free to install and use. Pets keep credit to their original authors.*

所以：素材是**同人二创**，平台免费给"安装/使用"，但不等同于可以再打包分发或商用。
本项目仅把它用于功能演示，作者署名与完整说明见 [assets/NOTICE.md](assets/NOTICE.md)；
原作者要求下架会立即移除。

**要拿这个项目做正式产品或商用**，请先把立绘换成自己有权利的素材
—— 只要替换 `assets/spritesheet.webp` + `frames.json`，代码一行都不用改。

## License

代码：[MIT](LICENSE)（素材除外，见上）
