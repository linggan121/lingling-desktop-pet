# 灵灵 · 桌面桌宠

> 一只住在 Windows 桌面右下角的小桌宠：会换装、会看屏幕、能接大模型聊天。
> 纯 Python + tkinter 实现，**不填 Key 也能离线运行**。

<p align="center">
  <img src="docs/screenshots/icon.png" width="120" alt="灵灵">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-7c3ddb" alt="License">
  <img src="https://img.shields.io/badge/python-3.9%2B-7c3ddb" alt="Python">
  <img src="https://img.shields.io/badge/platform-Windows-7c3ddb" alt="Platform">
</p>

<p align="center">
  <img src="docs/screenshots/pet.png" width="260" alt="桌宠">
  <img src="docs/screenshots/chat.png" width="260" alt="聊天">
</p>

---

## 特性

- **真·桌面住客**：无边框、不占任务栏、置顶、可拖动、位置记忆，拖到屏幕外能一键叫回
- **会动**：9 组动作 / 57 帧，摸头会压扁弹回 + 冒心心，靠近屏幕边缘会吸附
- **会换装**：6 套配色（原色 / 酒红 / 藏蓝 / 墨绿 / 奶油 / 雾紫），**按时段和季节自动换**（夜里雾紫、冬天藏蓝、夏天奶油…），手动换的衣服 2 小时内不会被覆盖
- **会聊天**：接任意 OpenAI 兼容服务（DeepSeek / 豆包 / 硅基流动 / Kimi / 智谱 / 通义 / OpenRouter / 本地 Ollama），流式逐字回复；没 Key 时只说自己内置的台词
- **记得你**：每聊 8 轮提炼一次「关于你的事」，存成本地事实卡，下次聊天会想起来
- **看屏幕**：右键「看看我在干什么」，截一张屏让视觉模型随口点评一句；**窗口标题命中密码 / 银行 / 支付 / 验证码等词时连截图都不截**
- **情绪驱动**：回复里带 `<mood:开心>` 这类标记，会自动切到对应动作，标记本身不显示
- **省心**：单实例（重复双击不会开第二只）、设置原子写、断网自动退回离线台词

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

<p align="center">
  <img src="docs/screenshots/settings.png" width="420" alt="设置">
</p>

---

## 怎么玩

| 操作 | 反应 |
|---|---|
| 单击 | 摸头：压扁弹回 + 冒心心 + 说一句话 |
| 双击 | 打开聊天窗口（贴在灵灵左侧，拖动她时会一起走） |
| 拖动 | 跟着鼠标跑，松手记住位置、靠近边缘吸附 |
| 右键 | 聊天 / 看屏幕 / 逗一下 / 心情 / 投喂 / 换动作 / 换装 / 窗口搬回来 / 设置 / 回到右下角 / 退出 |
| 托盘 | 显示隐藏、设置、叫回屏幕、退出 |

换装效果（6 套配色）：

<p align="center">
  <img src="docs/screenshots/outfits.png" width="560" alt="换装">
</p>

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
│   ├── outfits.py        换装配色与素材包识别
│   ├── wardrobe.py       按时段/季节挑衣服
│   ├── behavior.py       漫游与睡觉决策（纯逻辑）
│   ├── persona.py        人设 + 时间上下文 + 系统提示
│   ├── memory.py         事实卡与关键词检索
│   ├── llm.py            OpenAI 兼容 / Ollama / 多模态
│   ├── vision.py         看屏幕：截屏、隐私过滤
│   ├── config.py         设置读写
│   ├── settings_ui.py    设置窗口
│   ├── tray.py           托盘图标
│   └── pet.py            窗口、交互、聊天、换装接线
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

## 自己加素材

**换一套配色**：改 `ling/outfits.py` 里的 `OUTFITS`（色相 / 饱和度 / 明度增益）。

**加真·新衣服**（需要新立绘）：

```
assets/outfits/<名字>/frames.json + spritesheet.webp
```

放进去后代码会自动优先用这套素材（不再上色），右键「换装」菜单里会多一项。

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
- 语音合成 / 语音识别还没做
- 只在 Windows 上测过

---

## 致谢

- 情绪解析的思路来自 [luna-desktop-pet](https://github.com/Elysia20230/luna-desktop-pet)（MIT）
- 漫游节奏与插件化设计参考了 [jarvis](https://github.com/ynnyh/jarvis)（MIT）

## License

[MIT](LICENSE)
