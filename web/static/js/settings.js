/* ==========================================================================
   页面:参数
   ========================================================================== */
(function () {
  "use strict";

  const SECTIONS = [
    {
      key: "answer",
      title: "答题策略",
      desc: "控制查库优先级、模糊匹配与自动学习行为。",
      fields: [
        { path: "answer.offline_first", label: "题库优先", type: "switch", hint: "先查本地题库，未命中才调用 AI" },
        { path: "answer.enable_ai", label: "启用 AI 兜底", type: "switch", hint: "关闭后只使用本地题库" },
        { path: "answer.fuzzy_enabled", label: "模糊匹配", type: "switch", hint: "题干有细微差异（标点、空格、少量错字）时仍能命中" },
        { path: "answer.fuzzy_threshold", label: "模糊阈值", type: "number", min: 0.5, max: 1, step: 0.01, hint: "越高越严格，0.92 为推荐值" },
        { path: "answer.cross_course", label: "跨课程检索", type: "switch", hint: "开启后可在所有课程题库中查找同一道题" },
        { path: "answer.answer_format", label: "返回格式", type: "select", options: [
          { value: "auto", label: "自动（判断题回「对/错」，其余回字母）" },
          { value: "letters", label: "始终返回选项字母（A / A#C）" },
          { value: "content", label: "始终返回答案内容" },
        ] },
        { path: "answer.use_option_labels", label: "向 AI 呈现选项字母", type: "switch", hint: "关闭则直接给选项文本，模型自行判断后由系统映射回字母" },
        { path: "answer.auto_save", label: "AI 答案自动入库", type: "switch", hint: "AI 答对一次就记入题库，下次直接命中" },
        { path: "answer.auto_save_verified", label: "自动入库标记为已验证", type: "switch", hint: "关闭时标记为「待验证」，可在题库页复核" },
        { path: "answer.request_timeout", label: "AI 请求超时（秒）", type: "number", min: 5, max: 600, step: 5 },
        { path: "answer.max_retries", label: "失败重试次数", type: "number", min: 0, max: 10, step: 1 },
        { path: "answer.extra_prompt", label: "附加提示词", type: "textarea", hint: "会追加到系统提示词末尾，用于约束输出风格，留空则不追加" },
      ],
    },
    {
      key: "ai",
      title: "AI 参数",
      desc: "发送给模型的采样参数与图片处理限制。单个模型的覆盖值在「模型」页设置。",
      fields: [
        { path: "ai.temperature", label: "temperature", type: "number", min: 0, max: 2, step: 0.05, hint: "答题建议 0.1 左右，越低越稳定" },
        { path: "ai.top_p", label: "top_p", type: "number", min: 0, max: 1, step: 0.05 },
        { path: "ai.max_tokens", label: "最大输出 token", type: "number", min: 16, max: 32000, step: 16 },
        { path: "ai.reasoning_max_tokens", label: "深度思考 token 上限", type: "number", min: 256, max: 65536, step: 256 },
        { path: "ai.force_reasoning", label: "强制深度思考", type: "switch", hint: "所有题目都要求模型先思考再作答（更慢、更贵）" },
        { path: "ai.auto_reasoning_multiple", label: "多选题自动思考", type: "switch", hint: "多选题通常更易出错，默认开启思考" },
        { path: "ai.auto_reasoning_images", label: "图片题自动思考", type: "switch" },
        { path: "ai.reasoning_effort", label: "思考强度", type: "select", options: [
          { value: "low", label: "low（快）" },
          { value: "medium", label: "medium（均衡）" },
          { value: "high", label: "high（更深入）" },
        ] },
        { path: "ai.max_images", label: "单题最多下载图片数", type: "number", min: 0, max: 20, step: 1 },
        { path: "ai.image_timeout", label: "图片下载超时（秒）", type: "number", min: 3, max: 60, step: 1 },
        { path: "ai.image_max_mb", label: "单张图片大小上限（MB）", type: "number", min: 1, max: 30, step: 1 },
        { path: "ai.proxy", label: "HTTP 代理", type: "text", hint: "例如 http://127.0.0.1:7890，留空表示直连" },
      ],
    },
    {
      key: "cache",
      title: "缓存",
      desc: "问答结果的内存缓存，命中后跳过查库与 AI，毫秒级返回。",
      fields: [
        { path: "cache.enabled", label: "启用缓存", type: "switch" },
        { path: "cache.ttl", label: "有效期（秒）", type: "number", min: 10, max: 86400, step: 10 },
        { path: "cache.size", label: "最大条数", type: "number", min: 16, max: 8192, step: 16 },
      ],
    },
    {
      key: "security",
      title: "安全",
      desc: "默认只允许本机访问管理接口，若需在局域网内管理，请同时设置访问令牌。",
      fields: [
        { path: "security.allow_lan_admin", label: "允许局域网访问管理接口", type: "switch", hint: "开启后必须设置访问令牌，否则拒绝" },
        { path: "security.access_token", label: "访问令牌", type: "password", hint: "留空表示不校验；设置后请求需带 X-Token 头" },
        { path: "security.rate_limit_attempts", label: "失败次数上限", type: "number", min: 1, max: 50, step: 1 },
        { path: "security.rate_limit_window", label: "统计窗口（秒）", type: "number", min: 30, max: 3600, step: 30 },
      ],
    },
    {
      key: "server",
      title: "服务",
      desc: "修改端口后需要重启程序生效。",
      fields: [
        { path: "server.host", label: "监听地址", type: "select", options: [
          { value: "127.0.0.1", label: "127.0.0.1（仅本机）" },
          { value: "0.0.0.0", label: "0.0.0.0（局域网可访问）" },
        ] },
        { path: "server.port", label: "端口", type: "number", min: 1, max: 65535, step: 1 },
        { path: "server.open_browser", label: "启动后自动打开浏览器", type: "switch" },
      ],
    },
  ];

  function valueAt(obj, path) {
    return path.split(".").reduce(function (acc, key) {
      return acc && typeof acc === "object" ? acc[key] : undefined;
    }, obj);
  }

  function fieldHtml(field, value) {
    const id = "s-" + field.path.replace(/\./g, "-");
    const hint = field.hint ? '<span class="tip">' + UI.escape(field.hint) + "</span>" : "";

    if (field.type === "switch") {
      return (
        '<label class="switch wide"><input type="checkbox" id="' + id + '" data-path="' + field.path + '"' +
          (value ? " checked" : "") + '><span class="track"></span><span class="lbl">' + UI.escape(field.label) + "</span></label>" +
        (field.hint ? '<div class="tip indent">' + UI.escape(field.hint) + "</div>" : "")
      );
    }
    if (field.type === "select") {
      return (
        '<label class="field"><span>' + UI.escape(field.label) + "</span>" +
          '<select id="' + id + '" data-path="' + field.path + '">' +
            (field.options || []).map(function (opt) {
              return '<option value="' + UI.escape(opt.value) + '"' + (String(value) === String(opt.value) ? " selected" : "") + ">" +
                UI.escape(opt.label) + "</option>";
            }).join("") +
          "</select>" + hint + "</label>"
      );
    }
    if (field.type === "textarea") {
      return (
        '<label class="field"><span>' + UI.escape(field.label) + "</span>" +
          '<textarea id="' + id + '" data-path="' + field.path + '" style="min-height:70px">' + UI.escape(value == null ? "" : value) +
          "</textarea>" + hint + "</label>"
      );
    }
    const type = field.type === "number" ? "number" : field.type === "password" ? "password" : "text";
    const extra =
      (field.min != null ? ' min="' + field.min + '"' : "") +
      (field.max != null ? ' max="' + field.max + '"' : "") +
      (field.step != null ? ' step="' + field.step + '"' : "");
    return (
      '<label class="field"><span>' + UI.escape(field.label) + "</span>" +
        '<input type="' + type + '" id="' + id + '" data-path="' + field.path + '" value="' +
          UI.escape(value == null ? "" : String(value)) + '"' + extra + ">" + hint + "</label>"
    );
  }

  function sectionHtml(section, data) {
    return (
      '<div class="card">' +
        '<div class="card-title">' + UI.escape(section.title) + "</div>" +
        '<div class="tip" style="margin-bottom:14px">' + UI.escape(section.desc) + "</div>" +
        '<div class="form-grid">' +
          section.fields.map(function (f) { return fieldHtml(f, valueAt(data, f.path)); }).join("") +
        "</div>" +
      "</div>"
    );
  }

  window.Pages.settings = {
    title: "参数",
    sub: "全局答题参数、缓存与安全设置",
    actions:
      '<button class="btn" id="s-reload">重新加载</button>' +
      '<button class="btn primary" id="s-save"><span data-icon="check"></span>保存设置</button>',

    async render(root) {
      const data = await API.get("/api/admin/settings");
      const env = data.env || {};

      root.innerHTML =
        '<div class="stack">' +
          SECTIONS.map(function (s) { return sectionHtml(s, data); }).join("") +
          '<div class="card">' +
            '<div class="card-title">危险操作</div>' +
            '<div class="row">' +
              '<button class="btn" id="s-clear-cache">清空问答缓存</button>' +
              '<button class="btn danger" id="s-reset">恢复默认设置</button>' +
            "</div>" +
            '<div class="tip" style="margin-top:10px">' +
              "配置文件：<code class=\"mono\">" + UI.escape(env.data_dir || "data") + "/config.json</code> · Python " +
              UI.escape(env.python || "?") + " · v" + UI.escape(env.version || "") +
            "</div>" +
          "</div>" +
        "</div>";

      UI.fillIcons(root);

      const save = async function () {
        const patch = {};
        root.querySelectorAll("[data-path]").forEach(function (el) {
          const path = el.dataset.path;
          let value;
          if (el.type === "checkbox") value = el.checked;
          else if (el.type === "number") value = Number(el.value);
          else value = el.value;
          if (path === "security.access_token" && String(value).indexOf("****") >= 0) return; // 脱敏值不回写
          if (path === "security.access_token" && value === "") return;
          const parts = path.split(".");
          let node = patch;
          for (let i = 0; i < parts.length - 1; i += 1) {
            node[parts[i]] = node[parts[i]] || {};
            node = node[parts[i]];
          }
          node[parts[parts.length - 1]] = value;
        });
        try {
          await API.post("/api/admin/settings", { patch: patch });
          UI.toast("已保存", "ok");
          if (window.AppRender) window.AppRender();
        } catch (err) {
          UI.toast(err.message, "err");
        }
      };

      const saveBtn = UI.act("s-save");
      if (saveBtn) saveBtn.onclick = save;
      const reloadBtn = UI.act("s-reload");
      if (reloadBtn) reloadBtn.onclick = function () {
        if (window.AppRender) window.AppRender();
      };
      root.querySelector("#s-clear-cache").onclick = function () {
        UI.confirm("清空缓存后，下一次相同问题会重新查库/AI，确定继续？", async function () {
          await API.post("/api/admin/cache/clear", {});
          UI.toast("缓存已清空", "ok");
        }, "清空");
      };
      root.querySelector("#s-reset").onclick = function () {
        UI.confirm("将恢复为出厂默认参数（不会删除题库，但会重置模型 Key 的脱敏显示与映射）。确定继续？", async function () {
          try {
            await API.post("/api/admin/settings/reset", {});
            UI.toast("已恢复默认", "ok");
            if (window.AppRender) window.AppRender();
          } catch (err) {
            UI.toast(err.message, "err");
          }
        }, "恢复默认");
      };
    },
  };
})();