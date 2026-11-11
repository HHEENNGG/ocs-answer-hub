/* ==========================================================================
   页面:题库
   ========================================================================== */
(function () {
  "use strict";

  const TYPES = [
    { key: "single", label: "单选题" },
    { key: "multiple", label: "多选题" },
    { key: "judgement", label: "判断题" },
    { key: "completion", label: "填空题" },
  ];

  const state = { page: 1, size: 20, keyword: "", qtype: "", verified: "", course_id: "", total: 0 };

  let coursesCache = null;

  async function loadCourses(force) {
    if (coursesCache && !force) return coursesCache;
    const data = await API.get("/api/admin/courses");
    coursesCache = (data && data.items) || [];
    return coursesCache;
  }

  function typeLabel(key) {
    const hit = TYPES.find(function (t) { return t.key === key; });
    return hit ? hit.label : key || "—";
  }

  function optionsText(q) {
    return (q.options || []).map(function (opt, i) { return String.fromCharCode(65 + i) + ". " + opt; }).join("  ");
  }

  async function renderTable(root) {
    const params = new URLSearchParams({ page: state.page, size: state.size, order: "id_desc" });
    if (state.course_id) params.set("course_id", state.course_id);
    if (state.keyword) params.set("keyword", state.keyword);
    if (state.qtype) params.set("qtype", state.qtype);
    if (state.verified !== "") params.set("verified", state.verified);

    const data = await API.get("/api/admin/questions?" + params.toString());
    state.total = data.total;

    const rows = (data.items || [])
      .map(function (q) {
        return (
          '<tr data-qid="' + q.id + '">' +
            '<td class="nowrap mono" style="color:var(--muted)">' + q.id + "</td>" +
            '<td class="nowrap"><span class="badge">' + UI.escape(typeLabel(q.qtype)) + "</span></td>" +
            '<td class="q-title"><div class="text">' + UI.escape(q.title) + "</div>" +
              '<div class="opts">' + UI.escape(optionsText(q)) + "</div></td>" +
            '<td class="nowrap"><span class="badge ok">' + UI.escape((q.answer || []).join(" / ") || "—") + "</span></td>" +
            '<td class="nowrap">' + (q.verified
              ? '<span class="badge ok">已验证</span>'
              : '<span class="badge warn">待验证</span>') + "</td>" +
            '<td class="nowrap num">' + UI.fmtNum(q.hit_count || 0) + "</td>" +
            '<td class="nowrap"><span class="badge info">' + UI.escape(q.source || "—") + "</span></td>" +
            '<td class="nowrap">' +
              '<button class="btn tiny ghost" data-act="edit">编辑</button> ' +
              '<button class="btn tiny ghost danger" data-act="del">删除</button>' +
            "</td>" +
          "</tr>"
        );
      })
      .join("");

    const pages = Math.max(1, Math.ceil(state.total / state.size));
    const table =
      '<div class="card pad0">' +
        '<div class="table-wrap"><table class="tbl"><thead><tr>' +
          "<th>ID</th><th>题型</th><th>题目 / 选项</th><th>答案</th><th>状态</th><th>命中</th><th>来源</th><th>操作</th>" +
        "</tr></thead><tbody>" +
          (rows || '<tr><td colspan="8"><div class="empty">没有符合条件的题目</div></td></tr>') +
        "</tbody></table></div>" +
        '<div class="pager" style="padding:12px 16px">' +
          "<span>共 " + UI.fmtNum(state.total) + " 题 · 第 " + state.page + " / " + pages + " 页</span>" +
          '<button class="btn tiny" data-page="prev"' + (state.page <= 1 ? " disabled" : "") + ">上一页</button>" +
          '<button class="btn tiny" data-page="next"' + (state.page >= pages ? " disabled" : "") + ">下一页</button>" +
        "</div>" +
      "</div>";

    const holder = root.querySelector("#q-table");
    holder.innerHTML = table;

    holder.querySelectorAll("[data-page]").forEach(function (btn) {
      btn.onclick = function () {
        state.page += btn.dataset.page === "next" ? 1 : -1;
        renderTable(root);
      };
    });

    holder.querySelectorAll("tr[data-qid]").forEach(function (tr) {
      const qid = Number(tr.dataset.qid);
      tr.querySelector('[data-act="edit"]').onclick = async function () {
        const q = await API.get("/api/admin/questions/" + qid);
        openEditor(q);
      };
      tr.querySelector('[data-act="del"]').onclick = function () {
        UI.confirm("确定删除第 " + qid + " 题？该操作不可撤销。", async function () {
          await API.del("/api/admin/questions/" + qid);
          UI.toast("已删除", "ok");
          renderTable(root);
          if (window.AppRender) window.AppRender();
        });
      };
    });
  }

  function openEditor(question) {
    const isNew = !question;
    const q = question || { qtype: "single", title: "", options: [], answer: [], verified: true };
    const body =
      '<label class="field"><span>题型</span><select id="ed-type">' +
        TYPES.map(function (t) {
          return '<option value="' + t.key + '"' + (q.qtype === t.key ? " selected" : "") + ">" + t.label + "</option>";
        }).join("") +
      "</select></label>" +
      '<label class="field"><span>题干</span><textarea id="ed-title" placeholder="粘贴题目文本">' +
        UI.escape(q.title) + "</textarea></label>" +
      '<label class="field"><span>选项（每行一个，可带 A. 前缀）</span>' +
        '<textarea id="ed-options" placeholder="A. 选项一&#10;B. 选项二">' +
        UI.escape((q.options || []).map(function (o, i) { return String.fromCharCode(65 + i) + ". " + o; }).join("\n")) +
      "</textarea><span class=\"tip\">判断题可只填「对 / 错」，填空题留空</span></label>" +
      '<label class="field"><span>正确答案（内容，多个用 # 或换行分隔）</span>' +
        '<textarea id="ed-answer" placeholder="节俭，珍惜劳动成果">' +
        UI.escape((q.answer || []).join("#")) + "</textarea></label>" +
      '<label class="switch"><input type="checkbox" id="ed-verified"' + (q.verified ? " checked" : "") +
        '><span class="track"></span><span>标记为「已验证」（命中后直接使用，不参与 AI 复核）</span></label>';

    UI.modal({
      title: isNew ? "新增题目" : "编辑题目 #" + q.id,
      body: body,
      footer:
        '<button class="btn" data-close="1">取消</button>' +
        '<button class="btn primary" id="ed-save">保存</button>',
      onMount: function (root) {
        root.querySelector("#ed-save").onclick = async function () {
          const payload = {
            qtype: root.querySelector("#ed-type").value,
            title: root.querySelector("#ed-title").value.trim(),
            options: root.querySelector("#ed-options").value,
            answer: root.querySelector("#ed-answer").value,
            verified: root.querySelector("#ed-verified").checked,
          };
          if (!payload.title) return UI.toast("题干不能为空", "err");
          if (state.course_id) payload.course_id = Number(state.course_id);
          try {
            if (isNew) await API.post("/api/admin/questions", payload);
            else await API.put("/api/admin/questions/" + q.id, payload);
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

  function openImport() {
    const body =
      '<div class="alert info"><span>支持 AutoCourse-DB 题库格式（<code class="mono">{ "[single] 题干 | 选项A | 选项B": "答案内容" }</code>），' +
        "也支持本系统导出的 JSON。可直接粘贴或上传文件。</span></div>" +
      '<label class="field"><span>课程名（留空则用文件名或「测试课程」）</span>' +
        '<input type="text" id="im-course" placeholder="如：示例题库"></label>' +
      '<label class="field"><span>题库 JSON</span>' +
        '<textarea id="im-data" style="min-height:180px;font-family:var(--mono);font-size:12px" placeholder=\'{"[single] 题干 | 甲 | 乙": "甲"}\'></textarea></label>' +
      '<label class="field"><span>或者选择文件</span><input type="file" id="im-file" accept=".json,application/json"></label>' +
      '<label class="field"><span>重复题目处理</span><select id="im-strategy">' +
        '<option value="skip">跳过（保留题库现有答案）</option>' +
        '<option value="overwrite_unverified">仅覆盖未验证题目</option>' +
        '<option value="overwrite">全部覆盖</option>' +
      "</select></label>";

    UI.modal({
      title: "导入题库",
      body: body,
      footer: '<button class="btn" data-close="1">取消</button><button class="btn primary" id="im-ok">开始导入</button>',
      onMount: function (root) {
        const fileInput = root.querySelector("#im-file");
        fileInput.onchange = function () {
          const file = fileInput.files && fileInput.files[0];
          if (!file) return;
          const reader = new FileReader();
          reader.onload = function () {
            root.querySelector("#im-data").value = String(reader.result || "");
            if (!root.querySelector("#im-course").value) {
              root.querySelector("#im-course").value = file.name.replace(/\.json$/i, "");
            }
          };
          reader.readAsText(file, "utf-8");
        };

        root.querySelector("#im-ok").onclick = async function () {
          const raw = root.querySelector("#im-data").value.trim();
          if (!raw) return UI.toast("请粘贴题库 JSON 或选择文件", "err");
          const btn = root.querySelector("#im-ok");
          btn.disabled = true;
          btn.textContent = "导入中…";
          try {
            const result = await API.post("/api/admin/import", {
              course_name: root.querySelector("#im-course").value.trim(),
              data: raw,
              strategy: root.querySelector("#im-strategy").value,
            });
            UI.closeModal();
            UI.toast(
              "导入完成：新增 " + UI.fmtNum(result.created) + "，更新 " + UI.fmtNum(result.updated) +
                "，跳过 " + UI.fmtNum(result.skipped) + "，无效 " + UI.fmtNum(result.invalid),
              "ok"
            );
            loadCourses(true);
            if (window.AppRender) window.AppRender();
          } catch (err) {
            btn.disabled = false;
            btn.textContent = "开始导入";
            UI.toast(err.message, "err");
          }
        };
      },
    });
  }

  window.Pages.questions = {
    title: "题库",
    sub: "管理本地题库：检索、增删改、导入导出",
    actions:
      '<button class="btn" id="q-import"><span data-icon="upload"></span>导入</button>' +
      '<button class="btn" id="q-export"><span data-icon="download"></span>导出</button>' +
      '<button class="btn primary" id="q-new"><span data-icon="plus"></span>新增题目</button>',

    async render(root) {
      const courses = await loadCourses();
      const courseOptions = courses
        .map(function (c) {
          return '<option value="' + c.id + '"' + (String(c.id) === String(state.course_id) ? " selected" : "") + ">" +
            UI.escape(c.name) + "（" + UI.fmtNum(c.question_count) + " 题）</option>";
        })
        .join("");

      root.innerHTML =
        '<div class="stack">' +
          '<div class="card"><div class="row">' +
            '<select id="q-course" style="width:230px"><option value="">全部课程</option>' + courseOptions + "</select>" +
            '<select id="q-type" style="width:120px"><option value="">全部题型</option>' +
              TYPES.map(function (t) {
                return '<option value="' + t.key + '"' + (state.qtype === t.key ? " selected" : "") + ">" + t.label + "</option>";
              }).join("") +
            "</select>" +
            '<select id="q-verified" style="width:120px"><option value="">全部状态</option>' +
              '<option value="1"' + (state.verified === "1" ? " selected" : "") + ">已验证</option>" +
              '<option value="0"' + (state.verified === "0" ? " selected" : "") + ">待验证</option>" +
            "</select>" +
            '<input type="text" id="q-keyword" placeholder="搜索题干 / 选项…" style="flex:1;min-width:180px" value="' +
              UI.escape(state.keyword) + '">' +
            '<button class="btn" id="q-search"><span data-icon="search"></span>搜索</button>' +
            '<button class="btn ghost tiny" id="q-dedupe" title="清理同一课程内的重复题目">去重</button>' +
          "</div></div>" +
          '<div id="q-table"></div>' +
        "</div>";

      UI.fillIcons(root);

      const bind = function (id, event, handler) {
        const node = UI.act(id.slice(1)) || root.querySelector(id);
        if (node) node.addEventListener(event, handler);
      };

      bind("#q-search", "click", function () {
        state.keyword = root.querySelector("#q-keyword").value.trim();
        state.page = 1;
        renderTable(root);
      });
      bind("#q-keyword", "keydown", function (event) {
        if (event.key === "Enter") {
          state.keyword = root.querySelector("#q-keyword").value.trim();
          state.page = 1;
          renderTable(root);
        }
      });
      bind("#q-course", "change", function (event) {
        state.course_id = event.target.value;
        state.page = 1;
        renderTable(root);
      });
      bind("#q-type", "change", function (event) {
        state.qtype = event.target.value;
        state.page = 1;
        renderTable(root);
      });
      bind("#q-verified", "change", function (event) {
        state.verified = event.target.value;
        state.page = 1;
        renderTable(root);
      });
      bind("#q-new", "click", function () { openEditor(null); });
      bind("#q-import", "click", openImport);
      bind("#q-export", "click", function () {
        const params = new URLSearchParams({ download: "1" });
        if (state.course_id) params.set("course_id", state.course_id);
        window.open("/api/admin/export?" + params.toString(), "_blank");
      });
      bind("#q-dedupe", "click", function () {
        UI.confirm("将删除同一课程内重复的题目（保留命中次数更高的那条），是否继续？", async function () {
          const result = await API.post("/api/admin/questions/dedupe", state.course_id ? { course_id: Number(state.course_id) } : {});
          UI.toast("去重完成，删除 " + UI.fmtNum(result.deleted || 0) + " 条", "ok");
          renderTable(root);
        }, "开始去重");
      });

      await renderTable(root);
    },
  };
})();