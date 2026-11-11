/* ==========================================================================
   页面:模型
   ========================================================================== */
(function () {
  "use strict";

  const PROTOCOLS = [
    { key: "chat_completions", label: "Chat Completions（OpenAI 兼容，通用）" },
    { key: "responses", label: "Responses（OpenAI 新版接口，支持思考）" },
  ];

  const TYPE_ORDER = ["single", "multiple", "judgement", "completion", "image"];

  let cache = null;

  function protocolLabel(key) {
    const hit = PROTOCOLS.find(function (p) { return p.key === key; });
    return hit ? hit.label.split("（")[0] : key || "—";
  }

  async function load(force) {
    if (cache && !force) return cache;
    cache = await API.get("/api/admin/models");
    return cache;
  }

  function modelCard(model, mapping) {
    const usedBy = TYPE_ORDER.filter(function (t) {
      const node = (mapping || {})[t];
      return node && (node.models || []).some(function (m) { return m.id === model.id; });
    }).map(function (t) { return (mapping[t] && mapping[t].label) || t; });

    return (
      '<div class="model-card" data-mid="' + UI.escape(model.id) + '">' +
        '<div class="row between">' +
          "<div>" +
            '<div class="name">' + UI.escape(model.name) +
              (model.builtin ? ' <span class="badge">内置</span>' : "") +
              (model.is_multimodal ? ' <span class="badge info">多模态</span>' : "") +
              (model.has_key ? "" : ' <span class="badge warn">未填 Key</span>') +
            "</div>" +
            '<div class="meta mono">' + UI.escape(model.model_name || "—") + " · " + UI.escape(protocolLabel(model.protocol)) + "</div>" +
            '<div class="meta mono">' + UI.escape(model.base_url || "—") + "</div>" +
          "</div>" +
          '<label class="switch"><input type="checkbox" data-act="toggle"' + (model.enabled ? " checked" : "") +
            '><span class="track"></span><span>启用</span></label>' +
        "</div>" +
        (usedBy.length
          ? '<div class="meta">用于：' + usedBy.map(function (t) { return '<span class="badge ok">' + UI.escape(t) + "</span>"; }).join(" ") + "</div>"
          : '<div class="meta">未分配题型（将使用回退模型）</div>') +
        '<div class="row" style="margin-top:10px">' +
          '<button class="btn tiny" data-act="test">测试连通</button>' +
          '<button class="btn tiny ghost" data-act="edit">编辑</button>' +
          '<button class="btn tiny ghost danger" data-act="del"' + (model.builtin ? " disabled" : "") + ">删除</button>" +
        "</div>" +
        '<div class="test-out" data-role="out"></div>' +
      "</div>"
    );
  }

  function mappingPanel(mapping, models) {
    return (
      '<div class="card"><div class="card-title">题型 → 模型映射</div>' +
        '<div class="alert info"><span>每类题型可绑定多个模型，按顺序尝试，前一个失败自动切到下一个；图片题只能选「多模态」模型。留空则使用回退模型。</span></div>' +
        TYPE_ORDER.map(function (t) {
          const node = (mapping || {})[t] || { label: t, models: [], enable_reasoning: false };
          const chosen = (node.models || []).map(function (m) { return m.id; });
          return (
            '<div class="map-row" data-type="' + t + '">' +
              '<div class="row between">' +
                '<div class="map-label">' + UI.escape(node.label || t) + "</div>" +
                '<label class="switch"><input type="checkbox" data-role="reasoning"' + (node.enable_reasoning ? " checked" : "") +
                  '><span class="track"></span><span>启用深度思考</span></label>' +
              "</div>" +
              '<div class="chips">' +
                models.map(function (m) {
                  const disabled = t === "image" && !m.is_multimodal;
                  const on = chosen.indexOf(m.id) >= 0;
                  return (
                    '<button class="chip' + (on ? " on" : "") + (disabled ? " disabled" : "") + '" data-mid="' + UI.escape(m.id) + '"' +
                      (disabled ? " disabled title=\"图片题需要多模态模型\"" : "") + ">" +
                      UI.escape(m.name) + (m.enabled ? "" : "（已停用）") +
                    "</button>"
                  );
                }).join("") +
              "</div>" +
            "</div>"
          );
        }).join("") +
        '<div class="row" style="margin-top:14px"><button class="btn primary" id="m-save">保存映射</button></div>' +
      "</div>"
    );
  }

  function fallbackPanel(models, fallback) {
    return (
      '<div class="card"><div class="card-title">回退模型</div>' +
        '<div class="alert"><span>当某类题型没有绑定模型、或绑定的模型全部失败时，按此顺序兜底。</span></div>' +
        '<div class="chips" id="m-fallback">' +
          models.map(function (m) {
            const on = (fallback || []).indexOf(m.id) >= 0;
            return '<button class="chip' + (on ? " on" : "") + '" data-mid="' + UI.escape(m.id) + '">' + UI.escape(m.name) + "</button>";
          }).join("") +
        "</div>" +
      "</div>"
    );
  }

  function openEditor(model) {
    const isNew = !model;
    const m = model || {
      name: "",
      protocol: "chat_completions",
      base_url: "https://api.deepseek.com/v1",
      model_name: "",
      api_key: "",
      enabled: true,
      is_multimodal: false,
      supports_reasoning: false,
      reasoning_param_name: "reasoning_effort",
      reasoning_param_value: "medium",
      max_tokens: 0,
      temperature: 0,
      top_p: 0,
      price_in: 0,
      price_out: 0,
    };

    const body =
      '<div class="grid2">' +
        '<label class="field"><span>显示名称</span><input type="text" id="f-name" value="' + UI.escape(m.name) + '" placeholder="DeepSeek Chat"></label>' +
        '<label class="field"><span>接口协议</span><select id="f-protocol">' +
          PROTOCOLS.map(function (p) {
            return '<option value="' + p.key + '"' + (m.protocol === p.key ? " selected" : "") + ">" + p.label + "</option>";
          }).join("") +
        "</select></label>" +
      "</div>" +
      '<label class="field"><span>API 地址（Base URL）</span><input type="text" id="f-base" value="' + UI.escape(m.base_url) +
        '" placeholder="https://api.deepseek.com/v1"></label>' +
      '<div class="grid2">' +
        '<label class="field"><span>模型名（请求体里的 model）</span><input type="text" id="f-model" value="' + UI.escape(m.model_name) +
          '" placeholder="deepseek-chat"></label>' +
        '<label class="field"><span>API Key</span><input type="password" id="f-key" value="' + UI.escape(m.api_key || "") +
          '" placeholder="' + (m.has_key ? "已保存，留空则保持不变" : "sk-…") + '"></label>' +
      "</div>" +
      '<div class="grid2">' +
        '<label class="field"><span>输入价格（元 / 百万 token）</span><input type="number" step="0.01" min="0" id="f-pin" value="' + (m.price_in || 0) + '"></label>' +
        '<label class="field"><span>输出价格（元 / 百万 token）</span><input type="number" step="0.01" min="0" id="f-pout" value="' + (m.price_out || 0) + '"></label>' +
      "</div>" +
      '<div class="grid3">' +
        '<label class="field"><span>max_tokens（0=不指定）</span><input type="number" min="0" id="f-maxtok" value="' + (m.max_tokens || 0) + '"></label>' +
        '<label class="field"><span>temperature（0=默认）</span><input type="number" step="0.05" min="0" max="2" id="f-temp" value="' + (m.temperature || 0) + '"></label>' +
        '<label class="field"><span>top_p（0=默认）</span><input type="number" step="0.05" min="0" max="1" id="f-topp" value="' + (m.top_p || 0) + '"></label>' +
      "</div>" +
      '<div class="grid2">' +
        '<label class="field"><span>思考参数名</span><input type="text" id="f-rname" value="' + UI.escape(m.reasoning_param_name || "") + '" placeholder="reasoning_effort"></label>' +
        '<label class="field"><span>思考参数值</span><input type="text" id="f-rvalue" value="' + UI.escape(String(m.reasoning_param_value == null ? "" : m.reasoning_param_value)) + '" placeholder="medium"></label>' +
      "</div>" +
      '<div class="stack-tight">' +
        '<label class="switch"><input type="checkbox" id="f-multi"' + (m.is_multimodal ? " checked" : "") +
          '><span class="track"></span><span>多模态（能看图，可处理图片题）</span></label>' +
        '<label class="switch"><input type="checkbox" id="f-reason"' + (m.supports_reasoning ? " checked" : "") +
          '><span class="track"></span><span>支持深度思考（思考参数会随请求发送）</span></label>' +
        '<label class="switch"><input type="checkbox" id="f-enabled"' + (m.enabled ? " checked" : "") +
          '><span class="track"></span><span>启用该模型</span></label>' +
      "</div>";

    UI.modal({
      title: isNew ? "新增模型" : "编辑模型 · " + m.name,
      body: body,
      wide: true,
      footer: '<button class="btn" data-close="1">取消</button><button class="btn primary" id="f-save">保存</button>',
      onMount: function (root) {
        root.querySelector("#f-save").onclick = async function () {
          const payload = {
            id: m.id,
            name: root.querySelector("#f-name").value.trim(),
            protocol: root.querySelector("#f-protocol").value,
            base_url: root.querySelector("#f-base").value.trim(),
            model_name: root.querySelector("#f-model").value.trim(),
            api_key: root.querySelector("#f-key").value,
            price_in: Number(root.querySelector("#f-pin").value || 0),
            price_out: Number(root.querySelector("#f-pout").value || 0),
            max_tokens: Number(root.querySelector("#f-maxtok").value || 0),
            temperature: Number(root.querySelector("#f-temp").value || 0),
            top_p: Number(root.querySelector("#f-topp").value || 0),
            reasoning_param_name: root.querySelector("#f-rname").value.trim(),
            reasoning_param_value: root.querySelector("#f-rvalue").value.trim(),
            is_multimodal: root.querySelector("#f-multi").checked,
            supports_reasoning: root.querySelector("#f-reason").checked,
            enabled: root.querySelector("#f-enabled").checked,
          };
          if (!payload.name) return UI.toast("请填写显示名称", "err");
          if (!payload.model_name) return UI.toast("请填写模型名", "err");
          if (!payload.base_url) return UI.toast("请填写 API 地址", "err");
          try {
            await API.post("/api/admin/models", payload);
            UI.closeModal();
            UI.toast("已保存", "ok");
            if (window.AppRender) window.AppRender();
          } catch (err) {
            UI.toast(err.message, "err");
          }
        };
      },
    });
  }

  window.Pages.models = {
    title: "模型",
    sub: "配置 AI 供应商、题型映射与回退顺序",
    actions: '<button class="btn primary" id="m-new"><span data-icon="plus"></span>新增模型</button>',

    async render(root) {
      const data = await load(true);
      const models = data.items || [];
      const mapping = data.mapping || {};
      const fallback = data.fallback_models || [];

      root.innerHTML =
        '<div class="stack">' +
          '<div class="card"><div class="card-title">模型列表</div>' +
            '<div class="alert"><span>支持任意 OpenAI 兼容接口（DeepSeek、豆包、通义、Kimi、OpenAI、本地 Ollama / vLLM 等）。' +
              "API Key 仅保存在本机 <code class=\"mono\">data/config.json</code>，界面回显脱敏。</span></div>" +
            '<div class="model-grid">' +
              (models.length ? models.map(function (m) { return modelCard(m, mapping); }).join("")
                             : '<div class="empty">还没有配置模型</div>') +
            "</div>" +
          "</div>" +
          mappingPanel(mapping, models) +
          fallbackPanel(models, fallback) +
        "</div>";

      UI.fillIcons(root);
      const newBtn = UI.act("m-new");
      if (newBtn) newBtn.onclick = function () { openEditor(null); };

      root.querySelectorAll(".model-card").forEach(function (card) {
        const mid = card.dataset.mid;
        const model = models.find(function (m) { return m.id === mid; });
        const out = card.querySelector('[data-role="out"]');

        card.querySelector('[data-act="edit"]').onclick = function () { openEditor(model); };

        card.querySelector('[data-act="toggle"]').onchange = async function (event) {
          try {
            await API.post("/api/admin/models", { id: mid, enabled: event.target.checked });
            UI.toast(event.target.checked ? "已启用" : "已停用", "ok");
            if (window.AppRender) window.AppRender();
          } catch (err) {
            UI.toast(err.message, "err");
          }
        };

        card.querySelector('[data-act="del"]').onclick = function () {
          UI.confirm("删除模型「" + model.name + "」？同时会从题型映射中移除。", async function () {
            await API.del("/api/admin/models/" + encodeURIComponent(mid));
            UI.toast("已删除", "ok");
            if (window.AppRender) window.AppRender();
          });
        };

        card.querySelector('[data-act="test"]').onclick = async function (event) {
          const btn = event.target;
          btn.disabled = true;
          out.className = "test-out";
          out.textContent = "正在请求…";
          try {
            const result = await API.post("/api/admin/models/" + encodeURIComponent(mid) + "/test", {});
            if (result.ok === false) {
              out.className = "test-out err";
              out.textContent = "失败：" + (result.error || "未知错误");
            } else {
              out.className = "test-out ok";
              out.textContent = "成功 · " + UI.fmtMs(result.latency_ms || 0) + " · 回复：" + String(result.content || "").slice(0, 60);
            }
          } catch (err) {
            out.className = "test-out err";
            out.textContent = "失败：" + err.message;
          }
          btn.disabled = false;
        };
      });

      // 题型映射：点击 chip 切换
      root.querySelectorAll(".map-row").forEach(function (row) {
        const type = row.dataset.type;
        row.querySelectorAll(".chip").forEach(function (chip) {
          chip.onclick = function () {
            if (chip.disabled) return;
            chip.classList.toggle("on");
          };
        });
        row.dataset.changed = "";
      });

      root.querySelector("#m-save").onclick = async function () {
        const next = {};
        root.querySelectorAll(".map-row").forEach(function (row) {
          const type = row.dataset.type;
          next[type] = {
            models: Array.prototype.map.call(row.querySelectorAll(".chip.on"), function (c) { return c.dataset.mid; }),
            enable_reasoning: row.querySelector('[data-role="reasoning"]').checked,
          };
        });
        try {
          await API.post("/api/admin/mapping", { mapping: next });
          UI.toast("映射已保存", "ok");
          if (window.AppRender) window.AppRender();
        } catch (err) {
          UI.toast(err.message, "err");
        }
      };

      // 回退模型
      root.querySelectorAll("#m-fallback .chip").forEach(function (chip) {
        chip.onclick = async function () {
          chip.classList.toggle("on");
          const picked = Array.prototype.map.call(root.querySelectorAll("#m-fallback .chip.on"), function (c) { return c.dataset.mid; });
          try {
            await API.post("/api/admin/mapping", { fallback_models: picked });
            UI.toast("回退顺序已保存", "ok");
          } catch (err) {
            UI.toast(err.message, "err");
          }
        };
      });
    },
  };
})();