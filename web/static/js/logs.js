/* ==========================================================================
   页面:日志
   ========================================================================== */
(function () {
  "use strict";

  const SOURCE_LABEL = {
    cache: "缓存",
    bank: "题库",
    fuzzy: "模糊",
    ai: "AI",
    "": "未命中",
    none: "未命中",
  };

  const SOURCE_TONE = {
    cache: "info",
    bank: "ok",
    fuzzy: "warn",
    ai: "info",
    "": "err",
    none: "err",
  };

  const TYPES = [
    { key: "single", label: "单选" },
    { key: "multiple", label: "多选" },
    { key: "judgement", label: "判断" },
    { key: "completion", label: "填空" },
    { key: "image", label: "图片" },
  ];

  const state = { page: 1, size: 30, keyword: "", hit_source: "", qtype: "", date_from: "", date_to: "", total: 0 };

  function rowHtml(row) {
    const source = row.hit_source || "";
    const label = SOURCE_LABEL[source] != null ? SOURCE_LABEL[source] : source;
    const tone = SOURCE_TONE[source] || "info";
    return (
      '<tr data-id="' + row.id + '">' +
        '<td class="nowrap mono" style="color:var(--muted)">' + UI.shortTime(row.ts) + "</td>" +
        '<td class="nowrap"><span class="badge">' + UI.escape(row.protocol || "—") + "</span></td>" +
        '<td class="q-title"><div class="text">' + UI.escape(row.title || "") + "</div>" +
          (row.error ? '<div class="opts" style="color:var(--err)">' + UI.escape(row.error) + "</div>" : "") + "</td>" +
        '<td class="nowrap"><span class="badge ' + tone + '">' + UI.escape(label) + "</span></td>" +
        '<td class="nowrap mono">' + UI.escape(String(row.answer || "—")) + "</td>" +
        '<td class="nowrap num">' + UI.fmtMs(row.latency_ms || 0) + "</td>" +
        '<td class="nowrap" style="color:var(--muted)">' + UI.escape(row.model_name || "—") + "</td>" +
        '<td class="nowrap num">' + (row.cost_cny ? UI.fmtMoney(row.cost_cny) : "—") + "</td>" +
      "</tr>"
    );
  }

  async function renderTable(root) {
    const params = new URLSearchParams({ page: state.page, size: state.size });
    if (state.keyword) params.set("keyword", state.keyword);
    if (state.hit_source) params.set("hit_source", state.hit_source);
    if (state.qtype) params.set("qtype", state.qtype);
    if (state.date_from) params.set("date_from", state.date_from);
    if (state.date_to) params.set("date_to", state.date_to);

    const data = await API.get("/api/admin/logs?" + params.toString());
    state.total = data.total;
    const rows = (data.items || []).map(rowHtml).join("");
    const pages = Math.max(1, Math.ceil(state.total / state.size));

    const holder = root.querySelector("#l-table");
    holder.innerHTML =
      '<div class="card pad0">' +
        '<div class="table-wrap"><table class="tbl"><thead><tr>' +
          "<th>时间</th><th>协议</th><th>题目</th><th>来源</th><th>答案</th><th>耗时</th><th>模型</th><th>费用</th>" +
        "</tr></thead><tbody>" +
          (rows || '<tr><td colspan="8"><div class="empty">暂无记录</div></td></tr>') +
        "</tbody></table></div>" +
        '<div class="pager" style="padding:12px 16px">' +
          "<span>共 " + UI.fmtNum(state.total) + " 条 · 第 " + state.page + " / " + pages + " 页</span>" +
          '<button class="btn tiny" data-page="prev"' + (state.page <= 1 ? " disabled" : "") + ">上一页</button>" +
          '<button class="btn tiny" data-page="next"' + (state.page >= pages ? " disabled" : "") + ">下一页</button>" +
        "</div>" +
      "</div>";

    holder.querySelectorAll("[data-page]").forEach(function (btn) {
      btn.onclick = function () {
        state.page += btn.dataset.page === "next" ? 1 : -1;
        renderTable(root);
      };
    });

    const items = data.items || [];
    holder.querySelectorAll("tr[data-id]").forEach(function (tr) {
      const row = items.find(function (i) { return String(i.id) === tr.dataset.id; });
      tr.onclick = function () { showDetail(row); };
    });
  }

  function showDetail(row) {
    if (!row) return;
    let options = [];
    try {
      options = typeof row.options_json === "string" ? JSON.parse(row.options_json || "[]") : (row.options_json || []);
    } catch (err) {
      options = [];
    }
    const kvs = [
      ["请求 ID", row.request_id],
      ["时间", row.ts],
      ["协议", row.protocol],
      ["题型", row.qtype],
      ["命中来源", row.hit_source || "未命中"],
      ["匹配题目", row.matched_qid ? "#" + row.matched_qid : "—"],
      ["相似度", row.similarity ? UI.fmtPct(row.similarity) : "—"],
      ["模型", row.model_name || "—"],
      ["是否思考", row.reasoning ? "是" : "否"],
      ["Token", (row.prompt_tokens || 0) + " → " + (row.completion_tokens || 0)],
      ["费用", row.cost_cny ? UI.fmtMoney(row.cost_cny) : "—"],
      ["耗时", UI.fmtMs(row.latency_ms || 0)],
      ["图片数", row.images_count || 0],
      ["来源 IP", row.remote_addr || "—"],
    ];

    UI.modal({
      title: "调用详情 #" + row.id,
      wide: true,
      body:
        '<div class="kv">' +
          kvs.map(function (kv) {
            return "<div>" + UI.escape(kv[0]) + '</div><div class="mono">' + UI.escape(String(kv[1] == null ? "—" : kv[1])) + "</div>";
          }).join("") +
        "</div>" +
        '<div class="card-title" style="margin-top:16px">题目</div>' +
        '<pre class="code">' + UI.escape(row.title || "") +
          (options.length ? "\n\n" + options.map(function (o, i) { return String.fromCharCode(65 + i) + ". " + o; }).join("\n") : "") +
        "</pre>" +
        (row.answer ? '<div class="card-title" style="margin-top:14px">返回</div><pre class="code">' + UI.escape(String(row.answer)) + "</pre>" : "") +
        (row.error ? '<div class="alert err" style="margin-top:12px"><span>' + UI.escape(row.error) + "</span></div>" : ""),
      footer: '<button class="btn" data-close="1">关闭</button>',
    });
  }

  window.Pages.logs = {
    title: "日志",
    sub: "每次答题请求的命中来源、耗时与费用",
    actions:
      '<button class="btn" id="l-export"><span data-icon="download"></span>导出 CSV</button>' +
      '<button class="btn danger ghost" id="l-clear">清空日志</button>',

    async render(root) {
      root.innerHTML =
        '<div class="stack">' +
          '<div class="card"><div class="row">' +
            '<input type="text" id="l-keyword" placeholder="搜索题干 / 答案…" style="flex:1;min-width:180px" value="' + UI.escape(state.keyword) + '">' +
            '<select id="l-source" style="width:130px"><option value="">全部来源</option>' +
              [["bank", "题库"], ["cache", "缓存"], ["fuzzy", "模糊"], ["ai", "AI"]].map(function (pair) {
                return '<option value="' + pair[0] + '"' + (state.hit_source === pair[0] ? " selected" : "") + ">" + pair[1] + "</option>";
              }).join("") +
            "</select>" +
            '<select id="l-type" style="width:120px"><option value="">全部题型</option>' +
              TYPES.map(function (t) {
                return '<option value="' + t.key + '"' + (state.qtype === t.key ? " selected" : "") + ">" + t.label + "</option>";
              }).join("") +
            "</select>" +
            '<input type="date" id="l-from" style="width:150px" value="' + UI.escape(state.date_from) + '">' +
            '<input type="date" id="l-to" style="width:150px" value="' + UI.escape(state.date_to) + '">' +
            '<button class="btn" id="l-search"><span data-icon="search"></span>查询</button>' +
          "</div></div>" +
          '<div id="l-table"></div>' +
        "</div>";

      UI.fillIcons(root);

      const apply = function () {
        state.keyword = root.querySelector("#l-keyword").value.trim();
        state.hit_source = root.querySelector("#l-source").value;
        state.qtype = root.querySelector("#l-type").value;
        state.date_from = root.querySelector("#l-from").value;
        state.date_to = root.querySelector("#l-to").value;
        state.page = 1;
        renderTable(root);
      };

      root.querySelector("#l-search").onclick = apply;
      root.querySelector("#l-keyword").addEventListener("keydown", function (event) {
        if (event.key === "Enter") apply();
      });
      ["#l-source", "#l-type", "#l-from", "#l-to"].forEach(function (sel) {
        root.querySelector(sel).addEventListener("change", apply);
      });

      const exportBtn = UI.act("l-export");
      if (exportBtn) exportBtn.onclick = function () {
        window.open("/api/admin/logs/export", "_blank");
      };

      const clearBtn = UI.act("l-clear");
      if (clearBtn) clearBtn.onclick = function () {
        UI.confirm("清空全部调用日志？该操作不可撤销（题库不受影响）。", async function () {
          await API.del("/api/admin/logs");
          UI.toast("日志已清空", "ok");
          renderTable(root);
        }, "清空");
      };

      await renderTable(root);
    },
  };
})();