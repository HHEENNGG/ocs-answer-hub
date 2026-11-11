/* ==========================================================================
   页面:答题测试
   ========================================================================== */
(function () {
  "use strict";

  const TYPES = [
    { key: "single", label: "单选题" },
    { key: "multiple", label: "多选题" },
    { key: "judgement", label: "判断题" },
    { key: "completion", label: "填空题" },
  ];

  // 示例题取自仓库自带的 libraries/示例题库.json，点「填入示例」能直接命中题库
  const SAMPLES = [
    {
      type: "single",
      title: "本项目用什么数据库保存题库？",
      options: "A. SQLite\nB. MySQL\nC. PostgreSQL\nD. Redis",
    },
    {
      type: "multiple",
      title: "本项目同时兼容哪些接入协议？",
      options: "A. /search\nB. /api/search\nC. /api/answer\nD. /api/v1/ask",
    },
    {
      type: "judgement",
      title: "同一道题的选项顺序被调换后，本项目依然能命中题库。（ ）",
      options: "对\n错",
    },
  ];

  const SOURCE_LABEL = {
    cache: "缓存",
    bank: "题库",
    fuzzy: "模糊匹配",
    ai: "AI 兜底",
    none: "未命中",
  };

  function resultHtml(result, forced) {
    if (!result) {
      return '<div class="empty">填写题目后点击「开始答题」</div>';
    }
    const source = forced ? "ai" : result.hit_source || "none";
    const ok = source !== "none" && !result.error;
    const ai = result.ai || {};
    const letters = result.letters || "";
    const contents = (result.contents || []).join(" / ");
    const big = result.type === "judgement" || result.type === "completion"
      ? (contents || result.answer || "—")
      : (letters || contents || "—");

    return (
      '<div class="result ' + (ok ? "ok" : "err") + '">' +
        '<div class="result-answer">' + UI.escape(big) + "</div>" +
        '<div class="result-meta">' +
          '<span class="badge ' + (ok ? "ok" : "err") + '">' + UI.escape(SOURCE_LABEL[source] || source) + "</span>" +
          (result.type ? '<span class="badge">' + UI.escape(result.type_label || result.type) + "</span>" : "") +
          (result.confidence != null && result.confidence > 0
            ? '<span class="badge info">相似度 ' + UI.fmtPct(result.confidence) + "</span>" : "") +
          (ai.model_name ? '<span class="badge info">' + UI.escape(ai.model_name) + "</span>" : "") +
          (ai.reasoning ? '<span class="badge warn">已思考</span>' : "") +
          '<span class="badge">' + UI.fmtMs(result.elapsed_ms || ai.elapsed_ms || 0) + "</span>" +
          (result.course ? '<span class="badge">' + UI.escape(result.course) + "</span>" : "") +
        "</div>" +
        (result.error ? '<div class="alert err"><span>' + UI.escape(result.error) + "</span></div>" : "") +
        (contents && letters ? '<div class="kv-line"><b>答案内容</b><span>' + UI.escape(contents) + "</span></div>" : "") +
        (result.question_id ? '<div class="kv-line"><b>题库 ID</b><span class="mono">#' + result.question_id + "</span></div>" : "") +
        (result.request_id ? '<div class="kv-line"><b>请求 ID</b><span class="mono">' + UI.escape(result.request_id) + "</span></div>" : "") +
        (ai.prompt_tokens != null && ai.prompt_tokens
          ? '<div class="kv-line"><b>Token</b><span class="mono">' + ai.prompt_tokens + " → " + (ai.completion_tokens || 0) +
            "（合计 " + (ai.total_tokens || (ai.prompt_tokens + (ai.completion_tokens || 0))) + "）</span></div>"
          : "") +
        (ai.cost_cny ? '<div class="kv-line"><b>费用</b><span class="mono">' + UI.fmtMoney(ai.cost_cny) + "</span></div>" : "") +
        (result.raw
          ? '<details class="raw"><summary>模型原始输出</summary><pre class="code">' + UI.escape(result.raw) + "</pre></details>"
          : "") +
        (ai.reasoning_content
          ? '<details class="raw"><summary>思考过程</summary><pre class="code">' + UI.escape(ai.reasoning_content) + "</pre></details>"
          : "") +
      "</div>"
    );
  }

  window.Pages.playground = {
    title: "答题测试",
    sub: "在本页模拟 OCS 的一次请求，验证题库命中与 AI 效果",
    actions:
      '<button class="btn ghost" id="p-sample">填入示例</button>' +
      '<button class="btn" id="p-ai"><span data-icon="spark"></span>强制 AI</button>' +
      '<button class="btn primary" id="p-run"><span data-icon="play"></span>开始答题</button>',

    render(root) {
      root.innerHTML =
        '<div class="split">' +
          '<div class="card">' +
            '<div class="card-title">题目</div>' +
            '<label class="field"><span>题型</span><select id="p-type">' +
              TYPES.map(function (t) { return '<option value="' + t.key + '">' + t.label + "</option>"; }).join("") +
            "</select></label>" +
            '<label class="field"><span>题干</span><textarea id="p-title" placeholder="粘贴题干，可包含图片地址" style="min-height:96px"></textarea></label>' +
            '<label class="field"><span>选项（每行一个，可带 A. 前缀；判断题填「对 / 错」）</span>' +
              '<textarea id="p-options" data-role="opts" placeholder="A. 选项一&#10;B. 选项二" style="min-height:110px"></textarea></label>' +
            '<div class="tip">提示：题干或选项中包含 <code class="mono">https://p.ananas.chaoxing.com/…</code> 这类图片地址时，会自动下载并交给多模态模型识别。</div>' +
          "</div>" +
          '<div class="card" id="p-result">' + resultHtml(null) + "</div>" +
        "</div>";

      UI.fillIcons(root);

      const collect = function () {
        return {
          type: root.querySelector("#p-type").value,
          title: root.querySelector("#p-title").value.trim(),
          options: root.querySelector("#p-options").value,
        };
      };

      const run = async function (forced) {
        const payload = collect();
        if (!payload.title) return UI.toast("请先填写题干", "err");
        const holder = root.querySelector("#p-result");
        holder.innerHTML = '<div class="empty">正在请求…</div>';
        const started = Date.now();
        try {
          const result = forced
            ? await API.post("/api/admin/ai-preview", payload)
            : await API.post("/api/v1/ask", payload);
          if (!result.elapsed_ms) result.elapsed_ms = Date.now() - started;
          holder.innerHTML = resultHtml(result, forced);
        } catch (err) {
          holder.innerHTML =
            '<div class="empty" style="color:var(--err)">请求失败：' + UI.escape(err.message) + "</div>";
        }
      };

      const runBtn = UI.act("p-run");
      if (runBtn) runBtn.onclick = function () { run(false); };
      const aiBtn = UI.act("p-ai");
      if (aiBtn) aiBtn.onclick = function () { run(true); };
      const sampleBtn = UI.act("p-sample");
      if (sampleBtn) sampleBtn.onclick = async function () {
        const fallback = SAMPLES[Math.floor(Math.random() * SAMPLES.length)];
        let picked = null;
        try {
          const data = await API.get("/api/admin/questions?size=200&order=id_desc");
          const pool = (data.items || []).filter(function (i) { return (i.options || []).length >= 2; });
          if (pool.length) picked = pool[Math.floor(Math.random() * pool.length)];
        } catch (err) {
          picked = null;
        }
        const sample = picked
          ? {
              type: picked.qtype,
              title: picked.title,
              options: (picked.options || []).map(function (o, i) { return String.fromCharCode(65 + i) + ". " + o; }).join("\n"),
            }
          : fallback;
        root.querySelector("#p-type").value = sample.type;
        root.querySelector("#p-title").value = sample.title;
        root.querySelector("#p-options").value = sample.options;
        root.querySelector("#p-result").innerHTML = resultHtml(null);
      };
    },
  };
})();