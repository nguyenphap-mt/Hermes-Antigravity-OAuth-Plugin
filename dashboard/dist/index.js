/**
 * Hermes Antigravity OAuth & Google Flow Suite — Cockpit Dashboard
 *
 * Comprehensive Multi-AI Provider Management:
 * 1. Antigravity OAuth Multi-Account Pool & 4 Rotation Strategies.
 * 2. 32+ Dynamic Model Catalog & Live Quota Telemetry (Gemini, Claude, GPT-OSS).
 * 3. Google Flow Veo 3.1 & Omni 1.1 Video Studio (1-Click Handshake, 5 Tiers).
 * 4. Gemini 3.1 Flash AI Image Gen Playground & Aspect Ratio Config.
 * 5. System Doctor Diagnostics (6-Point Health Suite) & Live Daemon Controller.
 *
 * Architecture & Design:
 * - Built on window.__HERMES_PLUGIN_SDK__ (Host React + Nous DS + fetchJSON).
 * - Taste-Skill Anti-Slop: Pure SVG vector icons, obsidian cyber-lab theme, 0 emojis.
 * - Dual-Mode: Full Tab (/antigravity) + Settings Slot Widget (settings:providers).
 */
(function () {
  "use strict";

  var SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK || !window.__HERMES_PLUGINS__) {
    console.warn("[Antigravity] Plugin SDK not found on window.");
    return;
  }

  var React = SDK.React;
  var h = React.createElement;
  var useState = SDK.hooks.useState;
  var useEffect = SDK.hooks.useEffect;
  var useCallback = SDK.hooks.useCallback;
  var useRef = SDK.hooks.useRef;
  var useToast = SDK.hooks.useToast;

  var API_BASE = "/api/plugins/antigravity";

  // Safe API helper using host fetchJSON
  function apiFetch(endpoint, options) {
    var url = API_BASE + endpoint;
    if (SDK.fetchJSON) {
      return SDK.fetchJSON(url, options);
    }
    return fetch(url, options).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    });
  }

  // Self-contained CSS injection so dynamic plugin elements never rely on missing Tailwind JIT rules
  function ensureCockpitStyles() {
    if (typeof document === "undefined") return;
    if (document.getElementById("ag-cockpit-inline-css")) return;
    var styleEl = document.createElement("style");
    styleEl.id = "ag-cockpit-inline-css";
    styleEl.textContent = [
      ".ag-cockpit-root{color:#f4f4f5;max-width:1152px;margin:0 auto;padding:12px;box-sizing:border-box;}",
      "@media(min-width:768px){.ag-cockpit-root{padding:24px;}}",
      ".ag-card{background:#0e1118 !important;border:1px solid rgba(255,255,255,0.08) !important;border-radius:16px !important;padding:18px !important;box-shadow:0 10px 30px -10px rgba(0,0,0,0.6) !important;}",
      "@media(min-width:640px){.ag-card{padding:24px !important;}}",
      ".ag-subcard{background:#090a0f !important;border:1px solid rgba(255,255,255,0.07) !important;border-radius:14px !important;padding:16px !important;transition:border-color .2s ease,box-shadow .2s ease;}",
      ".ag-subcard:hover{border-color:rgba(255,255,255,0.16) !important;}",
      ".ag-subcard-active{background:linear-gradient(180deg,rgba(16,185,129,0.06) 0%,#090a0f 100%) !important;border:1px solid rgba(16,185,129,0.45) !important;box-shadow:0 4px 20px -4px rgba(16,185,129,0.12) !important;}",
      ".ag-subcard-disabled{background:#08090d !important;border:1px solid rgba(239,68,68,0.28) !important;opacity:0.85;}",
      ".ag-btn{display:inline-flex !important;align-items:center !important;justify-content:center !important;gap:6px !important;padding:8px 14px !important;border-radius:10px !important;font-size:12px !important;font-weight:600 !important;line-height:1.2 !important;white-space:nowrap !important;cursor:pointer !important;transition:all .18s ease !important;text-decoration:none !important;box-sizing:border-box !important;}",
      ".ag-btn:disabled{opacity:0.5 !important;cursor:not-allowed !important;}",
      ".ag-btn-primary{background:linear-gradient(135deg,#059669 0%,#0d9488 100%) !important;color:#fff !important;border:1px solid rgba(52,211,153,0.35) !important;box-shadow:0 4px 14px rgba(5,150,105,0.3) !important;}",
      ".ag-btn-primary:hover:not(:disabled){background:linear-gradient(135deg,#10b981 0%,#14b8a6 100%) !important;}",
      ".ag-btn-secondary{background:#141822 !important;color:#e4e4e7 !important;border:1px solid #27272a !important;}",
      ".ag-btn-secondary:hover:not(:disabled){background:#1d2332 !important;border-color:#3f3f46 !important;color:#fff !important;}",
      ".ag-btn-amber{background:rgba(120,53,15,0.35) !important;color:#fcd34d !important;border:1px solid rgba(217,119,6,0.45) !important;}",
      ".ag-btn-amber:hover:not(:disabled){background:rgba(146,64,14,0.5) !important;border-color:rgba(245,158,11,0.65) !important;}",
      ".ag-btn-danger{background:rgba(127,29,29,0.3) !important;color:#f87171 !important;border:1px solid rgba(239,68,68,0.35) !important;}",
      ".ag-btn-danger:hover:not(:disabled){background:rgba(153,27,27,0.45) !important;}",
      ".ag-btn-sm{padding:5px 10px !important;border-radius:8px !important;font-size:11px !important;gap:5px !important;}",
      ".ag-btn-icon{display:inline-flex !important;align-items:center !important;justify-content:center !important;width:34px !important;height:34px !important;padding:0 !important;border-radius:10px !important;flex-shrink:0 !important;cursor:pointer !important;}",
      ".ag-tabs-grid{display:grid !important;grid-template-columns:repeat(2,minmax(0,1fr)) !important;gap:8px !important;margin-bottom:20px !important;padding-bottom:12px !important;border-bottom:1px solid rgba(255,255,255,0.08) !important;}",
      "@media(min-width:640px){.ag-tabs-grid{display:flex !important;flex-wrap:nowrap !important;gap:10px !important;}}",
      ".ag-tab-btn{display:inline-flex !important;align-items:center !important;justify-content:center !important;gap:8px !important;padding:10px 14px !important;border-radius:12px !important;font-size:12px !important;font-weight:600 !important;white-space:nowrap !important;background:#0e1118 !important;color:#a1a1aa !important;border:1px solid rgba(255,255,255,0.07) !important;cursor:pointer !important;transition:all .18s ease !important;}",
      ".ag-tab-btn:hover{color:#f4f4f5 !important;border-color:rgba(255,255,255,0.18) !important;}",
      ".ag-tab-btn-active{background:rgba(16,185,129,0.14) !important;color:#34d399 !important;border:1px solid rgba(16,185,129,0.4) !important;box-shadow:0 2px 12px rgba(16,185,129,0.12) !important;}",
      ".ag-badge{display:inline-flex !important;align-items:center !important;gap:5px !important;padding:3px 9px !important;border-radius:9999px !important;font-size:10px !important;font-weight:700 !important;font-family:monospace !important;white-space:nowrap !important;line-height:1.3 !important;}",
      ".ag-badge-emerald{background:rgba(16,185,129,0.14) !important;color:#34d399 !important;border:1px solid rgba(16,185,129,0.35) !important;}",
      ".ag-badge-red{background:rgba(127,29,29,0.5) !important;color:#f87171 !important;border:1px solid rgba(239,68,68,0.45) !important;}",
      ".ag-badge-amber{background:rgba(120,53,15,0.45) !important;color:#fbbf24 !important;border:1px solid rgba(245,158,11,0.4) !important;}",
      ".ag-badge-neutral{background:#141822 !important;color:#a1a1aa !important;border:1px solid #27272a !important;}",
      ".ag-avatar{width:36px !important;height:36px !important;border-radius:10px !important;display:flex !important;align-items:center !important;justify-content:center !important;font-weight:700 !important;font-size:13px !important;flex-shrink:0 !important;}",
      ".ag-avatar-active{background:linear-gradient(135deg,#059669,#0d9488) !important;color:#fff !important;box-shadow:0 2px 10px rgba(16,185,129,0.3) !important;}",
      ".ag-avatar-ready{background:#181c26 !important;color:#34d399 !important;border:1px solid rgba(16,185,129,0.3) !important;}",
      ".ag-avatar-disabled{background:rgba(127,29,29,0.35) !important;color:#f87171 !important;border:1px solid rgba(239,68,68,0.35) !important;}",
      ".ag-modal-backdrop{position:fixed !important;top:0 !important;left:0 !important;right:0 !important;bottom:0 !important;z-index:9999 !important;background:rgba(3,5,8,0.85) !important;backdrop-filter:blur(6px) !important;-webkit-backdrop-filter:blur(6px) !important;display:flex !important;align-items:center !important;justify-content:center !important;padding:16px !important;overflow-y:auto !important;}",
      ".ag-modal-dialog{background:#0e1118 !important;border:1px solid rgba(16,185,129,0.35) !important;border-radius:18px !important;width:100% !important;max-width:520px !important;padding:20px !important;box-shadow:0 25px 60px -15px rgba(0,0,0,0.85),0 0 30px rgba(16,185,129,0.1) !important;box-sizing:border-box !important;}",
      ".ag-input,.ag-select,.ag-textarea{background:#090a0f !important;border:1px solid #27272a !important;border-radius:10px !important;color:#f4f4f5 !important;font-size:12px !important;padding:8px 12px !important;outline:none !important;transition:border-color .15s ease !important;box-sizing:border-box !important;}",
      ".ag-input:focus,.ag-select:focus,.ag-textarea:focus{border-color:#10b981 !important;}",
      ".ag-cockpit-root svg{flex-shrink:0;}",
      ".w-3{width:12px !important;}.h-3{height:12px !important;}.w-3\\.5{width:14px !important;}.h-3\\.5{height:14px !important;}.w-4{width:16px !important;}.h-4{height:16px !important;}.w-5{width:20px !important;}.h-5{height:20px !important;}.w-6{width:24px !important;}.h-6{height:24px !important;}",
      "@keyframes ag-led-blink{0%,100%{opacity:1;transform:scale(1);}50%{opacity:.45;transform:scale(.9);}}",
      ".ag-led-pulse{animation:ag-led-blink 2.2s infinite ease-in-out;}"
    ].join("\n");
    document.head.appendChild(styleEl);
  }
  ensureCockpitStyles();

  // ---------------------------------------------------------------------------
  // Vector Icons (High-End Anti-Slop, Pure SVG, Zero Emojis)
  // ---------------------------------------------------------------------------
  function Icon(props) {
    var name = props.name;
    var cls = props.className || "w-4 h-4";
    var strokeWidth = props.strokeWidth || 2;
    var p = {
      viewBox: "0 0 24 24",
      fill: "none",
      stroke: "currentColor",
      strokeWidth: strokeWidth,
      strokeLinecap: "round",
      strokeLinejoin: "round",
      className: cls,
    };

    switch (name) {
      case "zap":
        return h("svg", p, h("polygon", { points: "13 2 3 14 12 14 11 22 21 10 12 10 13 2" }));
      case "server":
        return h("svg", p,
          h("rect", { width: 20, height: 8, x: 2, y: 2, rx: 2, ry: 2 }),
          h("rect", { width: 20, height: 8, x: 2, y: 14, rx: 2, ry: 2 }),
          h("line", { x1: 6, x2: 6.01, y1: 6, y2: 6 }),
          h("line", { x1: 6, x2: 6.01, y1: 18, y2: 18 })
        );
      case "shield":
        return h("svg", p, h("path", { d: "M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" }));
      case "video":
        return h("svg", p,
          h("path", { d: "m16 13 5.223 3.482a.5.5 0 0 0 .777-.416V7.934a.5.5 0 0 0-.777-.416L16 11" }),
          h("rect", { width: 14, height: 12, x: 2, y: 6, rx: 2 })
        );
      case "image":
        return h("svg", p,
          h("rect", { width: 18, height: 18, x: 3, y: 3, rx: 2, ry: 2 }),
          h("circle", { cx: 9, cy: 9, r: 2 }),
          h("path", { d: "m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21" })
        );
      case "activity":
        return h("svg", p, h("path", { d: "M22 12h-4l-3 9L9 3l-3 9H2" }));
      case "refresh":
        return h("svg", p,
          h("path", { d: "M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" }),
          h("path", { d: "M3 3v5h5" }),
          h("path", { d: "M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" }),
          h("path", { d: "M16 16h5v5" })
        );
      case "play":
        return h("svg", p, h("polygon", { points: "6 3 20 12 6 21 6 3" }));
      case "square":
        return h("svg", p, h("rect", { width: 18, height: 18, x: 3, y: 3, rx: 2 }));
      case "rotate":
        return h("svg", p,
          h("path", { d: "M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8" }),
          h("path", { d: "M21 3v5h-5" })
        );
      case "check":
        return h("svg", p, h("path", { d: "M20 6 9 17l-5-5" }));
      case "alert":
        return h("svg", p,
          h("path", { d: "m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" }),
          h("line", { x1: 12, x2: 12, y1: 9, y2: 13 }),
          h("line", { x1: 12, x2: 12.01, y1: 17, y2: 17 })
        );
      case "user":
        return h("svg", p,
          h("path", { d: "M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" }),
          h("circle", { cx: 12, cy: 7, r: 4 })
        );
      case "key":
        return h("svg", p,
          h("circle", { cx: 7.5, cy: 15.5, r: 5.5 }),
          h("path", { d: "m21 2-9.6 9.6" }),
          h("path", { d: "m15.5 7.5 3 3L22 7l-3-3" })
        );
      case "trash":
        return h("svg", p,
          h("path", { d: "M3 6h18" }),
          h("path", { d: "M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" }),
          h("path", { d: "M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" })
        );
      case "terminal":
        return h("svg", p,
          h("polyline", { points: "4 17 10 11 4 5" }),
          h("line", { x1: 12, x2: 20, y1: 19, y2: 19 })
        );
      case "sparkles":
        return h("svg", p,
          h("path", { d: "m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z" })
        );
      case "search":
        return h("svg", p,
          h("circle", { cx: 11, cy: 11, r: 8 }),
          h("path", { d: "m21 21-4.3-4.3" })
        );
      case "film":
        return h("svg", p,
          h("rect", { width: 20, height: 20, x: 2, y: 2, rx: 2.18 }),
          h("line", { x1: 7, x2: 7, y1: 2, y2: 22 }),
          h("line", { x1: 17, x2: 17, y1: 2, y2: 22 }),
          h("line", { x1: 2, x2: 22, y1: 12, y2: 12 }),
          h("line", { x1: 2, x2: 7, y1: 7, y2: 7 }),
          h("line", { x1: 2, x2: 7, y1: 17, y2: 17 }),
          h("line", { x1: 17, x2: 22, y1: 7, y2: 7 }),
          h("line", { x1: 17, x2: 22, y1: 17, y2: 17 })
        );
      default:
        return h("svg", p, h("circle", { cx: 12, cy: 12, r: 10 }));
    }
  }

  // ---------------------------------------------------------------------------
  // Main Cockpit Component
  // ---------------------------------------------------------------------------
  function AntigravityCockpit() {
    var activeTabState = useState("oauth");
    var activeTab = activeTabState[0];
    var setActiveTab = activeTabState[1];

    var toastObj = useToast ? useToast() : null;
    function notify(msg, type) {
      if (toastObj && toastObj.showToast) {
        toastObj.showToast(msg, type || "info");
      } else {
        console.log("[" + (type || "info") + "] " + msg);
      }
    }

    // Daemon state
    var daemonState = useState({ running: false, port: 8100, uptime_seconds: null, pid: null });
    var daemon = daemonState[0];
    var setDaemon = daemonState[1];
    var daemonLoadingState = useState(false);
    var daemonLoading = daemonLoadingState[0];
    var setDaemonLoading = daemonLoadingState[1];

    var fetchDaemon = useCallback(function () {
      apiFetch("/daemon/status").then(function (res) {
        setDaemon(res);
      }).catch(function (e) {
        console.debug("Daemon check error:", e);
      });
    }, []);

    useEffect(function () {
      fetchDaemon();
      var interval = setInterval(fetchDaemon, 4000);
      return function () { clearInterval(interval); };
    }, [fetchDaemon]);

    function handleDaemonControl(action) {
      setDaemonLoading(true);
      apiFetch("/daemon/control", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: action }),
      }).then(function (res) {
        setDaemon(res.status);
        notify(res.message, res.ok ? "success" : "error");
      }).catch(function (e) {
        notify("Lỗi điều khiển daemon: " + e.message, "error");
      }).finally(function () {
        setDaemonLoading(false);
      });
    }

    // -------------------------------------------------------------------------
    // Top Bar Telemetry Header
    // -------------------------------------------------------------------------
    var headerNode = h("div", {
      className: "ag-card mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4",
    }, [
      // Left identity
      h("div", { className: "flex items-center gap-3.5", key: "ident" }, [
        h("div", {
          className: "ag-avatar ag-avatar-active",
          style: { width: "44px", height: "44px", borderRadius: "12px" },
        }, h(Icon, { name: "zap", className: "w-5 h-5" })),
        h("div", { style: { minWidth: 0 } }, [
          h("div", { className: "flex flex-wrap items-center gap-2" }, [
            h("h1", { className: "text-base sm:text-lg font-bold text-white tracking-tight" }, "Antigravity & Google Flow Suite"),
            h("span", {
              className: "ag-badge ag-badge-emerald",
            }, "v3.1.0 Enterprise"),
          ]),
          h("p", { className: "text-xs text-zinc-400 mt-1" },
            "Buồng lái quản trị Google Antigravity OAuth, 32+ Models, Sinh ảnh & Veo 3.1 Video"
          ),
        ]),
      ]),

      // Right Daemon Telemetry & Controls
      h("div", { className: "flex flex-wrap items-center gap-2", key: "controls" }, [
        // Daemon pill
        h("div", {
          className: "ag-badge " + (daemon.running ? "ag-badge-emerald" : "ag-badge-neutral"),
          style: { padding: "6px 12px", fontSize: "11px" },
        }, [
          h("span", {
            className: "w-2 h-2 rounded-full " + (daemon.running ? "bg-emerald-400 ag-led-pulse" : "bg-zinc-500"),
            style: { display: "inline-block", width: "8px", height: "8px", borderRadius: "9999px" },
          }),
          h("span", null, daemon.running ? "PROXY :8100 [ONLINE]" : "PROXY [STANDBY]"),
          daemon.pid && h("span", { style: { opacity: 0.75, marginLeft: "4px" } },
            "• PID " + daemon.pid
          ),
        ]),

        // Action buttons
        daemon.running
          ? h("div", { className: "flex items-center gap-1.5", key: "act-run" }, [
              h("button", {
                disabled: daemonLoading,
                onClick: function () { handleDaemonControl("restart"); },
                className: "ag-btn ag-btn-secondary ag-btn-icon",
                title: "Khởi động lại Bridge Daemon",
              }, h(Icon, { name: "rotate", className: "w-3.5 h-3.5" })),
              h("button", {
                disabled: daemonLoading,
                onClick: function () { handleDaemonControl("stop"); },
                className: "ag-btn ag-btn-danger ag-btn-icon",
                title: "Dừng Bridge Daemon",
              }, h(Icon, { name: "square", className: "w-3.5 h-3.5" })),
            ])
          : h("button", {
              disabled: daemonLoading,
              onClick: function () { handleDaemonControl("start"); },
              className: "ag-btn ag-btn-primary",
              key: "act-start",
            }, [
              h(Icon, { name: "play", className: "w-3.5 h-3.5" }),
              h("span", null, "Kích hoạt Daemon"),
            ]),

        h("button", {
          onClick: function () { fetchDaemon(); notify("Đã làm mới telemetry", "success"); },
          className: "ag-btn ag-btn-secondary ag-btn-icon",
          title: "Làm mới dữ liệu",
        }, h(Icon, { name: "refresh", className: "w-4 h-4" })),
      ]),
    ]);

    // -------------------------------------------------------------------------
    // Tabs Navigation Bar (2x2 Grid on Mobile, Single Row on Desktop)
    // -------------------------------------------------------------------------
    var tabs = [
      { id: "oauth", label: "OAuth & Models", icon: "shield", count: null },
      { id: "flow", label: "Google Flow Video", icon: "video", count: null },
      { id: "image", label: "Image Gen Studio", icon: "image", count: null },
      { id: "doctor", label: "Doctor & Logs", icon: "activity", count: null },
    ];

    var navNode = h("div", {
      className: "ag-tabs-grid",
      key: "tabs-nav",
    }, tabs.map(function (tab) {
      var isActive = activeTab === tab.id;
      return h("button", {
        key: tab.id,
        onClick: function () { setActiveTab(tab.id); },
        className: "ag-tab-btn " + (isActive ? "ag-tab-btn-active" : ""),
      }, [
        h(Icon, { name: tab.icon, className: "w-4 h-4" }),
        h("span", null, tab.label),
      ]);
    }));

    // -------------------------------------------------------------------------
    // Tab Content Switcher
    // -------------------------------------------------------------------------
    var contentNode;
    if (activeTab === "oauth") {
      contentNode = h(TabOAuthAndModels, { notify: notify, daemonRunning: daemon.running });
    } else if (activeTab === "flow") {
      contentNode = h(TabGoogleFlow, { notify: notify });
    } else if (activeTab === "image") {
      contentNode = h(TabImageGen, { notify: notify });
    } else if (activeTab === "doctor") {
      contentNode = h(TabDoctorAndLogs, { notify: notify, fetchDaemon: fetchDaemon });
    }

    return h("div", { className: "ag-cockpit-root max-w-6xl mx-auto p-4 md:p-6" }, [
      headerNode,
      navNode,
      contentNode,
    ]);
  }

  // ===========================================================================
  // TAB 1: OAUTH & MODEL CATALOG
  // ===========================================================================
  function TabOAuthAndModels(props) {
    var notify = props.notify;
    var accountsState = useState([]);
    var accounts = accountsState[0];
    var setAccounts = accountsState[1];

    var poolInfoState = useState({ strategy: "fill_first", active_email: null, mode: "" });
    var poolInfo = poolInfoState[0];
    var setPoolInfo = poolInfoState[1];

    var modelsState = useState([]);
    var models = modelsState[0];
    var setModels = modelsState[1];

    var quotaState = useState(null);
    var quota = quotaState[0];
    var setQuota = quotaState[1];

    var searchState = useState("");
    var search = searchState[0];
    var setSearch = searchState[1];

    var loadingAccountsState = useState(false);
    var loadingAccounts = loadingAccountsState[0];
    var setLoadingAccounts = loadingAccountsState[1];

    var loadAccounts = useCallback(function () {
      setLoadingAccounts(true);
      apiFetch("/accounts").then(function (res) {
        if (res.ok) {
          setAccounts(res.accounts || []);
          setPoolInfo({ strategy: res.strategy, active_email: res.active_email, mode: res.mode });
        }
      }).catch(function (e) {
        console.error("Accounts fetch failed:", e);
      }).finally(function () {
        setLoadingAccounts(false);
      });
    }, []);

    var loadModelsAndQuota = useCallback(function () {
      apiFetch("/antigravity/models").then(function (res) {
        if (res.ok) setModels(res.models || []);
      }).catch(function () {});

      apiFetch("/antigravity/quota").then(function (res) {
        if (res.ok) setQuota(res.summary);
      }).catch(function () {});
    }, []);

    useEffect(function () {
      loadAccounts();
      loadModelsAndQuota();
    }, [loadAccounts, loadModelsAndQuota]);

    function handleSwitch(email) {
      apiFetch("/accounts/switch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email }),
      }).then(function (res) {
        notify(res.message, "success");
        loadAccounts();
      }).catch(function (e) {
        notify("Lỗi chuyển tài khoản: " + e.message, "error");
      });
    }

    function handleRemove(email) {
      if (!confirm("Bạn có chắc chắn muốn gỡ tài khoản " + email + " khỏi pool không?")) return;
      apiFetch("/accounts/remove", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email }),
      }).then(function (res) {
        notify(res.message, "success");
        loadAccounts();
      }).catch(function (e) {
        notify("Lỗi xóa tài khoản: " + e.message, "error");
      });
    }

    function handleStrategy(strat) {
      apiFetch("/accounts/strategy", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ strategy: strat }),
      }).then(function (res) {
        notify(res.message, "success");
        loadAccounts();
      }).catch(function (e) {
        notify("Lỗi lưu chiến lược: " + e.message, "error");
      });
    }

    function handleRole(email, role) {
      apiFetch("/accounts/role", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email, role: role }),
      }).then(function (res) {
        notify(res.message, "success");
        loadAccounts();
      }).catch(function (e) {
        notify("Lỗi lưu role: " + e.message, "error");
      });
    }

    var checkingUnlockState = useState(null);
    var checkingUnlock = checkingUnlockState[0];
    var setCheckingUnlock = checkingUnlockState[1];

    function handleCheckUnlock(email) {
      setCheckingUnlock(email);
      apiFetch("/accounts/check-unlock", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email }),
      })
        .then(function (res) {
          if (res.unlocked || (res.unlocked_count && res.unlocked_count > 0)) {
            notify(res.message || "Tài khoản đã được mở khóa!", "success");
          } else {
            notify(res.message || "Tài khoản vẫn đang bị khóa.", "info");
          }
          loadAccounts();
          loadModelsAndQuota();
        })
        .catch(function (e) {
          notify("Lỗi kiểm tra mở khóa: " + e.message, "error");
        })
        .finally(function () {
          setCheckingUnlock(null);
        });
    }

    var refreshingPlanQuotaState = useState(false);
    var refreshingPlanQuota = refreshingPlanQuotaState[0];
    var setRefreshingPlanQuota = refreshingPlanQuotaState[1];

    function handleRefreshPlanQuota(email) {
      setRefreshingPlanQuota(true);
      apiFetch("/accounts/refresh-plan-quota", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email || "all" }),
      })
        .then(function (res) {
          notify(res.message || "Đã cập nhật gói và hạn mức quota!", "success");
          loadAccounts();
          loadModelsAndQuota();
        })
        .catch(function (e) {
          notify("Lỗi quét plan & quota: " + e.message, "error");
        })
        .finally(function () {
          setRefreshingPlanQuota(false);
        });
    }

    var oauthModalState = useState(null);
    var oauthModal = oauthModalState[0];
    var setOauthModal = oauthModalState[1];

    var callbackInputState = useState("");
    var callbackInput = callbackInputState[0];
    var setCallbackInput = callbackInputState[1];

    var submittingOAuthState = useState(false);
    var submittingOAuth = submittingOAuthState[0];
    var setSubmittingOAuth = submittingOAuthState[1];

    var oauthMsgState = useState(null);
    var oauthMsg = oauthMsgState[0];
    var setOauthMsg = oauthMsgState[1];

    function handleAddAccount() {
      setCallbackInput("");
      setOauthMsg(null);
      setOauthModal({ loading: true, session_id: "", auth_url: "" });
      apiFetch("/accounts/login-start", { method: "POST" })
        .then(function (res) {
          if (res.ok && res.auth_url) {
            setOauthModal({
              loading: false,
              session_id: res.session_id,
              auth_url: res.auth_url,
              redirect_uri: res.redirect_uri,
            });
          } else {
            setOauthMsg({ type: "error", text: res.message || "Không thể khởi tạo phiên OAuth." });
            setOauthModal({ loading: false, session_id: "", auth_url: "" });
          }
        })
        .catch(function (e) {
          setOauthMsg({ type: "error", text: "Lỗi kết nối OAuth: " + e.message });
          setOauthModal({ loading: false, session_id: "", auth_url: "" });
        });
    }

    function handleSubmitOAuth() {
      if (!oauthModal || !oauthModal.session_id) return;
      if (!callbackInput || !callbackInput.trim()) {
        setOauthMsg({ type: "error", text: "Vui lòng dán đường link http://127.0.0.1:51121/... hoặc mã code vào ô bên dưới." });
        return;
      }
      setSubmittingOAuth(true);
      setOauthMsg(null);
      apiFetch("/accounts/login-submit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: oauthModal.session_id,
          callback_url: callbackInput.trim(),
        }),
      })
        .then(function (res) {
          if (res.ok) {
            notify(res.message || ("Đăng nhập thành công: " + res.email), "success");
            setOauthModal(null);
            setCallbackInput("");
            loadAccounts();
            loadModelsAndQuota();
          } else {
            setOauthMsg({ type: "error", text: res.message || "Xác thực thất bại." });
          }
        })
        .catch(function (e) {
          setOauthMsg({ type: "error", text: "Lỗi xác thực: " + e.message });
        })
        .finally(function () {
          setSubmittingOAuth(false);
        });
    }

    // Filter models
    var filteredModels = models.filter(function (m) {
      if (!search) return true;
      var q = search.toLowerCase();
      return m.id.toLowerCase().indexOf(q) !== -1 || m.display_name.toLowerCase().indexOf(q) !== -1;
    });

    // Sort accounts: ACTIVE first, then READY, then Cooldown, then DISABLED
    var sortedAccounts = accounts.slice().sort(function (a, b) {
      var rankA = (a.is_active && a.status !== "disabled") ? 0 : (a.status !== "disabled" && a.cooldown_seconds === 0 ? 1 : (a.status !== "disabled" ? 2 : 3));
      var rankB = (b.is_active && b.status !== "disabled") ? 0 : (b.status !== "disabled" && b.cooldown_seconds === 0 ? 1 : (b.status !== "disabled" ? 2 : 3));
      if (rankA !== rankB) return rankA - rankB;
      return String(a.email || "").localeCompare(String(b.email || ""));
    });

    var readyCount = accounts.filter(function (a) { return a.status !== "disabled"; }).length;
    var disabledCount = accounts.filter(function (a) { return a.status === "disabled"; }).length;

    return h("div", { className: "space-y-6" }, [
      // OAuth PKCE Modal (Mobile & Remote VPS Friendly, Fixed Overlay)
      oauthModal && h("div", {
        key: "oauth-pkce-modal",
        className: "ag-modal-backdrop",
      }, [
        h("div", {
          className: "ag-modal-dialog space-y-4",
        }, [
          h("div", {
            className: "flex items-center justify-between pb-3",
            style: { borderBottom: "1px solid rgba(255,255,255,0.08)" },
          }, [
            h("div", { className: "flex items-center gap-2.5" }, [
              h("div", { className: "ag-avatar ag-avatar-ready", style: { width: "34px", height: "34px" } },
                h(Icon, { name: "key", className: "w-4 h-4" })
              ),
              h("div", null, [
                h("h3", { className: "text-sm font-bold text-white" }, "Thêm Tài Khoản Google Antigravity OAuth"),
                h("p", { className: "text-xs text-zinc-400" }, "Hỗ trợ đăng nhập trực tiếp trên Điện thoại & Máy tính"),
              ]),
            ]),
            h("button", {
              onClick: function () { setOauthModal(null); },
              className: "ag-btn ag-btn-secondary ag-btn-sm",
            }, "Đóng"),
          ]),

          oauthModal.loading
            ? h("div", { className: "py-6 text-center text-xs text-zinc-300" }, "Đang khởi tạo liên kết bảo mật Google OAuth PKCE...")
            : h("div", { className: "space-y-4" }, [
                // Step 1
                h("div", { className: "ag-subcard space-y-2.5" }, [
                  h("div", { className: "text-xs font-semibold text-emerald-400" }, "Bước 1: Mở trang Đăng nhập Google"),
                  h("p", { className: "text-xs text-zinc-400 leading-relaxed" },
                    "Nhấn nút bên dưới để mở trang đăng nhập Google, chọn tài khoản Gmail muốn thêm vào hệ thống và nhấn Cho phép (Allow)."
                  ),
                  oauthModal.auth_url && h("input", {
                    type: "text",
                    readOnly: true,
                    value: oauthModal.auth_url,
                    onClick: function (e) { if (e.target && e.target.select) e.target.select(); },
                    className: "ag-input w-full font-mono",
                    style: { fontSize: "11px", color: "#6ee7b7" },
                  }),
                  h("div", { className: "flex flex-wrap items-center gap-2.5 pt-1" }, [
                    oauthModal.auth_url
                      ? h("a", {
                          href: oauthModal.auth_url,
                          target: "_blank",
                          rel: "noopener noreferrer",
                          className: "ag-btn ag-btn-primary",
                        }, [
                          h(Icon, { name: "key", className: "w-3.5 h-3.5" }),
                          h("span", null, "1. Mở Trang Đăng Nhập Google"),
                        ])
                      : h("span", { className: "text-xs text-red-400" }, "Chưa tạo được link OAuth"),
                    h("button", {
                      onClick: function () {
                        if (!oauthModal.auth_url) return;
                        var copied = false;
                        try {
                          var ta = document.createElement("textarea");
                          ta.value = oauthModal.auth_url;
                          ta.style.position = "fixed";
                          ta.style.opacity = "0";
                          document.body.appendChild(ta);
                          ta.focus();
                          ta.select();
                          copied = document.execCommand("copy");
                          document.body.removeChild(ta);
                        } catch (err) {}
                        if (navigator.clipboard && navigator.clipboard.writeText) {
                          navigator.clipboard.writeText(oauthModal.auth_url).catch(function () {});
                          copied = true;
                        }
                        if (copied) {
                          setOauthMsg({ type: "info", text: "Đã sao chép đường link đăng nhập Google vào bộ nhớ tạm!" });
                        }
                      },
                      className: "ag-btn ag-btn-secondary",
                    }, "Copy Link"),
                  ]),
                ]),

                // Step 2
                h("div", { className: "ag-subcard space-y-2.5" }, [
                  h("div", { className: "text-xs font-semibold text-cyan-400" }, "Bước 2: Dán đường link kết quả (Callback URL)"),
                  h("p", { className: "text-xs text-zinc-400 leading-relaxed" },
                    "Sau khi đăng nhập xong, trình duyệt sẽ chuyển đến trang http://127.0.0.1:51121/oauth-callback?code=... (trên điện thoại sẽ báo Không thể truy cập trang web — điều này hoàn toàn bình thường). Hãy copy toàn bộ đường link trên thanh địa chỉ đó và dán vào ô dưới đây:"
                  ),
                  h("textarea", {
                    rows: 3,
                    value: callbackInput,
                    onChange: function (e) { setCallbackInput(e.target.value); },
                    placeholder: "Dán toàn bộ link http://127.0.0.1:51121/oauth-callback?state=...&code=... vào đây",
                    className: "ag-textarea w-full font-mono",
                  }),
                ]),

                oauthMsg && h("div", {
                  className: "ag-subcard text-xs",
                  style: {
                    borderColor: oauthMsg.type === "error" ? "rgba(239,68,68,0.5)" : "rgba(16,185,129,0.45)",
                    color: oauthMsg.type === "error" ? "#fca5a5" : "#6ee7b7",
                  },
                }, oauthMsg.text),

                h("div", {
                  className: "flex flex-wrap items-center justify-end gap-2.5 pt-2",
                }, [
                  h("button", {
                    onClick: function () { setOauthModal(null); },
                    className: "ag-btn ag-btn-secondary",
                  }, "Hủy"),
                  h("button", {
                    disabled: submittingOAuth,
                    onClick: handleSubmitOAuth,
                    className: "ag-btn ag-btn-primary",
                  }, submittingOAuth ? "Đang xác thực & đồng bộ..." : "2. Xác Nhận & Thêm Tài Khoản"),
                ]),
              ]),
        ]),
      ]),

      // 1. Account Pool Card
      h("div", { className: "ag-card" }, [
        h("div", {
          className: "flex flex-col lg:flex-row lg:items-center justify-between gap-4 pb-4 mb-5",
          style: { borderBottom: "1px solid rgba(255,255,255,0.08)" },
        }, [
          h("div", { className: "flex items-center gap-3" }, [
            h("div", { className: "ag-avatar ag-avatar-ready" },
              h(Icon, { name: "user", className: "w-5 h-5" })
            ),
            h("div", null, [
              h("div", { className: "flex flex-wrap items-center gap-2" }, [
                h("h2", { className: "text-sm font-bold text-white" }, "Google Antigravity OAuth Account Pool"),
                h("span", { className: "ag-badge ag-badge-emerald" }, readyCount + " SẴN SÀNG"),
                disabledCount > 0 && h("span", { className: "ag-badge ag-badge-red" }, disabledCount + " BỊ KHÓA"),
              ]),
              h("p", { className: "text-xs text-zinc-400 mt-0.5" }, (poolInfo.mode || "Multi-Account Sharded Pool") + " • Tổng " + accounts.length + " tài khoản"),
            ]),
          ]),

          h("div", { className: "flex flex-wrap items-center gap-2.5" }, [
            // Strategy dropdown
            h("div", { className: "flex items-center gap-2 text-xs" }, [
              h("span", { className: "text-zinc-400 hidden sm:inline" }, "Chiến lược:"),
              h("select", {
                value: poolInfo.strategy,
                onChange: function (e) { handleStrategy(e.target.value); },
                className: "ag-select",
              }, [
                h("option", { value: "fill_first", key: "ff" }, "Fill-First (Dùng cạn mới đổi)"),
                h("option", { value: "round_robin", key: "rr" }, "Round-Robin (Xoay vòng đều)"),
                h("option", { value: "least_used", key: "lu" }, "Least-Used (Ưu tiên ít dùng)"),
                h("option", { value: "sharded", key: "sh" }, "Sharded (Phân mảnh thông minh)"),
              ]),
            ]),

            accounts.some(function (a) { return a.status === "disabled" || a.status === "cooling_down"; }) && h("button", {
              disabled: checkingUnlock === "all",
              onClick: function () { handleCheckUnlock("all"); },
              className: "ag-btn ag-btn-amber",
            }, [
              h(Icon, { name: "refresh", className: "w-3.5 h-3.5 " + (checkingUnlock === "all" ? "animate-spin" : "") }),
              h("span", null, checkingUnlock === "all" ? "Đang kiểm tra..." : "Kiểm tra TK khóa"),
            ]),

            h("button", {
              disabled: refreshingPlanQuota,
              onClick: function () { handleRefreshPlanQuota("all"); },
              className: "ag-btn ag-btn-secondary",
              title: "Quét thông tin gói Google AI (Ultra/Pro/Free) và hạn mức quota thời gian thực",
            }, [
              h(Icon, { name: "refresh", className: "w-3.5 h-3.5 " + (refreshingPlanQuota ? "animate-spin" : "") }),
              h("span", null, refreshingPlanQuota ? "Đang quét..." : "Quét Plan & Quota"),
            ]),

            h("button", {
              onClick: handleAddAccount,
              className: "ag-btn ag-btn-primary",
            }, [
              h(Icon, { name: "key", className: "w-3.5 h-3.5" }),
              h("span", null, "+ Đăng nhập Tài Khoản"),
            ]),
          ]),
        ]),

        // Account Bento Grid (Sorted: ACTIVE & READY on top, DISABLED at bottom)
        sortedAccounts.length === 0
          ? h("div", { className: "text-center py-10 text-zinc-500 text-xs" },
              "Chưa có tài khoản nào trong pool. Nhấn '+ Đăng nhập Tài Khoản' để xác thực."
            )
          : h("div", { className: "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4" },
              sortedAccounts.map(function (acc) {
                var isDisabled = acc.status === "disabled";
                var isCooling = !isDisabled && (acc.cooldown_seconds > 0 || acc.status === "cooling_down");
                var cardCls = "ag-subcard flex flex-col justify-between " +
                  (isDisabled ? "ag-subcard-disabled" : (acc.is_active ? "ag-subcard-active" : ""));
                var avatarCls = "ag-avatar " +
                  (isDisabled ? "ag-avatar-disabled" : (acc.is_active ? "ag-avatar-active" : "ag-avatar-ready"));

                var tierId = (acc.tier_id || "").toLowerCase();
                var planType = (acc.plan_type || "").toLowerCase();
                var planName = acc.plan_name || "";
                if (tierId.indexOf("ultra") !== -1 || planName.toLowerCase().indexOf("ultra") !== -1) {
                  planType = "ultra";
                } else if (tierId.indexOf("pro") !== -1 || planName.toLowerCase().indexOf("pro") !== -1) {
                  planType = "pro";
                }
                if (planType === "pro" && (!planName || planName === "Free Tier")) {
                  planName = "Google AI Pro";
                } else if (planType === "ultra" && (!planName || planName === "Free Tier")) {
                  planName = "Google AI Ultra";
                } else if (!planName) {
                  planName = "Free Tier";
                }
                var planBadgeCls = planType === "ultra"
                  ? "ag-badge ag-badge-purple"
                  : (planType === "pro" ? "ag-badge ag-badge-blue" : "ag-badge ag-badge-neutral");
                var planLabel = planType === "ultra"
                  ? ("⚡ " + planName)
                  : (planType === "pro"
                      ? ("💎 " + planName)
                      : ("🌱 " + planName));

                return h("div", {
                  key: acc.email,
                  className: cardCls,
                }, [
                  h("div", { className: "space-y-3" }, [
                    h("div", { className: "flex items-start justify-between gap-2" }, [
                      h("div", { className: "flex items-center gap-2.5 overflow-hidden", style: { minWidth: 0 } }, [
                        h("div", { className: avatarCls }, (acc.email[0] || "U").toUpperCase()),
                        h("div", { className: "overflow-hidden", style: { minWidth: 0 } }, [
                          h("div", { className: "text-xs font-semibold text-white truncate", title: acc.email }, acc.email),
                          h("div", { className: "text-[11px] text-zinc-500 font-mono truncate" }, acc.project_id || "aicode-consumers"),
                        ]),
                      ]),
                      acc.is_active && !isDisabled && h("span", {
                        className: "ag-badge ag-badge-emerald",
                      }, "ACTIVE"),
                    ]),

                    // Plan, Role, and Status tags
                    h("div", { className: "flex flex-wrap items-center gap-1.5" }, [
                      h("span", {
                        className: planBadgeCls,
                        title: "Gói Google AI: " + (planName || "Free Tier"),
                      }, planLabel),
                      h("span", {
                        className: "ag-badge ag-badge-neutral",
                      }, "Role: " + (acc.role || "all").toUpperCase()),
                      isDisabled
                        ? h("span", {
                            className: "ag-badge ag-badge-red",
                          }, "BỊ KHÓA")
                        : isCooling
                          ? h("span", {
                              className: "ag-badge ag-badge-amber",
                            }, "Cooldown: " + acc.cooldown_seconds + "s")
                          : h("span", {
                              className: "ag-badge ag-badge-emerald",
                            }, "READY"),
                      h("span", {
                        className: "ag-badge ag-badge-neutral",
                        style: { marginLeft: "auto" },
                      }, (acc.usage_count || 0) + " reqs"),
                    ]),

                    // Mini Quota Telemetry (if available)
                    acc.quota_summary && (acc.quota_summary.gemini_weekly_pct != null || acc.quota_summary.claude_weekly_pct != null) && h("div", {
                      className: "ag-quota-bar-wrap",
                    }, [
                      acc.quota_summary.gemini_weekly_pct != null && h("div", { className: "space-y-1" }, [
                        h("div", { className: "ag-quota-row" }, [
                          h("span", null, "Gemini (Tuần)"),
                          h("span", { style: { color: acc.quota_summary.gemini_weekly_pct > 20 ? "#34d399" : "#f87171", fontWeight: "bold" } }, acc.quota_summary.gemini_weekly_pct + "% còn lại"),
                        ]),
                        h("div", { className: "ag-quota-progress" }, [
                          h("div", {
                            className: "ag-quota-fill ag-quota-fill-gemini",
                            style: { width: Math.min(100, Math.max(0, acc.quota_summary.gemini_weekly_pct)) + "%" },
                          }),
                        ]),
                      ]),
                      acc.quota_summary.claude_weekly_pct != null && h("div", { className: "space-y-1" }, [
                        h("div", { className: "ag-quota-row" }, [
                          h("span", null, "Claude & GPT (Tuần)"),
                          h("span", { style: { color: acc.quota_summary.claude_weekly_pct > 20 ? "#c084fc" : "#f87171", fontWeight: "bold" } }, acc.quota_summary.claude_weekly_pct + "% còn lại"),
                        ]),
                        h("div", { className: "ag-quota-progress" }, [
                          h("div", {
                            className: "ag-quota-fill ag-quota-fill-claude",
                            style: { width: Math.min(100, Math.max(0, acc.quota_summary.claude_weekly_pct)) + "%" },
                          }),
                        ]),
                      ]),
                    ]),
                  ]),

                  // Actions
                  h("div", {
                    className: "flex flex-wrap items-center gap-2 pt-3 mt-3",
                    style: { borderTop: "1px solid rgba(255,255,255,0.06)" },
                  }, [
                    !acc.is_active && !isDisabled && h("button", {
                      onClick: function () { handleSwitch(acc.email); },
                      className: "ag-btn ag-btn-primary ag-btn-sm",
                    }, "Chọn Active"),
                    (isDisabled || isCooling) && h("button", {
                      disabled: checkingUnlock === acc.email || checkingUnlock === "all",
                      onClick: function () { handleCheckUnlock(acc.email); },
                      className: "ag-btn ag-btn-amber ag-btn-sm",
                      title: "Kiểm tra trực tiếp xem Google đã mở khóa tài khoản này chưa",
                    }, [
                      h(Icon, { name: "refresh", className: "w-3 h-3 " + (checkingUnlock === acc.email ? "animate-spin" : "") }),
                      h("span", null, checkingUnlock === acc.email ? "Đang kiểm tra..." : "Kiểm tra mở khóa"),
                    ]),
                    isDisabled && h("a", {
                      href: "https://forms.gle/hGzM9MEUv2azZsrb9",
                      target: "_blank",
                      rel: "noopener noreferrer",
                      className: "ag-btn ag-btn-secondary ag-btn-sm",
                      title: "Mở biểu mẫu kháng nghị chính thức của Google Antigravity",
                    }, "Kháng nghị ↗"),
                    h("button", {
                      disabled: refreshingPlanQuota,
                      onClick: function () { handleRefreshPlanQuota(acc.email); },
                      className: "ag-btn ag-btn-secondary ag-btn-icon",
                      style: { width: "28px", height: "28px", borderRadius: "8px" },
                      title: "Quét lại Plan & Quota của tài khoản này",
                    }, h(Icon, { name: "refresh", className: "w-3.5 h-3.5 " + (refreshingPlanQuota ? "animate-spin" : "") })),
                    h("select", {
                      value: acc.role,
                      onChange: function (e) { handleRole(acc.email, e.target.value); },
                      className: "ag-select",
                      style: { padding: "4px 8px", fontSize: "11px", marginLeft: "auto" },
                    }, [
                      h("option", { value: "all", key: "r-all" }, "Role: ALL"),
                      h("option", { value: "llm", key: "r-llm" }, "Role: LLM"),
                      h("option", { value: "image_gen", key: "r-img" }, "Role: Image"),
                    ]),
                    h("button", {
                      onClick: function () { handleRemove(acc.email); },
                      className: "ag-btn ag-btn-danger ag-btn-icon",
                      style: { width: "28px", height: "28px", borderRadius: "8px" },
                      title: "Xóa tài khoản",
                    }, h(Icon, { name: "trash", className: "w-3.5 h-3.5" })),
                  ]),
                ]);
              })
            ),
      ]),

      // 2. Quota Telemetry (If Available)
      quota && quota.groups && quota.groups.length > 0 && h("div", {
        className: "ag-card",
      }, [
        h("div", {
          className: "flex items-center gap-3 pb-3 mb-4",
          style: { borderBottom: "1px solid rgba(255,255,255,0.08)" },
        }, [
          h("div", { className: "ag-avatar ag-avatar-ready" },
            h(Icon, { name: "activity", className: "w-4 h-4" })
          ),
          h("div", null, [
            h("h3", { className: "text-sm font-bold text-white" }, "Hạn Mức Quota API (Google Code Assist)"),
            h("p", { className: "text-xs text-zinc-400" }, "Theo dõi tỷ lệ sử dụng thực tế và chu kỳ hồi phục hạn mức"),
          ]),
        ]),

        h("div", { className: "grid grid-cols-1 md:grid-cols-2 gap-4" },
          quota.groups.map(function (grp, idx) {
            return h("div", { key: idx, className: "ag-subcard" }, [
              h("div", { className: "text-xs font-semibold text-zinc-200 mb-2" }, grp.displayName || "Group"),
              h("div", { className: "space-y-3" },
                (grp.buckets || []).map(function (b, bIdx) {
                  var rem = b.remainingFraction || 0;
                  var pct = Math.round(rem * 100);
                  return h("div", { key: bIdx, className: "space-y-1" }, [
                    h("div", { className: "flex justify-between text-xs font-mono" }, [
                      h("span", { className: "text-zinc-400" }, b.displayName || b.bucketId),
                      h("span", { className: pct > 20 ? "text-emerald-400 font-bold" : "text-amber-400 font-bold" }, pct + "% còn lại"),
                    ]),
                    h("div", { className: "w-full h-1.5 rounded-full bg-zinc-800 overflow-hidden" }, [
                      h("div", {
                        className: "h-full rounded-full",
                        style: {
                          width: pct + "%",
                          background: pct > 20 ? "linear-gradient(90deg, #10b981, #06b6d4)" : "#f59e0b",
                        },
                      }),
                    ]),
                  ]);
                })
              ),
            ]);
          })
        ),
      ]),

      // 3. Dynamic Model Catalog (32+ Models)
      h("div", { className: "ag-card" }, [
        h("div", {
          className: "flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 mb-5",
          style: { borderBottom: "1px solid rgba(255,255,255,0.08)" },
        }, [
          h("div", { className: "flex items-center gap-3" }, [
            h("div", { className: "ag-avatar ag-avatar-ready" },
              h(Icon, { name: "zap", className: "w-4 h-4" })
            ),
            h("div", null, [
              h("h3", { className: "text-sm font-bold text-white flex flex-wrap items-center gap-2" }, [
                h("span", null, "Danh Mục Mô Hình Khả Dụng"),
                h("span", { className: "ag-badge ag-badge-emerald" },
                  models.length + " Models"
                ),
              ]),
              h("p", { className: "text-xs text-zinc-400 mt-0.5" }, "Tự động khám phá qua quyền hạn tài khoản (Gemini 3.7, Claude Sonnet/Opus, GPT-OSS)"),
            ]),
          ]),

          h("div", { className: "relative w-full sm:w-64" }, [
            h("input", {
              type: "text",
              placeholder: "Tìm mô hình...",
              value: search,
              onChange: function (e) { setSearch(e.target.value); },
              className: "ag-input w-full",
            }),
          ]),
        ]),

        h("div", { className: "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 max-h-[420px] overflow-y-auto pr-1 ag-scrollbar" },
          filteredModels.map(function (m) {
            return h("div", {
              key: m.id,
              className: "ag-subcard flex flex-col justify-between",
            }, [
              h("div", { className: "space-y-1.5" }, [
                h("div", { className: "flex items-start justify-between gap-2" }, [
                  h("div", { className: "text-xs font-semibold text-white tracking-tight" }, m.display_name),
                  m.recommended && h("span", {
                    className: "ag-badge ag-badge-emerald",
                  }, "GỢI Ý"),
                ]),
                h("div", { className: "text-xs font-mono text-zinc-500 truncate", title: m.id }, m.id),
              ]),

              h("div", {
                className: "flex items-center gap-2 pt-2.5 mt-2 text-xs font-mono text-zinc-400",
                style: { borderTop: "1px solid rgba(255,255,255,0.06)" },
              }, [
                h("span", null, "Context: " + (m.max_tokens >= 1024 ? Math.round(m.max_tokens / 1024) + "k" : m.max_tokens)),
                m.supports_thinking && h("span", {
                  className: "ag-badge ag-badge-neutral",
                  style: { marginLeft: "auto" },
                }, "Thinking " + (m.thinking_budget ? m.thinking_budget + "t" : "")),
              ]),
            ]);
          })
        ),
      ]),
    ]);
  }

  // ===========================================================================
  // TAB 2: GOOGLE FLOW VEO VIDEO STUDIO
  // ===========================================================================
  function TabGoogleFlow(props) {
    var notify = props.notify;
    var flowStatusState = useState(null);
    var flowStatus = flowStatusState[0];
    var setFlowStatus = flowStatusState[1];

    var flowAccountsState = useState([]);
    var flowAccounts = flowAccountsState[0];
    var setFlowAccounts = flowAccountsState[1];

    var videoModelsState = useState([]);
    var videoModels = videoModelsState[0];
    var setVideoModels = videoModelsState[1];

    var currentVideoModelState = useState("omni-1.1-flash");
    var currentVideoModel = currentVideoModelState[0];
    var setCurrentVideoModel = currentVideoModelState[1];

    var handshakeOverlayState = useState(false);
    var handshakeOverlay = handshakeOverlayState[0];
    var setHandshakeOverlay = handshakeOverlayState[1];

    var activeSessionIdRef = useRef(null);
    var pollIntervalRef = useRef(null);

    var loadFlowData = useCallback(function () {
      apiFetch("/flow/status").then(function (res) {
        setFlowStatus(res);
      }).catch(function () {});

      apiFetch("/flow/accounts").then(function (res) {
        if (res.ok) {
          setFlowAccounts(res.accounts || []);
        }
      }).catch(function () {});

      apiFetch("/flow/models").then(function (res) {
        if (res.ok) {
          setVideoModels(res.models || []);
          setCurrentVideoModel(res.current_model || "omni-1.1-flash");
        }
      }).catch(function () {});
    }, []);

    useEffect(function () {
      loadFlowData();
    }, [loadFlowData]);

    function startHandshake() {
      setHandshakeOverlay(true);
      apiFetch("/flow/login-start", { method: "POST" }).then(function (res) {
        if (!res.ok) throw new Error(res.message || "Lỗi khởi chạy");
        activeSessionIdRef.current = res.session_id;
        pollIntervalRef.current = setInterval(pollHandshake, 2000);
      }).catch(function (e) {
        setHandshakeOverlay(false);
        notify("Lỗi khởi chạy 1-Click Handshake: " + e.message, "error");
      });
    }

    function pollHandshake() {
      if (!activeSessionIdRef.current) return;
      apiFetch("/flow/login-poll/" + activeSessionIdRef.current).then(function (data) {
        if (data.connected || data.status === "completed") {
          clearInterval(pollIntervalRef.current);
          setHandshakeOverlay(false);
          notify("Kết nối Google Flow thành công: " + (data.email || ""), "success");
          loadFlowData();
        } else if (data.status === "error" || data.status === "timeout" || data.status === "cancelled") {
          clearInterval(pollIntervalRef.current);
          setHandshakeOverlay(false);
          notify("Phiên đăng nhập kết thúc: " + (data.error || data.status), "error");
          loadFlowData();
        }
      }).catch(function () {});
    }

    function cancelHandshake() {
      if (activeSessionIdRef.current) {
        apiFetch("/flow/login-cancel/" + activeSessionIdRef.current, { method: "POST" }).catch(function () {});
      }
      clearInterval(pollIntervalRef.current);
      setHandshakeOverlay(false);
      notify("Đã hủy phiên đăng nhập", "info");
    }

    function handleRefresh() {
      notify("Đang kích hoạt làm mới token ngầm...", "info");
      apiFetch("/flow/refresh", { method: "POST" }).then(function (res) {
        notify(res.message, res.ok ? "success" : "error");
        setFlowStatus(res.status);
        loadFlowData();
      }).catch(function (e) {
        notify("Lỗi làm mới: " + e.message, "error");
      });
    }

    function handleDisconnect() {
      if (!confirm("Bạn có chắc chắn muốn ngắt kết nối Google Flow không?")) return;
      apiFetch("/flow/disconnect", { method: "POST" }).then(function (res) {
        notify(res.message, "success");
        loadFlowData();
      }).catch(function (e) {
        notify("Lỗi ngắt kết nối: " + e.message, "error");
      });
    }

    function handleSwitchFlowAccount(accId) {
      apiFetch("/flow/accounts/switch?account_id=" + encodeURIComponent(accId), { method: "POST" })
        .then(function (res) {
          notify(res.message, "success");
          loadFlowData();
        }).catch(function (e) {
          notify("Lỗi chuyển tài khoản Flow: " + e.message, "error");
        });
    }

    function handleSetVideoModel(modelId) {
      apiFetch("/flow/model/set", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model_id: modelId }),
      }).then(function (res) {
        notify(res.message, "success");
        setCurrentVideoModel(modelId);
        loadFlowData();
      }).catch(function (e) {
        notify("Lỗi đổi model: " + e.message, "error");
      });
    }

    var activeFlowAccount = flowAccounts.find(function (a) { return a.is_active; }) || (flowAccounts.length > 0 ? flowAccounts[0] : null);
    var activeEmail = (flowStatus && flowStatus.email) || (activeFlowAccount && activeFlowAccount.email) || "";
    var hasAccount = Boolean(activeEmail || (flowStatus && flowStatus.has_session_cookie) || flowAccounts.length > 0);
    var isReady = Boolean(flowStatus && flowStatus.connected);

    return h("div", { className: "space-y-6 relative" }, [
      // 1. Connection & Session Card
      h("div", { className: "ag-card relative overflow-hidden" }, [
        h("div", {
          className: "flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 mb-5",
          style: { borderBottom: "1px solid rgba(255,255,255,0.08)" },
        }, [
          h("div", { className: "flex items-center gap-3" }, [
            h("div", { className: "ag-avatar ag-avatar-ready" },
              h(Icon, { name: "video", className: "w-5 h-5" })
            ),
            h("div", null, [
              h("h2", { className: "text-sm font-bold text-white" }, "Google Flow (Veo AI Video Generator)"),
              h("p", { className: "text-xs text-zinc-400" }, "Camofox Anti-Detection, reCAPTCHA Enterprise bypass & 30-Day Session Keep-Alive"),
            ]),
          ]),

          h("div", null, [
            isReady
              ? h("span", {
                  className: "ag-badge ag-badge-emerald",
                }, [
                  h("span", {
                    className: "ag-led-pulse",
                    style: { display: "inline-block", width: "7px", height: "7px", borderRadius: "9999px", background: "#34d399" },
                  }),
                  h("span", null, "Đã Kết Nối (Active)"),
                ])
              : hasAccount
                ? h("span", {
                    className: "ag-badge ag-badge-amber",
                  }, [
                    h("span", {
                      className: "ag-led-pulse",
                      style: { display: "inline-block", width: "7px", height: "7px", borderRadius: "9999px", background: "#fbbf24" },
                    }),
                    h("span", null, "Session 30 Ngày Sẵn Sàng (Cần Làm Mới)"),
                  ])
                : h("span", {
                    className: "ag-badge ag-badge-neutral",
                  }, "Chưa Kết Nối"),
          ]),
        ]),

        // State: Has Registered Account View
        hasAccount
          ? h("div", { className: "space-y-5" }, [
              h("div", { className: "grid grid-cols-1 md:grid-cols-3 gap-4" }, [
                h("div", { className: "ag-subcard flex items-center gap-3" }, [
                  h("div", {
                    className: "ag-avatar " + (isReady ? "ag-avatar-active" : "ag-avatar-ready"),
                  }, (activeEmail || "F")[0].toUpperCase()),
                  h("div", { className: "overflow-hidden" }, [
                    h("div", { className: "text-xs text-zinc-500" }, "Tài khoản Google Flow (Đang chọn)"),
                    h("div", { className: "text-xs font-semibold text-white truncate", title: activeEmail }, activeEmail || "Chưa kết nối"),
                  ]),
                ]),

                h("div", { className: "ag-subcard" }, [
                  h("div", { className: "text-xs text-zinc-500" }, "Số dư Tín Dụng AI (Credits)"),
                  h("div", { className: "flex items-baseline gap-1 mt-0.5" }, [
                    h("span", { className: "text-xl font-bold text-emerald-400 font-mono" }, flowStatus && flowStatus.credits != null ? flowStatus.credits : "--"),
                    h("span", { className: "text-xs text-zinc-400" }, "credits"),
                  ]),
                ]),

                h("div", { className: "ag-subcard" }, [
                  h("div", { className: "text-xs text-zinc-500" }, "Thời hạn Phiên Google"),
                  h("div", { className: "text-xs font-semibold " + (isReady ? "text-emerald-400" : "text-amber-400") + " mt-1" },
                    isReady
                      ? (flowStatus && flowStatus.status_label || "Đã kết nối")
                      : "Token tạm hết hạn • Session 30 ngày sẵn sàng"
                  ),
                ]),
              ]),

              // Action buttons
              h("div", { className: "flex flex-wrap items-center gap-3 pt-2" }, [
                h("button", {
                  onClick: handleRefresh,
                  className: "ag-btn ag-btn-primary",
                }, [
                  h(Icon, { name: "refresh", className: "w-3.5 h-3.5" }),
                  h("span", null, "Làm mới Token Ngầm"),
                ]),
                h("button", {
                  onClick: startHandshake,
                  className: "ag-btn ag-btn-secondary",
                }, [
                  h(Icon, { name: "key", className: "w-3.5 h-3.5" }),
                  h("span", null, "Đăng nhập lại (1-Click Handshake)"),
                ]),
                h("button", {
                  onClick: handleDisconnect,
                  className: "ag-btn ag-btn-danger",
                  style: { marginLeft: "auto" },
                }, [
                  h(Icon, { name: "trash", className: "w-3.5 h-3.5" }),
                  h("span", null, "Ngắt kết nối"),
                ]),
              ]),
            ])
          : h("div", { className: "text-center py-8 space-y-4" }, [
              h("div", {
                className: "ag-avatar ag-avatar-ready mx-auto",
                style: { width: "52px", height: "52px", borderRadius: "14px" },
              }, h(Icon, { name: "film", className: "w-6 h-6" })),
              h("div", null, [
                h("h3", { className: "text-base font-bold text-white" }, "Chưa kết nối Google Flow"),
                h("p", { className: "text-xs text-zinc-400 max-w-md mx-auto mt-1" },
                  "Nhấn nút bên dưới để khởi chạy 1-Click Handshake. Cửa sổ trình duyệt sẽ tự động mở trên màn hình, bạn chỉ cần nhấn vào tài khoản Google và cửa sổ sẽ tự động đóng sau 1-2 giây!"
                ),
              ]),
              h("button", {
                onClick: startHandshake,
                className: "ag-btn ag-btn-primary mx-auto",
              }, [
                h(Icon, { name: "zap", className: "w-4 h-4" }),
                h("span", null, "Kết Nối 1-Click Handshake"),
              ]),
            ]),
      ]),

      // 2. Multi-Account Pool Bento Grid
      h("div", { className: "ag-card" }, [
        h("div", {
          className: "flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 mb-5",
          style: { borderBottom: "1px solid rgba(255,255,255,0.08)" },
        }, [
          h("div", { className: "flex items-center gap-3" }, [
            h("div", { className: "ag-avatar ag-avatar-ready" },
              h(Icon, { name: "user", className: "w-5 h-5" })
            ),
            h("div", null, [
              h("h3", { className: "text-sm font-bold text-white" }, "Google Flow Multi-Account Pool"),
              h("p", { className: "text-xs text-zinc-400" }, (flowAccounts.length || 1) + " tài khoản đã đăng ký • Tự động chuyển đổi tài khoản khi hết quota"),
            ]),
          ]),
          h("button", {
            onClick: startHandshake,
            className: "ag-btn ag-btn-primary",
          }, [
            h(Icon, { name: "key", className: "w-3.5 h-3.5" }),
            h("span", null, "+ Thêm Tài Khoản Flow"),
          ]),
        ]),

        flowAccounts.length === 0
          ? h("div", { className: "text-center py-6 text-zinc-500 text-xs" }, "Chưa có tài khoản nào trong pool.")
          : h("div", { className: "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4" },
              flowAccounts.map(function (acc) {
                var isAct = acc.is_active || acc.id === "default";
                var emailDisplay = acc.email || activeEmail || "Tài khoản mặc định";
                return h("div", {
                  key: acc.id,
                  className: "ag-subcard flex flex-col justify-between " + (isAct ? "ag-subcard-active" : ""),
                }, [
                  h("div", { className: "space-y-2" }, [
                    h("div", { className: "flex items-start justify-between gap-2" }, [
                      h("div", { className: "flex items-center gap-2 overflow-hidden" }, [
                        h("div", {
                          className: "ag-avatar " + (isAct ? "ag-avatar-active" : "ag-avatar-ready"),
                        }, (emailDisplay[0] || "F").toUpperCase()),
                        h("div", { className: "overflow-hidden" }, [
                          h("div", { className: "text-xs font-semibold text-white truncate", title: emailDisplay }, emailDisplay),
                          h("div", { className: "text-xs text-zinc-500 font-mono" }, "ID: " + acc.id + (acc.label ? " • " + acc.label : "")),
                        ]),
                      ]),
                      isAct && h("span", {
                        className: "ag-badge ag-badge-emerald",
                      }, "ACTIVE"),
                    ]),
                    h("div", { className: "flex flex-wrap items-center gap-1.5 pt-1" }, [
                      h("span", {
                        className: "ag-badge ag-badge-neutral",
                      }, (acc.status || "ready").toUpperCase()),
                      h("span", {
                        className: "ag-badge ag-badge-neutral",
                        style: { marginLeft: "auto" },
                      }, (acc.total_creations || 0) + " video tạo"),
                    ]),
                  ]),
                  h("div", {
                    className: "flex items-center gap-2 pt-3 mt-3",
                    style: { borderTop: "1px solid rgba(255,255,255,0.06)" },
                  }, [
                    !isAct && h("button", {
                      onClick: function () { handleSwitchFlowAccount(acc.id); },
                      className: "ag-btn ag-btn-primary ag-btn-sm",
                    }, "Chọn Active"),
                    h("button", {
                      onClick: handleRefresh,
                      className: "ag-btn ag-btn-secondary ag-btn-sm",
                      style: { marginLeft: "auto" },
                    }, [
                      h(Icon, { name: "refresh", className: "w-3 h-3" }),
                      h("span", null, "Làm mới"),
                    ]),
                  ]),
                ]);
              })
            ),
      ]),

      // 2. 5 Model Tiers Selector Card
      h("div", { className: "ag-card" }, [
        h("div", {
          className: "pb-4 mb-5",
          style: { borderBottom: "1px solid rgba(255,255,255,0.08)" },
        }, [
          h("h3", { className: "text-sm font-bold text-white flex flex-wrap items-center gap-2" }, [
            h("span", null, "5 Phân Tầng Mô Hình Video Google Flow Veo 3.1"),
            h("span", { className: "ag-badge ag-badge-emerald" },
              "Đang dùng: " + currentVideoModel
            ),
          ]),
          h("p", { className: "text-xs text-zinc-400 mt-1" },
            "Chọn mô hình mặc định được lưu vào config.yaml (Agent tự động định tuyến khi tạo video)"
          ),
        ]),

        h("div", { className: "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4" },
          videoModels.map(function (vm) {
            var isSelected = vm.id === currentVideoModel;
            return h("div", {
              key: vm.id,
              className: "ag-subcard flex flex-col justify-between " + (isSelected ? "ag-subcard-active" : ""),
            }, [
              h("div", { className: "space-y-2" }, [
                h("div", { className: "flex items-center justify-between" }, [
                  h("span", { className: "ag-badge ag-badge-neutral" }, vm.tier),
                  isSelected && h("span", { className: "ag-badge ag-badge-emerald" }, "ĐANG CHỌN"),
                ]),
                h("div", { className: "text-sm font-bold text-white" }, vm.display),
                h("p", { className: "text-xs text-zinc-400" }, vm.strengths),
              ]),

              h("div", {
                className: "pt-3 mt-3 space-y-2",
                style: { borderTop: "1px solid rgba(255,255,255,0.06)" },
              }, [
                h("div", { className: "flex items-center justify-between text-xs font-mono text-zinc-400" }, [
                  h("span", null, "Chi phí:"),
                  h("span", { className: "text-emerald-400 font-bold" }, vm.credits + " credits"),
                ]),
                h("div", { className: "flex items-center justify-between text-xs font-mono text-zinc-400" }, [
                  h("span", null, "Thời lượng / Tốc độ:"),
                  h("span", { className: "text-zinc-300" }, vm.duration + " • " + vm.speed),
                ]),
                !isSelected && h("button", {
                  onClick: function () { handleSetVideoModel(vm.id); },
                  className: "ag-btn ag-btn-secondary w-full mt-2",
                }, "Chọn mô hình này"),
              ]),
            ]);
          })
        ),
      ]),

      // 3. Handshake In-Progress Modal Overlay
      handshakeOverlay && h("div", {
        className: "ag-modal-backdrop",
        key: "overlay",
      }, [
        h("div", { className: "ag-modal-dialog text-center space-y-4" }, [
          h("h3", { className: "text-base font-bold text-white" }, "Cửa sổ Google Flow đang mở trên màn hình..."),
          h("p", { className: "text-xs text-zinc-300" },
            "Vui lòng nhìn màn hình desktop và nhấn vào tài khoản Google của bạn. Cửa sổ sẽ tự động đóng ngay lập tức khi đăng nhập hoàn tất!"
          ),
          h("button", {
            onClick: cancelHandshake,
            className: "ag-btn ag-btn-secondary",
          }, "Hủy phiên đăng nhập"),
        ]),
      ]),
    ]);
  }

  // ===========================================================================
  // TAB 3: IMAGE GENERATION STUDIO
  // ===========================================================================
  function TabImageGen(props) {
    var notify = props.notify;
    var imgCfgState = useState({ provider: "antigravity", aspect_ratio: "16:9", available_aspect_ratios: [] });
    var imgCfg = imgCfgState[0];
    var setImgCfg = imgCfgState[1];

    var promptState = useState("");
    var prompt = promptState[0];
    var setPrompt = promptState[1];

    var selectedAspectState = useState("16:9");
    var selectedAspect = selectedAspectState[0];
    var setSelectedAspect = selectedAspectState[1];

    var generatingState = useState(false);
    var generating = generatingState[0];
    var setGenerating = generatingState[1];

    var resultState = useState(null);
    var result = resultState[0];
    var setResult = resultState[1];

    useEffect(function () {
      apiFetch("/image/config").then(function (res) {
        if (res.ok) {
          setImgCfg(res);
          setSelectedAspect(res.aspect_ratio || "16:9");
        }
      }).catch(function () {});
    }, []);

    function handleSaveConfig(aspect) {
      setSelectedAspect(aspect);
      apiFetch("/image/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ aspect_ratio: aspect }),
      }).then(function (res) {
        notify("Đã lưu tỷ lệ mặc định: " + aspect, "success");
      }).catch(function (e) {
        notify("Lỗi lưu cấu hình: " + e.message, "error");
      });
    }

    function handleGenerate() {
      if (!prompt.trim()) {
        notify("Vui lòng nhập mô tả ảnh (prompt)", "error");
        return;
      }
      setGenerating(true);
      setResult(null);
      notify("Đang gửi yêu cầu sinh ảnh đến Gemini 3.1 Flash Image...", "info");

      apiFetch("/image/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: prompt, aspect_ratio: selectedAspect }),
      }).then(function (res) {
        if (res.ok) {
          setResult(res);
          notify("Sinh ảnh thành công!", "success");
        } else {
          notify("Sinh ảnh thất bại: " + (res.error || "Unknown"), "error");
        }
      }).catch(function (e) {
        notify("Lỗi gọi API sinh ảnh: " + e.message, "error");
      }).finally(function () {
        setGenerating(false);
      });
    }

    var aspectOptions = ["1:1", "16:9", "9:16", "4:3", "3:4"];

    return h("div", { className: "space-y-6" }, [
      // Config & Generator Form Card
      h("div", { className: "ag-card" }, [
        h("div", {
          className: "flex items-center gap-3 pb-4 mb-5",
          style: { borderBottom: "1px solid rgba(255,255,255,0.08)" },
        }, [
          h("div", { className: "ag-avatar ag-avatar-ready" },
            h(Icon, { name: "image", className: "w-5 h-5" })
          ),
          h("div", null, [
            h("h2", { className: "text-sm font-bold text-white" }, "AI Image Generation Studio"),
            h("p", { className: "text-xs text-zinc-400" }, "Mô hình Gemini 3.1 Flash Image qua Antigravity OAuth Bridge"),
          ]),
        ]),

        h("div", { className: "space-y-4" }, [
          // Aspect ratio selector
          h("div", null, [
            h("label", { className: "text-xs font-semibold text-zinc-300 block mb-2" }, "Tỷ Lệ Khung Hình (Aspect Ratio):"),
            h("div", { className: "flex flex-wrap gap-2" },
              aspectOptions.map(function (opt) {
                var isAct = selectedAspect === opt;
                return h("button", {
                  key: opt,
                  onClick: function () { handleSaveConfig(opt); },
                  className: "ag-btn " + (isAct ? "ag-btn-primary" : "ag-btn-secondary"),
                }, opt);
              })
            ),
          ]),

          // Prompt input
          h("div", null, [
            h("label", { className: "text-xs font-semibold text-zinc-300 block mb-2" }, "Prompt Mô Tả Ảnh:"),
            h("textarea", {
              rows: 3,
              placeholder: "Mô tả bức ảnh bạn muốn sinh (ví dụ: A cybernetic hermes agent standing in futuristic neo-tokyo, 8k, cinematic lighting...)",
              value: prompt,
              onChange: function (e) { setPrompt(e.target.value); },
              className: "ag-textarea w-full",
            }),
          ]),

          // Generate button
          h("div", { className: "flex flex-wrap items-center justify-between gap-3 pt-2" }, [
            h("div", { className: "text-xs text-zinc-500 font-mono" },
              "Model: gemini-3.1-flash-image • Tự động lưu vào ~/.hermes/media/"
            ),
            h("button", {
              disabled: generating,
              onClick: handleGenerate,
              className: "ag-btn ag-btn-primary",
            }, [
              h(Icon, { name: "sparkles", className: "w-4 h-4" }),
              h("span", null, generating ? "Đang sinh ảnh..." : "Sinh Ảnh Trực Tiếp"),
            ]),
          ]),
        ]),
      ]),

      // Result Preview Card
      result && h("div", {
        className: "ag-card space-y-4",
      }, [
        h("div", { className: "flex items-center justify-between" }, [
          h("h3", { className: "text-sm font-bold text-white flex items-center gap-2" }, [
            h(Icon, { name: "check", className: "w-4 h-4 text-emerald-400" }),
            h("span", null, "Kết Quả Sinh Ảnh Thành Công"),
          ]),
          h("span", { className: "ag-badge ag-badge-emerald" }, result.aspect_ratio),
        ]),

        result.preview_data_url && h("div", {
          className: "ag-subcard max-w-xl mx-auto flex items-center justify-center overflow-hidden",
          style: { padding: "8px" },
        }, [
          h("img", {
            src: result.preview_data_url,
            alt: "Generated Preview",
            className: "w-full h-auto object-contain max-h-[480px]",
          }),
        ]),

        h("div", { className: "ag-subcard text-xs font-mono text-zinc-400 break-all" },
          "File lưu tại: " + result.image_path
        ),
      ]),
    ]);
  }

  // ===========================================================================
  // TAB 4: SYSTEM DOCTOR & LIVE LOGS
  // ===========================================================================
  function TabDoctorAndLogs(props) {
    var notify = props.notify;
    var fetchDaemon = props.fetchDaemon;

    var reportState = useState(null);
    var report = reportState[0];
    var setReport = reportState[1];

    var checkingState = useState(false);
    var checking = checkingState[0];
    var setChecking = checkingState[1];

    var logsState = useState([]);
    var logs = logsState[0];
    var setLogs = logsState[1];

    var autoScrollState = useState(true);
    var autoScroll = autoScrollState[0];
    var setAutoScroll = autoScrollState[1];

    var terminalRef = useRef(null);

    var runDoctor = useCallback(function () {
      setChecking(true);
      apiFetch("/doctor").then(function (res) {
        setReport(res);
      }).catch(function (e) {
        notify("Lỗi chạy Doctor: " + e.message, "error");
      }).finally(function () {
        setChecking(false);
      });
    }, [notify]);

    var fetchLogs = useCallback(function () {
      apiFetch("/logs?lines=150").then(function (res) {
        if (res.ok) setLogs(res.lines || []);
      }).catch(function () {});
    }, []);

    useEffect(function () {
      runDoctor();
      fetchLogs();
      var interval = setInterval(fetchLogs, 3000);
      return function () { clearInterval(interval); };
    }, [runDoctor, fetchLogs]);

    useEffect(function () {
      if (autoScroll && terminalRef.current) {
        terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
      }
    }, [logs, autoScroll]);

    return h("div", { className: "space-y-6" }, [
      // 1. Doctor 6-Point Health Suite
      h("div", { className: "ag-card" }, [
        h("div", {
          className: "flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 mb-5",
          style: { borderBottom: "1px solid rgba(255,255,255,0.08)" },
        }, [
          h("div", { className: "flex items-center gap-3" }, [
            h("div", { className: "ag-avatar ag-avatar-ready" },
              h(Icon, { name: "activity", className: "w-5 h-5" })
            ),
            h("div", null, [
              h("h2", { className: "text-sm font-bold text-white" }, "System Doctor & Self-Diagnostics"),
              h("p", { className: "text-xs text-zinc-400" }, "Kiểm tra toàn diện 6 thành phần cốt lõi của suite"),
            ]),
          ]),

          h("div", { className: "flex items-center gap-3" }, [
            report && h("div", { className: "flex items-baseline gap-1 text-xs font-mono font-bold" }, [
              h("span", { className: "text-zinc-400" }, "Điểm Sức Khỏe:"),
              h("span", { className: report.score >= 80 ? "text-emerald-400 text-sm" : "text-amber-400 text-sm" },
                report.score + "/100"
              ),
            ]),
            h("button", {
              disabled: checking,
              onClick: runDoctor,
              className: "ag-btn ag-btn-secondary",
            }, [
              h(Icon, { name: "refresh", className: "w-3.5 h-3.5" }),
              h("span", null, checking ? "Đang kiểm tra..." : "Chạy Lại Doctor"),
            ]),
          ]),
        ]),

        // Checklist items
        report && report.checks && h("div", { className: "grid grid-cols-1 md:grid-cols-2 gap-3" },
          report.checks.map(function (c) {
            var isOk = c.status === "ok";
            var isWarn = c.status === "warn";
            return h("div", {
              key: c.id,
              className: "ag-subcard flex items-start gap-3 " + (isOk ? "ag-subcard-active" : ""),
            }, [
              h("div", {
                className: "ag-avatar " + (isOk ? "ag-avatar-ready" : isWarn ? "ag-avatar-disabled" : ""),
                style: { width: "30px", height: "30px" },
              }, h(Icon, { name: isOk ? "check" : "alert", className: "w-4 h-4" })),
              h("div", { className: "overflow-hidden space-y-0.5" }, [
                h("div", { className: "text-xs font-bold text-white flex items-center gap-2" }, [
                  h("span", null, c.label),
                ]),
                h("div", { className: "text-xs text-zinc-300" }, c.message),
                c.detail && h("div", { className: "text-xs text-zinc-500 font-mono truncate" }, c.detail),
              ]),
            ]);
          })
        ),
      ]),

      // 2. Live Logs Terminal Streamer
      h("div", { className: "ag-card" }, [
        h("div", {
          className: "flex items-center justify-between pb-3 mb-4",
          style: { borderBottom: "1px solid rgba(255,255,255,0.08)" },
        }, [
          h("div", { className: "flex items-center gap-2" }, [
            h(Icon, { name: "terminal", className: "w-4 h-4 text-zinc-400" }),
            h("h3", { className: "text-xs font-bold text-white tracking-tight font-mono" }, "antigravity_bridge.log (Live Tail)"),
          ]),
          h("div", { className: "flex items-center gap-3 text-xs" }, [
            h("label", { className: "flex items-center gap-1.5 text-zinc-400 cursor-pointer text-xs" }, [
              h("input", {
                type: "checkbox",
                checked: autoScroll,
                onChange: function (e) { setAutoScroll(e.target.checked); },
              }),
              h("span", null, "Auto-scroll"),
            ]),
            h("button", {
              onClick: fetchLogs,
              className: "ag-btn ag-btn-secondary ag-btn-sm",
            }, "Làm mới"),
          ]),
        ]),

        h("div", {
          ref: terminalRef,
          className: "ag-subcard font-mono text-xs text-zinc-300 h-72 overflow-y-auto ag-scrollbar space-y-1 select-text",
          style: { background: "#050608" },
        }, [
          logs.length === 0
            ? h("div", { className: "text-zinc-600 italic" }, "Chưa có dữ liệu log ghi nhận...")
            : logs.map(function (l, idx) {
                var isErr = l.indexOf("ERROR") !== -1 || l.indexOf("Exception") !== -1;
                var isWarn = l.indexOf("WARNING") !== -1;
                var isOk = l.indexOf("HTTP/1.1 200") !== -1 || l.indexOf("SUCCESS") !== -1;
                var col = isErr ? "text-red-400" : isWarn ? "text-amber-400" : isOk ? "text-emerald-400" : "text-zinc-300";
                return h("div", { key: idx, className: col + " leading-relaxed" }, l);
              }),
        ]),
      ]),
    ]);
  }

  // ===========================================================================
  // SETTINGS SLOT WIDGET (Dual-Mode: Embedded into settings:providers)
  // ===========================================================================
  function AntigravitySettingsWidget() {
    var state = useState({ active_email: null, running: false, credits: null });
    var data = state[0];
    var setData = state[1];

    useEffect(function () {
      apiFetch("/accounts").then(function (r) {
        if (r.ok) setData(function (prev) { return Object.assign({}, prev, { active_email: r.active_email }); });
      }).catch(function () {});

      apiFetch("/daemon/status").then(function (r) {
        setData(function (prev) { return Object.assign({}, prev, { running: r.running }); });
      }).catch(function () {});

      apiFetch("/flow/status").then(function (r) {
        if (r.connected) setData(function (prev) { return Object.assign({}, prev, { credits: r.credits }); });
      }).catch(function () {});
    }, []);

    return h("div", {
      className: "ag-card",
    }, [
      h("div", { className: "flex items-center justify-between mb-3" }, [
        h("div", { className: "flex items-center gap-3" }, [
          h("div", { className: "ag-avatar ag-avatar-active" }, "AG"),
          h("div", null, [
            h("div", { className: "text-xs font-bold text-white" }, "Google Antigravity & Flow Suite"),
            h("div", { className: "text-xs text-zinc-400" }, data.active_email || "Chưa có tài khoản active"),
          ]),
        ]),
        h("span", {
          className: "ag-badge " + (data.running ? "ag-badge-emerald" : "ag-badge-neutral"),
        }, data.running ? "BRIDGE ONLINE" : "STANDBY"),
      ]),
      h("div", {
        className: "flex items-center justify-between text-xs pt-2",
        style: { borderTop: "1px solid rgba(255,255,255,0.08)" },
      }, [
        h("span", { className: "text-xs text-zinc-400" },
          data.credits != null ? "Flow Credits: " + data.credits : "Tích hợp đa mô hình"
        ),
        h("a", {
          href: "/antigravity",
          className: "ag-btn ag-btn-primary ag-btn-sm",
        }, "Mở Cockpit →"),
      ]),
    ]);
  }

  // ---------------------------------------------------------------------------
  // Register with Hermes Dashboard Plugin System
  // ---------------------------------------------------------------------------
  window.__HERMES_PLUGINS__.register("antigravity", AntigravityCockpit);

  if (window.__HERMES_PLUGINS__.registerSlot) {
    window.__HERMES_PLUGINS__.registerSlot("settings:providers", "antigravity", AntigravitySettingsWidget);
  }

  console.log("[Antigravity] Cockpit Dashboard registered successfully.");
})();
