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
      className: "bg-[#0e1118] border border-white/[0.08] rounded-2xl p-5 mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-xl",
    }, [
      // Left identity
      h("div", { className: "flex items-center gap-4", key: "ident" }, [
        h("div", {
          className: "w-12 h-12 rounded-xl bg-gradient-to-br from-emerald-500/20 to-cyan-500/20 border border-emerald-500/30 flex items-center justify-center text-emerald-400 shadow-inner",
        }, h(Icon, { name: "zap", className: "w-6 h-6" })),
        h("div", null, [
          h("div", { className: "flex items-center gap-2" }, [
            h("h1", { className: "text-lg font-bold text-white tracking-tight" }, "Antigravity & Google Flow Suite"),
            h("span", {
              className: "text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-semibold",
            }, "v3.1.0 Enterprise"),
          ]),
          h("p", { className: "text-xs text-zinc-400 mt-0.5" },
            "Buồng lái quản trị Google Antigravity OAuth, 32+ Models, Sinh ảnh & Veo 3.1 Video"
          ),
        ]),
      ]),

      // Right Daemon Telemetry & Controls
      h("div", { className: "flex items-center gap-3", key: "controls" }, [
        // Daemon pill
        h("div", {
          className: "flex items-center gap-2 px-3 py-1.5 rounded-xl bg-[#090a0f] border border-white/[0.07] text-xs font-mono",
        }, [
          h("span", {
            className: "w-2 h-2 rounded-full " + (daemon.running ? "bg-emerald-400 ag-led-pulse" : "bg-zinc-600"),
          }),
          h("span", { className: daemon.running ? "text-emerald-400 font-medium" : "text-zinc-400" },
            daemon.running ? "PROXY :8100 [ONLINE]" : "PROXY [STANDBY]"
          ),
          daemon.pid && h("span", { className: "text-[10px] text-zinc-500 border-l border-zinc-800 pl-2" },
            "PID " + daemon.pid
          ),
        ]),

        // Action buttons
        daemon.running
          ? h("div", { className: "flex items-center gap-1.5", key: "act-run" }, [
              h("button", {
                disabled: daemonLoading,
                onClick: function () { handleDaemonControl("restart"); },
                className: "p-2 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-zinc-300 border border-zinc-800 hover:border-zinc-700 transition text-xs flex items-center gap-1",
                title: "Khởi động lại Bridge Daemon",
              }, h(Icon, { name: "rotate", className: "w-3.5 h-3.5" })),
              h("button", {
                disabled: daemonLoading,
                onClick: function () { handleDaemonControl("stop"); },
                className: "p-2 rounded-lg bg-red-950/40 hover:bg-red-900/50 text-red-400 border border-red-900/30 hover:border-red-800 transition text-xs flex items-center gap-1",
                title: "Dừng Bridge Daemon",
              }, h(Icon, { name: "square", className: "w-3.5 h-3.5" })),
            ])
          : h("button", {
              disabled: daemonLoading,
              onClick: function () { handleDaemonControl("start"); },
              className: "px-3 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-xs flex items-center gap-1.5 transition shadow-md shadow-emerald-950",
              key: "act-start",
            }, [
              h(Icon, { name: "play", className: "w-3.5 h-3.5" }),
              h("span", null, "Kích hoạt Daemon"),
            ]),

        h("button", {
          onClick: function () { fetchDaemon(); notify("Đã làm mới telemetry", "success"); },
          className: "p-2 rounded-xl bg-zinc-900 hover:bg-zinc-800 text-zinc-300 border border-zinc-800 transition",
          title: "Làm mới dữ liệu",
        }, h(Icon, { name: "refresh", className: "w-4 h-4" })),
      ]),
    ]);

    // -------------------------------------------------------------------------
    // Tabs Navigation Bar
    // -------------------------------------------------------------------------
    var tabs = [
      { id: "oauth", label: "OAuth & Models", icon: "shield", count: null },
      { id: "flow", label: "Google Flow Video", icon: "video", count: null },
      { id: "image", label: "Image Gen Studio", icon: "image", count: null },
      { id: "doctor", label: "Doctor & Logs", icon: "activity", count: null },
    ];

    var navNode = h("div", {
      className: "flex items-center gap-2 border-b border-white/[0.08] pb-3 mb-6 overflow-x-auto ag-scrollbar",
      key: "tabs-nav",
    }, tabs.map(function (tab) {
      var isActive = activeTab === tab.id;
      return h("button", {
        key: tab.id,
        onClick: function () { setActiveTab(tab.id); },
        className: "px-4 py-2 rounded-xl text-xs font-medium flex items-center gap-2 transition border " +
          (isActive
            ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30 shadow-sm"
            : "bg-[#0e1118] text-zinc-400 border-white/[0.06] hover:text-zinc-200 hover:border-zinc-700"),
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

    function handleAddAccount() {
      notify("Đang mở trình duyệt đăng nhập Google OAuth PKCE...", "info");
      apiFetch("/accounts/login-start", { method: "POST" })
        .then(function (res) {
          if (res.ok) {
            notify("Đăng nhập thành công: " + res.email, "success");
            loadAccounts();
          } else {
            notify(res.message || "Đăng nhập thất bại", "error");
          }
        })
        .catch(function (e) {
          notify("Lỗi luồng OAuth: " + e.message, "error");
        });
    }

    // Filter models
    var filteredModels = models.filter(function (m) {
      if (!search) return true;
      var q = search.toLowerCase();
      return m.id.toLowerCase().indexOf(q) !== -1 || m.display_name.toLowerCase().indexOf(q) !== -1;
    });

    return h("div", { className: "space-y-6" }, [
      // 1. Account Pool Card
      h("div", { className: "bg-[#0e1118] border border-white/[0.08] rounded-2xl p-6 shadow-xl" }, [
        h("div", { className: "flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-white/[0.06] mb-5" }, [
          h("div", { className: "flex items-center gap-3" }, [
            h("div", { className: "w-9 h-9 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400" },
              h(Icon, { name: "user", className: "w-5 h-5" })
            ),
            h("div", null, [
              h("h2", { className: "text-sm font-bold text-white" }, "Google Antigravity OAuth Account Pool"),
              h("p", { className: "text-xs text-zinc-400" }, poolInfo.mode + " • " + accounts.length + " tài khoản"),
            ]),
          ]),

          h("div", { className: "flex items-center gap-3" }, [
            // Strategy dropdown
            h("div", { className: "flex items-center gap-2 text-xs" }, [
              h("span", { className: "text-zinc-400 hidden sm:inline" }, "Chiến lược:"),
              h("select", {
                value: poolInfo.strategy,
                onChange: function (e) { handleStrategy(e.target.value); },
                className: "bg-[#090a0f] border border-zinc-800 text-zinc-200 rounded-xl px-2.5 py-1.5 text-xs outline-none focus:border-emerald-500",
              }, [
                h("option", { value: "fill_first", key: "ff" }, "Fill-First (Dùng cạn mới đổi)"),
                h("option", { value: "round_robin", key: "rr" }, "Round-Robin (Xoay vòng đều)"),
                h("option", { value: "least_used", key: "lu" }, "Least-Used (Ưu tiên ít dùng)"),
                h("option", { value: "sharded", key: "sh" }, "Sharded (Phân mảnh thông minh)"),
              ]),
            ]),

            h("button", {
              onClick: handleAddAccount,
              className: "px-3.5 py-1.5 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-medium text-xs flex items-center gap-1.5 transition shadow-md shadow-emerald-950",
            }, [
              h(Icon, { name: "key", className: "w-3.5 h-3.5" }),
              h("span", null, "+ Đăng nhập Tài Khoản"),
            ]),
          ]),
        ]),

        // Account Bento Grid
        accounts.length === 0
          ? h("div", { className: "text-center py-10 text-zinc-500 text-xs" },
              "Chưa có tài khoản nào trong pool. Nhấn '+ Đăng nhập Tài Khoản' để xác thực."
            )
          : h("div", { className: "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4" },
              accounts.map(function (acc) {
                return h("div", {
                  key: acc.email,
                  className: "bg-[#090a0f] border " + (acc.is_active ? "border-emerald-500/40 bg-emerald-500/[0.02]" : "border-white/[0.06]") + " rounded-xl p-4 flex flex-col justify-between transition hover:border-zinc-700",
                }, [
                  h("div", { className: "space-y-2" }, [
                    h("div", { className: "flex items-start justify-between gap-2" }, [
                      h("div", { className: "flex items-center gap-2 overflow-hidden" }, [
                        h("div", {
                          className: "w-8 h-8 rounded-lg " + (acc.is_active ? "bg-emerald-600" : "bg-zinc-800") + " text-white flex items-center justify-center font-bold text-xs shrink-0",
                        }, (acc.email[0] || "U").toUpperCase()),
                        h("div", { className: "overflow-hidden" }, [
                          h("div", { className: "text-xs font-semibold text-white truncate", title: acc.email }, acc.email),
                          h("div", { className: "text-[10px] text-zinc-500 font-mono" }, acc.project_id || "default-project"),
                        ]),
                      ]),
                      acc.is_active && h("span", {
                        className: "px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30",
                      }, "ACTIVE"),
                    ]),

                    // Role and Status tags
                    h("div", { className: "flex flex-wrap items-center gap-1.5 pt-1" }, [
                      h("span", {
                        className: "text-[10px] px-2 py-0.5 rounded-md bg-zinc-900 border border-zinc-800 text-zinc-300 font-mono",
                      }, "Role: " + acc.role.toUpperCase()),
                      acc.cooldown_seconds > 0
                        ? h("span", {
                            className: "text-[10px] px-2 py-0.5 rounded-md bg-amber-950/40 border border-amber-800/30 text-amber-400 font-mono",
                          }, "Cooldown: " + acc.cooldown_seconds + "s")
                        : h("span", {
                            className: "text-[10px] px-2 py-0.5 rounded-md bg-emerald-950/40 border border-emerald-800/30 text-emerald-400 font-mono",
                          }, "READY"),
                      h("span", {
                        className: "text-[10px] px-2 py-0.5 rounded-md bg-zinc-900 border border-zinc-800 text-zinc-400 font-mono ml-auto",
                      }, acc.usage_count + " reqs"),
                    ]),
                  ]),

                  // Actions
                  h("div", { className: "flex items-center gap-2 pt-4 mt-3 border-t border-zinc-900" }, [
                    !acc.is_active && h("button", {
                      onClick: function () { handleSwitch(acc.email); },
                      className: "text-[11px] font-medium text-emerald-400 hover:text-emerald-300 transition",
                    }, "Chọn Active"),
                    h("select", {
                      value: acc.role,
                      onChange: function (e) { handleRole(acc.email, e.target.value); },
                      className: "text-[10px] bg-zinc-900 border border-zinc-800 text-zinc-400 rounded px-1.5 py-0.5 ml-auto outline-none",
                    }, [
                      h("option", { value: "all", key: "r-all" }, "Role: ALL"),
                      h("option", { value: "llm", key: "r-llm" }, "Role: LLM"),
                      h("option", { value: "image_gen", key: "r-img" }, "Role: Image"),
                    ]),
                    h("button", {
                      onClick: function () { handleRemove(acc.email); },
                      className: "text-zinc-500 hover:text-red-400 transition p-1",
                      title: "Xóa tài khoản",
                    }, h(Icon, { name: "trash", className: "w-3.5 h-3.5" })),
                  ]),
                ]);
              })
            ),
      ]),

      // 2. Quota Telemetry (If Available)
      quota && quota.groups && quota.groups.length > 0 && h("div", {
        className: "bg-[#0e1118] border border-white/[0.08] rounded-2xl p-6 shadow-xl",
      }, [
        h("div", { className: "flex items-center gap-3 pb-3 border-b border-white/[0.06] mb-4" }, [
          h("div", { className: "w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400" },
            h(Icon, { name: "activity", className: "w-4 h-4" })
          ),
          h("div", null, [
            h("h3", { className: "text-sm font-bold text-white" }, "Hạn Mức Quota API (Google Code Assist)"),
            h("p", { className: "text-xs text-zinc-400" }, "Theo dõi tỷ lệ sử dụng thực tế và chu kỳ hồi phục hạn mức"),
          ]),
        ]),

        h("div", { className: "grid grid-cols-1 md:grid-cols-2 gap-4" },
          quota.groups.map(function (grp, idx) {
            return h("div", { key: idx, className: "bg-[#090a0f] border border-zinc-800/80 rounded-xl p-4" }, [
              h("div", { className: "text-xs font-semibold text-zinc-200 mb-2" }, grp.displayName || "Group"),
              h("div", { className: "space-y-3" },
                (grp.buckets || []).map(function (b, bIdx) {
                  var rem = b.remainingFraction || 0;
                  var pct = Math.round(rem * 100);
                  return h("div", { key: bIdx, className: "space-y-1" }, [
                    h("div", { className: "flex justify-between text-[11px] font-mono" }, [
                      h("span", { className: "text-zinc-400" }, b.displayName || b.bucketId),
                      h("span", { className: pct > 20 ? "text-emerald-400 font-bold" : "text-amber-400 font-bold" }, pct + "% còn lại"),
                    ]),
                    h("div", { className: "w-full h-1.5 rounded-full bg-zinc-800 overflow-hidden" }, [
                      h("div", {
                        className: "h-full rounded-full " + (pct > 20 ? "bg-gradient-to-r from-emerald-500 to-cyan-500" : "bg-amber-500"),
                        style: { width: pct + "%" },
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
      h("div", { className: "bg-[#0e1118] border border-white/[0.08] rounded-2xl p-6 shadow-xl" }, [
        h("div", { className: "flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-white/[0.06] mb-5" }, [
          h("div", { className: "flex items-center gap-3" }, [
            h("div", { className: "w-8 h-8 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400" },
              h(Icon, { name: "zap", className: "w-4 h-4" })
            ),
            h("div", null, [
              h("h3", { className: "text-sm font-bold text-white flex items-center gap-2" }, [
                h("span", null, "Danh Mục Mô Hình Khả Dụng"),
                h("span", { className: "text-[10px] font-mono px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/30" },
                  models.length + " Models"
                ),
              ]),
              h("p", { className: "text-xs text-zinc-400" }, "Tự động khám phá qua quyền hạn tài khoản (Gemini 3.7, Claude Sonnet/Opus, GPT-OSS)"),
            ]),
          ]),

          h("div", { className: "relative w-full sm:w-64" }, [
            h(Icon, { name: "search", className: "w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" }),
            h("input", {
              type: "text",
              placeholder: "Tìm mô hình...",
              value: search,
              onChange: function (e) { setSearch(e.target.value); },
              className: "w-full bg-[#090a0f] border border-zinc-800 text-zinc-200 rounded-xl pl-8 pr-3 py-1.5 text-xs outline-none focus:border-indigo-500",
            }),
          ]),
        ]),

        h("div", { className: "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 max-h-[420px] overflow-y-auto pr-1 ag-scrollbar" },
          filteredModels.map(function (m) {
            return h("div", {
              key: m.id,
              className: "bg-[#090a0f] border border-white/[0.05] hover:border-indigo-500/30 rounded-xl p-3.5 transition flex flex-col justify-between",
            }, [
              h("div", { className: "space-y-1.5" }, [
                h("div", { className: "flex items-start justify-between gap-1" }, [
                  h("div", { className: "text-xs font-semibold text-white tracking-tight" }, m.display_name),
                  m.recommended && h("span", {
                    className: "text-[9px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-medium",
                  }, "GỢI Ý"),
                ]),
                h("div", { className: "text-[10px] font-mono text-zinc-500 truncate", title: m.id }, m.id),
              ]),

              h("div", { className: "flex items-center gap-2 pt-2.5 mt-2 border-t border-zinc-900 text-[10px] font-mono text-zinc-400" }, [
                h("span", null, "Context: " + (m.max_tokens >= 1024 ? Math.round(m.max_tokens / 1024) + "k" : m.max_tokens)),
                m.supports_thinking && h("span", {
                  className: "px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 ml-auto",
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
      h("div", { className: "bg-[#0e1118] border border-white/[0.08] rounded-2xl p-6 shadow-xl relative overflow-hidden" }, [
        h("div", { className: "flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-white/[0.06] mb-5" }, [
          h("div", { className: "flex items-center gap-3" }, [
            h("div", { className: "w-9 h-9 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400" },
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
                  className: "px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1.5",
                }, [
                  h("span", { className: "w-2 h-2 rounded-full bg-emerald-400 ag-led-pulse" }),
                  h("span", null, "Đã Kết Nối (Active)"),
                ])
              : hasAccount
                ? h("span", {
                    className: "px-3 py-1 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20 flex items-center gap-1.5",
                  }, [
                    h("span", { className: "w-2 h-2 rounded-full bg-amber-400 ag-led-pulse" }),
                    h("span", null, "Session 30 Ngày Sẵn Sàng (Cần Làm Mới)"),
                  ])
                : h("span", {
                    className: "px-3 py-1 rounded-full text-xs font-semibold bg-zinc-800 text-zinc-400 border border-zinc-700",
                  }, "Chưa Kết Nối"),
          ]),
        ]),

        // State: Has Registered Account View
        hasAccount
          ? h("div", { className: "space-y-5" }, [
              h("div", { className: "grid grid-cols-1 md:grid-cols-3 gap-4" }, [
                h("div", { className: "bg-[#090a0f] border border-white/[0.06] rounded-xl p-4 flex items-center gap-3" }, [
                  h("div", {
                    className: "w-10 h-10 rounded-full " + (isReady ? "bg-blue-600" : "bg-zinc-800 border border-zinc-700") + " flex items-center justify-center font-bold text-white overflow-hidden uppercase",
                  }, (activeEmail || "F")[0]),
                  h("div", { className: "overflow-hidden" }, [
                    h("div", { className: "text-[10px] text-zinc-500" }, "Tài khoản Google Flow (Đang chọn)"),
                    h("div", { className: "text-xs font-semibold text-white truncate", title: activeEmail }, activeEmail || "lecao043@gmail.com"),
                  ]),
                ]),

                h("div", { className: "bg-[#090a0f] border border-white/[0.06] rounded-xl p-4" }, [
                  h("div", { className: "text-[10px] text-zinc-500" }, "Số dư Tín Dụng AI (Credits)"),
                  h("div", { className: "flex items-baseline gap-1 mt-0.5" }, [
                    h("span", { className: "text-xl font-bold text-emerald-400 font-mono" }, flowStatus && flowStatus.credits != null ? flowStatus.credits : "--"),
                    h("span", { className: "text-[10px] text-zinc-400" }, "credits"),
                  ]),
                ]),

                h("div", { className: "bg-[#090a0f] border border-white/[0.06] rounded-xl p-4" }, [
                  h("div", { className: "text-[10px] text-zinc-500" }, "Thời hạn Phiên Google"),
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
                  className: "px-3.5 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold flex items-center gap-2 transition shadow-md shadow-blue-950",
                }, [
                  h(Icon, { name: "refresh", className: "w-3.5 h-3.5" }),
                  h("span", null, "Làm mới Token Ngầm"),
                ]),
                h("button", {
                  onClick: startHandshake,
                  className: "px-3.5 py-2 rounded-xl bg-zinc-900 hover:bg-zinc-800 text-zinc-200 text-xs font-medium flex items-center gap-2 transition border border-zinc-800",
                }, [
                  h(Icon, { name: "key", className: "w-3.5 h-3.5" }),
                  h("span", null, "Đăng nhập lại (1-Click Handshake)"),
                ]),
                h("button", {
                  onClick: handleDisconnect,
                  className: "px-3.5 py-2 rounded-xl bg-red-950/30 hover:bg-red-900/40 text-red-400 text-xs font-medium flex items-center gap-1.5 transition border border-red-900/30 ml-auto",
                }, [
                  h(Icon, { name: "trash", className: "w-3.5 h-3.5" }),
                  h("span", null, "Ngắt kết nối"),
                ]),
              ]),
            ])
          : h("div", { className: "text-center py-8 space-y-4" }, [
              h("div", {
                className: "w-14 h-14 rounded-2xl bg-blue-500/10 text-blue-400 flex items-center justify-center mx-auto border border-blue-500/20",
              }, h(Icon, { name: "film", className: "w-7 h-7" })),
              h("div", null, [
                h("h3", { className: "text-base font-bold text-white" }, "Chưa kết nối Google Flow"),
                h("p", { className: "text-xs text-zinc-400 max-w-md mx-auto mt-1" },
                  "Nhấn nút bên dưới để khởi chạy 1-Click Handshake. Cửa sổ trình duyệt sẽ tự động mở trên màn hình, bạn chỉ cần nhấn vào tài khoản Google và cửa sổ sẽ tự động đóng sau 1-2 giây!"
                ),
              ]),
              h("button", {
                onClick: startHandshake,
                className: "px-6 py-3 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-semibold text-xs shadow-lg shadow-blue-950 transition flex items-center gap-2 mx-auto",
              }, [
                h(Icon, { name: "zap", className: "w-4 h-4" }),
                h("span", null, "Kết Nối 1-Click Handshake"),
              ]),
            ]),
      ]),

      // 2. Multi-Account Pool Bento Grid
      h("div", { className: "bg-[#0e1118] border border-white/[0.08] rounded-2xl p-6 shadow-xl" }, [
        h("div", { className: "flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-white/[0.06] mb-5" }, [
          h("div", { className: "flex items-center gap-3" }, [
            h("div", { className: "w-9 h-9 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400" },
              h(Icon, { name: "user", className: "w-5 h-5" })
            ),
            h("div", null, [
              h("h3", { className: "text-sm font-bold text-white" }, "Google Flow Multi-Account Pool"),
              h("p", { className: "text-xs text-zinc-400" }, (flowAccounts.length || 1) + " tài khoản đã đăng ký • Tự động chuyển đổi tài khoản khi hết quota"),
            ]),
          ]),
          h("button", {
            onClick: startHandshake,
            className: "px-3.5 py-1.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-medium text-xs flex items-center gap-1.5 transition shadow-md shadow-blue-950",
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
                var emailDisplay = acc.email || activeEmail || "lecao043@gmail.com";
                return h("div", {
                  key: acc.id,
                  className: "bg-[#090a0f] border " + (isAct ? "border-blue-500/40 bg-blue-500/[0.02]" : "border-white/[0.06]") + " rounded-xl p-4 flex flex-col justify-between transition hover:border-zinc-700",
                }, [
                  h("div", { className: "space-y-2" }, [
                    h("div", { className: "flex items-start justify-between gap-2" }, [
                      h("div", { className: "flex items-center gap-2 overflow-hidden" }, [
                        h("div", {
                          className: "w-8 h-8 rounded-lg " + (isAct ? "bg-blue-600" : "bg-zinc-800") + " text-white flex items-center justify-center font-bold text-xs shrink-0 uppercase",
                        }, (emailDisplay[0] || "F")),
                        h("div", { className: "overflow-hidden" }, [
                          h("div", { className: "text-xs font-semibold text-white truncate", title: emailDisplay }, emailDisplay),
                          h("div", { className: "text-[10px] text-zinc-500 font-mono" }, "ID: " + acc.id + (acc.label ? " • " + acc.label : "")),
                        ]),
                      ]),
                      isAct && h("span", {
                        className: "px-2 py-0.5 rounded-full text-[10px] font-semibold bg-blue-500/10 text-blue-400 border border-blue-500/30",
                      }, "ACTIVE"),
                    ]),
                    h("div", { className: "flex flex-wrap items-center gap-1.5 pt-1" }, [
                      h("span", {
                        className: "text-[10px] px-2 py-0.5 rounded-md bg-zinc-900 border border-zinc-800 text-zinc-300 font-mono",
                      }, acc.status.toUpperCase()),
                      h("span", {
                        className: "text-[10px] px-2 py-0.5 rounded-md bg-zinc-900 border border-zinc-800 text-zinc-400 font-mono ml-auto",
                      }, (acc.total_creations || 0) + " video tạo"),
                    ]),
                  ]),
                  h("div", { className: "flex items-center gap-2 pt-3 mt-3 border-t border-zinc-900" }, [
                    !isAct && h("button", {
                      onClick: function () { handleSwitchFlowAccount(acc.id); },
                      className: "text-[11px] font-medium text-blue-400 hover:text-blue-300 transition",
                    }, "Chọn Active"),
                    h("button", {
                      onClick: handleRefresh,
                      className: "text-[11px] text-zinc-400 hover:text-white transition ml-auto flex items-center gap-1",
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
      h("div", { className: "bg-[#0e1118] border border-white/[0.08] rounded-2xl p-6 shadow-xl" }, [
        h("div", { className: "pb-4 border-b border-white/[0.06] mb-5" }, [
          h("h3", { className: "text-sm font-bold text-white flex items-center gap-2" }, [
            h("span", null, "5 Phân Tầng Mô Hình Video Google Flow Veo 3.1"),
            h("span", { className: "text-[10px] font-mono px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/30" },
              "Đang dùng: " + currentVideoModel
            ),
          ]),
          h("p", { className: "text-xs text-zinc-400 mt-0.5" },
            "Chọn mô hình mặc định được lưu vào config.yaml (Agent tự động định tuyến khi tạo video)"
          ),
        ]),

        h("div", { className: "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4" },
          videoModels.map(function (vm) {
            var isSelected = vm.id === currentVideoModel;
            return h("div", {
              key: vm.id,
              className: "bg-[#090a0f] border " + (isSelected ? "border-blue-500/50 bg-blue-500/[0.03]" : "border-white/[0.06]") + " rounded-xl p-4 flex flex-col justify-between transition hover:border-zinc-700",
            }, [
              h("div", { className: "space-y-2" }, [
                h("div", { className: "flex items-center justify-between" }, [
                  h("span", { className: "text-[10px] px-2 py-0.5 rounded-full bg-zinc-900 border border-zinc-800 text-zinc-300 font-semibold" }, vm.tier),
                  isSelected && h("span", { className: "text-[10px] px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-400 border border-blue-500/30 font-bold" }, "ĐANG CHỌN"),
                ]),
                h("div", { className: "text-sm font-bold text-white" }, vm.display),
                h("p", { className: "text-xs text-zinc-400" }, vm.strengths),
              ]),

              h("div", { className: "pt-3 mt-3 border-t border-zinc-900 space-y-2" }, [
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
                  className: "w-full mt-2 py-1.5 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-zinc-200 border border-zinc-800 text-xs font-medium transition",
                }, "Chọn mô hình này"),
              ]),
            ]);
          })
        ),
      ]),

      // 3. Handshake In-Progress Modal Overlay
      handshakeOverlay && h("div", {
        className: "fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex flex-col items-center justify-center p-6 text-center",
        key: "overlay",
      }, [
        h("div", { className: "w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mb-4" }),
        h("h3", { className: "text-base font-bold text-white mb-1" }, "Cửa sổ Google Flow đang mở trên màn hình..."),
        h("p", { className: "text-xs text-zinc-300 max-w-md mb-5" },
          "Vui lòng nhìn màn hình desktop và nhấn vào tài khoản Google của bạn. Cửa sổ sẽ tự động đóng ngay lập tức khi đăng nhập hoàn tất!"
        ),
        h("button", {
          onClick: cancelHandshake,
          className: "px-4 py-2 rounded-xl bg-zinc-900 hover:bg-zinc-800 text-zinc-300 text-xs font-semibold border border-zinc-700 transition",
        }, "Hủy phiên đăng nhập"),
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
      h("div", { className: "bg-[#0e1118] border border-white/[0.08] rounded-2xl p-6 shadow-xl" }, [
        h("div", { className: "flex items-center gap-3 pb-4 border-b border-white/[0.06] mb-5" }, [
          h("div", { className: "w-9 h-9 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400" },
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
                  className: "px-3.5 py-1.5 rounded-xl text-xs font-mono font-medium transition border " +
                    (isAct
                      ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/40 shadow-sm"
                      : "bg-[#090a0f] text-zinc-400 border-zinc-800 hover:text-zinc-200"),
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
              className: "w-full bg-[#090a0f] border border-zinc-800 text-zinc-200 rounded-xl p-3 text-xs outline-none focus:border-emerald-500",
            }),
          ]),

          // Generate button
          h("div", { className: "flex items-center justify-between pt-2" }, [
            h("div", { className: "text-[11px] text-zinc-500 font-mono" },
              "Model: gemini-3.1-flash-image • Tự động lưu vào ~/.hermes/media/"
            ),
            h("button", {
              disabled: generating,
              onClick: handleGenerate,
              className: "px-5 py-2.5 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-semibold text-xs flex items-center gap-2 transition shadow-md shadow-emerald-950 disabled:opacity-50",
            }, [
              h(Icon, { name: "sparkles", className: "w-4 h-4" }),
              h("span", null, generating ? "Đang sinh ảnh..." : "Sinh Ảnh Trực Tiếp"),
            ]),
          ]),
        ]),
      ]),

      // Result Preview Card
      result && h("div", {
        className: "bg-[#0e1118] border border-emerald-500/30 rounded-2xl p-6 shadow-xl space-y-4",
      }, [
        h("div", { className: "flex items-center justify-between" }, [
          h("h3", { className: "text-sm font-bold text-white flex items-center gap-2" }, [
            h(Icon, { name: "check", className: "w-4 h-4 text-emerald-400" }),
            h("span", null, "Kết Quả Sinh Ảnh Thành Công"),
          ]),
          h("span", { className: "text-[11px] font-mono text-zinc-400" }, result.aspect_ratio),
        ]),

        result.preview_data_url && h("div", {
          className: "rounded-xl overflow-hidden border border-white/[0.08] max-w-xl mx-auto bg-black flex items-center justify-center",
        }, [
          h("img", {
            src: result.preview_data_url,
            alt: "Generated Preview",
            className: "w-full h-auto object-contain max-h-[480px]",
          }),
        ]),

        h("div", { className: "p-3 rounded-xl bg-[#090a0f] border border-zinc-800 text-[11px] font-mono text-zinc-400 break-all" },
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
      h("div", { className: "bg-[#0e1118] border border-white/[0.08] rounded-2xl p-6 shadow-xl" }, [
        h("div", { className: "flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-white/[0.06] mb-5" }, [
          h("div", { className: "flex items-center gap-3" }, [
            h("div", { className: "w-9 h-9 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400" },
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
              className: "px-3.5 py-1.5 rounded-xl bg-zinc-900 hover:bg-zinc-800 text-zinc-200 border border-zinc-800 text-xs font-medium flex items-center gap-1.5 transition",
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
              className: "bg-[#090a0f] border " + (isOk ? "border-emerald-500/20" : isWarn ? "border-amber-500/30" : "border-white/[0.06]") + " rounded-xl p-3.5 flex items-start gap-3",
            }, [
              h("div", {
                className: "w-7 h-7 rounded-lg shrink-0 flex items-center justify-center " +
                  (isOk ? "bg-emerald-500/10 text-emerald-400" : isWarn ? "bg-amber-500/10 text-amber-400" : "bg-zinc-800 text-zinc-400"),
              }, h(Icon, { name: isOk ? "check" : "alert", className: "w-4 h-4" })),
              h("div", { className: "overflow-hidden space-y-0.5" }, [
                h("div", { className: "text-xs font-bold text-white flex items-center gap-2" }, [
                  h("span", null, c.label),
                ]),
                h("div", { className: "text-xs text-zinc-300" }, c.message),
                c.detail && h("div", { className: "text-[10px] text-zinc-500 font-mono truncate" }, c.detail),
              ]),
            ]);
          })
        ),
      ]),

      // 2. Live Logs Terminal Streamer
      h("div", { className: "bg-[#0e1118] border border-white/[0.08] rounded-2xl p-6 shadow-xl" }, [
        h("div", { className: "flex items-center justify-between pb-3 border-b border-white/[0.06] mb-4" }, [
          h("div", { className: "flex items-center gap-2" }, [
            h(Icon, { name: "terminal", className: "w-4 h-4 text-zinc-400" }),
            h("h3", { className: "text-xs font-bold text-white tracking-tight font-mono" }, "antigravity_bridge.log (Live Tail)"),
          ]),
          h("div", { className: "flex items-center gap-3 text-xs" }, [
            h("label", { className: "flex items-center gap-1.5 text-zinc-400 cursor-pointer text-[11px]" }, [
              h("input", {
                type: "checkbox",
                checked: autoScroll,
                onChange: function (e) { setAutoScroll(e.target.checked); },
                className: "rounded bg-zinc-900 border-zinc-700 text-emerald-500",
              }),
              h("span", null, "Auto-scroll"),
            ]),
            h("button", {
              onClick: fetchLogs,
              className: "text-[11px] text-zinc-400 hover:text-zinc-200 transition",
            }, "Làm mới"),
          ]),
        ]),

        h("div", {
          ref: terminalRef,
          className: "bg-[#050608] border border-white/[0.05] rounded-xl p-4 font-mono text-[11px] text-zinc-300 h-72 overflow-y-auto ag-scrollbar space-y-1 select-text",
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
      className: "bg-[#0e1118] border border-white/[0.08] hover:border-emerald-500/30 rounded-2xl p-5 shadow-lg transition",
    }, [
      h("div", { className: "flex items-center justify-between mb-3" }, [
        h("div", { className: "flex items-center gap-3" }, [
          h("div", { className: "w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400 font-bold text-xs" }, "AG"),
          h("div", null, [
            h("div", { className: "text-xs font-bold text-white" }, "Google Antigravity & Flow Suite"),
            h("div", { className: "text-[10px] text-zinc-400" }, data.active_email || "Chưa có tài khoản active"),
          ]),
        ]),
        h("span", {
          className: "px-2 py-0.5 rounded-full text-[10px] font-semibold " +
            (data.running ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" : "bg-zinc-800 text-zinc-400"),
        }, data.running ? "BRIDGE ONLINE" : "STANDBY"),
      ]),
      h("div", { className: "flex items-center justify-between text-xs pt-2 border-t border-zinc-900" }, [
        h("span", { className: "text-[11px] text-zinc-400" },
          data.credits != null ? "Flow Credits: " + data.credits : "Tích hợp đa mô hình"
        ),
        h("a", {
          href: "/antigravity",
          className: "text-[11px] text-emerald-400 hover:text-emerald-300 font-semibold flex items-center gap-1",
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
