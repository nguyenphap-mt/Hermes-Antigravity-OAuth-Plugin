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
      case "globe":
        return h("svg", p,
          h("circle", { cx: 12, cy: 12, r: 10 }),
          h("path", { d: "M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20" }),
          h("path", { d: "M2 12h20" })
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
      { id: "gemini_web", label: "Gemini Web App", icon: "globe", count: null },
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
    } else if (activeTab === "gemini_web") {
      contentNode = h(TabGeminiWebPool, { notify: notify });
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
  // TAB 1B: DEDICATED GEMINI WEB APP POOL MANAGER (`gemini.google.com/app`)
  // ===========================================================================
  function TabGeminiWebPool(props) {
    var notify = props.notify;
    var poolState = useState({
      config: {
        routing_mode: "hybrid_failover",
        rotation_strategy: "sticky_session",
        auto_rotate_cookies: true,
        preserve_server_context: true,
      },
      total_nodes: 0,
      ready_nodes: 0,
      nodes: [],
    });
    var pool = poolState[0];
    var setPool = poolState[1];

    var loadingState = useState(false);
    var loading = loadingState[0];
    var setLoading = loadingState[1];

    var showImportModalState = useState(false);
    var showImportModal = showImportModalState[0];
    var setShowImportModal = showImportModalState[1];

    var showAdvancedPasteState = useState(false);
    var showAdvancedPaste = showAdvancedPasteState[0];
    var setShowAdvancedPaste = showAdvancedPasteState[1];

    var webOauthState = useState({ loading: false, session_id: "", auth_url: "", callback_url: "" });
    var webOauth = webOauthState[0];
    var setWebOauth = webOauthState[1];

    var importFormState = useState({
      email: "",
      display_name: "",
      psid: "",
      psidts: "",
      raw_cookie_input: "",
      node_id: "",
    });
    var importForm = importFormState[0];
    var setImportForm = importFormState[1];

    var testModalNodeState = useState(null);
    var testModalNode = testModalNodeState[0];
    var setTestModalNode = testModalNodeState[1];

    var testModelState = useState("gemini-web-argon");
    var testModel = testModelState[0];
    var setTestModel = testModelState[1];

    var testPromptState = useState("Xin chào! Hãy xác nhận bạn đang phản hồi từ Gemini Web App (Argon/Pro).");
    var testPrompt = testPromptState[0];
    var setTestPrompt = testPromptState[1];

    var testResultState = useState(null);
    var testResult = testResultState[0];
    var setTestResult = testResultState[1];

    var fetchWebPool = useCallback(function () {
      apiFetch("/gemini-web/pool").then(function (res) {
        if (res && res.ok) {
          setPool(res);
        }
      }).catch(function (e) {
        console.debug("Gemini Web pool fetch error:", e);
      });
    }, []);

    useEffect(function () {
      fetchWebPool();
      var timer = setInterval(fetchWebPool, 10000);
      return function () { clearInterval(timer); };
    }, [fetchWebPool]);

    function openAutoCaptureModal(existingNode) {
      if (existingNode) {
        setImportForm({
          email: existingNode.email || "",
          display_name: existingNode.display_name || "",
          psid: "",
          psidts: "",
          raw_cookie_input: "",
          node_id: existingNode.node_id || "",
        });
      } else {
        setImportForm({ email: "", display_name: "", psid: "", psidts: "", raw_cookie_input: "", node_id: "" });
      }
      setShowAdvancedPaste(false);
      setShowImportModal(true);
      setWebOauth({ loading: true, session_id: "", auth_url: "", callback_url: "" });
      apiFetch("/accounts/login-start", { method: "POST" }).then(function (res) {
        if (res && res.ok && res.auth_url) {
          setWebOauth({
            loading: false,
            session_id: res.session_id,
            auth_url: res.auth_url,
            callback_url: "",
          });
        } else {
          setWebOauth({ loading: false, session_id: "", auth_url: "", callback_url: "" });
        }
      }).catch(function () {
        setWebOauth({ loading: false, session_id: "", auth_url: "", callback_url: "" });
      });
    }

    function handleAutoCaptureHandshake() {
      setLoading(true);
      apiFetch("/gemini-web/handshake/start", { method: "POST" }).then(function (res) {
        if (res && res.ok && res.imported_count > 0) {
          notify(res.message || ("Đã tự động bắt " + res.imported_count + " Node Gemini Web!"), "success");
          if (res.pool) setPool(res.pool);
          else fetchWebPool();
          setShowImportModal(false);
        } else if (res && res.auth_url) {
          setWebOauth({
            loading: false,
            session_id: res.session_id || "",
            auth_url: res.auth_url,
            callback_url: "",
          });
          notify("Hãy nhấn '1. Mở Trang Đăng Nhập Google' bên dưới để xác thực tài khoản mới!", "info");
        } else {
          notify((res && (res.message || res.error)) || "Chưa tìm thấy phiên có sẵn.", "warning");
        }
      }).catch(function (e) {
        notify("Lỗi bắt tự động: " + e.message, "error");
      }).finally(function () {
        setLoading(false);
      });
    }

    function handleWebOAuthSubmit() {
      if (!webOauth.session_id || !webOauth.callback_url || !webOauth.callback_url.trim()) {
        notify("Vui lòng dán đường link kết quả (http://127.0.0.1:51121/oauth-callback?code=...) vào ô Bước 2.", "warning");
        return;
      }
      setLoading(true);
      apiFetch("/accounts/login-submit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: webOauth.session_id,
          callback_url: webOauth.callback_url.trim(),
        }),
      }).then(function (res) {
        if (res && res.ok) {
          notify(res.message || ("Đã tự động thêm & đồng bộ Node Web: " + (res.email || "")), "success");
          setShowImportModal(false);
          fetchWebPool();
        } else {
          notify((res && (res.message || res.error)) || "Xác thực Google thất bại.", "error");
        }
      }).catch(function (e) {
        notify("Lỗi xác thực OAuth: " + e.message, "error");
      }).finally(function () {
        setLoading(false);
      });
    }

    function handleUpdateConfig(patch) {
      setLoading(true);
      apiFetch("/gemini-web/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      }).then(function (res) {
        if (res.ok) {
          notify(res.message, "success");
          fetchWebPool();
        }
      }).catch(function (e) {
        notify("Lỗi cập nhật cấu hình Gemini Web: " + e.message, "error");
      }).finally(function () {
        setLoading(false);
      });
    }

    function handleImportSubmit() {
      setLoading(true);
      apiFetch("/gemini-web/nodes/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(importForm),
      }).then(function (res) {
        if (res.node) {
          notify(res.message || "Đã lưu node Gemini Web!", res.ok ? "success" : "warning");
          setShowImportModal(false);
          setImportForm({ email: "", display_name: "", psid: "", psidts: "", raw_cookie_input: "", node_id: "" });
          fetchWebPool();
        } else {
          notify(res.error || "Không thể nhập Cookie Gemini Web", "error");
        }
      }).catch(function (e) {
        notify("Lỗi nhập Cookie: " + e.message, "error");
      }).finally(function () {
        setLoading(false);
      });
    }

    function handleSyncBrowser() {
      setLoading(true);
      apiFetch("/gemini-web/nodes/sync-browser", { method: "POST" }).then(function (res) {
        notify(res.message || res.error || "Đã đồng bộ từ Browser & Google Pool", res.ok ? "success" : "warning");
        if (res && res.pool) {
          setPool(res.pool);
        } else {
          fetchWebPool();
        }
      }).catch(function (e) {
        notify("Lỗi đồng bộ từ Browser Profile: " + e.message, "error");
      }).finally(function () {
        setLoading(false);
      });
    }

    function handleRotateNode(nodeId) {
      setLoading(true);
      apiFetch("/gemini-web/nodes/rotate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ node_id: nodeId || null }),
      }).then(function (res) {
        notify(res.message || "Đã xoay Cookie", res.ok ? "success" : "warning");
        fetchWebPool();
      }).catch(function (e) {
        notify("Lỗi xoay Cookie: " + e.message, "error");
      }).finally(function () {
        setLoading(false);
      });
    }

    function handleToggleNode(nodeId) {
      apiFetch("/gemini-web/nodes/toggle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ node_id: nodeId }),
      }).then(function (res) {
        notify(res.message, "success");
        fetchWebPool();
      }).catch(function (e) {
        notify("Lỗi bật/tắt node: " + e.message, "error");
      });
    }

    function handleDeleteNode(nodeId) {
      apiFetch("/gemini-web/nodes/" + encodeURIComponent(nodeId), {
        method: "DELETE",
      }).then(function (res) {
        notify(res.message || "Đã xóa node", "success");
        fetchWebPool();
      }).catch(function (e) {
        notify("Lỗi xóa node: " + e.message, "error");
      });
    }

    function handleRunTest() {
      setLoading(true);
      setTestResult({ loading: true });
      apiFetch("/gemini-web/nodes/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          node_id: testModalNode ? testModalNode.node_id : null,
          model: testModel,
          prompt: testPrompt,
        }),
      }).then(function (res) {
        setTestResult(res);
        fetchWebPool();
      }).catch(function (e) {
        setTestResult({ ok: false, error: e.message });
      }).finally(function () {
        setLoading(false);
      });
    }

    function renderQuotaBar(label, used1h, lim1h, used24h, lim24h, remPct) {
      var barColor = remPct <= 10 ? "#ef4444" : remPct <= 30 ? "#f59e0b" : "#10b981";
      return h("div", { className: "space-y-1", key: label }, [
        h("div", { className: "flex items-center justify-between text-xs" }, [
          h("span", { className: "text-zinc-300 font-semibold" }, label),
          h("span", { className: "font-mono text-zinc-400" },
            "Còn " + remPct + "% • 1h: " + used1h + "/" + lim1h + " • 24h: " + used24h + "/" + lim24h
          ),
        ]),
        h("div", {
          style: { width: "100%", height: "6px", background: "#18181b", borderRadius: "9999px", overflow: "hidden" },
        }, [
          h("div", {
            style: {
              width: Math.max(2, Math.min(100, remPct)) + "%",
              height: "100%",
              background: barColor,
              transition: "width .3s ease",
            },
          }),
        ]),
      ]);
    }

    var cfg = pool.config || {};

    return h("div", { className: "space-y-6" }, [
      // 1. Global Control Bar for Gemini Web Pool
      h("div", { className: "ag-card space-y-4", key: "gweb-header" }, [
        h("div", { className: "flex flex-col md:flex-row md:items-center justify-between gap-4" }, [
          h("div", null, [
            h("div", { className: "flex items-center gap-2" }, [
              h(Icon, { name: "globe", className: "w-5 h-5 text-emerald-400" }),
              h("h2", { className: "text-sm sm:text-base font-bold text-white" },
                "Quản Lý Bể Gemini Web App Độc Lập (gemini.google.com/app)"
              ),
              h("span", { className: "ag-badge ag-badge-emerald" },
                pool.ready_nodes + "/" + pool.total_nodes + " NODE SẴN SÀNG"
              ),
            ]),
            h("p", { className: "text-xs text-zinc-400 mt-1" },
              "Khai thác hạn mức Gemini Argon, Gemini 2.5 Pro & 2.5 Flash trực tiếp trên nền Web App (hoạt động độc lập ngay cả khi tài khoản bị hết hoặc khóa quota Code Assist)."
            ),
          ]),
          h("div", { className: "flex flex-wrap items-center gap-2" }, [
            h("button", {
              onClick: function () {
                openAutoCaptureModal(null);
              },
              className: "ag-btn ag-btn-primary",
            }, [
              h(Icon, { name: "zap", className: "w-3.5 h-3.5" }),
              h("span", null, "+ Thêm Node Web (Tự Động)"),
            ]),
            h("button", {
              disabled: loading,
              onClick: handleSyncBrowser,
              className: "ag-btn ag-btn-secondary",
            }, [
              h(Icon, { name: "refresh", className: "w-3.5 h-3.5 " + (loading ? "animate-spin" : "") }),
              h("span", null, loading ? "Đang đồng bộ..." : "Đồng Bộ Từ Browser"),
            ]),
            h("button", {
              disabled: loading || pool.total_nodes === 0,
              onClick: function () { handleRotateNode(null); },
              className: "ag-btn ag-btn-amber",
            }, [
              h(Icon, { name: "rotate", className: "w-3.5 h-3.5" }),
              h("span", null, "Xoay Cookie Toàn Bể"),
            ]),
          ]),
        ]),

        // Routing Mode & Strategy Selectors
        h("div", {
          className: "grid grid-cols-1 md:grid-cols-2 gap-4 pt-3",
          style: { borderTop: "1px solid rgba(255,255,255,0.08)" },
        }, [
          h("div", { className: "space-y-1.5" }, [
            h("label", { className: "text-xs font-semibold text-zinc-300 block" }, "Chế Độ Định Tuyến Giữa Code Assist & Gemini Web:"),
            h("select", {
              className: "ag-select w-full",
              value: cfg.routing_mode || "hybrid_failover",
              onChange: function (e) { handleUpdateConfig({ routing_mode: e.target.value }); },
            }, [
              h("option", { value: "hybrid_failover" }, "Hybrid Failover — Tự động tràn sang Gemini Web khi Code Assist <=10% hoặc 429/403"),
              h("option", { value: "web_first" }, "Web-First — Ưu tiên dùng hết Quota Gemini Web trước cho mọi model Gemini"),
              h("option", { value: "isolated" }, "Isolated — Tách biệt 100% (Chỉ dùng bể Web khi chọn model gemini-web-*)"),
            ]),
          ]),
          h("div", { className: "space-y-1.5" }, [
            h("label", { className: "text-xs font-semibold text-zinc-300 block" }, "Chiến Lược Xoay Vòng Riêng Cho Bể Gemini Web:"),
            h("select", {
              className: "ag-select w-full",
              value: cfg.rotation_strategy || "sticky_session",
              onChange: function (e) { handleUpdateConfig({ rotation_strategy: e.target.value }); },
            }, [
              h("option", { value: "sticky_session" }, "Sticky Session — Giữ ngữ cảnh hội thoại [cid, rid, rcid] phía server Google"),
              h("option", { value: "least_used" }, "Least-Used — Ưu tiên Node còn nhiều % Quota Argon/Pro nhất"),
              h("option", { value: "round_robin" }, "Round-Robin — Chia đều lượt gọi giữa các Node Web"),
            ]),
          ]),
        ]),
      ]),

      // 2. Node Cards Grid
      pool.nodes && pool.nodes.length > 0
        ? h("div", { className: "grid grid-cols-1 md:grid-cols-2 gap-4", key: "gweb-nodes" },
            pool.nodes.map(function (node) {
              var q = node.quota_summary || {};
              var ck = node.cookie_health || {};
              var isReady = node.enabled && node.status === "ready" && ck.has_1psid;
              return h("div", {
                key: node.node_id,
                className: "ag-subcard space-y-3 " + (isReady ? "ag-subcard-active" : !node.enabled ? "ag-subcard-disabled" : ""),
              }, [
                // Header
                h("div", { className: "flex items-start justify-between gap-2" }, [
                  h("div", { className: "flex items-center gap-2.5 min-w-0" }, [
                    h("div", {
                      className: "ag-avatar " + (isReady ? "ag-avatar-active" : "ag-avatar-disabled"),
                    }, (node.display_name || "GW").slice(0, 2).toUpperCase()),
                    h("div", { className: "min-w-0" }, [
                      h("div", { className: "text-xs font-bold text-white truncate" }, node.display_name),
                      h("div", { className: "text-xs text-zinc-400 font-mono truncate" }, node.email || node.node_id),
                    ]),
                  ]),
                  h("div", { className: "flex flex-wrap items-center gap-1.5" }, [
                    h("span", {
                      className: "ag-badge " + (node.detected_tier === "ultra" || node.detected_tier === "pro" ? "ag-badge-emerald" : "ag-badge-neutral"),
                    }, node.tier_badge || "GOOGLE AI PRO"),
                    h("span", {
                      className: "ag-badge " + (isReady ? "ag-badge-emerald" : "ag-badge-amber"),
                    }, !node.enabled ? "PAUSED" : node.status.toUpperCase()),
                  ]),
                ]),

                // Cookie Health Telemetry
                h("div", {
                  className: "p-2.5 rounded-lg text-xs font-mono space-y-1",
                  style: { background: "#050609", border: "1px solid rgba(255,255,255,0.06)" },
                }, [
                  h("div", { className: "flex items-center justify-between" }, [
                    h("span", { className: "text-zinc-400" }, "Phiên Google / Cookie 1PSID:"),
                    h("span", { className: ck.has_1psid ? "text-emerald-400" : "text-red-400" },
                      ck.has_1psid ? ("OK (" + (ck.psid_preview || "linked") + ")") : "Thiếu Phiên"
                    ),
                  ]),
                  h("div", { className: "flex items-center justify-between" }, [
                    h("span", { className: "text-zinc-400" }, "CSRF SNlM0e & Tự xoay 9m:"),
                    h("span", { className: ck.has_snlm0e ? "text-emerald-400" : "text-amber-400" },
                      ck.has_snlm0e
                        ? ("Hợp lệ • Xoay sau " + Math.ceil((ck.seconds_until_next_rotation || 0) / 60) + "p")
                        : "Chưa lấy SNlM0e"
                    ),
                  ]),
                ]),

                // Available Web Models Chips
                h("div", { className: "flex flex-wrap items-center gap-1.5" },
                  (node.available_models || []).map(function (m) {
                    return h("span", {
                      key: m.id,
                      className: "ag-badge ag-badge-neutral",
                    }, m.label + " (" + m.id + ")");
                  })
                ),

                // Sliding-Window Quota Bars
                h("div", { className: "space-y-2 pt-1" }, [
                  renderQuotaBar(
                    "Gemini Argon (Pro/Ultra)",
                    q.argon_1h_count || 0,
                    q.argon_1h_limit || 40,
                    q.argon_24h_count || 0,
                    q.argon_24h_limit || 200,
                    q.argon_remaining_pct != null ? q.argon_remaining_pct : 100
                  ),
                  renderQuotaBar(
                    "Gemini 2.5 Pro",
                    q.pro_1h_count || 0,
                    q.pro_1h_limit || 50,
                    q.pro_24h_count || 0,
                    q.pro_24h_limit || 300,
                    q.pro_remaining_pct != null ? q.pro_remaining_pct : 100
                  ),
                  renderQuotaBar(
                    "Gemini 2.5 Flash",
                    q.flash_1h_count || 0,
                    q.flash_1h_limit || 200,
                    q.flash_24h_count || 0,
                    q.flash_24h_limit || 1500,
                    q.flash_remaining_pct != null ? q.flash_remaining_pct : 100
                  ),
                ]),

                node.last_error && h("div", { className: "text-xs text-amber-400 font-mono truncate" },
                  "Lưu ý: " + node.last_error
                ),

                // Action Bar
                h("div", {
                  className: "flex flex-wrap items-center justify-between gap-2 pt-2",
                  style: { borderTop: "1px solid rgba(255,255,255,0.06)" },
                }, [
                  h("div", { className: "flex flex-wrap items-center gap-1.5" }, [
                    h("button", {
                      onClick: function () { handleToggleNode(node.node_id); },
                      className: "ag-btn ag-btn-sm " + (node.enabled ? "ag-btn-secondary" : "ag-btn-primary"),
                    }, node.enabled ? "Tạm dừng" : "Bật lại"),
                    h("button", {
                      onClick: function () { handleRotateNode(node.node_id); },
                      className: "ag-btn ag-btn-secondary ag-btn-sm",
                    }, "Xoay Cookie"),
                    h("button", {
                      onClick: function () {
                        openAutoCaptureModal(node);
                      },
                      className: "ag-btn ag-btn-secondary ag-btn-sm",
                    }, "Làm mới phiên"),
                    h("button", {
                      onClick: function () {
                        setTestModalNode(node);
                        setTestResult(null);
                      },
                      className: "ag-btn ag-btn-primary ag-btn-sm",
                    }, "Test Argon/Web"),
                  ]),
                  h("button", {
                    onClick: function () { handleDeleteNode(node.node_id); },
                    className: "ag-btn ag-btn-danger ag-btn-sm",
                  }, "Xóa"),
                ]),
              ]);
            })
          )
        : h("div", { className: "ag-card text-center py-8 space-y-3", key: "gweb-empty" }, [
            h("div", { className: "text-sm font-bold text-white" },
              "Chưa có Node nào trong Bể Gemini Web App"
            ),
            h("p", { className: "text-xs text-zinc-400 max-w-lg mx-auto" },
              "Nhấn 'Đồng Bộ Từ Browser' hoặc '+ Thêm Node Web (Tự Động)' để tự động bắt phiên Google (Email, Gói Pro/Ultra, Cookie & Hạn mức Argon/Pro) chỉ với 1 chạm!"
            ),
            h("div", { className: "pt-2 flex justify-center gap-2" }, [
              h("button", {
                disabled: loading,
                onClick: handleSyncBrowser,
                className: "ag-btn ag-btn-primary",
              }, [
                h(Icon, { name: "zap", className: "w-3.5 h-3.5" }),
                h("span", null, "Bắt Tự Động Từ Browser / Google Pool"),
              ]),
            ]),
          ]),

      // 3. Automatic Node Capture & Google Login Modal (Zero manual 5-field typing)
      showImportModal && h("div", { className: "ag-modal-backdrop", key: "gweb-import-modal" }, [
        h("div", { className: "ag-modal-dialog space-y-4" }, [
          h("div", {
            className: "flex items-center justify-between pb-3",
            style: { borderBottom: "1px solid rgba(255,255,255,0.08)" },
          }, [
            h("div", { className: "flex items-center gap-2.5" }, [
              h("div", { className: "ag-avatar ag-avatar-ready", style: { width: "34px", height: "34px" } },
                h(Icon, { name: "zap", className: "w-4 h-4" })
              ),
              h("div", null, [
                h("h3", { className: "text-sm font-bold text-white" },
                  "Kết Nối Tự Động Node Gemini Web App"
                ),
                h("p", { className: "text-xs text-zinc-400" },
                  "Tự động phát hiện Email, Tên hiển thị, Gói Pro/Ultra & CSRF Token (Không cần nhập tay)"
                ),
              ]),
            ]),
            h("button", {
              onClick: function () { setShowImportModal(false); },
              className: "ag-btn ag-btn-secondary ag-btn-sm",
            }, "Đóng"),
          ]),

          // Option 1: 1-Click Auto-Sync from Browser / Camofox / Flow / Google Pool
          h("div", { className: "ag-subcard space-y-2.5" }, [
            h("div", { className: "flex items-center justify-between" }, [
              h("span", { className: "text-xs font-bold text-emerald-400" },
                "Cách 1 (Khuyên dùng): Tự Động Bắt 1-Chạm Từ Trình Duyệt & Google Pool"
              ),
              h("span", { className: "ag-badge ag-badge-emerald" }, "AUTO 1-CLICK"),
            ]),
            h("p", { className: "text-xs text-zinc-400 leading-relaxed" },
              "Tự động quét và trích xuất toàn bộ phiên Google đang đăng nhập từ Browser Profile (Camofox / Flow Storage State) và Bể Google OAuth sẵn có trên hệ thống mà không cần nhập bất kỳ thông tin nào."
            ),
            h("button", {
              disabled: loading,
              onClick: handleAutoCaptureHandshake,
              className: "ag-btn ag-btn-primary w-full justify-center",
            }, [
              h(Icon, { name: "zap", className: "w-4 h-4 " + (loading ? "animate-spin" : "") }),
              h("span", null, loading ? "Đang tự động quét & bắt phiên Google..." : "🚀 Bắt Tự Động Từ Browser / Google Pool Ngay"),
            ]),
          ]),

          // Option 2: Direct Google Login on Mobile / Browser (OAuth PKCE Auto-Link)
          h("div", { className: "ag-subcard space-y-2.5" }, [
            h("div", { className: "text-xs font-bold text-cyan-400" },
              "Cách 2: Đăng Nhập Tài Khoản Google Mới (Trực Tiếp Trên Điện Thoại / Web)"
            ),
            h("p", { className: "text-xs text-zinc-400 leading-relaxed" },
              "Bước 1: Mở trang đăng nhập Google, chọn tài khoản Gmail muốn thêm. Bước 2: Copy thanh địa chỉ kết quả (http://127.0.0.1:51121/oauth-callback?code=...) dán vào ô dưới để hệ thống tự động lấy Email, Gói Pro/Ultra và gắn thẳng vào bể Gemini Web:"
            ),
            h("div", { className: "flex flex-wrap items-center gap-2" }, [
              webOauth.auth_url
                ? h("a", {
                    href: webOauth.auth_url,
                    target: "_blank",
                    rel: "noopener noreferrer",
                    className: "ag-btn ag-btn-primary ag-btn-sm",
                  }, [
                    h(Icon, { name: "key", className: "w-3.5 h-3.5" }),
                    h("span", null, "1. Mở Trang Đăng Nhập Google ↗"),
                  ])
                : h("span", { className: "text-xs text-zinc-500" },
                    webOauth.loading ? "Đang tạo link đăng nhập Google..." : "Nhấn Bắt Tự Động để tạo link"
                  ),
              webOauth.auth_url && h("button", {
                onClick: function () {
                  if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(webOauth.auth_url).catch(function () {});
                  }
                  notify("Đã sao chép link đăng nhập Google!", "info");
                },
                className: "ag-btn ag-btn-secondary ag-btn-sm",
              }, "Copy Link"),
            ]),
            h("div", { className: "flex flex-col sm:flex-row gap-2 pt-1" }, [
              h("input", {
                type: "text",
                className: "ag-input flex-1 font-mono text-xs",
                placeholder: "Bước 2: Dán link http://127.0.0.1:51121/oauth-callback?code=... vào đây",
                value: webOauth.callback_url,
                onChange: function (e) {
                  setWebOauth(Object.assign({}, webOauth, { callback_url: e.target.value }));
                },
              }),
              h("button", {
                disabled: loading,
                onClick: handleWebOAuthSubmit,
                className: "ag-btn ag-btn-primary ag-btn-sm",
              }, loading ? "Đang xác thực..." : "2. Xác Nhận & Gắn Node"),
            ]),
          ]),

          // Option 3: Collapsible 1-Box Smart Auto-Parser (Advanced)
          h("div", { className: "space-y-2" }, [
            h("button", {
              onClick: function () { setShowAdvancedPaste(!showAdvancedPaste); },
              className: "ag-btn ag-btn-secondary ag-btn-sm w-full justify-between",
            }, [
              h("span", null, "📋 Tùy chọn nâng cao: Dán nhanh 1 ô (Cookie-Editor JSON / cURL — Tự bóc tách 100%)"),
              h("span", null, showAdvancedPaste ? "▲ Thu gọn" : "▼ Mở rộng"),
            ]),
            showAdvancedPaste && h("div", { className: "ag-subcard space-y-2.5 text-xs" }, [
              h("p", { className: "text-zinc-400" },
                "Chỉ cần dán 1 ô duy nhất (mảng JSON từ Cookie-Editor, lệnh cURL, hoặc storage-state.json). Hệ thống tự động bóc tách Cookie, Email, Tên hiển thị và Gói Pro/Ultra:"
              ),
              h("textarea", {
                className: "ag-textarea w-full font-mono",
                rows: 3,
                placeholder: "Dán mảng JSON Cookie-Editor, lệnh cURL, hoặc chuỗi Cookie từ gemini.google.com/app...",
                value: importForm.raw_cookie_input,
                onChange: function (e) {
                  setImportForm(Object.assign({}, importForm, { raw_cookie_input: e.target.value }));
                },
              }),
              h("div", { className: "flex justify-end" }, [
                h("button", {
                  disabled: loading,
                  onClick: handleImportSubmit,
                  className: "ag-btn ag-btn-primary ag-btn-sm",
                }, loading ? "Đang phân tích & kết nối..." : "Tự Động Bóc Tách & Kết Nối"),
              ]),
            ]),
          ]),
        ]),
      ]),

      // 4. Live Test Playground Modal
      testModalNode && h("div", { className: "ag-modal-backdrop", key: "gweb-test-modal" }, [
        h("div", { className: "ag-modal-dialog space-y-4" }, [
          h("div", { className: "flex items-center justify-between" }, [
            h("h3", { className: "text-sm font-bold text-white" },
              "Test Trực Tiếp Gemini Web App: " + (testModalNode.display_name || testModalNode.node_id)
            ),
            h("button", {
              onClick: function () { setTestModalNode(null); },
              className: "ag-btn ag-btn-secondary ag-btn-sm",
            }, "Đóng"),
          ]),
          h("div", { className: "space-y-3 text-xs" }, [
            h("div", null, [
              h("label", { className: "text-zinc-400 block mb-1" }, "Chọn Model Nhánh Web:"),
              h("select", {
                className: "ag-select w-full",
                value: testModel,
                onChange: function (e) { setTestModel(e.target.value); },
              }, [
                h("option", { value: "gemini-web-argon" }, "Gemini Argon (gemini-web-argon — Pro/Ultra)"),
                h("option", { value: "gemini-web-2.5-pro" }, "Gemini 2.5 Pro (gemini-web-2.5-pro)"),
                h("option", { value: "gemini-web-2.5-flash" }, "Gemini 2.5 Flash (gemini-web-2.5-flash)"),
              ]),
            ]),
            h("div", null, [
              h("label", { className: "text-zinc-400 block mb-1" }, "Câu lệnh kiểm thử:"),
              h("textarea", {
                className: "ag-textarea w-full",
                rows: 3,
                value: testPrompt,
                onChange: function (e) { setTestPrompt(e.target.value); },
              }),
            ]),
            testResult && h("div", {
              className: "p-3 rounded-lg font-mono text-xs space-y-1.5",
              style: { background: "#050609", border: "1px solid rgba(255,255,255,0.1)" },
            }, [
              testResult.loading
                ? h("div", { className: "text-amber-400" }, "Đang gửi yêu cầu tới gemini.google.com/app...")
                : testResult.ok
                ? h("div", { className: "space-y-1" }, [
                    h("div", { className: "text-emerald-400 font-bold" },
                      "THÀNH CÔNG (" + testResult.latency_ms + " ms) • Model: " + testResult.model
                    ),
                    h("div", { className: "text-zinc-200 whitespace-pre-wrap" }, testResult.reply),
                  ])
                : h("div", { className: "text-red-400" }, "Lỗi: " + (testResult.error || "Unknown error")),
            ]),
          ]),
          h("div", { className: "flex items-center justify-end gap-2" }, [
            h("button", {
              disabled: loading,
              onClick: handleRunTest,
              className: "ag-btn ag-btn-primary",
            }, loading ? "Đang chạy..." : "Gửi Lệnh Test"),
          ]),
        ]),
      ]),
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

    var selectedEmailState = useState(null);
    var selectedEmail = selectedEmailState[0];
    var setSelectedEmail = selectedEmailState[1];

    var quotaLoadingState = useState(false);
    var quotaLoading = quotaLoadingState[0];
    var setQuotaLoading = quotaLoadingState[1];

    var searchState = useState("");
    var search = searchState[0];
    var setSearch = searchState[1];

    var loadingAccountsState = useState(false);
    var loadingAccounts = loadingAccountsState[0];
    var setLoadingAccounts = loadingAccountsState[1];

    function synthesizeQuotaGroups(qs) {
      if (!qs) return [];
      var gPct = qs.gemini_weekly_pct;
      var cPct = qs.claude_weekly_pct;
      var groups = [];
      if (gPct != null) {
        var b1 = [{ displayName: "Weekly Limit Remaining", remainingFraction: gPct / 100.0, bucketId: "gemini_weekly" }];
        if (qs.gemini_5h_pct != null) {
          b1.push({ displayName: "Five Hour Limit Remaining", remainingFraction: qs.gemini_5h_pct / 100.0, bucketId: "gemini_5h" });
        }
        groups.push({ displayName: "Gemini Models", buckets: b1 });
      }
      if (cPct != null) {
        var b2 = [{ displayName: "Weekly Limit Remaining", remainingFraction: cPct / 100.0, bucketId: "claude_weekly" }];
        if (qs.claude_5h_pct != null) {
          b2.push({ displayName: "Five Hour Limit Remaining", remainingFraction: qs.claude_5h_pct / 100.0, bucketId: "claude_5h" });
        }
        groups.push({ displayName: "Claude and GPT models", buckets: b2 });
      }
      return groups;
    }

    var fetchQuotaForAccount = useCallback(function (targetEmail, forceRefresh) {
      if (!targetEmail) return;
      setQuotaLoading(true);
      var url = "/antigravity/quota?email=" + encodeURIComponent(targetEmail) + (forceRefresh ? "&refresh=true" : "");
      apiFetch(url).then(function (res) {
        if (res.ok && res.summary && res.summary.groups && res.summary.groups.length > 0) {
          setQuota(res.summary);
        } else {
          setAccounts(function (latestAccs) {
            var matched = latestAccs.find(function (a) { return a.email === targetEmail; });
            if (matched && matched.quota_summary) {
              var groups = synthesizeQuotaGroups(matched.quota_summary);
              if (groups.length > 0) setQuota({ groups: groups });
            }
            return latestAccs;
          });
        }
      }).catch(function (e) {
        console.debug("Fetch quota error for " + targetEmail + ":", e);
      }).finally(function () {
        setQuotaLoading(false);
      });
    }, []);

    var loadAccounts = useCallback(function () {
      setLoadingAccounts(true);
      apiFetch("/accounts").then(function (res) {
        if (res.ok) {
          var accs = res.accounts || [];
          setAccounts(accs);
          setPoolInfo({ strategy: res.strategy, active_email: res.active_email, mode: res.mode });
          setSelectedEmail(function (prev) {
            var validPrev = prev && accs.some(function (a) { return a.email === prev; });
            var target = validPrev ? prev : (res.active_email || (accs[0] ? accs[0].email : null));
            if (target) {
              var targetAcc = accs.find(function (a) { return a.email === target; });
              if (targetAcc && targetAcc.quota_summary) {
                var groups = synthesizeQuotaGroups(targetAcc.quota_summary);
                if (groups.length > 0) setQuota({ groups: groups });
              }
              fetchQuotaForAccount(target, false);
            }
            return target;
          });
        }
      }).catch(function (e) {
        console.error("Accounts fetch failed:", e);
      }).finally(function () {
        setLoadingAccounts(false);
      });
    }, [fetchQuotaForAccount]);

    var loadModelsAndQuota = useCallback(function () {
      apiFetch("/antigravity/models").then(function (res) {
        if (res.ok) setModels(res.models || []);
      }).catch(function () {});
    }, []);

    function handleSelectAccount(email) {
      if (!email) return;
      setSelectedEmail(email);
      // Immediately preview local cached quota if available
      var matched = accounts.find(function (a) { return a.email === email; });
      if (matched && matched.quota_summary) {
        var groups = synthesizeQuotaGroups(matched.quota_summary);
        if (groups.length > 0) {
          setQuota({ groups: groups });
        }
      }
      fetchQuotaForAccount(email, false);
    }

    useEffect(function () {
      loadAccounts();
    }, [loadAccounts]);

    useEffect(function () {
      loadModelsAndQuota();
    }, [loadModelsAndQuota]);

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
                var effectiveSelectedEmail = selectedEmail || poolInfo.active_email || (accounts[0] ? accounts[0].email : null);
                var isSelected = effectiveSelectedEmail === acc.email;
                var cardCls = "ag-subcard ag-subcard-clickable flex flex-col justify-between " +
                  (isDisabled ? "ag-subcard-disabled" : (acc.is_active ? "ag-subcard-active" : "")) +
                  (isSelected ? " ag-subcard-selected" : "");
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
                  onClick: function () { handleSelectAccount(acc.email); },
                  title: "Nhấp để xem hạn mức Quota chi tiết của " + acc.email,
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
                      h("div", { className: "flex items-center gap-1.5 flex-shrink-0" }, [
                        isSelected && h("span", {
                          className: "ag-badge ag-badge-cyan",
                          title: "Đang xem hạn mức Quota của tài khoản này ở bảng bên dưới",
                        }, "👁 ĐANG XEM"),
                        acc.is_active && !isDisabled && h("span", {
                          className: "ag-badge ag-badge-emerald",
                        }, "ACTIVE"),
                      ]),
                    ]),

                    // Plan, Role, Health Score, and Status tags
                    h("div", { className: "flex flex-wrap items-center gap-1.5" }, [
                      h("span", {
                        className: planBadgeCls,
                        title: "Gói Google AI: " + (planName || "Free Tier"),
                      }, planLabel),
                      h("span", {
                        className: "ag-badge ag-badge-neutral",
                      }, "Role: " + (acc.role || "all").toUpperCase()),
                      acc.health_score != null && !isDisabled && h("span", {
                        className: "ag-badge " + (acc.health_score >= 100 ? "ag-badge-cyan" : (acc.health_score > 15 ? "ag-badge-emerald" : "ag-badge-amber")),
                        title: "Điểm sức khỏe định tuyến (Quota % × Trọng số Gói - Phạt tải đồng thời)",
                      }, "Score: " + Math.round(acc.health_score)),
                      isDisabled
                        ? h("span", {
                            className: "ag-badge ag-badge-red",
                          }, "BỊ KHÓA")
                        : (acc.model_cooldowns && (acc.model_cooldowns.claude || acc.model_cooldowns.gemini))
                          ? [
                              acc.model_cooldowns.claude && h("span", {
                                key: "cd-claude",
                                className: "ag-badge ag-badge-amber",
                                title: "Nhánh Claude/GPT đang tạm nghỉ; nhánh Gemini vẫn khả dụng",
                              }, "Claude CD: " + acc.model_cooldowns.claude + "s"),
                              acc.model_cooldowns.gemini && h("span", {
                                key: "cd-gemini",
                                className: "ag-badge ag-badge-amber",
                                title: "Nhánh Gemini đang tạm nghỉ; nhánh Claude/GPT vẫn khả dụng",
                              }, "Gemini CD: " + acc.model_cooldowns.gemini + "s"),
                            ]
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
                      onClick: function (e) { e.stopPropagation(); handleSwitch(acc.email); },
                      className: "ag-btn ag-btn-primary ag-btn-sm",
                    }, "Chọn Active"),
                    (isDisabled || isCooling) && h("button", {
                      disabled: checkingUnlock === acc.email || checkingUnlock === "all",
                      onClick: function (e) { e.stopPropagation(); handleCheckUnlock(acc.email); },
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
                      onClick: function (e) { e.stopPropagation(); },
                      className: "ag-btn ag-btn-secondary ag-btn-sm",
                      title: "Mở biểu mẫu kháng nghị chính thức của Google Antigravity",
                    }, "Kháng nghị ↗"),
                    h("button", {
                      disabled: refreshingPlanQuota,
                      onClick: function (e) { e.stopPropagation(); handleRefreshPlanQuota(acc.email); },
                      className: "ag-btn ag-btn-secondary ag-btn-icon",
                      style: { width: "28px", height: "28px", borderRadius: "8px" },
                      title: "Quét lại Plan & Quota của tài khoản này",
                    }, h(Icon, { name: "refresh", className: "w-3.5 h-3.5 " + (refreshingPlanQuota ? "animate-spin" : "") })),
                    h("select", {
                      value: acc.role,
                      onClick: function (e) { e.stopPropagation(); },
                      onChange: function (e) { e.stopPropagation(); handleRole(acc.email, e.target.value); },
                      className: "ag-select",
                      style: { padding: "4px 8px", fontSize: "11px", marginLeft: "auto" },
                    }, [
                      h("option", { value: "all", key: "r-all" }, "Role: ALL"),
                      h("option", { value: "llm", key: "r-llm" }, "Role: LLM"),
                      h("option", { value: "image_gen", key: "r-img" }, "Role: Image"),
                    ]),
                    h("button", {
                      onClick: function (e) { e.stopPropagation(); handleRemove(acc.email); },
                      className: "ag-btn ag-btn-danger ag-btn-icon",
                      style: { width: "28px", height: "28px", borderRadius: "8px" },
                      title: "Xóa tài khoản",
                    }, h(Icon, { name: "trash", className: "w-3.5 h-3.5" })),
                  ]),
                ]);
              })
            ),
      ]),

      // 2. Quota Telemetry for Selected Account
      (function () {
        var effectiveSelectedEmail = selectedEmail || poolInfo.active_email || (accounts[0] ? accounts[0].email : null);
        var currentAccount = accounts.find(function (a) { return a.email === effectiveSelectedEmail; }) || accounts[0] || null;
        if (!currentAccount) return null;

        var isPro = currentAccount.plan_type === "pro";
        var isUltra = currentAccount.plan_type === "ultra";
        var planBadge = isUltra
          ? h("span", { className: "ag-badge ag-badge-purple" }, "⚡ " + (currentAccount.plan_name || "Google AI Ultra"))
          : (isPro
              ? h("span", { className: "ag-badge ag-badge-blue" }, "💎 " + (currentAccount.plan_name || "Google AI Pro"))
              : h("span", { className: "ag-badge ag-badge-neutral" }, "🌱 " + (currentAccount.plan_name || "Free Tier")));

        var displayGroups = (quota && quota.groups && quota.groups.length > 0)
          ? quota.groups
          : (currentAccount.quota_summary ? synthesizeQuotaGroups(currentAccount.quota_summary) : []);

        return h("div", {
          className: "ag-card",
          id: "ag-quota-section",
        }, [
          h("div", {
            className: "flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 mb-4",
            style: { borderBottom: "1px solid rgba(255,255,255,0.08)" },
          }, [
            h("div", { className: "flex items-center gap-3" }, [
              h("div", { className: "ag-avatar " + (currentAccount.is_active ? "ag-avatar-active" : "ag-avatar-ready") },
                (currentAccount.email[0] || "U").toUpperCase()
              ),
              h("div", null, [
                h("div", { className: "flex flex-wrap items-center gap-2" }, [
                  h("h3", { className: "text-sm font-bold text-white" }, "Hạn Mức Quota API: " + currentAccount.email),
                  planBadge,
                  currentAccount.is_active && h("span", { className: "ag-badge ag-badge-emerald" }, "ACTIVE"),
                  h("span", { className: "ag-badge ag-badge-cyan" }, "ĐANG XEM CHI TIẾT"),
                ]),
                h("p", { className: "text-xs text-zinc-400 mt-0.5" },
                  "Theo dõi tỷ lệ sử dụng thực tế và chu kỳ hồi phục • Nhấp vào bất kỳ thẻ tài khoản nào ở trên để xem quota của tài khoản đó"
                ),
              ]),
            ]),

            h("div", { className: "flex items-center gap-2" }, [
              h("button", {
                disabled: quotaLoading,
                onClick: function () { fetchQuotaForAccount(currentAccount.email, true); },
                className: "ag-btn ag-btn-secondary ag-btn-sm",
                title: "Quét trực tiếp hạn mức Quota từ Google Code Assist cho " + currentAccount.email,
              }, [
                h(Icon, { name: "refresh", className: "w-3.5 h-3.5 " + (quotaLoading ? "animate-spin" : "") }),
                h("span", null, quotaLoading ? "Đang quét Quota..." : "Làm mới Quota tài khoản này"),
              ]),
            ]),
          ]),

          (quotaLoading && displayGroups.length === 0)
            ? h("div", { className: "py-10 text-center text-xs text-zinc-400" }, [
                h(Icon, { name: "refresh", className: "w-5 h-5 animate-spin mx-auto mb-2 text-cyan-400" }),
                h("span", null, "Đang kết nối Google Code Assist để lấy dữ liệu hạn mức của " + currentAccount.email + "..."),
              ])
            : displayGroups.length > 0
              ? h("div", { className: "grid grid-cols-1 md:grid-cols-2 gap-4" },
                  displayGroups.map(function (grp, idx) {
                    return h("div", { key: idx, className: "ag-subcard" }, [
                      h("div", { className: "text-xs font-semibold text-zinc-200 mb-2 flex items-center justify-between" }, [
                        h("span", null, grp.displayName || "Group"),
                        h("span", { className: "text-[11px] text-zinc-500 font-mono" }, currentAccount.email),
                      ]),
                      h("div", { className: "space-y-3" },
                        (grp.buckets || []).map(function (b, bIdx) {
                          var rem = b.remainingFraction != null ? b.remainingFraction : 0;
                          var pct = Math.round(rem * 100);
                          var isZero = pct <= 0;
                          var isLow = pct <= 20;
                          return h("div", { key: bIdx, className: "space-y-1" }, [
                            h("div", { className: "flex justify-between text-xs font-mono" }, [
                              h("span", { className: "text-zinc-400" }, b.displayName || b.bucketId),
                              h("span", {
                                className: isZero ? "text-red-400 font-bold" : (isLow ? "text-amber-400 font-bold" : "text-emerald-400 font-bold"),
                              }, pct + "% còn lại"),
                            ]),
                            h("div", { className: "w-full h-1.5 rounded-full bg-zinc-800 overflow-hidden" }, [
                              h("div", {
                                className: "h-full rounded-full",
                                style: {
                                  width: Math.max(0, Math.min(100, pct)) + "%",
                                  background: isZero ? "#f87171" : (isLow ? "#f59e0b" : "linear-gradient(90deg, #10b981, #06b6d4)"),
                                },
                              }),
                            ]),
                          ]);
                        })
                      ),
                    ]);
                  })
                )
              : h("div", { className: "py-8 text-center text-xs text-zinc-400 ag-subcard" }, [
                  h("p", { className: "mb-2 text-zinc-300" }, "Chưa tải được bảng quota chi tiết từ Google Code Assist cho tài khoản này."),
                  h("button", {
                    onClick: function () { fetchQuotaForAccount(currentAccount.email, true); },
                    className: "ag-btn ag-btn-primary ag-btn-sm",
                  }, "Quét Quota Trực Tiếp Ngay"),
                ]),
        ]);
      })(),

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
