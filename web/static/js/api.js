/* ==========================================================================
   基础工具层：图标 / 请求 / 提示 / 弹窗 / 图表
   —— 无任何外部依赖
   ========================================================================== */
(function () {
  "use strict";

  const ICONS = {
    grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    book: '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5z"/><path d="M4 20.5V5.5"/>',
    cpu: '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/>',
    sliders: '<path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2.2"/><circle cx="9" cy="17" r="2.2"/>',
    flask: '<path d="M9 3h6M10 3v6L4.8 18A2 2 0 0 0 6.6 21h10.8a2 2 0 0 0 1.8-3L14 9V3"/><path d="M7.5 14h9"/>',
    list: '<path d="M8 6h13M8 12h13M8 18h13"/><circle cx="3.5" cy="6" r="1"/><circle cx="3.5" cy="12" r="1"/><circle cx="3.5" cy="18" r="1"/>',
    plug: '<path d="M9 3v6M15 3v6"/><path d="M7 9h10v3a5 5 0 0 1-10 0z"/><path d="M12 17v4"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 10.5V17M12 7.4v.2"/>',
    moon: '<path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M19.1 4.9l-1.8 1.8M6.7 17.3l-1.8 1.8"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    upload: '<path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>',
    download: '<path d="M12 4v12M7 11l5 5 5-5"/><path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>',
    trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
    edit: '<path d="M4 20h4L20 8l-4-4L4 16z"/>',
    check: '<path d="M4 12.5l5 5L20 6.5"/>',
    refresh: '<path d="M20 12a8 8 0 1 1-2.5-5.8"/><path d="M20 4v5h-5"/>',
    play: '<path d="M7 4l13 8-13 8z"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="M16.5 16.5L21 21"/>',
    copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h8"/>',
    zap: '<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>',
    spark: '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M18.5 15.5l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z"/>',
    database: '<ellipse cx="12" cy="5.5" rx="8" ry="3"/><path d="M4 5.5v13c0 1.7 3.6 3 8 3s8-1.3 8-3v-13"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
  };

  function icon(name, cls) {
    const body = ICONS[name] || ICONS.info;
    return (
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" ' +
      'stroke-linecap="round" stroke-linejoin="round"' + (cls ? ' class="' + cls + '"' : "") + ">" +
      body + "</svg>"
    );
  }

  function fillIcons(root) {
    (root || document).querySelectorAll("[data-icon]").forEach(function (node) {
      if (node.dataset.filled) return;
      node.innerHTML = icon(node.dataset.icon);
      node.dataset.filled = "1";
    });
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  /* ------------------------------------------------------------- 请求层 */
  async function request(path, options) {
    const opts = Object.assign({ method: "GET", headers: {} }, options || {});
    if (opts.body !== undefined && !(opts.body instanceof FormData)) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(opts.body);
    }
    let resp;
    try {
      resp = await fetch(path, opts);
    } catch (err) {
      throw new Error("无法连接到本地服务，请确认程序仍在运行");
    }
    let payload = null;
    const text = await resp.text();
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch (err) {
        payload = null;
      }
    }
    if (payload && typeof payload.ok === "boolean") {
      if (!payload.ok) throw new Error(payload.error || "请求失败（" + resp.status + "）");
      return payload.data;
    }
    if (!resp.ok) {
      throw new Error((payload && (payload.error || payload.msg)) || "请求失败（" + resp.status + "）");
    }
    return payload;
  }

  const API = {
    request: request,
    get: function (path) { return request(path, { method: "GET" }); },
    post: function (path, body) { return request(path, { method: "POST", body: body === undefined ? {} : body }); },
    put: function (path, body) { return request(path, { method: "PUT", body: body || {} }); },
    del: function (path) { return request(path, { method: "DELETE" }); },
  };

  /* ------------------------------------------------------------- Toast */
  let toastTimer = null;
  function toast(message, kind) {
    const wrap = document.getElementById("toast-wrap");
    if (!wrap) return;
    const node = document.createElement("div");
    node.className = "toast " + (kind || "");
    node.textContent = message;
    wrap.appendChild(node);
    setTimeout(function () {
      node.style.opacity = "0";
      node.style.transition = "opacity .2s";
      setTimeout(function () { node.remove(); }, 220);
    }, kind === "err" ? 4200 : 2600);
    if (wrap.children.length > 4) wrap.firstElementChild.remove();
  }

  /* ------------------------------------------------------------- 弹窗 */
  const modalRoot = function () { return document.getElementById("modal-root"); };

  function openModal(cfg) {
    const root = modalRoot();
    root.innerHTML =
      '<div class="modal' + (cfg.wide ? " wide" : "") + '" role="dialog" aria-modal="true">' +
        '<div class="modal-head"><h3>' + escapeHtml(cfg.title || "") + "</h3>" +
          '<button class="icon-btn" data-close="1" aria-label="关闭">×</button></div>' +
        '<div class="modal-body">' + (cfg.body || "") + "</div>" +
        (cfg.footer ? '<div class="modal-foot">' + cfg.footer + "</div>" : "") +
      "</div>";
    root.hidden = false;
    root.onclick = function (event) {
      if (event.target === root || event.target.closest("[data-close]")) closeModal();
    };
    fillIcons(root);
    if (typeof cfg.onMount === "function") cfg.onMount(root);
    return root;
  }

  function closeModal() {
    const root = modalRoot();
    if (!root) return;
    root.hidden = true;
    root.innerHTML = "";
  }

  function confirmDialog(message, onOk, okLabel) {
    openModal({
      title: "确认操作",
      body: '<p style="margin:0">' + escapeHtml(message) + "</p>",
      footer:
        '<button class="btn" data-close="1">取消</button>' +
        '<button class="btn danger" id="confirm-ok">' + escapeHtml(okLabel || "确定") + "</button>",
      onMount: function (root) {
        root.querySelector("#confirm-ok").onclick = async function () {
          closeModal();
          try {
            await onOk();
          } catch (err) {
            toast(err.message, "err");
          }
        };
      },
    });
  }

  /* ------------------------------------------------------------- 格式化 */
  function fmtNum(value) {
    const n = Number(value);
    if (!isFinite(n)) return "0";
    return n.toLocaleString("zh-CN");
  }

  function fmtMs(value) {
    const n = Number(value) || 0;
    if (n < 1000) return n + " ms";
    return (n / 1000).toFixed(n < 10000 ? 2 : 1) + " s";
  }

  function fmtPct(value, digits) {
    const n = Number(value) || 0;
    return (n * 100).toFixed(digits === undefined ? 1 : digits) + "%";
  }

  function fmtMoney(value) {
    const n = Number(value) || 0;
    if (n === 0) return "¥0";
    return "¥" + (n < 0.01 ? n.toFixed(4) : n.toFixed(2));
  }

  function shortTime(value) {
    if (!value) return "—";
    return String(value).replace(/^\d{4}-/, "").slice(0, 14);
  }

  /* ------------------------------------------------------------- 图表 */
  function emptyChart(width, height) {
    return (
      '<svg class="chart" viewBox="0 0 ' + width + " " + height + '" preserveAspectRatio="none">' +
      '<line class="axis" x1="0" y1="' + (height - 1) + '" x2="' + width + '" y2="' + (height - 1) + '"/></svg>'
    );
  }

  /**
   * 折线/面积图
   * @param {Object} cfg { labels:[], series:[{name, values:[], color}], height }
   */
  function lineChart(cfg) {
    const labels = cfg.labels || [];
    const series = (cfg.series || []).filter(function (s) { return s.values && s.values.length; });
    const height = cfg.height || 180;
    const width = 640;
    const pad = { l: 30, r: 12, t: 12, b: 22 };
    if (!labels.length || !series.length) return emptyChart(width, height);

    let max = 0;
    series.forEach(function (s) {
      s.values.forEach(function (v) { max = Math.max(max, Number(v) || 0); });
    });
    max = max <= 0 ? 1 : max;
    const niceMax = Math.ceil(max / 5) * 5 || 5;

    const iw = width - pad.l - pad.r;
    const ih = height - pad.t - pad.b;
    const stepX = labels.length > 1 ? iw / (labels.length - 1) : 0;
    const xAt = function (i) { return pad.l + (labels.length > 1 ? i * stepX : iw / 2); };
    const yAt = function (v) { return pad.t + ih - (Number(v) / niceMax) * ih; };

    let svg = '<svg class="chart" viewBox="0 0 ' + width + " " + height + '" preserveAspectRatio="none">';
    for (let i = 0; i <= 4; i++) {
      const y = pad.t + (ih / 4) * i;
      const v = Math.round(niceMax - (niceMax / 4) * i);
      svg += '<line class="gl" x1="' + pad.l + '" y1="' + y + '" x2="' + (width - pad.r) + '" y2="' + y + '"/>';
      svg += '<text class="lbl" x="4" y="' + (y + 3.5) + '">' + v + "</text>";
    }

    series.forEach(function (s, si) {
      const color = s.color || (si === 0 ? "var(--accent)" : "var(--purple)");
      const pts = s.values.map(function (v, i) { return xAt(i) + "," + yAt(v); });
      if (cfg.area !== false && si === 0) {
        svg += '<polygon class="area" points="' +
          [pad.l + "," + (pad.t + ih)].concat(pts).concat([(pad.l + iw) + "," + (pad.t + ih)]).join(" ") + '"/>';
      }
      svg += '<polyline points="' + pts.join(" ") + '" fill="none" stroke="' + color + '" stroke-width="2" ' +
        'stroke-linejoin="round" stroke-linecap="round"/>';
      s.values.forEach(function (v, i) {
        svg += '<circle cx="' + xAt(i) + '" cy="' + yAt(v) + '" r="2.6" fill="' + color + '"/>';
      });
    });

    labels.forEach(function (label, i) {
      if (labels.length > 8 && i % 2) return;
      svg += '<text class="lbl" x="' + xAt(i) + '" y="' + (height - 5) + '" text-anchor="middle">' +
        escapeHtml(label) + "</text>";
    });
    return svg + "</svg>";
  }

  /**
   * 横向条形图（用于题型分布等）
   * @param {Object} cfg { items:[{label, value}], height }
   */
  function barChart(cfg) {
    const items = cfg.items || [];
    if (!items.length) return emptyChart(640, 140);
    const max = Math.max.apply(null, items.map(function (i) { return Number(i.value) || 0; }).concat([1]));
    return items
      .map(function (item) {
        const pct = Math.round(((Number(item.value) || 0) / max) * 100);
        return (
          '<div class="row" style="gap:10px;margin:7px 0">' +
            '<span style="width:64px;font-size:12.5px;color:var(--muted)">' + escapeHtml(item.label) + "</span>" +
            '<div style="flex:1;height:10px;border-radius:99px;background:var(--panel-2);overflow:hidden">' +
              '<div style="width:' + pct + '%;height:100%;border-radius:99px;background:' +
                (item.color || "var(--accent)") + '"></div>' +
            "</div>" +
            '<span class="mono" style="width:52px;text-align:right;font-size:12.5px">' +
              fmtNum(item.value) + "</span>" +
          "</div>"
        );
      })
      .join("");
  }

  /* ------------------------------------------------------------- 剪贴板 */
  async function copyText(text) {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
      } else {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        ta.remove();
      }
      toast("已复制到剪贴板", "ok");
    } catch (err) {
      toast("复制失败，请手动选中复制", "err");
    }
  }

  function codeBlock(code, langLabel) {
    const id = "code-" + Math.random().toString(36).slice(2, 8);
    return (
      '<div><div class="code-head"><span>' + escapeHtml(langLabel || "") + "</span>" +
        '<button class="btn tiny ghost" data-copy="' + id + '">复制</button></div>' +
        '<pre class="code" id="' + id + '">' + escapeHtml(code) + "</pre></div>"
    );
  }

  document.addEventListener("click", function (event) {
    const btn = event.target.closest("[data-copy]");
    if (!btn) return;
    const node = document.getElementById(btn.dataset.copy);
    if (node) copyText(node.textContent);
  });

  /* 顶栏动作按钮（actions 区不在页面容器内，需单独取） */
  function act(id) {
    return document.querySelector('#topbar-actions [id="' + id + '"]');
  }

  window.UI = {
    icon: icon,
    fillIcons: fillIcons,
    act: act,
    escape: escapeHtml,
    toast: toast,
    modal: openModal,
    closeModal: closeModal,
    confirm: confirmDialog,
    fmtNum: fmtNum,
    fmtMs: fmtMs,
    fmtPct: fmtPct,
    fmtMoney: fmtMoney,
    shortTime: shortTime,
    lineChart: lineChart,
    barChart: barChart,
    copyText: copyText,
    codeBlock: codeBlock,
  };
  window.API = API;
  window.Pages = window.Pages || {};
})();