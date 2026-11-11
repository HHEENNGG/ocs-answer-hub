/* ==========================================================================
   页面：概览
   ========================================================================== */
(function () {
  "use strict";

  const TYPE_LABEL = { single: "单选题", multiple: "多选题", judgement: "判断题", completion: "填空题", image: "图片题" };
  const SOURCE_LABEL = { bank: "题库命中", legacy: "旧格式命中", fuzzy: "模糊匹配", cache: "缓存命中", ai: "AI 回答", "": "未命中" };

  function statCard(label, value, unit, delta, iconName) {
    return (
      '<div class="card stat">' +
        '<div class="label"><span style="width:14px;height:14px;display:inline-flex">' + UI.icon(iconName) + "</span>" + label + "</div>" +
        '<div class="value">' + value + (unit ? "<small>" + unit + "</small>" : "") + "</div>" +
        (delta ? '<div class="delta">' + delta + "</div>" : "") +
      "</div>"
    );
  }

  window.Pages.dashboard = {
    title: "概览",
    sub: "题库规模、作答情况与命中来源一览",

    async render(root) {
      const stats = await API.get("/api/admin/stats");
      const bank = stats.bank || {};
      const logs = stats.logs || {};
      const today = logs.today || {};
      const trend = logs.trend || [];
      const sources = (logs.sources || []).slice(0, 6);

      let recent = [];
      try {
        const data = await API.get("/api/admin/logs?size=8");
        recent = data.items || [];
      } catch (err) {
        recent = [];
      }

      const cards =
        '<div class="grid c4">' +
          statCard("题库总量", UI.fmtNum(bank.questions), " 题", "今日新增 " + UI.fmtNum(bank.today_new || 0) + " 题", "database") +
          statCard("今日答题", UI.fmtNum(today.total), " 次", "累计 " + UI.fmtNum(logs.total || 0) + " 次（近 7 天）", "zap") +
          statCard("今日命中率", UI.fmtPct(today.hit_rate || 0), "", "平均响应 " + UI.fmtMs(today.avg_latency_ms || 0), "check") +
          statCard("今日 AI 调用", UI.fmtNum(today.ai || 0), " 次", "费用 " + UI.fmtMoney(today.cost_cny || 0), "cpu") +
        "</div>";

      const trendCard =
        '<div class="card">' +
          '<div class="card-head"><h3>近 7 天答题趋势</h3><span class="hint">总调用 / 其中 AI 回答</span></div>' +
          '<div class="card-body">' +
            UI.lineChart({
              labels: trend.map(function (t) { return String(t.day).slice(5); }),
              series: [
                { name: "总调用", values: trend.map(function (t) { return t.total || 0; }), color: "var(--accent)" },
                { name: "AI 回答", values: trend.map(function (t) { return t.ai || 0; }), color: "var(--purple)" },
              ],
              height: 190,
            }) +
            '<div class="legend" style="margin-top:10px">' +
              '<span><i style="background:var(--accent)"></i>总调用</span>' +
              '<span><i style="background:var(--purple)"></i>AI 回答</span>' +
            "</div>" +
          "</div>" +
        "</div>";

      const typeItems = Object.keys(TYPE_LABEL).map(function (key) {
        return { label: TYPE_LABEL[key], value: (bank.by_type || {})[key] || 0 };
      });

      const typeCard =
        '<div class="card">' +
          '<div class="card-head"><h3>题型分布</h3><span class="hint">共 ' + UI.fmtNum(bank.questions) + " 题</span></div>" +
          '<div class="card-body">' + UI.barChart({ items: typeItems }) + "</div>" +
        "</div>";

      const sourceCard =
        '<div class="card">' +
          '<div class="card-head"><h3>命中来源</h3><span class="hint">近 7 天</span></div>' +
          '<div class="card-body">' +
            (sources.length
              ? UI.barChart({
                  items: sources.map(function (s) {
                    return { label: SOURCE_LABEL[s.source] || s.source || "未知", value: s.count, color: s.source === "ai" ? "var(--purple)" : "var(--accent)" };
                  }),
                })
              : '<div class="empty">暂无答题记录</div>') +
          "</div>" +
        "</div>";

      const recentRows = recent
        .map(function (row) {
          const source = row.hit_source || (row.success ? "" : "");
          return (
            "<tr>" +
              '<td class="nowrap mono" style="font-size:11.5px;color:var(--muted)">' + UI.shortTime(row.ts) + "</td>" +
              '<td class="q-title"><div class="text">' + UI.escape(row.title) + "</div></td>" +
              '<td class="nowrap">' + (TYPE_LABEL[row.qtype] || row.qtype || "—") + "</td>" +
              '<td class="nowrap">' +
                (row.success
                  ? '<span class="badge ok">' + UI.escape(row.answer || "—") + "</span>"
                  : '<span class="badge err">失败</span>') +
              "</td>" +
              '<td class="nowrap"><span class="badge ' + (source === "ai" ? "purple" : "info") + '">' +
                UI.escape(SOURCE_LABEL[source] || source || "未命中") + "</span></td>" +
              '<td class="nowrap num">' + UI.fmtMs(row.latency_ms) + "</td>" +
            "</tr>"
          );
        })
        .join("");

      const recentCard =
        '<div class="card pad0">' +
          '<div class="card-head"><h3>最近答题</h3>' +
            '<a class="btn tiny ghost" href="#/logs">查看全部</a></div>' +
          '<div class="table-wrap"><table class="tbl"><thead><tr>' +
            "<th>时间</th><th>题目</th><th>题型</th><th>答案</th><th>来源</th><th>耗时</th>" +
          "</tr></thead><tbody>" +
            (recentRows || '<tr><td colspan="6"><div class="empty">还没有答题记录，去「答题测试」试试</div></td></tr>') +
          "</tbody></table></div>" +
        "</div>";

      const base = location.origin;
      const intro =
        '<div class="alert info">' +
          "<span><b>接入地址：</b>" +
          '<code class="mono">' + UI.escape(base) + "/search</code>（AutoCourse-DB 兼容） · " +
          '<code class="mono">' + UI.escape(base) + "/api/answer</code>（ocs-ai-answerer 兼容） · " +
          '<code class="mono">' + UI.escape(base) + "/api/search</code>（直接查询）" +
          '<br>把这段地址填进 OCS 的「题库配置」即可，详见 <a href="#/integration">接入方式</a>。</span>' +
        "</div>";

      root.innerHTML =
        '<div class="stack">' +
          intro +
          cards +
          '<div class="grid c2">' + trendCard + '<div class="stack">' + typeCard + sourceCard + "</div></div>" +
          recentCard +
        "</div>";
    },
  };
})();