/* ==========================================================================
   页面:接入方式 / 关于
   ========================================================================== */
(function () {
  "use strict";

  function origin() {
    return window.location.origin && window.location.origin !== "null"
      ? window.location.origin
      : "http://127.0.0.1:8000";
  }

  function block(title, desc, code) {
    return (
      '<div class="card">' +
        '<div class="card-title">' + UI.escape(title) + "</div>" +
        '<div class="tip" style="margin-bottom:10px">' + desc + "</div>" +
        '<div class="code-wrap"><pre class="code">' + UI.escape(code) + "</pre>" +
          '<button class="btn tiny copy" data-copy-btn="1">复制</button></div>' +
      "</div>"
    );
  }

  window.Pages.integration = {
    title: "接入方式",
    sub: "三种现成客户端 + 一种原生协议，同一个端口全部兼容",
    actions: '<button class="btn primary" id="i-test"><span data-icon="play"></span>连接自检</button>',

    render(root) {
      const base = origin();
      const ocsJson =
        "[\n" +
        "  {\n" +
        '    "name": "OCS AnswerHub",\n' +
        '    "homepage": "' + base + '/",\n' +
        '    "url": "' + base + '/search",\n' +
        '    "method": "post",\n' +
        '    "type": "fetch",\n' +
        '    "contentType": "json",\n' +
        '    "headers": { "Content-Type": "application/json" },\n' +
        '    "data": {\n' +
        '      "title": { "handler": "return (env) => env.suggestion_title || env.title" },\n' +
        '      "type": "${type}",\n' +
        '      "options": { "handler": "return (env) => env.suggestion_options || env.options" },\n' +
        '      "images": { "handler": "return (env) => env.images || []" }\n' +
        "    },\n" +
        '    "handler": "return (res) => res && res.code === 1 ? [undefined, res.answer] : undefined"\n' +
        "  }\n" +
        "]";

      const ocsGmJson =
        "[\n" +
        "  {\n" +
        '    "name": "OCS AnswerHub (GM)",\n' +
        '    "homepage": "' + base + '/",\n' +
        '    "url": "' + base + '/search",\n' +
        '    "method": "post",\n' +
        '    "type": "GM_xmlhttpRequest",\n' +
        '    "contentType": "json",\n' +
        '    "headers": { "Content-Type": "application/json" },\n' +
        '    "data": {\n' +
        '      "title": { "handler": "return (env) => env.suggestion_title || env.title" },\n' +
        '      "type": "${type}",\n' +
        '      "options": { "handler": "return (env) => env.suggestion_options || env.options" },\n' +
        '      "images": { "handler": "return (env) => env.images || []" }\n' +
        "    },\n" +
        '    "handler": "return (res) => res && res.code === 1 ? [undefined, res.answer] : undefined"\n' +
        "  }\n" +
        "]";

      const answererJson =
        '{\n' +
        '  "url": "' + base + '/api/answer",\n' +
        '  "type": "fetch",\n' +
        '  "method": "POST",\n' +
        '  "headers": { "Content-Type": "application/json" },\n' +
        '  "data": {\n' +
        '    "title": "${title}",\n' +
        '    "type": "${type}",\n' +
        '    "options": "${options}"\n' +
        "  }\n" +
        "}";

      const curlSearch =
        'curl -X POST ' + base + '/search \\\n' +
        '  -H "Content-Type: application/json" \\\n' +
        '  -d \'{"title":"3 是偶数。","type":"judgement","options":["对","错"]}\'\n\n' +
        '# → {"answer": "错", "code": 1, "source": "bank"}';

      const curlAnswer =
        'curl -X POST ' + base + '/api/answer \\\n' +
        '  -H "Content-Type: application/json" \\\n' +
        '  -d \'{"title":"下列哪些是 HTTP 请求方法？","type":"multiple","options":["A. GET","B. POST","C. PUT","D. FETCH"]}\'\n\n' +
        '# → {"code":1,"ocs_format":["题干","A#B#C",{"ai":false,"model":"","source":"bank"}]}';

      const curlNative =
        'curl -X POST ' + base + '/api/v1/ask \\\n' +
        '  -H "Content-Type: application/json" \\\n' +
        '  -d \'{"title":"题干","type":"single","options":["甲","乙","丙","丁"]}\'\n\n' +
        "# → {\"ok\":true,\"data\":{\"letters\":\"C\",\"answer\":\"C\",\"hit_source\":\"bank\",\n" +
        '#        "confidence":0.98,"contents":["丙"],"elapsed_ms":3,...}}';

      root.innerHTML =
        '<div class="stack">' +
          '<div class="alert info"><span>本机地址 <code class="mono">' + UI.escape(base) +
            '</code> 同时提供 4 个入口：<code class="mono">/search</code>（AutoCourse-DB 题库脚本）、' +
            '<code class="mono">/api/answer</code>（AI 解题器）、<code class="mono">/api/search</code>（极简版）、' +
            '<code class="mono">/api/v1/ask</code>（原生完整结构）。</span></div>' +

          '<div class="tabs" id="i-tabs">' +
            '<button class="tab on" data-tab="0">OCS 题库脚本</button>' +
            '<button class="tab" data-tab="1">AI 解题器</button>' +
            '<button class="tab" data-tab="2">极简接口</button>' +
            '<button class="tab" data-tab="3">原生接口</button>' +
          "</div>" +

          '<div class="tab-panel" data-panel="0">' +
            '<div class="alert warn"><span>粘贴的是<b>数组</b>，最外层的 <code class="mono">[ ]</code> 不能省。<br>' +
              '只粘 <code class="mono">{ ... }</code> 会报 <code class="mono">Spread syntax requires ...iterable[Symbol.iterator] to be a function</code>（OCS 解析器直接 <code class="mono">JSON.parse</code> 后对结果展开，对象不可迭代）。<br>' +
              '题干/选项用 <code class="mono">handler</code> 取值，会先试 <code class="mono">suggestion_title</code>、取不到再退回 <code class="mono">title</code>——' +
              '所以<b>没开图片题优化、或这道题本来就没有图片时也不会取到 undefined</b>。<br>' +
              '配置含 <code class="mono">images</code> 字段，满足 OCS 5.0「图片题优化」检测，图片题会以 base64 直接上传。</span></div>' +
            block("OCS 题库配置（整段复制）", "打开 OCS 脚本设置 → 通用 → 题库配置 → 粘贴下面整段 → 保存，刷新答题页生效。", ocsJson) +
            block("油猴 / 跨域备选", "如果 fetch 被拦截，改用 GM_xmlhttpRequest 版本，并在脚本头加 <code class=\\\"mono\\\">// @connect 127.0.0.1</code>。", ocsGmJson) +
            block("命令行验证", "确认服务在线、题库能命中。", curlSearch) +
          "</div>" +

          '<div class="tab-panel hide" data-panel="1">' +
            block("ocs-ai-answerer 兼容配置", "如果你原来用的是 AI 解题器，把地址换成本服务即可，返回结构完全一致（含 ocs_format）。", answererJson) +
            block("命令行验证", "返回三元组：题干、字母答案、元信息。", curlAnswer) +
          "</div>" +

          '<div class="tab-panel hide" data-panel="2">' +
            block("极简接口 /api/search", "兼容最老的一版轻量服务：GET 或 POST，返回 <code class=\\\"mono\\\">{code,question,answer}</code>。",
              "GET  " + base + "/api/search?title=劳动最光荣。&type=judgement&options=对,错\n\n" +
              "POST " + base + "/api/search\n" +
              '  {"title":"劳动最光荣。","type":"judgement","options":["对","错"]}') +
          "</div>" +

          '<div class="tab-panel hide" data-panel="3">' +
            block("原生接口 /api/v1/ask", "最完整的返回：字母、内容、命中来源、相似度、耗时、AI 元信息。适合自己写客户端。", curlNative) +
            block("图片题", "题干或选项里直接放图片地址，服务会自动下载并交给多模态模型：\n\n" +
              '{"title":"看图选择正确答案 https://p.ananas.chaoxing.com/star3/origin/xxx.png","type":"single","options":["甲","乙"]}',
              "支持的图片扩展名：png / jpg / jpeg / gif / webp / bmp") +
          "</div>" +

          '<div class="card">' +
            '<div class="card-title">协议对照表</div>' +
            '<div class="table-wrap"><table class="tbl"><thead><tr>' +
              "<th>入口</th><th>方法</th><th>返回</th><th>适合</th>" +
            "</tr></thead><tbody>" +
              "<tr><td class=\"mono\">/search</td><td>POST</td><td class=\"mono\">{answer, code, source}</td><td>AutoCourse-DB 题库脚本</td></tr>" +
              "<tr><td class=\"mono\">/api/answer</td><td>POST</td><td class=\"mono\">{code, ocs_format:[…]}</td><td>ocs-ai-answerer</td></tr>" +
              "<tr><td class=\"mono\">/api/search</td><td>GET/POST</td><td class=\"mono\">{code, question, answer}</td><td>老版轻量服务</td></tr>" +
              "<tr><td class=\"mono\">/api/v1/ask</td><td>GET/POST</td><td class=\"mono\">{ok, data:{…}}</td><td>自研客户端 / 调试</td></tr>" +
            "</tbody></table></div>" +
          "</div>" +
        "</div>";

      UI.fillIcons(root);

      root.querySelectorAll("#i-tabs .tab").forEach(function (tab) {
        tab.onclick = function () {
          root.querySelectorAll("#i-tabs .tab").forEach(function (t) { t.classList.remove("on"); });
          tab.classList.add("on");
          root.querySelectorAll(".tab-panel").forEach(function (p) {
            p.classList.toggle("hide", p.dataset.panel !== tab.dataset.tab);
          });
        };
      });

      root.querySelectorAll("[data-copy-btn]").forEach(function (btn) {
        btn.onclick = function () {
          const pre = btn.parentElement.querySelector("pre");
          UI.copyText(pre ? pre.textContent : "");
        };
      });

      const testBtn = UI.act("i-test");
      if (testBtn) testBtn.onclick = async function () {
        const btn = testBtn;
        btn.disabled = true;
        const lines = [];
        try {
          const health = await API.get("/api/v1/health");
          lines.push('<span class="badge ok">服务在线</span> v' + UI.escape(health.version || "") +
            " · 课程：" + UI.escape(health.course || "未选择") + " · 模型：" + UI.fmtNum(health.models || 0));
        } catch (err) {
          lines.push('<span class="badge err">服务离线</span> ' + UI.escape(err.message));
        }
        try {
          let probe = { title: "劳动最光荣。", type: "judgement", options: ["对", "错"] };
          let fromBank = false;
          try {
            const data = await API.get("/api/admin/questions?size=200&order=id_desc");
            const pool = (data.items || []).filter(function (i) { return (i.options || []).length >= 2; });
            if (pool.length) {
              const picked = pool[Math.floor(Math.random() * pool.length)];
              probe = { title: picked.title, type: picked.qtype, options: picked.options };
              fromBank = true;
            }
          } catch (err) {
            fromBank = false;
          }
          const res = await fetch("/search", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(probe),
          }).then(function (r) { return r.json(); });
          const hit = !!(res && res.answer);
          lines.push(
            '<span class="badge ' + (hit ? "ok" : "warn") + '">/search</span> ' +
              (hit ? "命中题库" : "示例题未命中（可正常使用，题库里没有这道题）") +
              (hit ? " · 题干「" + UI.escape(String(probe.title).slice(0, 18)) + "…」→ " + UI.escape(String(res.answer)) : "") +
              (fromBank ? "" : ' <span class="badge">用的是内置示例</span>')
          );
        } catch (err) {
          lines.push('<span class="badge err">/search</span> ' + UI.escape(err.message));
        }
        UI.modal({
          title: "连接自检",
          body: '<div class="tip" style="line-height:2.1">' + lines.join("<br>") + "</div>",
          footer: '<button class="btn primary" data-close="1">知道了</button>',
        });
        btn.disabled = false;
      };
    },
  };

  window.Pages.about = {
    title: "关于",
    sub: "项目说明、致谢与数据位置",
    actions: "",

    render(root) {
      root.innerHTML =
        '<div class="stack">' +
          '<div class="card">' +
            '<div class="card-title">OCS 智题库 · AnswerHub</div>' +
            '<div class="tip" style="line-height:1.9">' +
              "把「本地题库秒回」「AI 智能兜底」「图片题多模态识别」三件事合到一个进程、一个端口里：" +
              "命中的题毫秒级返回且不花钱，没命中的题交给大模型，答完自动入库，下次就成了本地题。" +
            "</div>" +
          "</div>" +
          '<div class="card">' +
            '<div class="card-title">致谢与许可</div>' +
            '<div class="kv">' +
              "<div>题库格式</div><div>AutoCourse-DB · MIT · © 2026 JinHeng</div>" +
              "<div>AI 解题思路</div><div>ocs-ai-answerer · MIT · © 2025 Liu Keda</div>" +
              "<div>界面形态参考</div><div>ocsjs-ai-answer-service（未复制其代码）</div>" +
              "<div>本项目管理</div><div>MIT · 仅供个人学习研究，请遵守所在平台的用户协议</div>" +
            "</div>" +
          "</div>" +
          '<div class="card">' +
            '<div class="card-title">数据放在哪</div>' +
            '<div class="kv">' +
              "<div>题库</div><div class=\"mono\">data/bank.db</div>" +
              "<div>配置</div><div class=\"mono\">data/config.json</div>" +
              "<div>图片缓存</div><div class=\"mono\">data/cache/images</div>" +
              "<div>日志</div><div class=\"mono\">data/（SQLite answer_logs 表）</div>" +
            "</div>" +
            '<div class="tip" style="margin-top:12px">备份只需复制整个 <code class="mono">data</code> 目录；' +
              "换电脑时把它连同项目一起拷走即可。</div>" +
          "</div>" +
          '<div class="card">' +
            '<div class="card-title">快捷键与小技巧</div>' +
            '<div class="tip" style="line-height:2">' +
              "· 题库页「导入」可直接粘贴 AutoCourse-DB 的 JSON，无需转换<br>" +
              "· 模型页可以为每类题型绑定不同模型，按顺序故障转移<br>" +
              "· 参数页关闭「AI 答案自动入库」可让 AI 结果先进入「待验证」<br>" +
              "· 日志页支持按来源筛选，一眼看出还有多少题在花钱" +
            "</div>" +
          "</div>" +
        "</div>";

      UI.fillIcons(root);
    },
  };
})();