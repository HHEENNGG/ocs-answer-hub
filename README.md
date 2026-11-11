# OCS 智题库 · AnswerHub

> 一个端口，同时喂饱三种 OCS 答题插件；本地题库优先命中，AI 兜底，图片题也能认。

把「AutoCourse-DB 的本地题库」「ocs-ai-answerer 的 AI 识别」「ocsjs 服务的即插即用」三件事合成一个程序：
**双击 `一键启动.bat` 就能用，不需要 Node、不需要编译；自带示例题库，填入自己的题库或模型 Key 即可正式使用。**

---

## ✨ 它能做什么

| 能力 | 说明 |
|---|---|
| 🗃️ **本地题库秒答** | SQLite 存题，题干 + 选项归一化后精确匹配，**选项顺序打乱也能命中**（乱序全量回归） |
| 🔌 **四种协议同时兼容** | 一个端口上同时挂 `/search`、`/api/search`、`/api/answer`、`/api/v1/ask`，插件用哪种都行 |
| 🤖 **AI 兜底** | 本地没命中才调 AI；支持 DeepSeek / 豆包 / 任意 OpenAI 兼容接口，多模型顺序故障转移 |
| 🖼️ **图片题识别** | 题干或选项是图片时自动下载并转多模态输入（需要配置视觉模型） |
| 🧠 **思考模式** | 按题型单独开关，兼容 `reasoning_effort` / `thinking` 等参数名 |
| 💾 **自动积累题库** | AI 答对的题自动入库（可设「待验证」），越用越准；可导出为 AutoCourse-DB 格式 |
| 📊 **可视化后台** | 8 个页面：概览、题库、模型、参数、答题测试、日志、接入方式、关于 |
| 🔍 **全链路可追溯** | 每次请求都记日志：命中来源、相似度、模型、Token、费用、耗时 |

---

## 🚀 快速开始

### 方式一：双击运行（推荐）

1. 双击 **`一键启动.bat`**
2. 首次运行会自动准备环境（几秒到几十秒），然后浏览器自动打开 `http://127.0.0.1:8000/`
3. 想停止：关闭那个黑窗口，或按 `Ctrl+C`

> 前提：电脑上装了 **Python 3.9+**（[下载地址](https://www.python.org/downloads/)，安装时勾选 *Add python.exe to PATH*）。
> 脚本会自动找 `py`/`python`、复用已有依赖，缺依赖才联网装（失败会走清华镜像）。

### 方式一 · 免 Python 版：单文件 EXE

不想装 Python 也行——项目里带了打包脚本：

1. 双击 **`打包EXE.bat`**（首次会自动装 PyInstaller，约 1~3 分钟）
2. 完成后得到 `dist\OCS-AnswerHub.exe`（约 16 MB，内含前端与两个示例题库）
3. 把这个 exe 复制到任意位置，双击即可使用 —— 浏览器会自动打开

> `data\` 目录会创建在 **exe 旁边**（题库、配置、日志都在里面），所以换电脑时把整个文件夹一起带走即可。
> 也可以用 `set OCS_HUB_DATA_DIR=D:\my-data` 把数据放到指定目录。

### 方式二：命令行

```bat
python -m pip install -r requirements.txt
python -m app.main
```

可选参数：

```bat
python -m app.main --port 8000        :: 指定端口（被占用会自动顺延）
python -m app.main --host 0.0.0.0     :: 允许局域网访问（管理接口默认仍只对本机开放）
python -m app.main --no-browser       :: 不自动打开浏览器
```

---

## 🔌 接入 OCS 答题插件

打开后台首页「接入方式」页，四种协议都给了可复制的代码和自检按钮。

### 协议① `/search`（AutoCourse-DB 风格，返回选项字母）

把下面整段粘进 OCS 的「题库配置」，**最外层的 `[ ]` 不能省**（只粘 `{...}` 会报
`Spread syntax requires ...iterable[Symbol.iterator] to be a function`）：

```json
[
  {
    "name": "OCS AnswerHub",
    "homepage": "http://127.0.0.1:8000/",
    "url": "http://127.0.0.1:8000/search",
    "method": "post",
    "type": "fetch",
    "contentType": "json",
    "headers": { "Content-Type": "application/json" },
    "data": {
      "title": { "handler": "return (env) => env.suggestion_title || env.title" },
      "type": "${type}",
      "options": { "handler": "return (env) => env.suggestion_options || env.options" },
      "images": { "handler": "return (env) => env.images || []" }
    },
    "handler": "return (res) => res && res.code === 1 ? [undefined, res.answer] : undefined"
  }
]
```

四个要点：

- `title` / `options` 必须写成**字段解析器**（`{ "handler": ... }`）并带 `|| env.title` / `|| env.options` 回退。
  `env.suggestion_title` / `env.suggestion_options` **只在开启「图片题优化」且这道题真的带图时才有值**，
  否则是 `undefined`——直接写 `"${suggestion_title}"` 会被替换成字面量字符串 `undefined`，
  题干和选项全变成 `undefined`，题库必然查不到、OCS 就会弹「给出的答案和选项不匹配」。
- `"images"` 同理必须是解析器。`env.images` 是 base64 PNG 的 data URL **数组**，
  用 `"${images}"` 占位符会被字符串拼接成一整串。
- `suggestion_title` 里的图片 URL 已被换成 ` [图片1] ` 占位符，编号与 `images` 顺序严格对应，
  我们的服务按编号把图片内联到原位置。
- `method` 必须是 `post`（GET 传不了 base64）。`data` 里含 `images` 字段，OCS 5.0 的
  「图片题优化」检测才会判定为支持，不再弹「当前题库配置暂不支持图片、公式等题目处理」。

若 fetch 被跨域拦截，把 `"type": "fetch"` 换成 `"type": "GM_xmlhttpRequest"`，
并在油猴脚本头加 `// @connect 127.0.0.1`。

### 协议② `/api/search`（ocsjs-ai-answer-service 风格）

返回 `{"code": 1, "question": "...", "answer": "..."}`，`answer` 是选项**内容**（多选用 `#` 连接）。

### 协议③ `/api/answer`（ocs-ai-answerer 风格）

返回 `{"ocs_format": [题目, 答案, {ai, tags, model, reasoning_used, source, elapsed_ms, cost_cny}], ...}`。

### 协议④ `/api/v1/ask`（原生接口，信息最全）

```json
POST /api/v1/ask
{ "title": "题干", "type": "single", "options": ["A. 选项一"], "course_id": 1 }
```

返回完整结构：命中的题目、命中来源（`bank` / `fuzzy` / `ai` / `cache`）、相似度、字母答案、内容答案、AI 明细、耗时。

**题型取值**：`0/1/3/4`、`single/multiple/judgement/completion`、`单选/多选/判断/填空` 都能识别。

---

## 🖥️ 界面导览

| 页面 | 用途 |
|---|---|
| **概览** | 今日调用量、AI 占比、命中率、费用、近 7 天趋势、题型与来源分布 |
| **题库** | 按课程/题型/验证状态筛选，增删改查、批量导入（粘贴或选文件）、导出、去重 |
| **模型** | 增删模型、测连通、**按题型分配模型**（图片题只允许多模态）、配置回退顺序 |
| **参数** | 答题策略、AI 参数、缓存、安全、服务端设置，改完立即生效 |
| **答题测试** | 左边出题右边看结果，可切「完整流水线」或「强制 AI」，看原始输出与思考过程 |
| **日志** | 每次请求的完整记录，可筛选、看详情、导出 CSV |
| **接入方式** | 四种协议的配置片段 + 一键自检 |
| **关于** | 版本、运行环境、数据目录 |

---

## ⚙️ 配置

配置只有一个文件：`data/config.json`（后台「参数」页改的就是它，也可以手工编辑，改完重启生效或后台保存即热更新）。

```jsonc
{
  "server":  { "host": "127.0.0.1", "port": 8000, "open_browser": true },
  "answer":  {
    "prefer_bank": true,          // 题库优先
    "cross_course": true,         // 跨课程检索（同一个题库给所有课程用）
    "auto_save": true,            // AI 答对自动入库
    "auto_save_verified": false,  // 自动入库的题标为「待验证」
    "similarity_threshold": 0.92, // 模糊匹配阈值
    "answer_format": "auto"       // auto = 单选题回字母、判断题回「对/错」
  },
  "ai": {
    "enabled": true,
    "request_timeout": 180,
    "max_images": 8,
    "image_timeout": 15,
    "image_max_mb": 5
  },
  "cache": { "enabled": true, "ttl": 3600, "size": 512 },
  "security": { "allow_lan_admin": false, "access_token": "" }
}
```

模型同理放在 `models` 里，`api_key` 在界面上永远是脱敏的。

> ⚠️ 管理接口默认只允许本机访问（`REMOTE_ADDR` 非回环 → 403）。要远程管理：配置 `security.access_token` 并请求头带 `X-Token`，或把 `security.allow_lan_admin` 设为 `true`（不建议）。

---

## 📚 题库

- 自带 `libraries/示例题库.json`（十几道演示题），首次启动自动导入，用来验证流程能跑通
- 格式与 AutoCourse-DB 完全一致：`{"[single] 题干 | 选项1 | 选项2": "答案内容"}`，详见 [`libraries/README.md`](libraries/README.md)
- **导入**：后台「题库 → 导入」，粘贴 JSON 或选文件，策略可选 跳过重复 / 覆盖已有 / 只覆盖未验证
- **导出**：`GET /api/admin/export?course_id=1&download=1`，导出即为 AutoCourse-DB 可直接用的格式
- 想加题库：把 JSON 丢进 `libraries/` 目录，首次启动会自动导入（已导入过的课程不会重复）
- ⚠️ 本项目**不附带任何真实课程题库**——课程内容请自行准备，并确认你有权使用

---

## 🔐 数据与隐私

- 题库、配置（含 API Key）、日志、图片缓存全部存在程序目录下的 `data/`，**不会上传到任何地方**。
- 只有在你配置了 AI 模型并启用后，题目文本（及图片）才会发送给你自己填写的那个模型接口。
- CLI 后台的管理接口默认只允许本机访问；`data/` 已被 `.gitignore` 排除，不会误提交。
- 分享/开源前建议检查 `data/config.json` 与 `data/bank.db`，不要把 Key 和题库一起发出去。

---

## 🗂️ 目录结构

```
ocs-answer-hub/
├─ 一键启动.bat          # 双击即用（需要 Python）
├─ 打包EXE.bat           # 双击打出免 Python 的单文件 exe
├─ build_exe.py          # PyInstaller 打包脚本
├─ run_exe.py            # exe 入口
├─ requirements.txt
├─ app/                  # 后端
│  ├─ main.py            # 启动、端口、自动开浏览器、题库引导
│  ├─ api.py             # 全部路由（4 种协议 + 管理接口）
│  ├─ pipeline.py        # 五级流水线：缓存→精确→旧键→模糊→AI
│  ├─ bank.py            # 题库读写、导入导出、去重
│  ├─ normalize.py       # 题干/选项归一化与 canonical_key
│  ├─ match.py           # 模糊匹配打分
│  ├─ answer.py          # 模型输出 → 字母/内容
│  ├─ prompt.py          # 五类题型提示词
│  ├─ ai.py              # OpenAI 兼容调用、重试、计费
│  ├─ images.py          # 图片下载、磁盘缓存、多模态拼装
│  ├─ models.py          # 模型与题型映射
│  ├─ settings.py        # 配置读写（含脱敏、打包后路径处理）
│  ├─ db.py              # SQLite 连接与建表
│  ├─ cache.py           # 内存 TTL/LRU 缓存
│  └─ logging_store.py   # 异步日志落库
├─ web/                  # 前端（原生 HTML/CSS/JS，零 CDN、零构建）
├─ libraries/            # 题库目录（自带示例题库）
├─ data/                 # 运行时生成：bank.db、config.json、cache、logs
├─ docs/01-项目设计.md    # 完整设计文档
├─ LICENSE
└─ tests/                # 37 个单元/协议/AI 测试
```

---

## 🧪 测试

```bat
python -m unittest discover -s tests
```

37 个用例，覆盖：选项解析与归一化、canonical_key 稳定性、题型识别、答案处理、导入导出往返、upsert 幂等，
**把题库里的题逐条打乱选项后打 `/search`，断言返回的字母与打乱后的正确选项一致**（另有 150 道合成题的无题库回归，克隆下来即可跑），
以及用本地 mock 服务验证 AI 链路（单选/多选/判断解析、思考模式透传、报错降级、无 Key 跳过、AI 答完自动入库）。

---

## ❓ 常见问题

**Q：双击后窗口一闪而过？**
A：多半是没装 Python 或没勾 PATH。手动用命令行跑 `python -m app.main` 看报错。

**Q：端口 8000 被占用？**
A：会自动顺延到 8001、8002…，注意看黑窗口里打印的实际地址。

**Q：AI 一直报「未填写 API Key」？**
A：进后台「模型」页给某个模型填 Key 并启用，再到「模型 → 题型映射」把它分配给对应题型。只用本地题库的话可以完全不管 AI。

**Q：中文在窗口里乱码？**
A：本程序输出是 UTF-8；若用旧版 conhost，可先执行 `chcp 65001` 再启动。

**Q：题库文件能删吗？**
A：能。`data/bank.db` 删掉重启会重新从 `libraries/` 导入（日志一并清空）。

---

## 📄 版权与致谢

本项目融合了三个开源项目的能力，代码为重新实现，设计上大量借鉴：

- **AutoCourse-DB**（MIT © 2026 JinHeng）— 本地题库的 `canonical_key` 思路、平面 JSON 题库格式与 `/search` 协议形态
- **ocs-ai-answerer**（MIT © 2025 Liu Keda）— 题型分类、提示词结构、图片题多模态处理与 `/api/answer` 返回格式
- **ocsjs-ai-answer-service**（上游未声明许可证）— 仅借鉴简易搜索接口形态与管理页分工，未复制其代码

仅供个人学习与效率工具使用，请遵守所在平台的使用条款。