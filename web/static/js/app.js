/* ==========================================================================
   应用外壳：路由 / 健康检查 / 主题
   ========================================================================== */
(function () {
  "use strict";

  const ROUTES = [
    "dashboard",
    "questions",
    "models",
    "settings",
    "playground",
    "logs",
    "integration",
    "about",
  ];

  const App = {
    route: "dashboard",
    health: null,
    state: {},
  };

  function currentRoute() {
    const raw = (location.hash || "").replace(/^#\/?/, "").split("?")[0];
    return ROUTES.indexOf(raw) >= 0 ? raw : "dashboard";
  }

  function setActiveNav(route) {
    document.querySelectorAll(".nav-item").forEach(function (item) {
      item.classList.toggle("active", item.dataset.page === route);
    });
  }

  async function render() {
    const route = currentRoute();
    App.route = route;
    setActiveNav(route);
    const page = window.Pages[route];
    const content = document.getElementById("content");
    const titleNode = document.getElementById("page-title");
    const subNode = document.getElementById("page-sub");
    const actionsNode = document.getElementById("topbar-actions");

    titleNode.textContent = (page && page.title) || route;
    subNode.textContent = (page && page.sub) || "";
    actionsNode.innerHTML = (page && page.actions) || "";
    UI.fillIcons(actionsNode);
    content.innerHTML = '<div class="loading"><span class="spinner"></span> 加载中…</div>';

    if (!page) {
      content.innerHTML = '<div class="empty">页面不存在</div>';
      return;
    }
    try {
      await page.render(content, App);
      UI.fillIcons(content);
    } catch (err) {
      content.innerHTML =
        '<div class="alert err"><span>' + UI.escape(err.message || String(err)) + "</span></div>";
      UI.toast(err.message || String(err), "err");
    }
  }

  /* ---------------------------------------------------------------- 健康 */
  async function pollHealth() {
    const dot = document.getElementById("health-dot");
    const text = document.getElementById("health-text");
    const version = document.getElementById("version");
    try {
      const data = await API.get("/api/v1/health");
      App.health = data;
      dot.className = "dot ok";
      text.textContent =
        (data.course || "未选题库") + " · " + (data.models || 0) + " 模型" + (data.ai_enabled ? "" : " · AI 关闭");
      version.textContent = "v" + (data.version || "—");
    } catch (err) {
      dot.className = "dot err";
      text.textContent = "服务未连接";
    }
  }

  /* ---------------------------------------------------------------- 主题 */
  const THEME_KEY = "ocs-hub-theme";

  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    const label = document.getElementById("theme-label");
    const ico = document.querySelector("#theme-toggle [data-icon]");
    if (label) label.textContent = theme === "dark" ? "暗色" : "亮色";
    if (ico) {
      ico.dataset.icon = theme === "dark" ? "moon" : "sun";
      ico.dataset.filled = "";
      UI.fillIcons(document.getElementById("theme-toggle"));
    }
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch (err) {
      /* 隐私模式下忽略 */
    }
  }

  function initTheme() {
    let saved = null;
    try {
      saved = localStorage.getItem(THEME_KEY);
    } catch (err) {
      saved = null;
    }
    applyTheme(saved === "light" ? "light" : "dark");
    const btn = document.getElementById("theme-toggle");
    if (btn) {
      btn.addEventListener("click", function () {
        applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
      });
    }
  }

  /* ---------------------------------------------------------------- 启动 */
  function boot() {
    UI.fillIcons(document);
    initTheme();
    if (!location.hash) location.hash = "#/dashboard";
    window.addEventListener("hashchange", render);
    render();
    pollHealth();
    setInterval(pollHealth, 20000);
  }

  window.App = App;
  window.AppRender = render;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();