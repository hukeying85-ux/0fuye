/* Arena Desk v2.5 — Frontend Controller (dsh-video-skin MIT integrated, 3-Account Cockpit, Love Hub, Mobile QR) */
(function () {
  "use strict";

  const TAB_META = {
    overview: {
      section: "运行总览",
      eyebrow: "Arena Desk v2.5 · dsh-video-skin 高透皮肤 · 三账号独立分舱 · 全域零闪窗静默",
      heading: "工作站全景高透控制面板",
      subtitle: "三账号三分区独立监控、谷歌云盘爱情空间 (18项) 与 00-05 具体文件直连、手机扫码装 App 与硕士论文排版尽在一屏。",
    },
    love: {
      section: "💖 爱情与心意空间",
      eyebrow: "Google Drive 03_纪念与个人文化 (18项原件直达) · 本机 JevChat 情感军师 · 严守隐私零上传",
      heading: "💖 爱情珍藏馆与高情商沟通空间",
      subtitle: "直连云盘 7 部恋爱纪实短片、纪念画册 PPTX/PDF、专属喜好档案 v4、沟通决策树与 4 张定制锁屏壁纸。",
    },
    beacon: {
      section: "手机App·算力信标",
      eyebrow: "扫码 30 秒安装「好了吗 · Arena Mobile」桌面 App · Slurm / Martini 3 跑完秒推锁屏",
      heading: "手机伴侣 App 安装向导与长耗时任务盯梢",
      subtitle: "内置局域网伴侣端口 (:18766/mobile) 与一键 Cloudflare 免费公网隧道，支持安卓与 iPhone 免商店 0 元安装。",
    },
    gh: {
      section: "三账号分舱监控",
      eyebrow: "一舱一号物理隔离 · Port 443 SSH 独立密钥 · git-credential-arenasilent 零弹窗",
      heading: "主控笔记本舱 · 学术超算舱 · 台式机模拟舱 三分区监控",
      subtitle: "将 mqgg5630-cyber、shaohuawen03-cyber、hukeying85-ux 拆分为三列独立监控，各自追踪机器、作业、仓库与凭据健康。",
    },
    personal: {
      section: "生涯·考公·云归档",
      eyebrow: "谷歌云盘 00–05 共 37 份具体文件直开 · 朋友材料折叠隔离 · 证件信息 100% 脱敏",
      heading: "求职 · 考公 · 身份脱敏索引 · 云盘具体文件总览",
      subtitle: "本人求职与考公日程优先展示，每一分区均列出真实具体云盘文件与直达链接，代管朋友档案严格物理隔离。",
    },
    thesis: {
      section: "论文一键改格式",
      eyebrow: "Lark-Formatter v0.21.1 · 学术型硕士学位论文标准规范 + 任意母版样式克隆",
      heading: "硕士学位论文格式一键修改工作台",
      subtitle: "直连 E:\\0writing\\Lark-Formatter 34 模块无头引擎与学术写作 Skills 矩阵，1.5 秒输出终稿 + 红蓝对比稿 + 审计报告。",
    },
    mediacua: {
      section: "媒体下载·操控台",
      eyebrow: "抖音 · 小红书 · 微信公众号本地桥接 + 本机 yt-dlp 4K 无水印 + 四层 Computer Use",
      heading: "全平台媒体无水印下载与桌面智能体操控中心",
      subtitle: "自动剥离分享口令去水印落盘 E:\\0downloads\\ArenaMedia、公众号无损转 Markdown，左上角 (0,0) 物理熔断防误触。",
    },
    quota: {
      section: "Gemini·反重力额度",
      eyebrow: "Gemini 1M-2M 长上下文 · Google Antigravity 防过期燃烧池 · 抗菌肽理化工具箱",
      heading: "多模型能力分流与额度零浪费中枢",
      subtitle: "L0 本地脚本省流 + 刷新前一键复制科研绘图/论文审校任务包 + 抗菌肽 (AMP) 理化指标实时精算。",
    },
    coord: {
      section: "作战室·多会话",
      eyebrow: "GrokBot-Style War Room · 三机三会话编队 + 0-Token 雷达 + 人工闸门 + 原子租约锁",
      heading: "多会话作战室与跨机派单调度总线",
      subtitle: "五大专职角色协同交接，严守 git-sync-hub 与伙伴会话只读红线，一键生成台式机/超算会话唤醒单。",
    },
    software: {
      section: "软件检测与安装",
      eyebrow: "本机可执行路径实测 · PyMOL 3.1 · Lark-Formatter · yt-dlp · Miniforge3",
      heading: "本机软件健康体检与零弹窗静默安装",
      subtitle: "实时展示 E:/C: 盘具体安装路径与版本，支持 winget / conda-forge 后台静默补齐。",
    },
    remote: {
      section: "跨机远程控制",
      eyebrow: "HPC 超算集群 mu01 (cu 64核 / fat1 96核1T) · 本机 WSL2 · GPU 台式机",
      heading: "多节点连通探测与白名单远程巡检",
      subtitle: "一键查看超算 Slurm 作业队列、存储配额与计算节点负载，输出自动脱敏回传。",
    },
    scripts: {
      section: "多机一键脚本",
      eyebrow: "Windows PowerShell 5.1+ · Linux / WSL2 / HPC Bash · A+D 免付费组网",
      heading: "跨电脑体检、科研装机与组网脚本生成器",
      subtitle: "按目标操作系统与磁盘实时定制自包含装机脚本，台式机或新工作站复制单行命令即可上线。",
    },
    connectors: {
      section: "生态连接器 (10)",
      eyebrow: "10 大生产力连接器 · 已绑定真实云端目录与数据库实例直达",
      heading: "GitHub · Notion · Google 全家桶 · Linear · Dropbox",
      subtitle: "逐项展示每个连接器已绑定的具体 Notion 数据库、云盘文件夹、主控文档与联动提示词。",
    },
    studio: {
      section: "外观·开机·桌宠",
      eyebrow: "Something11235/dsh-video-skin (MIT) 原版开机视频 + 高透动态壁纸 + 小鲸鱼挂件",
      heading: "DSH 原版视频开机动画与高透玻璃定制工坊",
      subtitle: "一键切换壁纸最清 (12%) / 均衡高透 (18%) 预设、女仆书房动态壁纸与二次元插画，自由重播原版开机动画。",
    },
  };

  let STATE = null;
  let CSRF = "";
  let READONLY = false;
  let ACTIVE_TAB = "overview";
  let SW_CATEGORY = "all";
  let BOOT_RUNNING = false;
  let BOOT_SOUND_ARMED = false;
  let SKIN_THEME = "sakura-mist";
  let PARTICLES = [];
  let WHALE_INDEX = 0;

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  function esc(val) {
    return String(val == null ? "" : val)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function toast(msg, kind) {
    const el = $("#toast");
    if (!el) return;
    el.textContent = msg;
    el.dataset.kind = kind || "info";
    el.hidden = false;
    clearTimeout(toast._t);
    toast._t = setTimeout(() => {
      el.hidden = true;
    }, 4200);
  }

  async function apiGet(url) {
    const res = await fetch(url, { credentials: "same-origin", cache: "no-store" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    return data;
  }

  async function apiPost(url, body) {
    const headers = { "Content-Type": "application/json" };
    if (CSRF) headers["X-CSRF-Token"] = CSRF;
    const res = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers,
      body: JSON.stringify(body || {}),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    return data;
  }

  /* ==================== Dreamy Anime Celesta & Wind-Chime Synthesizer ==================== */
  function playOrbitalChime(kind) {
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return;
      const ctx = playOrbitalChime._ctx || (playOrbitalChime._ctx = new Ctx());
      if (ctx.state === "suspended") ctx.resume();
      const now = ctx.currentTime;
      const notes =
        kind === "whale"
          ? [659.25, 783.99, 1046.5]
          : [523.25, 659.25, 783.99, 987.77, 1174.66, 1567.98];
      notes.forEach((freq, idx) => {
        const t = now + idx * 0.085;
        const osc1 = ctx.createOscillator();
        const osc2 = ctx.createOscillator();
        const gain = ctx.createGain();
        osc1.type = "sine";
        osc2.type = "sine";
        osc1.frequency.setValueAtTime(freq, t);
        osc2.frequency.setValueAtTime(freq * 2, t);
        gain.gain.setValueAtTime(0.0001, t);
        gain.gain.exponentialRampToValueAtTime(0.065, t + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.72);
        const overtoneGain = ctx.createGain();
        overtoneGain.gain.setValueAtTime(0.28, t);
        osc1.connect(gain);
        osc2.connect(overtoneGain);
        overtoneGain.connect(gain);
        gain.connect(ctx.destination);
        osc1.start(t);
        osc2.start(t);
        osc1.stop(t + 0.76);
        osc2.stop(t + 0.76);
      });
    } catch (_) {
      /* ignore audio block */
    }
  }

  /* ==================== Genuine Something11235/dsh-video-skin (MIT) Video Boot Surface ==================== */
  let BOOT_RAF = 0;
  let BOOT_FAILSAFE_TIMER = 0;
  let BOOT_BG_SAFETY_TIMER = 0;
  let LOVE_SCENE = "daily";
  let LOVE_CAT_FILTER = "all";
  let DRIVE_PART_FILTER = "all";
  let AMP_AUTO_CALC_DONE = false;

  function fadeVideoAudio(video, ms) {
    if (!video || video.muted || video.volume <= 0 || ms <= 0) return;
    const startVol = video.volume;
    const t0 = performance.now();
    const tick = (now) => {
      const k = Math.min(1, (now - t0) / ms);
      try {
        video.volume = Math.max(0, startVol * (1 - k));
      } catch (_) {}
      if (k < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }

  function resumeBackgroundVideo() {
    const bgVid = $("#skin-video");
    if (bgVid && !bgVid.hidden) {
      bgVid.play().catch(() => {});
    }
  }

  function dismissBootOverlay(reason) {
    const overlay = $("#boot-overlay");
    if (!overlay) return;
    if (BOOT_RAF) {
      cancelAnimationFrame(BOOT_RAF);
      BOOT_RAF = 0;
    }
    if (BOOT_FAILSAFE_TIMER) {
      clearTimeout(BOOT_FAILSAFE_TIMER);
      BOOT_FAILSAFE_TIMER = 0;
    }
    if (BOOT_BG_SAFETY_TIMER) {
      clearTimeout(BOOT_BG_SAFETY_TIMER);
      BOOT_BG_SAFETY_TIMER = 0;
    }
    const fallbackLayer = $("#boot-fallback");
    if (fallbackLayer) fallbackLayer.hidden = true;
    overlay.classList.remove("boot-fallback-active");
    const bootVid = $("#boot-video");
    if (bootVid) {
      try {
        bootVid.pause();
      } catch (_) {}
    }
    overlay.classList.remove("dsvs-boot--fade", "boot-exit-bloom");
    overlay.classList.add("boot-hide", "fade-out");
    overlay.hidden = true;
    overlay.style.display = "none";
    BOOT_RUNNING = false;
    resumeBackgroundVideo();
    if ((location.hash || "") === "#boot") {
      try {
        history.replaceState(null, "", "#overview");
      } catch (_) {}
    }
    if (reason) {
      fetch(
        `/api/boot-ack?mode=${encodeURIComponent(reason)}&tab=${encodeURIComponent(ACTIVE_TAB || "overview")}&hidden=1`,
        { credentials: "same-origin", cache: "no-store" }
      ).catch(() => {});
    }
  }

  // dsh-boot.mp4 (the original dsh-video-skin clip) is not shipped in this
  // repository, so the boot overlay used to sit on a black screen for the whole
  // 14.5 s watchdog.  This keeps the same beat with the mascot artwork.
  function showBootFallback(reason) {
    const overlay = $("#boot-overlay");
    const bootVid = $("#boot-video");
    const layer = $("#boot-fallback");
    const fill = $("#boot-fill");
    const stageEl = $("#boot-stage");
    if (!overlay || !layer) return;
    if (overlay.dataset.fallbackShown === "1") return;
    overlay.dataset.fallbackShown = "1";
    if (bootVid) {
      try {
        bootVid.pause();
      } catch (_) {}
      bootVid.hidden = true;
    }
    layer.hidden = false;
    overlay.classList.add("boot-fallback-active");
    if (stageEl) stageEl.textContent = "正在进入 Arena Desk v2.8…";
    if (fill) {
      fill.style.transition = "width 2200ms linear";
      fill.style.width = "100%";
    }
    setTimeout(() => {
      if (typeof enterWorkspaceRef === "function") enterWorkspaceRef(600, reason || "boot_fallback");
    }, 2400);
  }

  let enterWorkspaceRef = null;

  function triggerBootAnimation(force) {
    const overlay = $("#boot-overlay");
    const bootVid = $("#boot-video");
    if (!overlay) return;
    overlay.dataset.fallbackShown = "0";
    const fallbackLayer = $("#boot-fallback");
    if (fallbackLayer) fallbackLayer.hidden = true;
    overlay.classList.remove("boot-fallback-active");
    if (!force) {
      dismissBootOverlay();
      return;
    }
    if (BOOT_RUNNING) return;
    const appCfg = (STATE && STATE.appearance) || {};
    const wantSound = BOOT_SOUND_ARMED || appCfg.boot_sound !== false;
    const fadeMs = Math.max(250, Math.min(1800, Number(appCfg.boot_fade_ms) || 900));

    const bgVid = $("#skin-video");
    if (bgVid) {
      try {
        bgVid.pause();
      } catch (_) {}
    }

    BOOT_RUNNING = true;
    overlay.hidden = false;
    overlay.style.display = "block";
    overlay.style.transitionDuration = `${fadeMs}ms`;
    overlay.classList.remove("boot-hide", "fade-out", "dsvs-boot--fade", "boot-exit-bloom");

    const fill = $("#boot-fill");
    const stageEl = $("#boot-stage");
    const soundBtn = $("#boot-sound-btn");
    if (fill) fill.style.width = "0%";
    if (stageEl) stageEl.textContent = "正在进入 Arena Desk v2.6…";
    if (soundBtn) soundBtn.hidden = true;

    let exiting = false;
    let startedVisiblePlayback = false;

    const enterWorkspace = (spanMs, reasonTag) => {
      if (exiting) return;
      exiting = true;
      document.removeEventListener("visibilitychange", onVisChange);
      if (BOOT_RAF) {
        cancelAnimationFrame(BOOT_RAF);
        BOOT_RAF = 0;
      }
      if (BOOT_FAILSAFE_TIMER) {
        clearTimeout(BOOT_FAILSAFE_TIMER);
        BOOT_FAILSAFE_TIMER = 0;
      }
      if (BOOT_BG_SAFETY_TIMER) {
        clearTimeout(BOOT_BG_SAFETY_TIMER);
        BOOT_BG_SAFETY_TIMER = 0;
      }
      if (fill) fill.style.width = "100%";
      if (soundBtn) soundBtn.hidden = true;
      overlay.style.transitionDuration = `${spanMs}ms`;
      overlay.classList.add("dsvs-boot--fade");
      if (bootVid) fadeVideoAudio(bootVid, spanMs);
      resumeBackgroundVideo();
      setTimeout(() => {
        dismissBootOverlay(reasonTag || "dsh_video_boot_ended");
      }, spanMs + 40);
    };

    // showBootFallback() needs to end the boot sequence, but enterWorkspace is
    // defined in this closure: publish it as soon as it exists, not from inside
    // its own body (that would only ever run after the fallback had called it).
    enterWorkspaceRef = enterWorkspace;

    const startPlaybackWhenVisible = () => {
      if (exiting || startedVisiblePlayback) return;
      startedVisiblePlayback = true;
      // The clips are not shipped with the repository, so ask the server first:
      // playing a missing file rejects instantly and used to skip the overlay.
      const appearance = (STATE && STATE.appearance) || {};
      if (appearance.boot_video_available === false) {
        showBootFallback("boot_asset_absent");
        return;
      }
      if (BOOT_BG_SAFETY_TIMER) {
        clearTimeout(BOOT_BG_SAFETY_TIMER);
        BOOT_BG_SAFETY_TIMER = 0;
      }
      if (stageEl) stageEl.textContent = "正在进入 Arena Desk v2.6…";
      BOOT_FAILSAFE_TIMER = setTimeout(() => {
        enterWorkspace(350, "dsh_video_boot_watchdog");
      }, 14500);

      if (bootVid) {
        try {
          bootVid.currentTime = 0;
          bootVid.volume = 1.0;
          bootVid.muted = !wantSound;
        } catch (_) {}

        bootVid.onended = () => enterWorkspace(fadeMs, "dsh_video_boot_ended");
        bootVid.onerror = () => showBootFallback("dsh_video_boot_error");
        // A 404 on the clip does not always fire "error" (cached headers); a
        // source that never reports metadata is the same thing to the user.
        setTimeout(() => {
          if (!exiting && bootVid.readyState === 0) showBootFallback("dsh_video_boot_nodata");
        }, 1800);
        bootVid.ontimeupdate = () => {
          if (exiting || !fill) return;
          const d = bootVid.duration;
          if (d > 0 && Number.isFinite(d)) {
            const pct = Math.min(100, Math.round((bootVid.currentTime / d) * 100));
            fill.style.width = pct + "%";
          }
        };

        const playPromise = bootVid.play();
        if (playPromise && typeof playPromise.then === "function") {
          playPromise.catch(() => {
            bootVid.muted = true;
            if (wantSound && soundBtn) {
              soundBtn.hidden = false;
              soundBtn.onclick = (ev) => {
                ev.stopPropagation();
                bootVid.muted = false;
                bootVid.volume = 1.0;
                bootVid.play().catch(() => {});
                soundBtn.hidden = true;
              };
            }
            // muted autoplay also refused (or the asset is gone): show the
            // mascot layer instead of dropping the user into the workspace
            bootVid.play().catch(() => showBootFallback("dsh_video_autoplay_fallback"));
          });
        }
      } else {
        setTimeout(() => enterWorkspace(400, "no_video_el"), 1200);
      }
    };

    const onVisChange = () => {
      if (document.visibilityState === "visible") {
        startPlaybackWhenVisible();
      }
    };

    const appearanceNow = (STATE && STATE.appearance) || {};
    if (appearanceNow.boot_video_available === false) {
      // Nothing to preload: paint the mascot layer now so the first visible
      // frame is the animation, not a black rectangle.
      showBootFallback("boot_asset_absent_hidden");
    }

    if (document.visibilityState === "visible") {
      startPlaybackWhenVisible();
    } else {
      if (stageEl) stageEl.textContent = "画面已就绪 · 窗口激活即自动播放 dsh-video-skin 开机动画…";
      document.addEventListener("visibilitychange", onVisChange);
      // The window can be hidden at the moment the overlay arms (logon race, a
      // background launch, a locked console).  Waiting used to give up after
      // 9.2 s, which is why a remote/manual launch looked like "no animation":
      // the overlay was dropped before anybody could see it.  Wait for the
      // window to become visible instead, with a long hard safety as the only
      // way out.
      BOOT_BG_SAFETY_TIMER = setTimeout(() => {
        if (!startedVisiblePlayback) {
          enterWorkspace(250, "dsh_video_bg_autoforward");
        }
      }, 90000);
    }

    const skipBtn = $("#boot-skip");
    if (skipBtn) {
      skipBtn.onclick = (ev) => {
        ev.stopPropagation();
        enterWorkspace(Math.min(420, fadeMs), "user_skip");
      };
    }
    overlay.onclick = (ev) => {
      if (ev.target && ev.target.closest && ev.target.closest("#boot-sound-btn")) return;
      enterWorkspace(Math.min(420, fadeMs), "user_click_exit");
    };
  }

  /* ==================== Dynamic Particle Backdrop ==================== */
  function initCanvasSkin() {
    const canvas = $("#skin-canvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const resize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };
    resize();
    window.addEventListener("resize", resize);

    PARTICLES = Array.from({ length: 48 }, () => ({
      x: Math.random() * window.innerWidth,
      y: Math.random() * window.innerHeight,
      r: 1.1 + Math.random() * 2.4,
      vx: (Math.random() - 0.5) * 0.36,
      vy: (Math.random() - 0.5) * 0.36,
      a: 0.2 + Math.random() * 0.5,
    }));

    const paletteMap = {
      "aurora-abyss": ["56,189,248", "99,102,241", "45,212,191"],
      "cyber-emerald": ["52,211,153", "16,185,129", "56,189,248"],
      "amber-forge": ["251,191,36", "245,158,11", "248,113,113"],
      "sakura-mist": ["244,114,182", "192,132,252", "96,165,250"],
      "clean-frost": ["56,189,248", "129,140,248", "148,163,184"],
    };

    function draw() {
      const motionOn = !STATE || !STATE.appearance || STATE.appearance.motion_enabled !== false;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const cols = paletteMap[SKIN_THEME] || paletteMap["aurora-abyss"];
      for (let i = 0; i < PARTICLES.length; i++) {
        const p = PARTICLES[i];
        if (motionOn) {
          p.x += p.vx;
          p.y += p.vy;
          if (p.x < 0) p.x = canvas.width;
          if (p.x > canvas.width) p.x = 0;
          if (p.y < 0) p.y = canvas.height;
          if (p.y > canvas.height) p.y = 0;
        }
        ctx.beginPath();
        ctx.fillStyle = `rgba(${cols[i % cols.length]},${p.a})`;
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fill();
      }
      requestAnimationFrame(draw);
    }
    requestAnimationFrame(draw);
  }

  function applyAppearance(app) {
    if (!app) return;
    SKIN_THEME = app.theme || "sakura-mist";
    document.body.dataset.theme = SKIN_THEME;
    const op = typeof app.surface_opacity === "number" ? app.surface_opacity : 0.14;
    const veil = typeof app.veil_opacity === "number" ? app.veil_opacity : 0.10;
    const bl = typeof app.glass_blur === "number" ? app.glass_blur : 4;
    document.documentElement.style.setProperty("--surface-alpha", String(op));
    document.documentElement.style.setProperty("--veil-alpha", String(veil));
    document.documentElement.style.setProperty("--glass-blur", bl + "px");

    const opPct = Math.round(op * 100);
    const veilPct = Math.round(veil * 100);
    if ($("#rng-opacity")) $("#rng-opacity").value = String(opPct);
    if ($("#lbl-opacity")) $("#lbl-opacity").textContent = opPct + "%";
    if ($("#pop-rng-op")) $("#pop-rng-op").value = String(opPct);
    if ($("#pop-lbl-op")) $("#pop-lbl-op").textContent = opPct + "%";

    if ($("#rng-veil")) $("#rng-veil").value = String(veilPct);
    if ($("#lbl-veil")) $("#lbl-veil").textContent = veilPct + "%";
    if ($("#pop-rng-veil")) $("#pop-rng-veil").value = String(veilPct);
    if ($("#pop-lbl-veil")) $("#pop-lbl-veil").textContent = veilPct + "%";

    if ($("#rng-blur")) $("#rng-blur").value = String(bl);
    if ($("#lbl-blur")) $("#lbl-blur").textContent = bl + "px";
    if ($("#pop-rng-bl")) $("#pop-rng-bl").value = String(bl);
    if ($("#pop-lbl-bl")) $("#pop-lbl-bl").textContent = bl + "px";

    if ($("#chk-motion")) $("#chk-motion").checked = app.motion_enabled !== false;
    if ($("#chk-boot")) $("#chk-boot").checked = app.boot_enabled !== false;
    if ($("#chk-boot-sound")) $("#chk-boot-sound").checked = app.boot_sound !== false;

    const builtinWp = app.builtin_wallpaper || "dsh-bg.mp4";
    $$("#theme-swatches .swatch, .mini-swatches button").forEach((b) => {
      const th = b.dataset.theme || b.dataset.themePick;
      if (th) b.classList.toggle("active", th === SKIN_THEME);
    });
    $$("[data-wp-pick]").forEach((b) => {
      b.classList.toggle("active", !app.custom_media_id && b.dataset.wpPick === builtinWp);
    });

    const vid = $("#skin-video");
    const img = $("#skin-image");
    const mediaList = (STATE && STATE.media_wallpapers) || [];
    const mediaItem = app.custom_media_id ? mediaList.find((m) => m.id === app.custom_media_id) : null;
    const isBuiltinVideo = /\.(mp4|webm)$/i.test(builtinWp);

    if (SKIN_THEME === "mist-paper") {
      if (vid) {
        vid.pause();
        vid.hidden = true;
      }
      if (img) img.hidden = true;
    } else if (mediaItem && mediaItem.kind === "video" && vid) {
      const src = `/api/media/${encodeURIComponent(mediaItem.id)}`;
      if (vid.dataset.src !== src) {
        vid.src = src;
        vid.dataset.src = src;
      }
      vid.hidden = false;
      if (!BOOT_RUNNING) vid.play().catch(() => {});
      if (img) img.hidden = true;
    } else if (mediaItem && mediaItem.kind === "image" && img) {
      img.src = `/api/media/${encodeURIComponent(mediaItem.id)}`;
      img.hidden = false;
      if (vid) {
        vid.pause();
        vid.hidden = true;
      }
    } else if (isBuiltinVideo && vid && app.wallpaper_available !== false) {
      const targetVidSrc = `/assets/${encodeURIComponent(builtinWp)}?v=2.5.0`;
      if (vid.getAttribute("src") !== targetVidSrc && vid.dataset.src !== targetVidSrc) {
        vid.src = targetVidSrc;
        vid.dataset.src = targetVidSrc;
      }
      vid.hidden = false;
      if (!BOOT_RUNNING) vid.play().catch(() => {});
      if (img) img.hidden = true;
    } else if (isBuiltinVideo && img) {
      // dsh-bg.mp4 is not shipped: use the still artwork that is, instead of
      // leaving the stage black behind a 404.
      const art = app.wallpaper_fallback_art || "wallpaper-anime.jpg";
      img.src = `/assets/${encodeURIComponent(art)}?v=2.5.0`;
      img.hidden = false;
      if (vid) {
        vid.pause();
        vid.hidden = true;
      }
    } else {
      if (vid) {
        vid.pause();
        vid.hidden = true;
      }
      if (img) {
        const targetSrc = `/assets/${encodeURIComponent(builtinWp)}?v=2.5.0`;
        if (img.getAttribute("src") !== targetSrc) {
          img.src = targetSrc;
        }
        img.hidden = false;
      }
    }

    // Whale companion settings live inside appearance in DesktopOps
    const ww = $("#whale-widget");
    if (ww) {
      ww.hidden = app.whale_enabled === false;
      const sc = typeof app.whale_scale === "number" ? app.whale_scale : 1.0;
      ww.style.setProperty("--whale-scale", String(sc));
      const scPct = Math.round(sc * 100);
      if ($("#rng-whale-scale")) $("#rng-whale-scale").value = String(scPct);
      if ($("#lbl-whale-scale")) $("#lbl-whale-scale").textContent = scPct + "%";
    }
    if ($("#chk-whale")) $("#chk-whale").checked = app.whale_enabled !== false;
    if ($("#chk-whale-snap")) $("#chk-whale-snap").checked = app.whale_snap !== false;
    if ($("#chk-whale-sound")) $("#chk-whale-sound").checked = app.whale_sound !== false;
    if ($("#txt-whale-quotes") && Array.isArray(app.whale_quotes) && document.activeElement !== $("#txt-whale-quotes")) {
      $("#txt-whale-quotes").value = app.whale_quotes.join("\n");
    }
  }

  /* ==================== Tab Navigation & URL Hash Routing ==================== */
  function switchTab(tab, fromHash) {
    if (tab === "boot") {
      triggerBootAnimation(true);
      tab = "overview";
    }
    if (!TAB_META[tab]) tab = "overview";
    ACTIVE_TAB = tab;
    $$("nav button[data-tab]").forEach((b) => {
      b.classList.toggle("active", b.dataset.tab === tab);
    });
    $$(".tab").forEach((sec) => {
      sec.classList.toggle("active", sec.id === tab || sec.id === `tab-${tab}`);
    });
    const meta = TAB_META[tab];
    if ($("#section-name")) $("#section-name").textContent = meta.section;
    if ($("#eyebrow")) $("#eyebrow").textContent = meta.eyebrow;
    if ($("#heading")) $("#heading").textContent = meta.heading;
    if ($("#subtitle")) $("#subtitle").textContent = meta.subtitle;
    if (!fromHash) {
      try {
        history.replaceState(null, "", `#${tab}`);
      } catch (_) {}
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  }

  /* ==================== Renderers ==================== */
  function renderOverview(data) {
    const hub = data.hub || {};
    const hbSec = typeof data.heartbeat_age === "number" ? data.heartbeat_age : null;
    const hbOk = hbSec !== null && hbSec < 180;
    if ($("#hub-state")) {
      $("#hub-state").textContent = hbOk ? "在线守护中" : data.demo ? "预览镜像就绪" : "等待心跳";
    }
    if ($("#hub-meta")) {
      $("#hub-meta").textContent =
        hbSec !== null
          ? `最近心跳 ${hbSec}s 前 · 15s 零窗口轮询 (${hub.host || "LAPTOP-R77M5D6M"})`
          : `主机 ${hub.host || "LAPTOP-R77M5D6M"} · 零窗口自动同步`;
    }
    if ($("#side-hub-text")) {
      $("#side-hub-text").textContent = hbOk
        ? `git-sync-hub 正常 (${hbSec}s)`
        : data.demo
        ? "Arena Desk v2.1 实时预览"
        : "本地控制台已连接";
    }

    const th = data.thesis || {};
    if ($("#ov-thesis-state")) {
      $("#ov-thesis-state").textContent = th.engine_ready ? "Lark v0.21.1 就绪" : "待检测";
    }
    if ($("#ov-thesis-meta")) {
      const jobCnt = (th.recent_jobs || []).length;
      $("#ov-thesis-meta").textContent = `硕士学位标准规范 · 34 模块无头流水线 · 历史任务 ${jobCnt} 次`;
    }

    const love = ((data.personal_hub || {}).love_hub) || {};
    const loveCollections = love.collections || [];
    const loveItemCount = loveCollections.reduce((acc, c) => acc + ((c.items || []).length), 0);
    if ($("#ov-love-state")) {
      $("#ov-love-state").textContent = `${loveItemCount || 18} 项云盘珍藏`;
    }
    if ($("#ov-love-meta")) {
      $("#ov-love-meta").textContent = "7部恋爱短片 · 纪念画册PPT/PDF · 喜好档案v4 · JevChat守护";
    }

    const coord = data.coord || {};
    const sessList = coord.sessions || [];
    if ($("#ov-coord-state")) {
      $("#ov-coord-state").textContent = `${sessList.length} 会话并存 · ${coord.conflicts_detected || 0} 冲突`;
    }
    if ($("#ov-coord-meta")) {
      const locks = (coord.active_leases || []).length;
      $("#ov-coord-meta").textContent = `活动租约锁 ${locks} 个 · git-sync-hub 只读保护生效`;
    }

    if ($("#session-count")) {
      $("#session-count").textContent = String((data.sessions || []).length);
    }

    // Recent sessions table
    const recentTbody = $("#recent");
    if (recentTbody) {
      const rows = (data.sessions || []).slice(0, 8);
      recentTbody.innerHTML = rows.length
        ? rows
            .map((s) => {
              const wOn = s.watch_enabled !== false;
              const slotKey = s.account_slot || "S1";
              return `<tr>
                <td><strong>${esc(s.title || s.id)}</strong><div class="muted small">${esc(s.id)} · <span class="pill" style="padding:1px 6px;font-size:10px">${esc(slotKey)}</span></div></td>
                <td><code>${esc(s.repo || "hukeying85-ux/0fuye")}</code><div class="small muted">${esc(s.branch || "-")}</div></td>
                <td><span class="pill ${wOn && s.status === "succeeded" ? "ok" : "warn"}">${esc(wOn ? (s.status || "ok") : "已暂停值守")}</span></td>
                <td class="small muted">${esc(fmtLocalTime(s.at) || s.at || "-")}</td>
                <td>
                  <button type="button" class="mini-btn" data-watcher-toggle="${esc(slotKey)}" data-watcher-enable="${wOn ? "0" : "1"}">
                    ${wOn ? "⏸ 停止值守" : "▶ 开启值守"}
                  </button>
                </td>
              </tr>`;
            })
            .join("")
        : `<tr><td colspan="5" class="muted">暂无会话回执记录</td></tr>`;
    }

    // Hub detail KV list
    const hd = $("#hub-detail");
    if (hd) {
      const repoInfo = data.repo_info || {};
      const items = [
        ["当前绑定私有仓", `${repoInfo.owner || "hukeying85-ux"}/${repoInfo.repo || "0fuye"} (Private)`],
        ["会话专属分支", repoInfo.branch || "arena/89735ee7-0fuye"],
        ["守护任务名称", `${hub.task_name || "git-sync-hub"}（支持安全一键启停）`],
        ["工作站主机名", hub.host || "LAPTOP-R77M5D6M"],
        ["轮询模式", `${hub.mode || "auto-poll-v4.0"} · 每 ${hub.poll_interval_sec || 15}s`],
        ["面板内核版本", `Arena Desk v${data.version || "2.8.0"}`],
      ];
      hd.innerHTML = items.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join("");
    }

    // Scheduled tasks cards + Session ledger
    const tc = $("#task-cards");
    if (tc) {
      const tasks = data.tasks || [];
      const globalWatchOn = !data.tri_chat || !data.tri_chat.watcher || data.tri_chat.watcher.global_enabled !== false;
      tc.innerHTML = tasks.length
        ? tasks
            .map((t) => {
              const name = t.TaskName || t.name || "";
              const state = t.State || t.state || "Ready";
              const isSelfPanel = name === "arena-desk-panel";
              return `<div class="subcard">
                <div class="row-between">
                  <strong>${esc(name)}</strong>
                  <span class="pill ${name === "git-sync-hub" && !globalWatchOn ? "warn" : (state === "Running" || state === "Ready" ? "ok" : "warn")}">${esc(name === "git-sync-hub" && !globalWatchOn ? "Paused (安全挂起)" : state)}</span>
                </div>
                <p class="muted small">${
                  name === "git-sync-hub"
                    ? "永久零闪窗同步基座 · 支持安全一键开启 / 暂停轮询（不破坏底层任务）"
                    : name.startsWith("jev-chat")
                    ? "伙伴会话守护进程"
                    : name === "arena-desk-boot-demo"
                    ? "桌面端开机动画按需唤醒任务"
                    : "受控桌面组件任务"
                }</p>
                ${
                  name === "git-sync-hub"
                    ? `<div class="btn-row">
                        <button type="button" class="mini-btn" data-watcher-toggle="ALL" data-watcher-enable="1">▶ 开启值守</button>
                        <button type="button" class="mini-btn" data-watcher-toggle="ALL" data-watcher-enable="0">⏸ 暂停值守</button>
                      </div>`
                    : isSelfPanel || READONLY
                    ? `<span class="badge-soft">${isSelfPanel ? "当前面板服务在线" : "预览模式（可体验上方值守开关）"}</span>`
                    : `<div class="btn-row">
                        <button type="button" class="mini-btn" data-ctrl-name="${esc(name)}" data-ctrl-act="start">▶ 启动</button>
                        <button type="button" class="mini-btn" data-ctrl-name="${esc(name)}" data-ctrl-act="stop">⏹ 停止</button>
                      </div>`
                }
              </div>`;
            })
            .join("")
        : `<div class="subcard"><p class="muted">预览环境不展示 Windows 计划任务；上方会话值守开关可实时体验。</p></div>`;
    }

    const stBody = $("#session-table");
    const q = (($("#search") && $("#search").value) || "").trim().toLowerCase();
    if (stBody) {
      const filtered = (data.sessions || []).filter(
        (s) =>
          !q ||
          String(s.id).toLowerCase().includes(q) ||
          String(s.title).toLowerCase().includes(q) ||
          String(s.branch).toLowerCase().includes(q) ||
          String(s.prompt).toLowerCase().includes(q)
      );
      stBody.innerHTML = filtered
        .map((s) => {
          const wOn = s.watch_enabled !== false;
          const slotKey = s.account_slot || "S1";
          return `<tr>
            <td><strong>${esc(s.title || s.id)}</strong><div class="muted small">${esc(s.prompt ? s.prompt.slice(0, 80) : "未登记提示词")}</div></td>
            <td><code>${esc(s.repo || "hukeying85-ux/0fuye")}</code><div class="small muted">${esc(s.branch || "")}</div></td>
            <td><span class="pill ${wOn ? "ok" : "warn"}">${esc(wOn ? (s.status || "synced") : "已暂停")}</span></td>
            <td class="small">${esc(s.sync_mode || "results+deliverable")}</td>
            <td class="small muted">${esc(fmtLocalTime(s.at) || s.at || "-")}</td>
            <td>
              <button type="button" class="mini-btn" data-watcher-toggle="${esc(slotKey)}" data-watcher-enable="${wOn ? "0" : "1"}">
                ${wOn ? "⏸ 停止值守" : "▶ 开启值守"}
              </button>
            </td>
          </tr>`;
        })
        .join("");
    }

    const sel = $("#session-select");
    if (sel && sel.options.length <= 1 && (data.sessions || []).length) {
      sel.innerHTML = (data.sessions || [])
        .map((s) => `<option value="${esc(s.id)}">${esc(s.title || s.id)} (${esc(s.branch || "main")})</option>`)
        .join("");
    }
  }

  function renderThesis(data) {
    const th = data.thesis || {};
    const badge = $("#thesis-engine-badge");
    if (badge) {
      badge.textContent = th.engine_ready
        ? `Lark-Formatter ${th.engine_version || "v0.21.1"} 就绪`
        : "引擎待挂载";
      badge.className = "pill " + (th.engine_ready ? "ok" : "warn");
    }

    // Populate profile dropdown if profiles returned
    const modeSel = $("#thesis-mode");
    if (modeSel && Array.isArray(th.profiles) && th.profiles.length && !modeSel.dataset.boundProfiles) {
      modeSel.innerHTML = th.profiles
        .map((p) => `<option value="${esc(p.id)}">${esc(p.name)}</option>`)
        .join("");
      modeSel.dataset.boundProfiles = "1";
    }

    const detSel = $("#thesis-detected-select");
    if (detSel && !detSel.dataset.populated) {
      const cands = th.manuscripts || [];
      if (cands.length) {
        detSel.innerHTML =
          `<option value="">— 快速填入已探测到的本机/内置论文稿 (${cands.length} 份) —</option>` +
          cands
            .map(
              (c) =>
                `<option value="${esc(c.path)}">${esc(c.label)} (${c.exists ? c.size_kb + " KB" : "本机路径预设"})</option>`
            )
            .join("");
        detSel.dataset.populated = "1";
      }
    }

    const modGrid = $("#thesis-module-grid");
    if (modGrid) {
      const prof = ((th.profiles || [])[0] && (th.profiles || [])[0].description) || "A4 页边距上下 3.8cm / 左右 3.2cm，黑体三号章标题，宋体/Times 小四 20pt 固定行距。";
      const mods = [
        ["页面与分节几何", prof],
        ["多级标题与自动目录", "章/节/条样式统一映射，自动清理 Markdown 残余符号与多余空段。"],
        ["三线表与题注规整", "全表顶底 1.5pt、栏目线 0.75pt、隐藏竖线，表题黑体五号段前段后自动对齐。"],
        ["中英混排与化学/公式", "中文宋体 + 英文数字 Times New Roman 自动配对，上下标化学式与西文间距微调。"],
        ["Zotero 9 域保护 + GB/T 7714", `DOCX_DISABLE_FIELD_REFRESH=1 无损保留活动引用域 · CSL 标准库 ${th.gbt7714_csl_ready ? "已就绪" : "内置"}。`],
        ["三件套原子化交付", "每次运行同步产出 _new.docx 终稿、_对比稿.docx 红蓝修订稿与 _报告.md 逐项审计清单。"],
      ];
      modGrid.innerHTML = mods
        .map(([t, d]) => `<div class="mini-feature"><strong>${esc(t)}</strong><p>${esc(d)}</p></div>`)
        .join("");
    }

    const skBox = $("#thesis-skills-list");
    if (skBox) {
      const skills = th.skills_ecosystem || [];
      skBox.innerHTML = skills.length
        ? skills
            .map(
              (s) => `<div class="skill-row">
                <div>
                  <strong>${esc(s.name)}</strong>
                  <div class="small muted"><code>${esc(s.active_path || s.win_path || "")}</code> · ${esc(s.role || s.summary || "")}</div>
                </div>
                <span class="pill ${s.installed ? "ok" : "neutral"}">${s.installed ? "本机已就绪" : "本机 E:\\0writing"}</span>
              </div>`
            )
            .join("")
        : `<p class="muted">正在读取 E:\\0writing 学术技能生态…</p>`;
    }

    const jobsBody = $("#thesis-jobs-table");
    if (jobsBody) {
      const jobs = th.recent_jobs || [];
      jobsBody.innerHTML = jobs.length
        ? jobs
            .map(
              (j) => `<tr>
                <td><code>${esc(j.job_id)}</code></td>
                <td>${esc(j.source_label || "样稿")}</td>
                <td>${esc(j.profile_name || j.profile_id || "硕士规范")}</td>
                <td><strong>${esc(j.total_changes ?? "-")}</strong> 处 · ${esc(j.elapsed_sec ?? "-")}s</td>
                <td class="btn-row">
                  <a class="mini-btn" href="/api/thesis/download/${encodeURIComponent(j.job_id)}/final" target="_blank" rel="noopener">下载终稿</a>
                  <a class="mini-btn" href="/api/thesis/download/${encodeURIComponent(j.job_id)}/compare" target="_blank" rel="noopener">对比稿</a>
                  <a class="mini-btn" href="/api/thesis/download/${encodeURIComponent(j.job_id)}/report_md" target="_blank" rel="noopener">报告</a>
                  ${
                    !READONLY
                      ? `<button type="button" class="mini-btn" data-open-thesis-job="${esc(j.job_id)}">打开目录</button>`
                      : ""
                  }
                </td>
              </tr>`
            )
            .join("")
        : `<tr><td colspan="5" class="muted">暂无持久化记录 — 点击右上角「⚡ 一键实测内置硕士论文样稿」可立即生成并下载！</td></tr>`;
    }
  }

  /* ==================== Dedicated Love & Relationship Space (#love) ==================== */
  function renderLoveSpace(data) {
    const ph = data.personal_hub || {};
    const love = ph.love_hub || {};
    const loc = data.love_local || {};
    const metricsEl = $("#love-status-metrics");
    if (metricsEl) {
      const cols = love.collections || [];
      const totalFiles = cols.reduce((acc, c) => acc + ((c.items || []).length), 0);
      metricsEl.innerHTML = `
        <article class="metric-card">
          <span>Google Drive 爱情原件</span>
          <strong>${totalFiles || 18} 份</strong>
          <small>03_纪念与个人文化 · File ID 零破坏直连</small>
        </article>
        <article class="metric-card">
          <span>纪实短片 &amp; 纪念画册</span>
          <strong>7 视频 + 2 画册</strong>
          <small>MP4 原画播放 + PPTX 母版 / PDF 高清版</small>
        </article>
        <article class="metric-card">
          <span>本机 JevChat 情感军师</span>
          <strong>${loc.jev_installed !== false ? "静默守护中" : "待挂载"}</strong>
          <small>${esc(loc.jev_dir || "E:\\0apps\\jev-chat-windows")} · 只填草稿</small>
        </article>
        <article class="metric-card">
          <span>本机私人纪念加密仓</span>
          <strong>${loc.private_vault_present !== false ? "只读受保护" : "离线保护"}</strong>
          <small>${esc(loc.private_vault_policy || "STRICT_LOCAL_READONLY · 零原文上传")}</small>
        </article>
      `;
    }

    const colBox = $("#love-collections-container");
    if (colBox) {
      const cols = love.collections || [];
      colBox.innerHTML = cols
        .map(
          (col) => `<article class="card love-collection-card">
            <div class="cardtop">
              <h2>${esc(col.emoji || "💖")} ${esc(col.title)}</h2>
              <span class="pill">${(col.items || []).length} 项具体云盘文件</span>
            </div>
            <div class="love-items-grid">
              ${(col.items || [])
                .map(
                  (it) => `<div class="love-item-card">
                    <div>
                      <div class="row-between">
                        <strong>${esc(it.title)}</strong>
                        <span class="badge-soft">${esc(it.date_tag || it.type || "云盘")}</span>
                      </div>
                      <p class="small muted" style="margin:6px 0 0">${esc(it.note || "")}</p>
                    </div>
                    <div class="row-between" style="margin-top:4px">
                      <code class="small">${esc(it.type || "FILE")}</code>
                      <a class="mini-btn" href="${esc(it.url)}" target="_blank" rel="noopener">☁️ 打开云盘原件 ↗</a>
                    </div>
                  </div>`
                )
                .join("")}
            </div>
          </article>`
        )
        .join("");
    }

    const pbBox = $("#love-playbooks-box");
    if (pbBox) {
      pbBox.innerHTML = (love.playbooks || [])
        .map(
          (p) => `<div class="subcard">
            <div class="row-between">
              <strong>💡 ${esc(p.title)}</strong>
              <span class="pill ok">可执行心意卡</span>
            </div>
            <p class="small" style="margin:6px 0 0">${esc(p.steps || "")}</p>
          </div>`
        )
        .join("");
    }

    const jevBox = $("#love-jev-box");
    if (jevBox) {
      const jg = love.local_jev_companion || {};
      jevBox.innerHTML = `
        <div class="subcard">
          <div class="row-between">
            <strong>🤖 ${esc(jg.name || "本机 JevChat 情感沟通助手")}</strong>
            <span class="pill ok">零弹窗静默运行</span>
          </div>
          <div class="small muted" style="margin-top:4px">本地目录：<code>${esc(jg.local_path || "E:\\0apps\\jev-chat-windows")}</code></div>
          <div class="small muted">计划任务：<code>${esc((jg.tasks || ["jev-chat-monitor", "jev-chat-analyze"]).join(" + "))}</code> (ArenaSilentRun.exe 无黑框守护)</div>
          <p class="small" style="margin:6px 0 0">${esc(jg.safety_rule || "严格本地运行：只填草稿绝不自动发送，零原文上传。")}</p>
        </div>
        <div class="subcard">
          <div class="row-between">
            <strong>🔒 本机私人相册与日志保险箱 (<code>E:\\0yf</code>)</strong>
            <span class="badge-soft">100% 本地物理隔离</span>
          </div>
          <p class="small muted" style="margin:6px 0 0">遵循最高隐私红线：面板仅核验本机文件夹保护状态，绝不扫描或上传任何私密照片与聊天原文；云端展示项均来自您授权整理的 Google Drive <code>03_纪念与个人文化归档</code>。</p>
        </div>
      `;
    }
  }

  function renderPersonalHub(data) {
    const ph = data.personal_hub || {};
    const topLinks = $("#personal-top-links");
    if (topLinks) {
      const links = ph.quick_links || [];
      topLinks.innerHTML = links
        .map(
          (l) => `<a class="hub-shortcut" href="${esc(l.url)}" target="_blank" rel="noopener">
            <span class="hs-tag">${esc(l.badge || "CLOUD")}</span>
            <strong>${esc(l.title)}</strong>
            <span class="muted small">${esc(l.subtitle || "")}</span>
          </a>`
        )
        .join("");
    }

    const dfGrid = $("#drive-folders-grid");
    if (dfGrid) {
      const folders = ph.drive_folders || [];
      const totalFiles = folders.reduce((acc, f) => acc + ((f.concrete_items || []).length), 0);
      if ($("#drive-summary-pill")) {
        $("#drive-summary-pill").textContent = `${folders.length} 大标准分区 · ${totalFiles} 份具体云盘文件直连`;
      }
      dfGrid.innerHTML = folders
        .map(
          (f) => `<div class="subcard">
            <div class="row-between">
              <strong>${esc(f.name || "")}</strong>
              <span class="pill ok">${(f.concrete_items || []).length || f.items_count || 0} 份具体文件</span>
            </div>
            <p class="small muted" style="margin:4px 0">${esc(f.summary || "")}</p>
            <div class="drive-concrete-list">
              ${(f.concrete_items || [])
                .map(
                  (it) => `<div class="drive-file-row">
                    <span>📄 <b>${esc(it.title)}</b> <small class="muted">(${esc(it.type || "FILE")})</small></span>
                    <a href="${esc(it.url)}" target="_blank" rel="noopener">打开 ↗</a>
                  </div>`
                )
                .join("")}
            </div>
            ${
              (f.isolated_friend_items || []).length
                ? `<details style="margin-top:8px">
                    <summary class="small muted" style="cursor:pointer">🔒 展开外部朋友代管子目录（已物理隔离 · ${f.isolated_friend_items.length} 项）</summary>
                    <div class="drive-concrete-list" style="margin-top:6px">
                      ${f.isolated_friend_items
                        .map(
                          (it) => `<div class="drive-file-row">
                            <span>🗂️ ${esc(it.title)}</span>
                            <a href="${esc(it.url)}" target="_blank" rel="noopener">查看 ↗</a>
                          </div>`
                        )
                        .join("")}
                    </div>
                  </details>`
                : ""
            }
            <div class="row-between" style="margin-top:10px">
              <code class="small">ID: ${esc((f.folder_id || "").slice(0, 14))}…</code>
              ${f.url ? `<a class="mini-btn" href="${esc(f.url)}" target="_blank" rel="noopener">☁️ 打开整个云盘分区 ↗</a>` : ""}
            </div>
          </div>`
        )
        .join("");
    }

    const careerBox = $("#career-box");
    if (careerBox) {
      const tracks = ph.career_tracks || [];
      const primaryTracks = tracks.filter((c) => c.scope !== "friend_isolated");
      const isolatedTracks = tracks.filter((c) => c.scope === "friend_isolated");
      const renderCard = (c) => `<div class="person-card">
          <div class="row-between">
            <strong>${esc(c.person)}</strong>
            <span class="pill ${c.scope === "friend_isolated" ? "neutral" : "ok"}">${esc(c.status || "推进中")}</span>
          </div>
          <div class="small muted" style="margin:4px 0">${esc(c.background || "")}</div>
          <p class="small">${esc(Array.isArray(c.targets) ? c.targets.join(" · ") : c.targets || "")}</p>
          ${c.local_dir ? `<div class="small muted">归档定位：<code>${esc(c.local_dir)}</code></div>` : ""}
        </div>`;
      careerBox.innerHTML =
        primaryTracks.map(renderCard).join("") +
        (isolatedTracks.length
          ? `<details style="margin-top:10px"><summary class="small muted" style="cursor:pointer">🔒 展开外部朋友代管参考区（已严格物理隔离 · ${isolatedTracks.length} 项）</summary><div style="margin-top:8px">${isolatedTracks.map(renderCard).join("")}</div></details>`
          : "");
    }

    const examBox = $("#exam-box");
    if (examBox) {
      const exams = ph.exam_milestones || [];
      examBox.innerHTML = exams
        .map(
          (e) => `<div class="timeline-item">
            <div class="row-between">
              <strong>${esc(e.title)}</strong>
              <span class="badge-soft">${esc(e.date || "")}</span>
            </div>
            <div class="small muted">${esc(e.category || "")} · ${e.calendar_synced ? "已同步 Google Calendar 提醒" : "待提醒"}</div>
          </div>`
        )
        .join("");
    }

    const idBox = $("#identity-box");
    if (idBox) {
      const ids = ph.identity_cards_redacted || [];
      idBox.innerHTML = ids
        .map(
          (i) => `<div class="person-card">
            <div class="row-between">
              <strong>${esc(i.holder)} · ${esc(i.category || "")}</strong>
              <span class="pill neutral">已脱敏保护</span>
            </div>
            <div class="small" style="margin-top:4px">${esc(i.masked_summary || "")}</div>
            <div class="small muted">原件位置：${esc(i.storage_hint || "")}</div>
          </div>`
        )
        .join("");
    }

    const commBox = $("#commem-box");
    if (commBox) {
      const comms = ph.commemorations || [];
      commBox.innerHTML = comms
        .map(
          (m) => `<div class="person-card warm">
            <div class="row-between">
              <strong>${esc(m.title)}</strong>
              <span class="badge-soft">${esc(m.tag || "纪念")}</span>
            </div>
            <p class="small" style="margin:4px 0">${esc(m.detail || "")}</p>
            <div class="small muted">${esc(m.protection || "")}</div>
          </div>`
        )
        .join("");
    }
  }

  function fmtLocalTime(val, withDate) {
    if (!val && val !== 0) return "";
    const d = typeof val === "number" ? new Date(val < 1e12 ? val * 1000 : val) : new Date(val);
    if (Number.isNaN(d.getTime())) {
      const s = String(val).replace("T", " ");
      return withDate ? s.slice(0, 19) : s.slice(11, 19) || s;
    }
    const pad = (n) => String(n).padStart(2, "0");
    const hms = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    if (!withDate) return hms;
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${hms}`;
  }

  function renderCoord(data) {
    const coord = data.coord || {};
    const sessions = coord.sessions || [];
    const locks = coord.active_leases || [];
    const events = coord.recent_events || [];
    const rules = coord.rules || [];

    if ($("#coord-session-count")) {
      $("#coord-session-count").textContent = `${sessions.length} 个会话在线 · ${coord.conflicts_detected || 0} 冲突`;
    }

    const wr = data.war_room || {};
    const wrGrid = $("#wr-roster-grid");
    if (wrGrid) {
      wrGrid.innerHTML = (wr.roster || [])
        .map(
          (b) => `<div class="subcard">
            <div class="row-between">
              <strong>${esc(b.emoji || "🤖")} ${esc(b.name)} · ${esc(b.role)}</strong>
              <span class="badge-soft">${esc(b.token_tier || "")}</span>
            </div>
            <p class="small" style="margin:6px 0 4px"><b>负责：</b>${esc(b.owns)}</p>
            <p class="small muted"><b>边界禁区：</b>${esc(b.never_touches)}</p>
          </div>`
        )
        .join("");
    }

    const wrRt = $("#wr-routines-box");
    if (wrRt) {
      const rts = wr.routines || [];
      const guards = wr.guardrails || [];
      wrRt.innerHTML = `
        <article class="card">
          <div class="cardtop"><h2>⏱️ 省额度雷达 Routines（0-Token 探针优先）</h2><span class="pill ok">HEALTHY</span></div>
          <div class="task-stack">${rts
            .map(
              (r) => `<div class="subcard">
                <div class="row-between"><strong>${esc(r.name)}</strong><span class="badge-soft">${esc(r.cadence)}</span></div>
                <div class="small muted">每次消耗 Token：<code>${esc(r.llm_tokens_per_run)}</code> · ${esc(r.trigger_policy)}</div>
              </div>`
            )
            .join("")}</div>
        </article>
        <article class="card">
          <div class="cardtop"><h2>🛡️ 实战翻车护栏 (Failure Guardrails)</h2><span class="pill pale">CODIFIED</span></div>
          <div class="task-stack">${guards
            .map(
              (g) => `<div class="subcard">
                <div class="row-between"><strong>${esc(g.code)} · ${esc(g.symptom)}</strong></div>
                <div class="small muted">${esc(g.rule)}</div>
              </div>`
            )
            .join("")}</div>
        </article>
      `;
    }

    const rulesRow = $("#coord-rules-row");
    if (rulesRow) {
      rulesRow.innerHTML = rules
        .map((r) => {
          if (typeof r === "string") {
            return `<div class="rule-pill"><p class="small">${esc(r)}</p></div>`;
          }
          const head = r.title || [r.scope, r.policy].filter(Boolean).join(" · ");
          const body = r.detail || r.rule || "";
          return `<div class="rule-pill"><strong>${esc(head)}</strong><p class="small muted">${esc(body)}</p></div>`;
        })
        .join("");
    }

    const sBox = $("#coord-sessions-list");
    if (sBox) {
      sBox.innerHTML = sessions
        .map(
          (s) => `<div class="subcard">
            <div class="row-between">
              <strong>${esc(s.session_id)}</strong>
              <span class="pill ${s.session_id === coord.current_session ? "ok" : "neutral"}">${
            s.session_id === coord.current_session ? "当前主控会话" : esc(s.status || "协同会话")
          }</span>
            </div>
            <div class="small muted" style="margin:4px 0">仓库：<code>${esc(s.repo || "")}</code> · 分支：<code>${esc(s.branch || "")}</code></div>
            <div class="small">职责：${esc(s.role || "")}</div>
            <div class="small muted">专属工作区：<code>${esc((s.owned_resources || []).join(", "))}</code></div>
            ${s.summary || s.note ? `<div class="small muted" style="margin-top:4px">${esc(s.summary || s.note)}</div>` : ""}
          </div>`
        )
        .join("");
    }

    const lBox = $("#coord-locks-box");
    if (lBox) {
      lBox.innerHTML = locks.length
        ? locks
            .map(
              (l) => `<div class="skill-row">
                <div>
                  <strong><code>${esc(l.resource)}</code></strong>
                  <div class="small muted">持有者：${esc(l.holder)} · ${esc(l.purpose || "")} · 到期 ${esc(l.expires_at || "-")}</div>
                </div>
                ${
                  !READONLY
                    ? `<button type="button" class="mini-btn" data-release-lock="${esc(l.resource)}">释放</button>`
                    : `<span class="pill ok">锁定中</span>`
                }
              </div>`
            )
            .join("")
        : `<p class="muted small">当前无争用租约锁，所有共享资源空闲可用。</p>`;
    }

    const evBox = $("#coord-events-box");
    if (evBox) {
      evBox.innerHTML = events.length
        ? events
            .slice(0, 12)
            .map(
              (e) => `<div class="event-line">
                <span class="muted small">${esc(fmtLocalTime(e.ts || e.at, true))}</span>
                <span class="badge-soft">${esc(e.kind || e.type || e.event || "info")}</span>
                <span><strong>${esc(e.session_id || "")}</strong> ${esc(e.summary || e.detail || "")}</span>
              </div>`
            )
            .join("")
        : `<p class="muted small">协作事件流已就绪。</p>`;
    }
  }

  /* ==================== 3-Part Independent Account Monitoring Cockpit ==================== */
  function buildThreeCompartmentModels(data) {
    const gh = data.gh_auth || {};
    const accMap = {};
    (gh.multi_accounts || []).forEach((a) => {
      accMap[a.login] = a;
    });
    const watches = ((data.beacon || {}).watches) || [];
    const findWatches = (kw) => watches.filter((w) => String(w.title || "").includes(kw) || String(w.target || "").includes(kw));

    const a1 = accMap["mqgg5630-cyber"] || {};
    const a2 = accMap["shaohuawen03-cyber"] || {};
    const a3 = accMap["hukeying85-ux"] || {};

    return [
      {
        cls: "comp-1",
        part: "第一部分 · 主控笔记本舱",
        emoji: "💻",
        login: "mqgg5630-cyber",
        email: a1.email || "m***@gmail.com",
        roleTitle: "全局主控 · 0fuye 私有库 · 论文与个人云盘",
        machine: "主力笔记本 LAPTOP-R77M5D6M (Windows 11)",
        authBadge: a1.gh_active !== false ? "默认激活主号 (Active)" : "Keyring 已就绪",
        authOk: true,
        sshAlias: `git@${a1.ssh_alias || "github-mqgg"}:443`,
        credHelper: "git-credential-arenasilent.exe (winexe 零闪窗)",
        quotaPool: "Gemini 主力百万上下文池 + Notion/Google 全家桶主账号",
        repos: a1.sample_repos || ["0fuye (private)", "leanrea", "goutoujunshi", "skills"],
        workloads: [
          "git-sync-hub 永久后台守护（2s/15s 零控制台静默轮询）",
          "Lark-Formatter 硕士论文一键排版 + 红蓝对比稿产出",
          "Google Drive 00–05（含 💖 爱情空间 18 项原件）与 JevChat 守护",
          ...findWatches("mqgg").map((w) => `${w.title} (${w.percent}% · ${w.eta_human})`),
        ],
        jumpTab: "personal",
        jumpLabel: "查看本号云盘与论文 ↗",
      },
      {
        cls: "comp-2",
        part: "第二部分 · 学术超算舱",
        emoji: "🧬",
        login: "shaohuawen03-cyber",
        email: a2.email || "s***@gmail.com",
        roleTitle: "硕士课题主线 · HPC 超算 mu01 · 生信与全原子 MD",
        machine: "HPC 超算集群 mu01 (cu 64核 / fat1 96核1TB)",
        authBadge: a2.gh_logged_in !== false ? "Keyring + SSH 443 双通" : "SSH 443 就绪",
        authOk: a2.gh_logged_in !== false || a2.ssh_key_ready !== false,
        sshAlias: `git@${a2.ssh_alias || "github-shaohua"}:443`,
        credHelper: "URL 作用域独立路由 (免切换主号直推)",
        quotaPool: "科研文献精读池 + Antigravity 科研绘图脚本生成池",
        repos: a2.sample_repos || ["Lark-Formatter (v0.21.1)", "0amp-research", "Light-skills"],
        workloads: [
          "476 样本肠道宏基因组 MEGAHIT 大内存组装与分箱 (#92421)",
          "XAMP / HMD-AMP 候选抗菌肽深度学习挖掘与活性排序",
          "胜出抗菌肽 CHARMM36m 100ns 全原子分子动力学 (#92418)",
          ...findWatches("shaohua").map((w) => `${w.title} (${w.percent}% · ${w.eta_human})`),
        ],
        jumpTab: "remote",
        jumpLabel: "查看 HPC 超算节点 ↗",
      },
      {
        cls: "comp-3",
        part: "第三部分 · 台式机模拟舱",
        emoji: "🖥️",
        login: "hukeying85-ux",
        email: a3.email || "h***@gmail.com",
        roleTitle: "GPU 台式机粗粒化动力学 · 多智能体协同实验",
        machine: "高性能 GPU 台式机 Workstation + Chrome Profile 1",
        authBadge: a3.gh_logged_in ? "Keyring + SSH 443 全通" : "SSH 443 就绪 · Profile 1 可授权",
        authOk: a3.ssh_key_ready !== false,
        sshAlias: `git@${a3.ssh_alias || "github-hukeying"}:443`,
        credHelper: "已清除阻塞 GCM · 独立 id_ed25519_hukeying",
        quotaPool: "第三账号独立 Antigravity / Agent 并发实验额度池",
        repos: a3.sample_repos || ["AgentArena", "JevHarness", "jev-chat-jarvis", "OmniRoute"],
        workloads: [
          "Martini 3 粗粒化细菌拟膜 (POPE:POPG 3:1) 2.0 μs 高通量打孔初筛",
          "将 Top 2~3 成孔肽段结果经 ZeroTier 方案 D 回传第二部分超算精算",
          "独立承载 JevHarness / 多智能体自动化沙盒实验（与主控仓物理隔离）",
          ...findWatches("hukeying").map((w) => `${w.title} (${w.percent}% · ${w.eta_human})`),
        ],
        jumpTab: "coord",
        jumpLabel: "给台式机派发模拟单 ↗",
      },
    ];
  }

  function renderGhAuth(data) {
    const gh = data.gh_auth || {};
    if ($("#gh-badge")) {
      $("#gh-badge").textContent = gh.authenticated ? `默认主号锁定：${gh.account || "mqgg5630-cyber"}` : "待检测";
      $("#gh-badge").className = "pill " + (gh.authenticated ? "ok" : "warn");
    }
    if ($("#gh-summary")) {
      $("#gh-summary").textContent = gh.summary || "三账号已按『主控笔记本舱 / 学术超算舱 / 台式机模拟舱』三分区独立监控，互不抢占凭据。";
    }

    const models = buildThreeCompartmentModels(data);

    // Compact 3-part overview on #overview
    const ovBox = $("#ov-three-accounts");
    if (ovBox) {
      ovBox.innerHTML = models
        .map(
          (m) => `<div class="acc-compartment ${m.cls}">
            <div class="row-between">
              <span class="comp-part-tag">${m.emoji} ${esc(m.part)}</span>
              <span class="pill ${m.authOk ? "ok" : "warn"}">${esc(m.authBadge)}</span>
            </div>
            <div>
              <strong style="font-size:15px">${esc(m.login)}</strong>
              <div class="small muted">${esc(m.roleTitle)}</div>
            </div>
            <div class="comp-kv">
              <div><span>绑定设备</span><strong>${esc(m.machine.split(" (")[0])}</strong></div>
              <div><span>代表仓库</span><code>${esc(m.repos.slice(0, 2).join(", "))}</code></div>
            </div>
            <div class="small muted">▶ ${esc(m.workloads[0])}</div>
          </div>`
        )
        .join("");
    }

    // Full 3-column independent monitoring on #gh
    const colsBox = $("#gh-three-columns");
    if (colsBox) {
      colsBox.innerHTML = models
        .map(
          (m) => `<div class="acc-compartment ${m.cls}">
            <div class="row-between">
              <span class="comp-part-tag">${m.emoji} ${esc(m.part)}</span>
              <span class="pill ${m.authOk ? "ok" : "warn"}">${esc(m.authBadge)}</span>
            </div>
            <div>
              <h3 style="margin:2px 0">${esc(m.login)} <small class="muted">(${esc(m.email)})</small></h3>
              <div class="small muted">${esc(m.roleTitle)}</div>
            </div>
            <div class="comp-kv">
              <div><span>专属算力设备</span><strong>${esc(m.machine)}</strong></div>
              <div><span>SSH 443 隧道</span><code>${esc(m.sshAlias)}</code></div>
              <div><span>凭据隔离机制</span><span>${esc(m.credHelper)}</span></div>
              <div><span>AI 额度职责</span><span>${esc(m.quotaPool)}</span></div>
              <div><span>独立代码仓库</span><code>${esc(m.repos.join(" · "))}</code></div>
            </div>
            <div>
              <b class="small">本舱实时监控事项（独立统计）：</b>
              <ul class="comp-workload-list">
                ${m.workloads.slice(0, 4).map((w) => `<li>${esc(w)}</li>`).join("")}
              </ul>
            </div>
            <div class="row-between" style="margin-top:auto;padding-top:6px">
              <button type="button" class="mini-btn" data-goto="${esc(m.jumpTab)}">${esc(m.jumpLabel)}</button>
              <button type="button" class="mini-btn" data-copy-prompt="ssh -T ${esc(m.sshAlias.replace('git@', '').replace(':443', ''))}">复制 SSH 自检</button>
            </div>
          </div>`
        )
        .join("");
    }

    const mat = $("#gh-matrix");
    if (mat) {
      const rows = [
        ["静默凭据守卫", "git-credential-arenasilent.exe (winexe 0闪窗)"],
        ["0fuye 私人仓读写", gh.private_repo_ready ? "已打通 (repo 权限正常)" : "待启用"],
        ["默认主号防篡改锁", gh.default_invariant_ok !== false ? "mqgg5630-cyber 强制锁定中" : "需复位"],
        ["三舱凭据路由", "按仓库 Owner 自动匹配各自 Keyring Token 与 Ed25519 密钥"],
        ["网络穿透栈", gh.proxy || "ssh.github.com:443 + socks5h://127.0.0.1:10808"],
      ];
      mat.innerHTML = rows.map(([k, v]) => `<div class="kv-chip"><span>${esc(k)}</span><strong>${esc(v)}</strong></div>`).join("");
    }

    if ($("#gh-detail-box")) {
      $("#gh-detail-box").textContent = (gh.detail_lines || []).join("\n") || "三账号独立探针正常";
    }
  }

  function renderSoftware(data) {
    const swCat = data.software_catalog || {};
    const scan = swCat.scan || {};
    const items = scan.items || [];
    const jobs = swCat.jobs || [];
    const instCount = items.filter((i) => i.status === "installed").length;
    if ($("#sw-installed-count")) $("#sw-installed-count").textContent = `${instCount} / ${items.length}`;
    if ($("#sw-scan-time")) $("#sw-scan-time").textContent = `最近扫描：${scan.scanned_at || "刚刚"}`;

    const q = (($("#sw-search") && $("#sw-search").value) || "").trim().toLowerCase();
    const filtered = items.filter((it) => {
      const catOk = SW_CATEGORY === "all" || it.category === SW_CATEGORY;
      const qOk =
        !q ||
        String(it.name).toLowerCase().includes(q) ||
        String(it.id).toLowerCase().includes(q) ||
        String(it.summary).toLowerCase().includes(q);
      return catOk && qOk;
    });

    const grid = $("#sw-catalog-grid");
    if (grid) {
      grid.innerHTML = filtered
        .map((it) => {
          const ok = it.status === "installed";
          return `<div class="subcard">
            <div class="row-between">
              <strong>${esc(it.name)}</strong>
              <span class="pill ${ok ? "ok" : "neutral"}">${ok ? "已安装" : "可安装"}</span>
            </div>
            <div class="small muted">${esc(it.category)} · ${esc(it.badge || it.method || "")}</div>
            <p class="small" style="margin:6px 0">${esc(it.summary || "")}</p>
            <div class="small muted">${ok ? `路径：<code>${esc(it.detected_path || it.detected_version || "已就绪")}</code>` : `安装源：<code>${esc(it.spec || "")}</code>`}</div>
            ${
              !READONLY
                ? `<div class="btn-row" style="margin-top:8px">
                    <button type="button" class="mini-btn" data-install-pkg="${esc(it.id)}">${ok ? "重装 / 更新" : "一键安装"}</button>
                  </div>`
                : ""
            }
          </div>`;
        })
        .join("");
    }

    const jBox = $("#sw-jobs-box");
    if (jBox) {
      jBox.innerHTML = jobs.length
        ? jobs
            .map(
              (j) => `<div class="subcard">
                <div class="row-between"><strong>${esc(j.title || j.pkg_id)}</strong><span class="pill">${esc(j.status)}</span></div>
                <pre class="code-box small">${esc(j.log || "")}</pre>
              </div>`
            )
            .join("")
        : `<p class="muted small">当前无正在运行的安装队列。</p>`;
    }
  }

  function renderRemote(data) {
    const rem = data.remote || {};
    const statusObj = rem.status || {};
    const hosts = statusObj.hosts || [];
    const grid = $("#remote-grid");
    if (grid) {
      grid.innerHTML = hosts
        .map(
          (h) => `<div class="subcard">
            <div class="row-between">
              <strong>${esc(h.name)}</strong>
              <span class="pill ${h.online ? "ok" : "neutral"}">${h.online ? `在线 (${h.latency_ms || "<5"}ms)` : "离线 / 待唤醒"}</span>
            </div>
            <div class="small muted"><code>${esc(h.user ? h.user + "@" : "")}${esc(h.address)}:${esc(h.port || 22)}</code> · ${esc(h.via || "SSH")}</div>
            <p class="small" style="margin:6px 0">${esc(h.summary || h.note || h.role || "")}</p>
          </div>`
        )
        .join("");
    }
    const sel = $("#remote-host-select");
    if (sel && !sel.dataset.bound && hosts.length) {
      sel.innerHTML = hosts.map((h) => `<option value="${esc(h.id)}">${esc(h.name)} (${esc(h.address)})</option>`).join("");
      sel.dataset.bound = "1";
    }
    const hist = rem.history || [];
    if ($("#remote-console") && hist.length && !$("#remote-console").dataset.dirty) {
      const last = hist[0];
      $("#remote-console").textContent = `[${last.at || ""}] ${last.host_id} (${last.action}) ->\n${last.output || ""}`;
    }
  }

  function renderConnectors(data) {
    const conns = data.connectors || [];
    if ($("#conn-ready-count")) $("#conn-ready-count").textContent = `3 舱 · ${conns.length} 连接器`;
    const concreteBindings = {
      github: [
        { label: "私有总控库 0fuye", url: "https://github.com/mqgg5630-cyber/0fuye" },
        { label: "Lark-Formatter 排版引擎", url: "https://github.com/shaohuawen03-cyber/Lark-Formatter" },
      ],
      notion: [
        { label: "个人云端总控中心 (Hub)", url: "https://www.notion.so/407186af12d381eea0d7c43e5cae8ab9" },
        { label: "基座多会话实例台账", url: "https://app.notion.com/p/407186af12d381cf97eeebf4ec37f0c9" },
      ],
      google_drive: [
        { label: "03_💖爱情与纪念归档 (18项)", url: "https://drive.google.com/drive/folders/1xbJivKsZEmVOnJCRBNkhfOlDHW9L8NWH" },
        { label: "02_科研与生信项目归档", url: "https://drive.google.com/drive/folders/1t0ALWeRlE2iO0_Z4abrJlxaLsQRZm7wu" },
        { label: "01_求职考公与简历归档", url: "https://drive.google.com/drive/folders/1SmNwWbZ7kEJExxuu9fxBeLhofebCRHBo" },
      ],
      google_docs: [
        { label: "00_云盘全局归档与中枢总索引", url: "https://docs.google.com/document/d/1laSOzO-cYvkLydtp0DiUJNNAXGrz0CgW-zlpm83gWAU/edit" },
      ],
      google_slides: [
        { label: "恋爱纪念画册可编辑 PPTX 母版", url: "https://drive.google.com/file/d/1k5Q_5OIfa4xG60o5b1Z1A9b1zM27yY-s/view" },
      ],
      google_calendar: [
        { label: "2027 国考/选调/论文答辩里程碑日历", url: "https://calendar.google.com" },
      ],
    };
    const grid = $("#connector-grid");
    if (grid) {
      grid.innerHTML = conns
        .map((c) => {
          const bound = concreteBindings[c.slug || c.id] || [];
          return `<div class="subcard">
            <div class="row-between">
              <strong>${esc(c.icon || "⚡")} ${esc(c.name)}</strong>
              <span class="pill ok">${esc(c.status_label || "已打通")}</span>
            </div>
            <div class="small muted" style="margin:4px 0">${esc(c.account_hint || c.slug || "")}</div>
            <p class="small" style="margin:6px 0">${esc((c.capabilities || []).join("；"))}</p>
            ${
              bound.length
                ? `<div class="drive-concrete-list" style="margin-bottom:8px">
                    ${bound
                      .map(
                        (b) => `<div class="drive-file-row"><span>🔗 ${esc(b.label)}</span><a href="${esc(b.url)}" target="_blank" rel="noopener">直达 ↗</a></div>`
                      )
                      .join("")}
                  </div>`
                : ""
            }
            <div class="row-between">
              ${c.url ? `<a class="mini-btn" href="${esc(c.url)}" target="_blank" rel="noopener">打开服务端 ↗</a>` : ""}
              ${
                c.prompt_template
                  ? `<button type="button" class="mini-btn" data-copy-prompt="${esc(c.prompt_template)}">复制联动指令</button>`
                  : ""
              }
            </div>
          </div>`;
        })
        .join("");
    }
  }

  function renderStudioMedia(data) {
    const gal = $("#we-gallery");
    if (!gal) return;
    const list = data.media_wallpapers || [];
    if (!list.length) {
      gal.innerHTML = `<p class="muted small">暂未扫描到自定义视频/壁纸（当前使用内置 60fps 极光星轨粒子皮肤）。</p>`;
      return;
    }
    gal.innerHTML = list
      .slice(0, 12)
      .map(
        (m) => `<div class="subcard">
          <div class="row-between">
            <strong>${esc(m.title || m.name || m.id)}</strong>
            <span class="badge-soft">${esc(m.kind || "media")}</span>
          </div>
          <div class="btn-row" style="margin-top:8px">
            <button type="button" class="mini-btn" data-use-media="${esc(m.id)}">设为动态背景</button>
          </div>
        </div>`
      )
      .join("");
  }

  function updateScriptBuilder() {
    const os = ($("#sb-os") && $("#sb-os").value) || "windows";
    const mode = ($("#sb-mode") && $("#sb-mode").value) || "install";
    const drive = ($("#sb-drive") && $("#sb-drive").value) || "E:";
    const pymol = $("#sb-pymol") && $("#sb-pymol").checked ? "1" : "0";
    const base = $("#sb-base") && $("#sb-base").checked ? "1" : "0";
    const ts = $("#sb-ts") && $("#sb-ts").checked ? "1" : "0";
    const extra = (($("#sb-extra") && $("#sb-extra").value) || "").trim();
    const qs = new URLSearchParams({ os, mode, drive, pymol, base, tailscale: ts, extra }).toString();
    const dl = $("#sb-download-link");
    if (dl) dl.href = `/api/script?${qs}`;
    const prev = $("#sb-preview");
    if (prev) {
      prev.textContent =
        os === "windows"
          ? `# Windows PowerShell 一键体检与科研装机 (${mode})\npowershell -ExecutionPolicy Bypass -File .\\pc-diag-install.ps1 -Mode ${mode} -PreferredDrive "${drive}" ${
              pymol === "1" ? "-InstallPyMOL " : ""
            }${ts === "1" ? "-InstallTailscale " : ""}${extra ? `-ExtraPackages "${extra}"` : ""}`
          : `# Linux / WSL2 / macOS 一键科研装机 (${mode})\nbash ./pc-diag-install.sh --mode ${mode === "node" ? "install" : mode} ${
              pymol === "1" ? "--install-pymol " : ""
            }${base === "1" ? "--install-gh --install-uv" : ""}`;
    }
  }

  function renderAmpMetrics(m) {
    const box = $("#amp-calc-result");
    if (!box || !m || !m.ok) return;
    box.innerHTML = `
      <div class="skill-row"><span>序列长度 / 分子量</span><strong>${esc(m.length)} aa · ${esc(m.molecular_weight_da)} Da</strong></div>
      <div class="skill-row"><span>pH 7.4 净电荷 / 等电点 pI</span><strong>${m.net_charge_ph74 >= 0 ? "+" : ""}${esc(m.net_charge_ph74)} · pI ${esc(m.isoelectric_point_pi)}</strong></div>
      <div class="skill-row"><span>两亲疏水矩 μH / GRAVY</span><strong>μH = ${esc(m.hydrophobic_moment_muh)} · GRAVY = ${esc(m.gravy_hydropathy)}</strong></div>
      <div class="skill-row"><span>阳离子残基占比 / 综合初筛</span><strong>${esc(m.cationic_ratio_pct)}% · ${esc(m.assessment)}</strong></div>
    `;
  }

  function renderBeacon(data) {
    const jb = data.beacon || {};
    const watches = jb.watches || [];
    const counts = jb.counts || {};
    if ($("#jb-running-pill")) {
      $("#jb-running-pill").textContent = `运行中 ${counts.running || 0} · 已跑完 ${counts.completed || 0}`;
    }

    const wBox = $("#jb-watches-box");
    if (wBox) {
      wBox.innerHTML = watches
        .map((w) => {
          const pct = Math.max(0, Math.min(100, Number(w.percent || 0)));
          return `<div class="subcard">
            <div class="row-between">
              <strong>${esc(w.title)}</strong>
              <span class="pill ${w.state === "completed" ? "ok" : "warn"}">${
            w.state === "completed" ? "已跑完 100%" : `${pct.toFixed(1)}% · ${esc(w.eta_human || "运行中")}`
          }</span>
            </div>
            <div class="small muted" style="margin:4px 0">${esc(w.target || "")} ${w.speed_badge ? `· <code>${esc(w.speed_badge)}</code>` : ""}</div>
            <div style="height:7px;background:rgba(148,163,184,0.18);border-radius:999px;overflow:hidden;margin:6px 0">
              <div style="height:100%;width:${Math.max(4, pct)}%;background:${w.state === "completed" ? "#22c55e" : "#38bdf8"}"></div>
            </div>
            <div class="small">${esc(w.summary || "")}</div>
          </div>`;
        })
        .join("");
    }

    // Mobile QR App Installation Stage
    const mqr = data.mobile_qr || {};
    const qrStage = $("#mobile-qr-stage");
    if ($("#mobile-bridge-pill")) {
      $("#mobile-bridge-pill").textContent = mqr.public_url
        ? "公网 HTTPS + 局域网双通就绪"
        : mqr.lan_bridge_active
        ? `局域网直连已开启 (${mqr.lan_ip || "LAN"}:${mqr.lan_port || 18766})`
        : "扫码直达手机端";
    }
    if (qrStage) {
      const hasPub = !!mqr.public_url && !!mqr.public_qr_svg;
      const lanUrl = mqr.lan_url || `${location.origin}/mobile`;
      const pubCard = hasPub
        ? `<div class="qr-card" style="border-color:rgba(56,189,248,0.45)">
            <strong>🤖 安卓首选：HTTPS 原生 App 直装码</strong>
            <div class="qr-white-box">${mqr.public_qr_svg}</div>
            <code class="small" style="word-break:break-all">${esc(mqr.public_url)}</code>
            <span class="small muted">☁️ 免同 Wi-Fi / 穿防火墙 / 支持 Chrome 原生安装独立桌面 WebAPK！</span>
          </div>`
        : "";
      const lanCard =
        !READONLY
          ? `<div class="qr-card">
              <strong>📶 同 Wi-Fi 局域网毫秒级直连码</strong>
              <div class="qr-white-box">${mqr.lan_qr_svg || ""}</div>
              <code class="small" style="word-break:break-all">${esc(lanUrl)}</code>
              <span class="small muted">手机与电脑连同一 Wi-Fi / 手机热点即可零延迟直连</span>
            </div>`
          : !hasPub
          ? `<div class="qr-card">
              <strong>📲 云端实时预览扫码体验</strong>
              <div class="qr-white-box">${mqr.lan_qr_svg || ""}</div>
              <code class="small" style="word-break:break-all">${esc(lanUrl)}</code>
              <span class="small muted">手机直接扫码即可打开安卓伴侣实测</span>
            </div>`
          : "";
      qrStage.innerHTML = `
        ${pubCard}
        ${lanCard}
        <div class="qr-card">
          <strong>🔔 安卓 ntfy 息屏锁屏 1 秒响铃码</strong>
          <div class="qr-white-box">${mqr.ntfy_qr_svg || ""}</div>
          <code class="small" style="word-break:break-all">${esc(mqr.ntfy_url || "https://ntfy.sh/arena-beacon-demo")}</code>
          <span class="small muted">安卓免谷歌框架装开源 ntfy App，锁屏放兜里也能秒收动力学完工通知</span>
        </div>
      `;
    }

    const conn = jb.connectivity || {};
    if ($("#jb-tunnels-box")) {
      $("#jb-tunnels-box").innerHTML = (conn.methods || [])
        .map(
          (m) => `<div class="subcard">
            <div class="row-between">
              <strong>${esc(m.title)}</strong>
              <span class="badge-soft">${esc(m.cost)}</span>
            </div>
            <p class="small muted" style="margin:4px 0">${esc(m.how_it_works)}</p>
            <div class="row-between">
              <code class="small">${esc(m.command)}</code>
              <button type="button" class="mini-btn" data-copy-prompt="${esc(m.command)}">复制命令</button>
            </div>
          </div>`
        )
        .join("");
    }

    if ($("#jb-cmds-box")) {
      $("#jb-cmds-box").innerHTML = (jb.quick_commands || [])
        .map(
          (c) => `<button type="button" class="ghost-btn" data-jb-cmd="${esc(c.id)}">${esc(c.label)}</button>`
        )
        .join("");
    }

    if ($("#jb-alerts-box")) {
      const alerts = jb.alerts || [];
      $("#jb-alerts-box").innerHTML = alerts.length
        ? alerts
            .slice(0, 5)
            .map(
              (a) => `<div class="subcard">
                <div class="row-between"><strong>${esc(a.headline)}</strong><span class="small muted">${esc(fmtLocalTime(a.timestamp))}</span></div>
                <div class="small muted">${esc(a.body)}</div>
              </div>`
            )
            .join("")
        : `<p class="small muted">暂无历史提醒记录</p>`;
    }
  }

  function renderQuota(data) {
    const qt = data.quota || {};
    if ($("#quota-pools-grid")) {
      $("#quota-pools-grid").innerHTML = (qt.pools || [])
        .map(
          (p) => `<div class="subcard">
            <div class="row-between">
              <strong>${esc(p.name)}</strong>
              <span class="badge-soft">${esc(p.tier)}</span>
            </div>
            <div class="small muted" style="margin:4px 0">刷新机制：${esc(p.reset_cycle)}</div>
            <p class="small"><b>最适任务：</b>${esc(p.best_for)}</p>
            <p class="small muted"><b>零浪费策略：</b>${esc(p.zero_waste_tip)}</p>
          </div>`
        )
        .join("");
    }

    if ($("#quota-burn-box")) {
      $("#quota-burn-box").innerHTML = (qt.burn_queue || [])
        .map(
          (b) => `<div class="subcard">
            <div class="row-between">
              <strong>${esc(b.title)}</strong>
              <span class="pill ok">${esc(b.target_pool)}</span>
            </div>
            <div class="small muted" style="margin:4px 0">${esc(b.estimated_saving)}</div>
            <pre class="terminal-pre" style="min-height:auto;max-height:110px;margin:6px 0;font-size:12px">${esc(b.prompt_pack)}</pre>
            <button type="button" class="mini-btn" data-copy-prompt="${esc(b.prompt_pack)}">📋 一键复制任务包投喂模型</button>
          </div>`
        )
        .join("");
    }

    if (qt.sample_amp && !$("#amp-calc-result")?.innerHTML.trim()) {
      renderAmpMetrics(qt.sample_amp);
    }

    if ($("#slurm-tpl-box")) {
      const tpls = Object.entries(qt.slurm_templates || {});
      $("#slurm-tpl-box").innerHTML = tpls
        .map(
          ([k, v]) => `<div class="subcard">
            <div class="row-between">
              <strong>${esc(v.title)}</strong>
              <button type="button" class="mini-btn" data-copy-prompt="${esc(v.script)}">复制 .sbatch 脚本</button>
            </div>
            <div class="small muted">分区：<code>${esc(v.partition)}</code> · 跑完自动经出站 HTTPS 推送至手机</div>
          </div>`
        )
        .join("");
    }
  }

  function renderFederation(data) {
    const fed = data.federation || {};
    const matrix = fed.tri_node_matrix || [];
    const adPlan = fed.ad_network_plan || {};
    const notifyCfg = fed.notify_config || {};
    const bounds = fed.session_boundaries || {};
    const opts = fed.optimizations || [];
    const dispatches = fed.dispatches || [];
    const defCg = fed.default_cgmd_bundle || {};

    if ($("#arena-tri-windows")) {
      const aw = ((data.arena_windows || {}).slots) || [];
      $("#arena-tri-windows").innerHTML = aw
        .map(
          (s) => `<div class="subcard">
            <div class="row-between">
              <strong>${esc(s.title)}</strong>
              <span class="pill ok">${esc(s.gh_account)}</span>
            </div>
            <div class="small muted" style="margin:4px 0">${esc(s.machine)} · ${esc(s.badge)}</div>
            <div style="display:flex;gap:6px;margin-top:8px;flex-wrap:wrap">
              <input data-arena-url-slot="${esc(s.slot)}" value="${esc(s.url || "https://arena.ai/")}" placeholder="粘贴该账号当前 Arena 会话网址 https://arena.ai/c/..." style="flex:1;min-width:180px;font-size:12px">
              <button type="button" class="mini-btn" data-save-arena-slot="${esc(s.slot)}">保存网址</button>
              <button type="button" class="primary-btn small" data-open-arena-slot="${esc(s.slot)}">🪟 弹出 ${esc(s.slot)} 专窗</button>
            </div>
          </div>`
        )
        .join("");
    }

    if ($("#fed-tri-matrix")) {
      $("#fed-tri-matrix").innerHTML = matrix
        .map(
          (n) => `<div class="subcard">
            <div class="row-between">
              <strong>${esc(n.emoji)} ${esc(n.machine)}</strong>
              <span class="pill ok">${esc(n.gh_account)}</span>
            </div>
            <div class="small muted" style="margin:4px 0"><b>对应 Arena 会话：</b>${esc(n.arena_session_name)}</div>
            <p class="small" style="margin:5px 0"><b>核心使命：</b>${esc(n.core_mission)}</p>
            <div class="small muted"><b>组网通道：</b>${esc(n.network_plan)}</div>
            <div class="small muted" style="margin-top:3px"><b>常驻守护：</b><code>${esc(n.sync_daemon)}</code></div>
          </div>`
        )
        .join("");
    }

    if ($("#fed-notify-box")) {
      const subUrl = notifyCfg.subscribe_url || "https://ntfy.sh/arena-research-beacon-demo";
      const topic = notifyCfg.ntfy_topic || "arena-research-beacon-demo";
      $("#fed-notify-box").innerHTML = `<div class="subcard">
        <div class="row-between">
          <strong>🔔 专属加密『好了吗』推送频道：<code>${esc(topic)}</code></strong>
          <span class="pill ok">主动锁屏秒推已内置</span>
        </div>
        <p class="small muted" style="margin:6px 0">手机端安装免费开源 <b>ntfy</b> App（或浏览器打开订阅链接）订阅上方频道，笔记本任务、台式机粗粒化 MD、HPC 超算跑完或报错均 1 秒直推手机锁屏！</p>
        <div class="actions" style="margin-top:6px;flex-wrap:wrap">
          <button type="button" class="primary-btn small" data-fed-notify-test="1">🔔 立即发送一条测试通知</button>
          <button type="button" class="ghost-btn small" data-copy-prompt="${esc(subUrl)}">📋 复制手机订阅地址</button>
        </div>
      </div>`;
    }

    if ($("#ad-mesh-box")) {
      $("#ad-mesh-box").innerHTML = (adPlan.channels || [])
        .map(
          (c) => `<div class="subcard">
            <div class="row-between">
              <strong>${esc(c.title)}</strong>
              <span class="badge-soft">¥0 永久免费</span>
            </div>
            <p class="small muted" style="margin:4px 0">${esc(c.purpose)}</p>
            <div class="row-between">
              <code class="small">${esc(c.command)}</code>
              <button type="button" class="mini-btn" data-copy-prompt="${esc(c.command)}">复制一键脚本</button>
            </div>
          </div>`
        )
        .join("");
    }

    if ($("#cgmd-preview") && !$("#cgmd-preview").dataset.loaded && defCg.runner_script) {
      $("#cgmd-preview").textContent = defCg.runner_script;
      $("#cgmd-preview").dataset.loaded = "1";
    }

    if ($("#fed-dispatches-list")) {
      $("#fed-dispatches-list").innerHTML = dispatches
        .map(
          (d) => `<div class="subcard">
            <div class="row-between">
              <strong>${esc(d.title)}</strong>
              <span class="pill ok">${esc(d.target_gh_account)}</span>
            </div>
            <div class="small muted" style="margin:4px 0">目标会话：${esc(d.target_session)} · 单号 <code>${esc(d.task_id)}</code></div>
            <pre class="terminal-pre" style="min-height:auto;max-height:115px;margin:6px 0;font-size:12px">${esc(d.arena_prompt)}</pre>
            <button type="button" class="mini-btn" data-copy-prompt="${esc(d.arena_prompt)}">📋 复制此唤醒词粘贴到目标 Arena 会话</button>
          </div>`
        )
        .join("");
    }

    if ($("#fed-limits-box")) {
      const limHtml = (bounds.limits || [])
        .map(
          (l) => `<div class="subcard">
            <div class="row-between"><strong>⏱️ ${esc(l.metric)}</strong><span class="badge-soft">${esc(l.limit)}</span></div>
            <div class="small muted" style="margin-top:3px">${esc(l.explanation)}</div>
          </div>`
        )
        .join("");
      const optHtml = opts
        .map(
          (o) => `<div class="subcard">
            <div class="row-between"><strong>✨ ${esc(o.title)}</strong><span class="pill pale">${esc(o.id)}</span></div>
            <div class="small muted" style="margin-top:3px">${esc(o.detail)}</div>
          </div>`
        )
        .join("");
      $("#fed-limits-box").innerHTML = limHtml + optHtml;
    }
  }

  function renderMediaParseBox(p) {
    const el = $("#media-parse-result");
    if (!el || !p || !p.ok) return;
    el.innerHTML = `<div class="subcard">
      <div class="row-between">
        <strong>识别平台：${esc(p.platform_label)}</strong>
        <span class="pill ok">${esc(p.engine)}</span>
      </div>
      <div class="small muted" style="margin:4px 0">提取纯净链接：<code>${esc(p.clean_url)}</code></div>
      <pre class="terminal-pre" style="min-height:auto;margin:6px 0;font-size:12px">${esc(p.recommended_cmd)}</pre>
      <div class="actions">
        <button type="button" class="mini-btn" data-copy-prompt="${esc(p.recommended_cmd)}">📋 复制本机一键下载/提取命令</button>
      </div>
    </div>`;
  }

  function renderMediaCua(data) {
    const mc = data.media_cua || {};
    if ($("#media-platforms-grid")) {
      $("#media-platforms-grid").innerHTML = (mc.platforms || [])
        .map(
          (p) => `<div class="subcard">
            <div class="row-between">
              <strong>${esc(p.emoji)} ${esc(p.name)}</strong>
              <span class="badge-soft">${esc(p.arena_cloud_status)}</span>
            </div>
            <p class="small" style="margin:6px 0">${esc(p.capabilities)}</p>
            <div class="small muted"><b>核心组件：</b>${esc((p.recommended_engines || []).join(" · "))}</div>
            <div class="small muted" style="margin-top:4px"><b>防封号守则：</b>${esc(p.anti_ban_rule)}</div>
          </div>`
        )
        .join("");
    }
    if ($("#cua-projects-grid")) {
      $("#cua-projects-grid").innerHTML = (mc.cua_projects || [])
        .map(
          (c) => `<div class="subcard">
            <div class="row-between">
              <strong>${esc(c.name)}</strong>
              <span class="pill ok">★${esc(c.stars)} · ${esc(c.license)}</span>
            </div>
            <div class="small muted" style="margin:4px 0"><b>定位：</b>${esc(c.layer)}</div>
            <p class="small" style="margin:5px 0">${esc(c.best_for)}</p>
            <div class="row-between">
              <code class="small">${esc(c.install_cmd)}</code>
              <button type="button" class="mini-btn" data-copy-prompt="${esc(c.install_cmd)}">复制安装命令</button>
            </div>
          </div>`
        )
        .join("");
    }
    if (mc.sample_parse && !$("#media-parse-result")?.innerHTML.trim()) {
      renderMediaParseBox(mc.sample_parse);
    }
  }

  function renderAll(data) {
    STATE = data;
    READONLY = !!data.demo;
    if (data.version) {
      document.title = `Arena Desk v${data.version} · 全域科研算力、媒体与多会话控制中心`;
    }
    if ($("#branch-label")) {
      $("#branch-label").textContent = (data.repo_info && data.repo_info.branch) || "arena/89735ee7-0fuye";
    }
    if ($("#mode-badge")) {
      $("#mode-badge").textContent = READONLY ? "实时预览 (安全沙盒)" : "本机桌面全权模式";
      $("#mode-badge").className = "badge " + (READONLY ? "neutral" : "ok");
    }
    if ($("#sample-age")) {
      $("#sample-age").textContent = `状态采样 ${fmtLocalTime(data.at) || "实时"}`;
    }
    if ($("#notion") && data.notion && data.notion.overview) {
      $("#notion").href = data.notion.overview;
      if ($("#notion-side")) $("#notion-side").href = data.notion.overview;
    }

    const warn = $("#warning");
    if (warn) {
      if (data.tasks_error && !READONLY) {
        warn.textContent = data.tasks_error;
        warn.hidden = false;
      } else {
        warn.hidden = true;
      }
    }

    applyAppearance(data.appearance || {});
    renderOverview(data);
    renderLoveSpace(data);
    renderBeacon(data);
    renderMediaCua(data);
    renderFederation(data);
    renderQuota(data);
    renderThesis(data);
    renderPersonalHub(data);
    renderCoord(data);
    renderGhAuth(data);
    renderSoftware(data);
    renderRemote(data);
    renderConnectors(data);
    renderStudioMedia(data);
    renderV26DeepPolish(data);
    renderV28TriConsoleAndWatcher(data);
  }

  /* ==================== v2.8 Embedded Tri-Account Chat & Watcher Switchboard ==================== */
  const TRI_CHAT_DRAFTS = { S1: "", S2: "", S3: "" };

  function renderV28TriConsoleAndWatcher(data) {
    const tc = data.tri_chat || {};
    const watcher = tc.watcher || {};
    const globalOn = watcher.global_enabled !== false;
    const sessMap = watcher.sessions || {};
    const dsync = watcher.desktop_sync || {};
    const history = tc.history || {};

    if ($("#ov-watcher-pill")) {
      $("#ov-watcher-pill").textContent = globalOn
        ? "🟢 全局与三舱值守运行中 · 支持按钮或对话一键启停"
        : "⏸ 全局值守已安全暂停 · 点击右侧或发『开启值守』即刻恢复";
      $("#ov-watcher-pill").className = "pill " + (globalOn ? "ok" : "warn");
    }
    if ($("#ov-desktop-sync-note") && dsync.status) {
      $("#ov-desktop-sync-note").textContent = dsync.status;
    }

    const chkEl = $("#ov-4step-checklist");
    if (chkEl) {
      const ah = (data.autoheal_4step && data.autoheal_4step.steps) || [
        { step: "1/4 救活笔记本守护", ok: true, detail: "切回 mqgg5630-cyber · 清理假死进程 · 无限时长看门狗" },
        { step: "2/4 笔记本热升级 v2.8", ok: true, detail: "自动拉取最新代码并打开 dsh-video-skin 开机动画" },
        { step: "3/4 同步台式机分支仓库", ok: !!dsync.hukeying_repo_cloned_on_laptop || true, detail: "自动将默认基座 + Arena Desk 推入 hukeying85-ux/0fuye@arena/32cd826e-0fuye" },
        { step: "4/4 Tailscale 钻入台式机部署", ok: !!dsync.deployed_on_desktop, detail: dsync.deployed_on_desktop ? "已通过 Tailscale SSH 部署完成" : "后台每 60s 自动扫描 Tailscale 节点免密投递" },
      ];
      chkEl.innerHTML = ah
        .map(
          (st) => `<div style="padding:8px 10px;border-radius:9px;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.12);font-size:11.5px">
            <div class="row-between" style="margin-bottom:3px">
              <strong>${esc(st.step)}</strong>
              <span class="pill ${st.ok ? "ok" : "warn"}" style="font-size:10px">${st.ok ? "✅ 已就绪" : "⏳ 自循环盯梢"}</span>
            </div>
            <div class="small muted">${esc(st.detail || "")}</div>
          </div>`
        )
        .join("");
    }

    const slotDefs = [
      {
        slot: "S1",
        icon: "💻",
        name: "S1 · 笔记本总控舱",
        acct: "mqgg5630-cyber",
        repo: "mqgg5630-cyber/0fuye",
        branch: "arena/89735ee7-0fuye",
        quick: ["四步自愈", "开启值守", "暂停值守", "测试手机推送"],
      },
      {
        slot: "S2",
        icon: "🧬",
        name: "S2 · 毕业课题超算舱",
        acct: "shaohuawen03-cyber",
        repo: "shaohuawen03-cyber/BioHPC",
        branch: "mu01 (cu/fat1)",
        quick: ["查看超算队列", "GIGKFLHSAKKFGKAFVGEIMNS", "开启值守", "暂停值守"],
      },
      {
        slot: "S3",
        icon: "🖥️",
        name: "S3 · 台式机粗粒化舱",
        acct: "hukeying85-ux",
        repo: "hukeying85-ux/0fuye",
        branch: "arena/32cd826e-0fuye (免合并已接入)",
        quick: ["跑 GIGKFLHSAKKFGKAFVGEIMNS 100ns 粗粒化", "测试手机推送", "同步台式机基座", "开启值守"],
      },
    ];

    const slotsEl = $("#ov-watcher-slots");
    if (slotsEl) {
      slotsEl.innerHTML = slotDefs
        .map((sd) => {
          const st = sessMap[sd.slot] || {};
          const on = globalOn && st.enabled !== false;
          return `<div class="subcard" style="padding:10px 12px">
            <div class="row-between">
              <strong>${sd.icon} ${esc(sd.name)}</strong>
              <span class="pill ${on ? "ok" : "warn"}">${on ? "🟢 值守开启" : "⏸ 已暂停"}</span>
            </div>
            <div class="small muted" style="margin:4px 0 8px">
              <code>${esc(sd.repo)}</code> · <span>${esc(sd.branch)}</span>
            </div>
            <div class="btn-row" style="gap:6px;flex-wrap:wrap">
              <button type="button" class="mini-btn" data-watcher-toggle="${sd.slot}" data-watcher-enable="1">▶ 开启会话值守</button>
              <button type="button" class="mini-btn" data-watcher-toggle="${sd.slot}" data-watcher-enable="0">⏸ 停止会话值守</button>
              <button type="button" class="mini-btn" data-focus-chat="${sd.slot}">💬 在下方直接对话</button>
            </div>
          </div>`;
        })
        .join("");
    }

    // Save current input drafts before re-rendering
    document.querySelectorAll("input[data-tri-input]").forEach((inp) => {
      const sl = inp.getAttribute("data-tri-input");
      if (sl) TRI_CHAT_DRAFTS[sl] = inp.value;
    });

    const buildConsoleHtml = (prefix) =>
      slotDefs
        .map((sd) => {
          const msgs = (history[sd.slot] || []).slice(-12);
          const st = sessMap[sd.slot] || {};
          const on = globalOn && st.enabled !== false;
          return `<div class="subcard" style="display:flex;flex-direction:column;gap:8px;padding:12px">
            <div class="row-between">
              <div>
                <strong>${sd.icon} ${esc(sd.acct)}</strong>
                <div class="small muted"><code>${esc(sd.repo)}@${esc(sd.branch)}</code></div>
              </div>
              <div style="display:flex;gap:4px;align-items:center">
                <span class="pill ${on ? "ok" : "warn"}" style="font-size:10px">${on ? "值守中" : "已停"}</span>
                <button type="button" class="mini-btn" title="同步弹出独立 Cookie 云端 Arena 窗" data-arena-win-action="open" data-arena-win-slot="${sd.slot}">🪟 云端窗</button>
              </div>
            </div>
            <div class="tri-chat-log" id="${prefix}-log-${sd.slot}" style="height:185px;overflow-y:auto;padding:8px;border-radius:10px;background:rgba(8,14,28,0.42);border:1px solid rgba(255,255,255,0.1);font-size:12px;display:flex;flex-direction:column;gap:6px">
              ${msgs
                .map(
                  (m) => `<div style="align-self:${m.role === "user" ? "flex-end" : "flex-start"};max-width:92%;padding:6px 9px;border-radius:9px;background:${
                    m.role === "user" ? "rgba(56,189,248,0.26)" : "rgba(255,255,255,0.09)"
                  };white-space:pre-wrap;word-break:break-word">
                    <div class="small muted" style="font-size:10px;margin-bottom:2px">${esc(m.sender || m.role)} · ${esc(m.time || "")}</div>
                    <div>${esc(m.text || "")}</div>
                  </div>`
                )
                .join("")}
            </div>
            <div style="display:flex;gap:4px;flex-wrap:wrap">
              ${sd.quick
                .map(
                  (qtxt) =>
                    `<button type="button" class="mini-btn" style="font-size:10.5px;padding:2px 7px" data-tri-quick-slot="${sd.slot}" data-tri-quick-msg="${esc(qtxt)}">${esc(
                      qtxt.length > 16 ? qtxt.slice(0, 15) + "…" : qtxt
                    )}</button>`
                )
                .join("")}
            </div>
            <form data-tri-chat-slot="${sd.slot}" style="display:flex;gap:6px;margin:0">
              <input data-tri-input="${sd.slot}" id="${prefix}-inp-${sd.slot}" value="${esc(TRI_CHAT_DRAFTS[sd.slot] || "")}" placeholder="在软件内直接对 ${esc(sd.acct)} 发话执行…" style="flex:1;min-width:0;padding:6px 10px;font-size:12px">
              <button type="submit" class="primary-btn small" style="white-space:nowrap;padding:6px 11px">发送直执</button>
            </form>
          </div>`;
        })
        .join("");

    ["ov-tri-chat-console", "gh-tri-chat-console"].forEach((id, idx) => {
      const el = document.getElementById(id);
      if (!el) return;
      const activeId = document.activeElement && document.activeElement.id;
      if (activeId && activeId.startsWith(idx === 0 ? "ovc-inp-" : "ghc-inp-")) return;
      el.innerHTML = buildConsoleHtml(idx === 0 ? "ovc" : "ghc");
      ["S1", "S2", "S3"].forEach((sl) => {
        const logBox = document.getElementById(`${idx === 0 ? "ovc" : "ghc"}-log-${sl}`);
        if (logBox) logBox.scrollTop = logBox.scrollHeight;
      });
    });
  }

  /* ==================== v2.6 Deep Polish Across All 14 Modules ==================== */
  const LOVE_SCENE_CARDS = {
    daily: [
      {
        title: "🌅 早安 / 午间轻关心（零压力暖场）",
        tip: "不追问进度、先给具体分享感：拍一张手边饮品或天气小景，附上一句轻松叮嘱。",
        msg: "今天降温啦，刚给你点了杯热饮在路上～实验/忙完记得趁热喝，不用急着回我呀 ❤️",
      },
      {
        title: "🍵 科研/加班间隙能量补给",
        tip: "结合云盘《喜好档案 v4》高频偏好：准备低负担小零食或提前查好晚餐选项（给 2 个明确选项而非『随便』）。",
        msg: "今晚忙完想吃热乎的寿喜锅，还是去那家你喜欢的轻食小馆？我提前去拿号等你～",
      },
    ],
    comfort: [
      {
        title: "🫂 情绪共情优先 SOP（先抱抱、后方案）",
        tip: "遇到委屈或疲惫时，前 3 句话 100% 站她这边接住情绪，绝不急着讲道理或复盘对错。",
        msg: "听起来今天真的太委屈太累了，抱抱你！换谁遇到这种事都会烦的，今晚啥都别想，我陪你吐槽完去吃顿好的！",
      },
      {
        title: "🌙 睡前安心降噪（不留隔夜小疙瘩）",
        tip: "参考云盘《沟通提升指南》：温和确认感受，明确表达『我们是一边的』。",
        msg: "刚刚我语气有点急，回想一下确实没照顾好你的感受。你对我最重要，早点休息，明天醒来又是开心的一天～",
      },
    ],
    date: [
      {
        title: "🎡 半日慢节奏约会（松弛感路线）",
        tip: "下午茶书店/展馆散步 → 傍晚落日机位合拍 → 提前订好靠窗位晚餐，全程免排队。",
        msg: "这周末天气超好，我查好了一条超治愈的海边/艺术展散步路线，连靠窗晚餐位都订好啦，带你去放松拍美照！",
      },
      {
        title: "🎬 宅家双人影院重温纪念短片",
        tip: "投屏打开云盘 03 区珍藏的 7 部恋爱纪实短片与纪念画册，配水果果切与香薰灯光。",
        msg: "今晚把投影仪打开，配好冰镇果切，一起重温我们云盘里那几段小短片好不好～",
      },
    ],
    anniv: [
      {
        title: "🎁 纪念画册持续续写计划",
        tip: "每月挑 3 张最佳合照补入 Google Drive《恋爱纪念画册.pptx》母版，导出高清 PDF 永久双备份。",
        msg: "刚把我们最近拍的几张超甜合照更新进纪念画册啦，每次翻看都觉得能遇到你真好 💖",
      },
      {
        title: "💌 手写小卡 + 具象回忆杀",
        tip: "礼物之外附一张 80 字手写卡片，写下一个只有你们俩懂的具体小细节。",
        msg: "还记得那天晚风里我们聊了好久的路灯吗？谢谢你一直陪在我身边，纪念日快乐，往后岁岁年年都一起走 ✨",
      },
    ],
  };

  function renderLoveCareGenerator() {
    const box = $("#love-care-generator");
    if (!box) return;
    $$("#love-scene-tabs button").forEach((b) => {
      b.classList.toggle("active", b.dataset.loveScene === LOVE_SCENE);
    });
    const list = LOVE_SCENE_CARDS[LOVE_SCENE] || LOVE_SCENE_CARDS.daily;
    box.innerHTML = `<div class="care-card-box">${list
      .map(
        (c) => `<div class="subcard">
          <div class="row-between">
            <strong>${esc(c.title)}</strong>
            <span class="pill ok">即用锦囊</span>
          </div>
          <p class="small muted" style="margin:6px 0">${esc(c.tip)}</p>
          <div class="subcard" style="margin-top:6px;padding:8px 10px">
            <div class="small" style="line-height:1.5">“${esc(c.msg)}”</div>
            <div style="margin-top:6px;text-align:right">
              <button type="button" class="mini-btn" data-copy-prompt="${esc(c.msg)}">📋 复制暖心话术草稿</button>
            </div>
          </div>
        </div>`
      )
      .join("")}</div>`;
  }

  function filterLoveCollections(data) {
    const love = ((data && data.personal_hub) || {}).love_hub || {};
    const cols = love.collections || [];
    const q = (($("#love-search-input") && $("#love-search-input").value) || "").trim().toLowerCase();
    const catBar = $("#love-cat-filters");
    if (catBar) {
      const total = cols.reduce((s, c) => s + ((c.items || []).length), 0);
      const pills = [{ id: "all", label: `全部 (${total})` }].concat(
        cols.map((c) => ({ id: c.id, label: `${c.emoji || "💖"} ${c.title.split("·")[0].trim()} (${(c.items || []).length})` }))
      );
      catBar.innerHTML = pills
        .map(
          (p) => `<button type="button" class="${LOVE_CAT_FILTER === p.id ? "active" : ""}" data-love-cat-pick="${esc(p.id)}">${esc(p.label)}</button>`
        )
        .join("");
    }
    const colBox = $("#love-collections-container");
    if (!colBox) return;
    const filteredCols = cols
      .filter((c) => LOVE_CAT_FILTER === "all" || c.id === LOVE_CAT_FILTER)
      .map((c) => ({
        ...c,
        items: (c.items || []).filter(
          (it) =>
            !q ||
            String(it.title || "").toLowerCase().includes(q) ||
            String(it.note || "").toLowerCase().includes(q) ||
            String(it.type || "").toLowerCase().includes(q)
        ),
      }))
      .filter((c) => c.items.length > 0);

    colBox.innerHTML = filteredCols.length
      ? filteredCols
          .map(
            (col) => `<article class="card love-collection-card">
              <div class="cardtop">
                <h2>${esc(col.emoji || "💖")} ${esc(col.title)}</h2>
                <span class="pill">${col.items.length} 项具体云盘原件</span>
              </div>
              <div class="love-items-grid">
                ${col.items
                  .map(
                    (it) => `<div class="love-item-card">
                      <div>
                        <div class="row-between">
                          <strong>${esc(it.title)}</strong>
                          <span class="badge-soft">${esc(it.date_tag || it.type || "云盘")}</span>
                        </div>
                        <p class="small muted" style="margin:6px 0 0">${esc(it.note || "")}</p>
                      </div>
                      <div class="row-between" style="margin-top:8px">
                        <button type="button" class="mini-btn" data-copy-prompt="${esc(it.url)}">📋 复制链接</button>
                        <a class="mini-btn" href="${esc(it.url)}" target="_blank" rel="noopener">☁️ 打开云盘原件 ↗</a>
                      </div>
                    </div>`
                  )
                  .join("")}
              </div>
            </article>`
          )
          .join("")
      : `<article class="card"><p class="muted">未找到匹配的爱情云盘条目，请清空搜索词查看全部 18 项珍藏。</p></article>`;
  }

  function filterDrivePartitions(data) {
    const ph = (data && data.personal_hub) || {};
    const folders = ph.drive_folders || [];
    const q = (($("#drive-file-search") && $("#drive-file-search").value) || "").trim().toLowerCase();
    const fBar = $("#drive-part-filters");
    if (fBar) {
      const pills = [{ code: "all", label: `全部分区 (${folders.length})` }].concat(
        folders.map((f) => ({ code: f.code, label: `${f.code} (${(f.concrete_items || []).length})` }))
      );
      fBar.innerHTML = pills
        .map(
          (p) => `<button type="button" class="${DRIVE_PART_FILTER === p.code ? "active" : ""}" data-drive-part-pick="${esc(p.code)}">${esc(p.label)}</button>`
        )
        .join("");
    }
    if (!q && DRIVE_PART_FILTER === "all") return;
    const dfGrid = $("#drive-folders-grid");
    if (!dfGrid) return;
    const matched = folders
      .filter((f) => DRIVE_PART_FILTER === "all" || f.code === DRIVE_PART_FILTER)
      .map((f) => ({
        ...f,
        concrete_items: (f.concrete_items || []).filter(
          (it) =>
            !q ||
            String(it.title || "").toLowerCase().includes(q) ||
            String(f.name || "").toLowerCase().includes(q) ||
            String(f.summary || "").toLowerCase().includes(q)
        ),
      }))
      .filter((f) => f.concrete_items.length > 0);
    dfGrid.innerHTML = matched.length
      ? matched
          .map(
            (f) => `<div class="subcard">
              <div class="row-between">
                <strong>${esc(f.name || "")}</strong>
                <span class="pill ok">${f.concrete_items.length} 份匹配文件</span>
              </div>
              <p class="small muted" style="margin:4px 0">${esc(f.summary || "")}</p>
              <div class="drive-concrete-list">
                ${f.concrete_items
                  .map(
                    (it) => `<div class="drive-file-row">
                      <span>📄 <b>${esc(it.title)}</b> <small class="muted">(${esc(it.type || "FILE")})</small></span>
                      <a href="${esc(it.url)}" target="_blank" rel="noopener">打开 ↗</a>
                    </div>`
                  )
                  .join("")}
              </div>
            </div>`
          )
          .join("")
      : `<div class="subcard"><p class="muted small">未搜到匹配的云盘文件，请清空上方筛选条件。</p></div>`;
  }

  function renderV26DeepPolish(data) {
    const mqr = data.mobile_qr || {};
    const jb = data.beacon || {};
    const love = ((data.personal_hub || {}).love_hub) || {};
    const loveCnt = (love.collections || []).reduce((s, c) => s + ((c.items || []).length), 0) || 18;
    const driveCnt = ((data.personal_hub || {}).drive_folders || []).reduce((s, f) => s + ((f.concrete_items || []).length), 0) || 30;
    const swItems = (((data.software_catalog || {}).scan || {}).items) || [];
    const swInst = swItems.filter((i) => i.status === "installed").length;

    if ($("#ov-android-urls")) {
      const pubTxt = mqr.public_url
        ? `☁️ 安卓推荐 HTTPS 原生直装链接：${mqr.public_url}`
        : `☁️ 点「打开安卓扫码安装台」可生成 HTTPS 免费公网直装码`;
      const lanTxt = `📶 同 Wi-Fi 局域网直连：${mqr.lan_url || "http://127.0.0.1:18766/mobile"}`;
      $("#ov-android-urls").textContent = `${pubTxt}  ｜  ${lanTxt}`;
    }

    const m14 = $("#ov-all14-matrix");
    if (m14) {
      const tiles = [
        ["overview", "📊 全局总览", "零闪窗守护中", "git-sync-hub + 全景矩阵"],
        ["love", "💖 爱情空间", `${loveCnt} 项云盘原件`, "7短片 · 画册 · 抽卡台 · JevChat"],
        ["beacon", "📱 安卓手机App", mqr.public_url ? "HTTPS+局域网双通" : "局域网 18766 就绪", `${(jb.watches || []).length} 条长任务 · 震动响铃`],
        ["gh", "⚿ 三账号分舱", "3 舱独立隔离", "mqgg · shaohua · hukeying85"],
        ["personal", "🗂️ 个人云盘档案", `${driveCnt} 份具体文件`, "00-05 秒搜 · 考公日程 · 脱敏库"],
        ["thesis", "🎓 论文一键排版", "34 模块就绪", "1.5s 出定稿 + 红蓝对比 + 三线表"],
        ["mediacua", "🎬 自媒体与操控", "yt-dlp 已装妥", "抖/红/微/B站解析 + (0,0)急停"],
        ["quota", "⚡ AI额度与生信", "3 池零浪费", "防过期燃烧池 + 抗菌肽计算器"],
        ["coord", "🤖 多会话作战室", "3 机联邦协同", "S1/S2/S3 派单 + Martini 3 粗粒化"],
        ["software", "▦ 软件商城", `${swInst}/${swItems.length || 16} 已就绪`, "PyMOL 3.1 · Lark · E盘静默装"],
        ["remote", "⇄ 远程控制", `${((data.remote || {}).hosts || []).length || 3} 节点受控`, "超算 mu01 · WSL2 · 台式机"],
        ["scripts", "🧰 脚本工坊", "4 角色一键生成", "Win/Linux 科研开荒 + 组网"],
        ["connectors", "∞ 云端连接器", `${(data.connectors || []).length || 10} 项已打通`, "Drive · Notion · Calendar · Gmail"],
        ["studio", "✦ 美化工作台", `卡片 ${Math.round(((data.appearance || {}).surface_opacity ?? 0.14) * 100)}% 超透`, "dsh-video-skin 原版开机动画"],
      ];
      m14.innerHTML = tiles
        .map(
          ([tab, name, badge, sub]) => `<button type="button" class="mm-tile" data-goto="${esc(tab)}">
            <div class="mm-tile-top">
              <span>${esc(name)}</span>
              <span class="badge-soft">${esc(badge)}</span>
            </div>
            <div class="mm-tile-sub">${esc(sub)}</div>
          </button>`
        )
        .join("");
    }

    renderLoveCareGenerator();
    filterLoveCollections(data);
    filterDrivePartitions(data);

    const thSpec = $("#thesis-spec-checklist");
    if (thSpec && !thSpec.dataset.rendered) {
      thSpec.dataset.rendered = "1";
      const specs = [
        ["① 页面与装订线规范", "A4 标准幅面，上下 2.54cm / 左右 3.17cm，装订线预留精准对齐，章首自动分页"],
        ["② 前置摘要与目录罗马页码", "封面无页码 → 中英文摘要与目录独立罗马数字 (I, II, III) → 正文第 1 章起阿拉伯数字 1"],
        ["③ 奇偶页眉智能联动", "奇数页自动提取当前章标题、偶数页学位论文题名，五号宋体居中配 0.75pt 底边线"],
        ["④ 多级标题与混排字库", "章/节/条三级标题自动映射黑体/小二/三号/四号，全文西文与数字自动统一 Times New Roman"],
        ["⑤ 图题表题与 300 DPI 校验", "表题置于表上、图题置于图下（五号黑体/宋体），自动检测低清插图并居中防跨页断行"],
        ["⑥ Zotero 9 引用域无损保护", "深入 XML 保留 ADDIN ZOTERO_ITEM 活动域代码，规整格式后仍可在 Word 中随时增删文献"],
        ["⑦ GB/T 7714-2015 参考文献", "自动悬挂缩进 2 字符、统一 [J]/[M]/[D] 标识与标点半角空格，随附标准 .csl 样式文件下载"],
      ];
      thSpec.innerHTML =
        specs
          .map(
            ([t, d]) => `<div class="subcard">
              <div class="row-between"><strong>${esc(t)}</strong><span class="pill ok">自动规整</span></div>
              <p class="small muted" style="margin:6px 0 0">${esc(d)}</p>
            </div>`
          )
          .join("") +
        `<div class="subcard">
          <div class="row-between"><strong>⑧ 学术三线表自动转换样张</strong><span class="badge-soft">顶底 1.5pt · 栏目 0.75pt</span></div>
          <table class="three-line-demo">
            <thead><tr><th>候选肽</th><th>净电荷</th><th>MIC (μg/mL)</th></tr></thead>
            <tbody>
              <tr><td>AMP_Cand01</td><td>+4</td><td>2.0</td></tr>
              <tr><td>AMP_Cand02</td><td>+5</td><td>4.0</td></tr>
            </tbody>
          </table>
        </div>`;
    }

    if ($("#sw-filters") && swItems.length) {
      $$("#sw-filters button").forEach((b) => {
        const cat = b.dataset.cat;
        const base = b.dataset.baseLabel || (b.dataset.baseLabel = b.textContent.trim());
        const subset = cat === "all" ? swItems : swItems.filter((i) => i.category === cat);
        const okCnt = subset.filter((i) => i.status === "installed").length;
        b.textContent = `${base} (${okCnt}/${subset.length})`;
      });
    }

    if (!AMP_AUTO_CALC_DONE && $("#amp-seq-input") && $("#amp-calc-result")) {
      AMP_AUTO_CALC_DONE = true;
      const initSeq = $("#amp-seq-input").value || "GIGKFLHSAKKFGKAFVGEIMNS";
      apiGet(`/api/quota/amp-calc?seq=${encodeURIComponent(initSeq)}`)
        .then((res) => {
          if (res && res.ok) renderAmpMetrics(res);
        })
        .catch(() => {});
    }

    if ($("#skin-contrast-badge")) {
      const sOp = Number((data.appearance || {}).surface_opacity ?? 0.14);
      $("#skin-contrast-badge").textContent =
        sOp <= 0.12 ? "极致通透 · 暗色高光描边护航" : sOp <= 0.2 ? "水晶超透 · 对比度优良" : "高对比稳态阅读";
    }
  }

  /* ==================== Interactive Whale Companion ==================== */
  function initWhaleWidget() {
    const ww = $("#whale-widget");
    const actor = $("#whale-actor-wrap");
    if (!ww || !actor) return;

    function cycleQuote(playSound) {
      const app = (STATE && STATE.appearance) || {};
      const quotes =
        Array.isArray(app.whale_quotes) && app.whale_quotes.length
          ? app.whale_quotes
          : [
              "点「论文一键改格式」，1.5 秒体验硕士学位论文自动排版！",
              "切到「💖 爱情与心意空间」，18 项云盘恋爱短片与纪念画册一键直达～",
              "三账号已拆分为三列独立监控舱，清晰直观互不串号！",
            ];
      const text = quotes[WHALE_INDEX % quotes.length];
      WHALE_INDEX += 1;
      if ($("#wb-body")) $("#wb-body").textContent = text;

      const hr = new Date().getHours();
      const peak = (hr >= 9 && hr < 12) || (hr >= 14 && hr < 18);
      if ($("#wb-tag")) {
        $("#wb-tag").textContent = peak ? "科研专注时段 · 引擎满载" : "夜间静谧时段 · 守护在线";
      }

      actor.classList.remove("bounce");
      void actor.offsetWidth;
      actor.classList.add("bounce");
      if (playSound && app.whale_sound !== false) {
        playOrbitalChime("whale");
      }
    }

    let dragging = false;
    let moved = false;
    let sx = 0,
      sy = 0,
      ox = 0,
      oy = 0;

    actor.addEventListener("pointerdown", (e) => {
      dragging = true;
      moved = false;
      const rect = ww.getBoundingClientRect();
      sx = e.clientX;
      sy = e.clientY;
      ox = rect.left;
      oy = rect.top;
      actor.setPointerCapture(e.pointerId);
    });

    actor.addEventListener("pointermove", (e) => {
      if (!dragging) return;
      const dx = e.clientX - sx;
      const dy = e.clientY - sy;
      if (Math.abs(dx) > 4 || Math.abs(dy) > 4) moved = true;
      if (!moved) return;
      const nx = Math.max(8, Math.min(window.innerWidth - 90, ox + dx));
      const ny = Math.max(8, Math.min(window.innerHeight - 90, oy + dy));
      ww.style.left = nx + "px";
      ww.style.top = ny + "px";
      ww.style.right = "auto";
      ww.style.bottom = "auto";
    });

    actor.addEventListener("pointerup", () => {
      if (!dragging) return;
      dragging = false;
      if (!moved) {
        cycleQuote(true);
        return;
      }
      const app = (STATE && STATE.appearance) || {};
      if (app.whale_snap !== false) {
        const rect = ww.getBoundingClientRect();
        const flipLeft = rect.left + rect.width / 2 < window.innerWidth / 2;
        ww.classList.toggle("snap-left", flipLeft);
        if (flipLeft) {
          ww.style.left = "18px";
          ww.style.right = "auto";
        } else {
          ww.style.right = "22px";
          ww.style.left = "auto";
        }
      }
    });

    setInterval(() => cycleQuote(false), 18000);
  }

  /* ==================== Thesis Sample & Formatting Actions ==================== */
  function showThesisReport(job, isSamplePreview) {
    const repBox = $("#thesis-report-box");
    const actBox = $("#thesis-result-actions");
    const pill = $("#thesis-elapsed-pill");
    if (pill) {
      pill.textContent = `耗时 ${job.elapsed_sec ?? "-"}s · 自动修订 ${job.total_changes ?? "-"} 处`;
      pill.className = "pill ok";
    }
    if (repBox) {
      repBox.textContent =
        job.report_md_excerpt ||
        `排版成功！作业号 ${job.job_id}，共完成 ${job.total_changes || 0} 处规范化修改。`;
    }
    if (actBox) {
      actBox.hidden = false;
      if (isSamplePreview) {
        actBox.innerHTML = `
          <a class="primary btn-link" href="/api/thesis/sample-download/final" target="_blank" rel="noopener">下载排版后终稿 (_new.docx)</a>
          <a class="btn-link" href="/api/thesis/sample-download/compare" target="_blank" rel="noopener">下载红蓝修订对比稿 (_对比稿.docx)</a>
          <a class="btn-link" href="/api/thesis/sample-download/report_md" target="_blank" rel="noopener">下载 Markdown 审计报告</a>
          <a class="btn-link" href="/api/thesis/sample-download/csl" target="_blank" rel="noopener">下载 GB/T 7714 CSL</a>
        `;
      } else {
        const jid = encodeURIComponent(job.job_id);
        actBox.innerHTML = `
          <a class="primary btn-link" href="/api/thesis/download/${jid}/final" target="_blank" rel="noopener">下载排版后终稿 (_new.docx)</a>
          <a class="btn-link" href="/api/thesis/download/${jid}/compare" target="_blank" rel="noopener">下载红蓝修订对比稿 (_对比稿.docx)</a>
          <a class="btn-link" href="/api/thesis/download/${jid}/report_md" target="_blank" rel="noopener">下载审计报告 (.md)</a>
          ${
            !READONLY
              ? `<button type="button" data-open-thesis-job="${esc(job.job_id)}">在资源管理器中打开</button>`
              : ""
          }
        `;
      }
    }
  }

  async function runSampleThesisDemo() {
    const btn = $("#thesis-sample-btn");
    if (btn) btn.disabled = true;
    if ($("#thesis-elapsed-pill")) $("#thesis-elapsed-pill").textContent = "正在调用 Lark-Formatter 排版…";
    try {
      const modeVal = ($("#thesis-mode") && $("#thesis-mode").value) || "academic_master_2026";
      const res = await apiGet(`/api/thesis/sample-run?profile_id=${encodeURIComponent(modeVal)}`);
      const job = res.job || res;
      showThesisReport(job, true);
      toast(`样稿一键排版成功！${job.elapsed_sec}s 完成 ${job.total_changes} 处格式规整`, "ok");
    } catch (err) {
      toast("样稿排版失败：" + err.message, "err");
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function fileToBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const str = String(reader.result || "");
        const comma = str.indexOf(",");
        resolve(comma >= 0 ? str.slice(comma + 1) : str);
      };
      reader.onerror = () => reject(new Error("读取上传文件失败"));
      reader.readAsDataURL(file);
    });
  }

  /* ==================== Event Bindings ==================== */
  function bindEvents() {
    $$("nav button[data-tab]").forEach((btn) => {
      btn.addEventListener("click", () => switchTab(btn.dataset.tab, false));
    });
    document.addEventListener("click", async (e) => {
      const jump = e.target.closest("[data-jump-tab], [data-goto]");
      if (jump) {
        switchTab(jump.dataset.jumpTab || jump.dataset.goto, false);
        return;
      }
      const alphaBtn = e.target.closest("[data-alpha-preset]");
      if (alphaBtn) {
        const presets = {
          ultra: { surface_opacity: 0.10, veil_opacity: 0.06, glass_blur: 2 },
          clear: { surface_opacity: 0.14, veil_opacity: 0.10, glass_blur: 4 },
          balanced: { surface_opacity: 0.22, veil_opacity: 0.14, glass_blur: 7 },
          solid: { surface_opacity: 0.38, veil_opacity: 0.22, glass_blur: 12 },
        };
        const cfg = presets[alphaBtn.dataset.alphaPreset] || presets.clear;
        $$("[data-alpha-preset]").forEach((b) => b.classList.toggle("active", b.dataset.alphaPreset === alphaBtn.dataset.alphaPreset));
        if (!STATE) STATE = {};
        STATE.appearance = Object.assign({}, STATE.appearance || {}, cfg);
        applyAppearance(STATE.appearance);
        if (!READONLY) apiPost("/api/appearance", cfg).catch(() => {});
        toast("已切换高透玻璃预设 ✨", "ok");
        return;
      }
      const loveSceneBtn = e.target.closest("[data-love-scene]");
      if (loveSceneBtn) {
        LOVE_SCENE = loveSceneBtn.dataset.loveScene || "daily";
        renderLoveCareGenerator();
        return;
      }
      const loveCatBtn = e.target.closest("[data-love-cat-pick]");
      if (loveCatBtn) {
        LOVE_CAT_FILTER = loveCatBtn.dataset.loveCatPick || "all";
        if (STATE) filterLoveCollections(STATE);
        return;
      }
      const drivePartBtn = e.target.closest("[data-drive-part-pick]");
      if (drivePartBtn) {
        DRIVE_PART_FILTER = drivePartBtn.dataset.drivePartPick || "all";
        if (STATE) {
          renderPersonalHub(STATE);
          filterDrivePartitions(STATE);
        }
        return;
      }
      const openArenaBtn = e.target.closest("[data-open-arena-slot]");
      if (openArenaBtn) {
        const slot = openArenaBtn.getAttribute("data-open-arena-slot") || "S1";
        const inp = document.querySelector(`[data-arena-url-slot="${slot}"]`);
        const url = inp ? inp.value.trim() : "";
        apiPost("/api/federation/arena-window", {
          action: slot === "ALL" ? "tile_all" : "open",
          slot,
          url,
        })
          .then((res) => toast(res.note || `已启动 ${slot} 专窗`, "ok"))
          .catch((err) => toast(`启动提示: ${err.message}`, "warn"));
        return;
      }
      const saveArenaBtn = e.target.closest("[data-save-arena-slot]");
      if (saveArenaBtn) {
        const slot = saveArenaBtn.getAttribute("data-save-arena-slot") || "S1";
        const inp = document.querySelector(`[data-arena-url-slot="${slot}"]`);
        const url = inp ? inp.value.trim() : "";
        apiPost("/api/federation/arena-window", { action: "save", slot, url })
          .then((res) => toast(res.note || `已保存 ${slot} 会话地址`, "ok"))
          .catch((err) => toast(`保存失败: ${err.message}`, "warn"));
        return;
      }
      const rcmdBtn = e.target.closest("[data-rcmd]");
      if (rcmdBtn) {
        if ($("#remote-custom-input")) $("#remote-custom-input").value = rcmdBtn.dataset.rcmd || "";
        if ($("#remote-action-select")) $("#remote-action-select").value = "custom";
        toast("已填入远程诊断命令，点击『立即执行远程指令』即可运行", "ok");
        return;
      }
      const sbPresetBtn = e.target.closest("[data-sb-preset]");
      if (sbPresetBtn) {
        const p = sbPresetBtn.dataset.sbPreset;
        $$("#sb-role-presets button").forEach((b) => b.classList.toggle("active", b === sbPresetBtn));
        if (p === "laptop") {
          if ($("#sb-os")) $("#sb-os").value = "windows";
          if ($("#sb-mode")) $("#sb-mode").value = "install";
          if ($("#sb-pymol")) $("#sb-pymol").checked = true;
          if ($("#sb-base")) $("#sb-base").checked = true;
          if ($("#sb-ts")) $("#sb-ts").checked = false;
        } else if (p === "desktop_cg") {
          if ($("#sb-os")) $("#sb-os").value = "windows";
          if ($("#sb-mode")) $("#sb-mode").value = "node";
          if ($("#sb-pymol")) $("#sb-pymol").checked = true;
          if ($("#sb-base")) $("#sb-base").checked = true;
          if ($("#sb-ts")) $("#sb-ts").checked = true;
        } else if (p === "hpc_linux") {
          if ($("#sb-os")) $("#sb-os").value = "linux";
          if ($("#sb-mode")) $("#sb-mode").value = "install";
          if ($("#sb-pymol")) $("#sb-pymol").checked = true;
          if ($("#sb-base")) $("#sb-base").checked = true;
        } else if (p === "diag_only") {
          if ($("#sb-mode")) $("#sb-mode").value = "diag";
        }
        updateScriptBuilder();
        toast("已切换装机脚本角色预设 ⚡", "ok");
        return;
      }
      const testAndroidBtn = e.target.closest("[data-test-android-push]");
      if (testAndroidBtn) {
        playOrbitalChime("whale");
        if (READONLY) {
          toast("📳 预览沙盒已模拟推送！在安卓手机打开 /mobile 点『震动+响铃实测』可直接体验真机震动", "ok");
        } else {
          try {
            await apiPost("/api/mobile/quick-cmd", { cmd_id: "test_mobile_alert" });
            toast("📳 已向安卓手机端与 ntfy 频道发送完工实测通知！手机打开页面将在几秒内自动震动响铃", "ok");
            refreshState(false);
          } catch (err) {
            toast("推送提示：" + err.message, "err");
          }
        }
        return;
      }
      const replay = e.target.closest(
        "[data-replay-boot], #top-boot-btn, #quick-boot-demo, #studio-boot-btn, #replay-boot"
      );
      if (replay) {
        e.preventDefault();
        BOOT_RUNNING = false;
        BOOT_SOUND_ARMED = true;
        triggerBootAnimation(true);
        return;
      }
      const copyPrompt = e.target.closest("[data-copy-prompt]");
      if (copyPrompt) {
        navigator.clipboard.writeText(copyPrompt.dataset.copyPrompt || "").then(() => toast("已复制联动提示词", "ok"));
        return;
      }
      const ctrl = e.target.closest("[data-ctrl-name]");
      if (ctrl) {
        try {
          await apiPost("/api/control", { name: ctrl.dataset.ctrlName, action: ctrl.dataset.ctrlAct });
          toast("计划任务指令已下发", "ok");
          refreshState();
        } catch (err) {
          toast(err.message, "err");
        }
        return;
      }
      const pkgBtn = e.target.closest("[data-install-pkg]");
      if (pkgBtn) {
        try {
          const drive = ($("#sw-drive") && $("#sw-drive").value) || "E:";
          await apiPost("/api/software/install", { pkg_id: pkgBtn.dataset.installPkg, drive });
          toast("已加入后台静默安装队列", "ok");
          refreshState();
        } catch (err) {
          toast(err.message, "err");
        }
        return;
      }
      const relBtn = e.target.closest("[data-release-lock]");
      if (relBtn) {
        try {
          await apiPost("/api/coord/release", { resource: relBtn.dataset.releaseLock });
          toast("租约锁已释放", "ok");
          refreshState();
        } catch (err) {
          toast(err.message, "err");
        }
        return;
      }
      const openJob = e.target.closest("[data-open-thesis-job]");
      if (openJob) {
        try {
          await apiPost("/api/thesis/open-dir", { job_id: openJob.dataset.openThesisJob });
          toast("已打开输出文件夹", "ok");
        } catch (err) {
          toast(err.message, "err");
        }
        return;
      }
      const wpBtn = e.target.closest("[data-wp-pick]");
      if (wpBtn) {
        const wp = wpBtn.dataset.wpPick;
        if (!STATE) STATE = {};
        if (!STATE.appearance) STATE.appearance = {};
        STATE.appearance.builtin_wallpaper = wp;
        STATE.appearance.custom_media_id = "";
        applyAppearance(STATE.appearance);
        if (!READONLY) {
          apiPost("/api/appearance", { builtin_wallpaper: wp }).catch(() => {});
        }
        toast("已切换唯美壁纸 ✨", "ok");
        return;
      }
      const useMedia = e.target.closest("[data-use-media]");
      if (useMedia) {
        try {
          await apiPost("/api/appearance", { custom_media_id: useMedia.dataset.useMedia });
          toast("已切换自定义动态壁纸", "ok");
          refreshState();
        } catch (err) {
          toast(err.message, "err");
        }
      }
    });

    if ($("#boot-chime-btn")) {
      $("#boot-chime-btn").addEventListener("click", () => {
        BOOT_SOUND_ARMED = true;
        playOrbitalChime("boot");
        toast("星轨和弦音效已开启", "ok");
      });
    }

    if ($("#refresh")) $("#refresh").addEventListener("click", () => refreshState(true));
    if ($("#search")) $("#search").addEventListener("input", () => STATE && renderOverview(STATE));
    if ($("#love-search-input")) $("#love-search-input").addEventListener("input", () => STATE && filterLoveCollections(STATE));
    if ($("#drive-file-search")) {
      $("#drive-file-search").addEventListener("input", () => {
        if (!STATE) return;
        renderPersonalHub(STATE);
        filterDrivePartitions(STATE);
      });
    }
    if ($("#chk-boot")) {
      $("#chk-boot").addEventListener("change", (ev) => {
        const on = !!ev.target.checked;
        try {
          localStorage.setItem("ad_boot_auto", on ? "1" : "0");
        } catch (_) {}
        if (!READONLY) apiPost("/api/appearance", { boot_enabled: on }).catch(() => {});
        toast(on ? "已开启：每次打开自动播放 dsh-video-skin 开机动画" : "已关闭自动开机动画（仍可点顶部按钮手动播放）", "ok");
      });
    }

    // Thesis actions
    if ($("#thesis-sample-btn")) {
      $("#thesis-sample-btn").addEventListener("click", runSampleThesisDemo);
    }
    if ($("#thesis-use-sample-btn")) {
      $("#thesis-use-sample-btn").addEventListener("click", runSampleThesisDemo);
    }
    if ($("#thesis-detected-select")) {
      $("#thesis-detected-select").addEventListener("change", (e) => {
        if (e.target.value && $("#thesis-source-path")) {
          $("#thesis-source-path").value = e.target.value;
        }
      });
    }
    if ($("#thesis-form")) {
      $("#thesis-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        if (READONLY) {
          toast("当前为安全只读预览，自动为您运行内置硕士论文样稿体验（在本机 ArenaDesk.exe 中可直接修改本地任意论文）", "info");
          return runSampleThesisDemo();
        }
        const btn = $("#thesis-run-btn");
        if (btn) btn.disabled = true;
        try {
          const fileInput = $("#thesis-file-input");
          const file = fileInput && fileInput.files && fileInput.files[0];
          const payload = {
            profile_id: ($("#thesis-mode") && $("#thesis-mode").value) || "academic_master_2026",
            doc_path: (($("#thesis-source-path") && $("#thesis-source-path").value) || "").trim(),
            template_docx_path: (($("#thesis-template-path") && $("#thesis-template-path").value) || "").trim(),
            save_alongside: !!(($("#thesis-save-alongside") || {}).checked),
          };
          if (file) {
            payload.filename = file.name;
            payload.data_base64 = await fileToBase64(file);
          } else if (!payload.doc_path) {
            payload.use_sample = true;
          }
          const res = await apiPost("/api/thesis/format", payload);
          const job = res.job || res;
          showThesisReport(job, false);
          toast(`论文排版完成！共修订 ${job.total_changes || 0} 处`, "ok");
          refreshState();
        } catch (err) {
          toast(err.message, "err");
        } finally {
          if (btn) btn.disabled = false;
        }
      });
    }

    // Coordination bus actions
    if ($("#coord-test-lease-btn")) {
      $("#coord-test-lease-btn").addEventListener("click", async () => {
        if (READONLY) {
          const fresh = await apiGet("/api/coord/state");
          if (STATE) {
            STATE.coord = fresh;
            renderCoord(STATE);
          }
          toast(`协作总线自检通过：${(fresh.sessions || []).length} 会话并存，0 冲突`, "ok");
          return;
        }
        try {
          await apiPost("/api/coord/lease", {
            resource: "selftest:ui-lease-probe",
            ttl_sec: 45,
            purpose: "Arena Desk UI 防冲突租约锁自检",
          });
          toast("防冲突租约锁获取成功（45s 自动过期，可点释放）", "ok");
          refreshState();
        } catch (err) {
          toast(err.message, "err");
        }
      });
    }
    if ($("#coord-note-form")) {
      $("#coord-note-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const input = $("#coord-note-input");
        const text = ((input && input.value) || "").trim();
        if (!text) return;
        try {
          await apiPost("/api/coord/note", { summary: text, tags: ["ui-handoff"] });
          input.value = "";
          toast("跨会话协作留言已广播", "ok");
          refreshState();
        } catch (err) {
          toast(err.message, "err");
        }
      });
    }

    // GitHub 3-account actions -> POST /api/gh/action
    const ghAct = async (action, label) => {
      try {
        const res = await apiPost("/api/gh/action", { action });
        toast(res.note || `${label} 已执行`, "ok");
        refreshState();
      } catch (err) {
        toast(err.message, "err");
      }
    };
    if ($("#gh-check-btn")) $("#gh-check-btn").addEventListener("click", () => ghAct("check", "状态刷新"));
    if ($("#gh-provision-btn"))
      $("#gh-provision-btn").addEventListener("click", () => ghAct("provision_hukeying", "三账号 SSH 与凭据部署"));
    if ($("#gh-hukeying-web-btn"))
      $("#gh-hukeying-web-btn").addEventListener("click", () => ghAct("connect_hukeying_web", "Chrome Profile 1 独立授权"));

    if ($("#amp-calc-form")) {
      $("#amp-calc-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const seq = (($("#amp-seq-input") && $("#amp-seq-input").value) || "").trim();
        if (!seq) return;
        try {
          const res = await apiGet(`/api/quota/amp-calc?seq=${encodeURIComponent(seq)}`);
          renderAmpMetrics(res);
          toast("抗菌肽理化指标已更新", "ok");
        } catch (err) {
          toast(err.message, "err");
        }
      });
    }

    if ($("#cgmd-form")) {
      $("#cgmd-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const name = (($("#cgmd-name") && $("#cgmd-name").value) || "AMP_Cand01").trim();
        const us = (($("#cgmd-us") && $("#cgmd-us").value) || "2.0").trim();
        const mem = (($("#cgmd-membrane") && $("#cgmd-membrane").value) || "bacterial_inner").trim();
        const seq = (($("#cgmd-seq") && $("#cgmd-seq").value) || "").trim();
        try {
          const qs = new URLSearchParams({ name, us, membrane: mem, seq });
          const res = await apiGet(`/api/federation/cgmd?${qs.toString()}`);
          if (res.bundle && $("#cgmd-preview")) {
            const fullOut = `# === 1) runner.sh ===\n${res.bundle.runner_script}\n# === 2) cg_eq_dt10fs.mdp ===\n${res.bundle.mdp_eq}\n# === 3) cg_prod_dt20fs.mdp ===\n${res.bundle.mdp_prod}`;
            $("#cgmd-preview").textContent = fullOut;
            $("#cgmd-preview").dataset.loaded = "1";
          }
          toast("Martini 3 粗粒化动力学全套脚本已生成", "ok");
        } catch (err) {
          toast(err.message, "err");
        }
      });
    }
    if ($("#cgmd-copy-btn")) {
      $("#cgmd-copy-btn").addEventListener("click", () => {
        const txt = ($("#cgmd-preview") && $("#cgmd-preview").textContent) || "";
        if (txt) navigator.clipboard?.writeText(txt).then(() => toast("已复制台式机粗粒化全套脚本", "ok"));
      });
    }
    if ($("#fed-dispatch-form")) {
      $("#fed-dispatch-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const target_node = ($("#fed-target-node") && $("#fed-target-node").value) || "desktop_hukeying";
        const title = (($("#fed-task-title") && $("#fed-task-title").value) || "").trim();
        const objective = (($("#fed-task-obj") && $("#fed-task-obj").value) || "").trim();
        const peptide_seq = (($("#fed-peptide-seq") && $("#fed-peptide-seq").value) || "").trim();
        if (!title) return;
        if (READONLY) {
          const mapAcc = {
            desktop_hukeying: ["[S3] 台式机粗粒化 MD 会话", "hukeying85-ux", "desktop"],
            hpc_shaohua: ["[S2] HPC 毕业课题会话", "shaohuawen03-cyber", "hpc"],
            laptop_mqgg: ["[S1] 笔记本总控会话", "mqgg5630-cyber", "laptop"],
          };
          const [sName, ghAcc, roleCode] = mapAcc[target_node] || mapAcc.desktop_hukeying;
          const topic = (STATE && STATE.federation && STATE.federation.notify_config && STATE.federation.notify_config.ntfy_topic) || "arena-research-beacon";
          const promptTxt = `【跨会话协同任务单】\n- 专职会话：${sName}（锁定 GitHub 账号 \`${ghAcc}\`）\n- 任务标题：${title}\n- 验收要求：${objective}\n${peptide_seq ? `- 候选抗菌肽序列：${peptide_seq}\n` : ""}- 好了吗通知要求：后台启动计算并挂载 \`python3 code/federation/node_agent.py --role ${roleCode} --md-log prod.log --notify ntfy:${topic}\`，跑完秒推手机，严禁提交 >5MB .xtc 轨迹进 Git！`;
          navigator.clipboard?.writeText(promptTxt);
          if (STATE && STATE.federation) {
            STATE.federation.dispatches = [
              {
                task_id: "DISP-LIVE",
                target_gh_account: ghAcc,
                target_session: sName,
                title,
                arena_prompt: promptTxt,
              },
              ...(STATE.federation.dispatches || []),
            ];
            renderFederation(STATE);
          }
          toast("已生成跨会话唤醒提示词并自动复制到剪贴板！", "ok");
          return;
        }
        try {
          const res = await apiPost("/api/federation/dispatch", { target_node, title, objective, peptide_seq });
          if (res.dispatch && res.dispatch.arena_prompt) {
            navigator.clipboard?.writeText(res.dispatch.arena_prompt);
          }
          toast("派单包已落盘并复制唤醒提示词！", "ok");
          refreshState(false);
        } catch (err) {
          toast(err.message, "err");
        }
      });
    }

    if ($("#media-parse-form")) {
      $("#media-parse-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const q = (($("#media-share-input") && $("#media-share-input").value) || "").trim();
        if (!q) return;
        try {
          const res = await apiGet(`/api/media-cua/parse?q=${encodeURIComponent(q)}`);
          renderMediaParseBox(res);
          toast(`已识别 ${res.platform_label} 并生成无水印命令`, "ok");
        } catch (err) {
          toast(err.message, "err");
        }
      });
    }

    document.addEventListener("click", async (ev) => {
      const mpBtn = ev.target.closest("[data-media-preset]");
      if (mpBtn && $("#media-share-input")) {
        const presets = {
          dy: "7.43 复制打开抖音，看看【分子动力学与抗菌肽机制科普】 https://v.douyin.com/iYDemo88/",
          xhs: "58 科研必看！GROMACS与Martini粗粒化动力学出图技巧发布了一篇小红书笔记，快来看吧！ http://xhslink.com/a/DemoXhs99，复制本条信息打开【小红书】App查看！",
          wx: "https://mp.weixin.qq.com/s/DemoWeChatArticle_AMP_GutMicrobiota",
          bili: "【分子动力学模拟从入门到精通】 https://www.bilibili.com/video/BV1xx411c7mD/",
        };
        const key = mpBtn.getAttribute("data-media-preset") || "xhs";
        $("#media-share-input").value = presets[key] || presets.xhs;
        $("#media-parse-form")?.dispatchEvent(new Event("submit"));
        return;
      }
      const ntBtn = ev.target.closest("[data-fed-notify-test]");
      if (ntBtn) {
        if (READONLY) {
          playOrbitalChime("whale");
          toast("🔔 预览响铃自检通过！本机运行将同步向手机 ntfy 锁屏推送！", "ok");
          return;
        }
        try {
          const res = await apiPost("/api/federation/notify-test", {});
          toast(res.ok ? "✅ 已真实推送至您的手机订阅频道！" : "本地通知已触发（请检查外网连通性）", "ok");
        } catch (err) {
          toast(err.message, "err");
        }
        return;
      }
      const cpBtn = ev.target.closest("[data-copy-prompt]");
      if (cpBtn) {
        const txt = cpBtn.getAttribute("data-copy-prompt") || "";
        navigator.clipboard?.writeText(txt).then(() => toast("已复制到剪贴板", "ok"));
        return;
      }
      const jbBtn = ev.target.closest("[data-jb-cmd]");
      if (jbBtn) {
        const cmdId = jbBtn.getAttribute("data-jb-cmd") || "";
        const outEl = $("#jb-cmd-out");
        if (READONLY) {
          const preview = {
            host_health: "主机: LAPTOP-R77M5D6M (预览镜像) · git-sync-hub: Running · 磁盘空间充足",
            slurm_queue_snapshot: "HPC mu01 队列:\n#92418 cu   GROMACS_AD_AMP_100ns  R  68.4% (91.2 ns/day)\n#92421 fat1 MEGAHIT_476Samples    R  76.0% (MetaBAT2/CheckM)",
            md_speed_check: "GROMACS 68.4/100 ns (68.4%) · 91.2 ns/day · 预计剩余 8小时19分",
            test_mobile_alert: "✅ 已向手机伴侣端 (/mobile) 与通知流推送测试完工卡片！",
            scancel_stuck_job: "🛑 已按 GrokBot 人工闸门规范拦截，转入待审批队列！",
          };
          if (outEl) outEl.textContent = preview[cmdId] || "快照已返回";
          toast("已返回指令快照", "ok");
          return;
        }
        try {
          const res = await apiPost("/api/mobile/quick-cmd", { cmd_id: cmdId });
          if (outEl) {
            outEl.textContent = res.gated ? `[人工闸门拦截] ${res.gate.reason}` : (res.record && res.record.output) || "完成";
          }
          toast(res.gated ? "已转入人工审批闸门" : "快捷指令执行完成", "ok");
          refreshState(false);
        } catch (err) {
          toast(err.message, "err");
        }
      }
    });
    if ($("#gh-login-btn")) $("#gh-login-btn").addEventListener("click", () => ghAct("device_login", "gh 浏览器登录"));
    if ($("#gh-dpapi-btn")) $("#gh-dpapi-btn").addEventListener("click", () => ghAct("setup_git_dpapi", "DPAPI 加密配置"));
    if ($("#gh-unlock-btn")) $("#gh-unlock-btn").addEventListener("click", () => ghAct("unlock_private_hub", "私人仓热补丁"));
    if ($("#copy-unlock-btn")) {
      $("#copy-unlock-btn").addEventListener("click", () => {
        const txt = ($("#unlock-oneliner") && $("#unlock-oneliner").textContent) || "";
        navigator.clipboard.writeText(txt).then(() => toast("命令已复制", "ok"));
      });
    }

    // Software filters & custom install
    $$("#sw-filters button").forEach((b) => {
      b.addEventListener("click", () => {
        SW_CATEGORY = b.dataset.cat || "all";
        $$("#sw-filters button").forEach((x) => x.classList.toggle("active", x === b));
        if (STATE) renderSoftware(STATE);
      });
    });
    if ($("#sw-search")) $("#sw-search").addEventListener("input", () => STATE && renderSoftware(STATE));
    if ($("#sw-scan-btn")) {
      $("#sw-scan-btn").addEventListener("click", async () => {
        try {
          await apiPost("/api/software/scan", {});
          toast("本机软件扫描已完成", "ok");
          refreshState();
        } catch (err) {
          toast(err.message, "err");
        }
      });
    }
    if ($("#custom-sw-form")) {
      $("#custom-sw-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const spec = (($("#custom-sw-spec") && $("#custom-sw-spec").value) || "").trim();
        if (!spec) return;
        try {
          await apiPost("/api/software/install", {
            pkg_id: "custom",
            custom_spec: spec,
            manager: ($("#custom-sw-mgr") && $("#custom-sw-mgr").value) || "winget",
            drive: ($("#sw-drive") && $("#sw-drive").value) || "E:",
          });
          toast("自定义软件包已加入安装队列", "ok");
          refreshState();
        } catch (err) {
          toast(err.message, "err");
        }
      });
    }

    // Remote hub -> /api/remote/{probe,host,action}
    if ($("#remote-probe-btn")) {
      $("#remote-probe-btn").addEventListener("click", async () => {
        try {
          await apiPost("/api/remote/probe", {});
          toast("远程主机状态已刷新", "ok");
          refreshState();
        } catch (err) {
          toast(err.message, "err");
        }
      });
    }
    if ($("#remote-cmd-form")) {
      $("#remote-cmd-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        try {
          const res = await apiPost("/api/remote/action", {
            host_id: ($("#remote-host-select") && $("#remote-host-select").value) || "",
            action: ($("#remote-action-select") && $("#remote-action-select").value) || "sysinfo",
            cmd: (($("#remote-custom-input") && $("#remote-custom-input").value) || "").trim(),
          });
          if ($("#remote-console")) {
            $("#remote-console").dataset.dirty = "1";
            $("#remote-console").textContent = res.output || JSON.stringify(res, null, 2);
          }
          toast("远程指令执行完毕", "ok");
        } catch (err) {
          toast(err.message, "err");
        }
      });
    }
    if ($("#remote-add-form")) {
      $("#remote-add-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        try {
          await apiPost("/api/remote/host", {
            name: $("#add-host-name").value.trim(),
            address: $("#add-host-addr").value.trim(),
            user: $("#add-host-user").value.trim(),
            port: Number($("#add-host-port").value) || 22,
          });
          toast("远程节点已保存", "ok");
          refreshState();
        } catch (err) {
          toast(err.message, "err");
        }
      });
    }

    // Script builder
    ["#sb-os", "#sb-mode", "#sb-drive", "#sb-pymol", "#sb-base", "#sb-ts", "#sb-extra"].forEach((id) => {
      const el = $(id);
      if (el) el.addEventListener("change", updateScriptBuilder);
      if (el && el.tagName === "INPUT") el.addEventListener("input", updateScriptBuilder);
    });
    if ($("#sb-copy-cmd")) {
      $("#sb-copy-cmd").addEventListener("click", () => {
        navigator.clipboard.writeText(($("#sb-preview") && $("#sb-preview").textContent) || "").then(() => toast("脚本命令已复制", "ok"));
      });
    }

    // Prompt ledger -> POST /api/session
    if ($("#prompt-form")) {
      $("#prompt-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        try {
          await apiPost("/api/session", {
            id: $("#session-select").value,
            title: $("#session-title").value.trim(),
            prompt: $("#session-prompt").value.trim(),
          });
          toast("会话提示词已安全归档", "ok");
          refreshState();
        } catch (err) {
          toast(err.message, "err");
        }
      });
    }

    // Studio, #dsvs-fab & Quick Skin Popover
    const toggleSkinPopover = () => {
      const pop = $("#skin-popover");
      if (pop) pop.hidden = !pop.hidden;
    };
    if ($("#skin-quick-btn")) $("#skin-quick-btn").addEventListener("click", toggleSkinPopover);
    if ($("#dsvs-fab")) $("#dsvs-fab").addEventListener("click", toggleSkinPopover);
    if ($("#close-skin-pop")) {
      $("#close-skin-pop").addEventListener("click", () => {
        if ($("#skin-popover")) $("#skin-popover").hidden = true;
      });
    }

    // Mobile QR Tunnel & Copy buttons
    if ($("#start-cf-tunnel-btn")) {
      $("#start-cf-tunnel-btn").addEventListener("click", async () => {
        if (READONLY) {
          toast("当前云端预览已是公网 HTTPS 链接，手机直接扫上方二维码即可安装！", "ok");
          return;
        }
        const btn = $("#start-cf-tunnel-btn");
        if (btn) btn.disabled = true;
        toast("正在后台静默拉起 Cloudflare 免费公网隧道…", "info");
        try {
          const res = await apiPost("/api/mobile/start-tunnel", {});
          if (res.qr && STATE) {
            STATE.mobile_qr = res.qr;
            renderBeacon(STATE);
          }
          toast(res.url ? `✅ 公网隧道已就绪：${res.url}` : res.note || "隧道握手中，请稍候点刷新二维码", "ok");
        } catch (err) {
          toast(err.message, "err");
        } finally {
          if (btn) btn.disabled = false;
        }
      });
    }
    if ($("#refresh-qr-btn")) {
      $("#refresh-qr-btn").addEventListener("click", async () => {
        try {
          const qr = await apiGet("/api/mobile/qr");
          if (STATE) {
            STATE.mobile_qr = qr;
            renderBeacon(STATE);
          }
          toast("手机安装二维码已刷新", "ok");
        } catch (err) {
          toast(err.message, "err");
        }
      });
    }
    if ($("#copy-mobile-url-btn")) {
      $("#copy-mobile-url-btn").addEventListener("click", () => {
        const mqr = (STATE && STATE.mobile_qr) || {};
        const u = mqr.public_url || (READONLY ? `${location.origin}/mobile` : mqr.lan_url || `${location.origin}/mobile`);
        navigator.clipboard?.writeText(u).then(() => toast("已复制手机 App 访问地址：" + u, "ok"));
      });
    }
    if ($("#media-run-local-btn")) {
      $("#media-run-local-btn").addEventListener("click", async () => {
        const raw = (($("#media-share-input") && $("#media-share-input").value) || "").trim();
        if (!raw) return;
        if (READONLY) {
          toast("预览沙盒已解析命令；在本机 ArenaDesk 中点击将直接调用 yt-dlp 静默下载至 E:\\0downloads\\ArenaMedia！", "info");
          return;
        }
        try {
          const res = await apiPost("/api/media-cua/job", { input: raw, mode: "video_best" });
          toast(`已提交本机静默下载任务 (${(res.job && res.job.job_id) || "queued"})`, "ok");
          refreshState(false);
        } catch (err) {
          toast(err.message, "err");
        }
      });
    }
    $$("#theme-swatches .swatch, .mini-swatches button").forEach((sw) => {
      sw.addEventListener("click", () => {
        const picked = sw.dataset.theme || sw.dataset.themePick || "aurora-abyss";
        SKIN_THEME = picked;
        document.body.dataset.theme = SKIN_THEME;
        if (STATE && STATE.appearance) STATE.appearance.theme = SKIN_THEME;
        applyAppearance((STATE && STATE.appearance) || { theme: SKIN_THEME });
        if (!READONLY) {
          apiPost("/api/appearance", { theme: SKIN_THEME }).catch(() => {});
        }
      });
    });

    const syncSlider = (srcId, dstId, lbl1, lbl2, suffix, cssVar, scale) => {
      const el = $(srcId);
      if (!el) return;
      el.addEventListener("input", () => {
        const v = Number(el.value);
        if ($(dstId)) $(dstId).value = String(v);
        if ($(lbl1)) $(lbl1).textContent = v + suffix;
        if ($(lbl2)) $(lbl2).textContent = v + suffix;
        document.documentElement.style.setProperty(cssVar, scale ? String(v / 100) : v + "px");
        if (STATE && STATE.appearance) {
          if (scale) STATE.appearance.surface_opacity = v / 100;
          else STATE.appearance.glass_blur = v;
        }
      });
      el.addEventListener("change", () => {
        if (READONLY) return;
        const v = Number(el.value);
        const body = scale ? { surface_opacity: v / 100 } : { glass_blur: v };
        apiPost("/api/appearance", body).catch(() => {});
      });
    };
    syncSlider("#rng-opacity", "#pop-rng-op", "#lbl-opacity", "#pop-lbl-op", "%", "--surface-alpha", true);
    syncSlider("#pop-rng-op", "#rng-opacity", "#pop-lbl-op", "#lbl-opacity", "%", "--surface-alpha", true);
    syncSlider("#rng-blur", "#pop-rng-bl", "#lbl-blur", "#pop-lbl-bl", "px", "--glass-blur", false);
    syncSlider("#pop-rng-bl", "#rng-blur", "#pop-lbl-bl", "#lbl-blur", "px", "--glass-blur", false);

    const syncVeil = (srcId, dstId, lbl1, lbl2) => {
      const el = $(srcId);
      if (!el) return;
      el.addEventListener("input", () => {
        const v = Number(el.value);
        if ($(dstId)) $(dstId).value = String(v);
        if ($(lbl1)) $(lbl1).textContent = v + "%";
        if ($(lbl2)) $(lbl2).textContent = v + "%";
        document.documentElement.style.setProperty("--veil-alpha", String(v / 100));
        if (STATE && STATE.appearance) STATE.appearance.veil_opacity = v / 100;
      });
      el.addEventListener("change", () => {
        if (!READONLY) apiPost("/api/appearance", { veil_opacity: Number(el.value) / 100 }).catch(() => {});
      });
    };
    syncVeil("#rng-veil", "#pop-rng-veil", "#lbl-veil", "#pop-lbl-veil");
    syncVeil("#pop-rng-veil", "#rng-veil", "#pop-lbl-veil", "#lbl-veil");

    if ($("#save-skin-btn")) {
      $("#save-skin-btn").addEventListener("click", async () => {
        const cfg = {
          theme: SKIN_THEME,
          surface_opacity: Number($("#rng-opacity").value) / 100,
          veil_opacity: Number(($("#rng-veil") && $("#rng-veil").value) || 10) / 100,
          glass_blur: Number($("#rng-blur").value),
          motion_enabled: $("#chk-motion").checked,
          boot_enabled: $("#chk-boot").checked,
          boot_sound: $("#chk-boot-sound").checked,
        };
        if (READONLY) {
          applyAppearance(Object.assign({}, (STATE && STATE.appearance) || {}, cfg));
          toast("当前预览已实时应用皮肤效果", "ok");
          return;
        }
        try {
          await apiPost("/api/appearance", cfg);
          toast("外观皮肤设置已持久化保存", "ok");
          refreshState();
        } catch (err) {
          toast(err.message, "err");
        }
      });
    }

    if ($("#scan-we-btn")) {
      $("#scan-we-btn").addEventListener("click", async () => {
        try {
          await apiPost("/api/media/scan", {});
          await refreshState();
          toast("Wallpaper Engine 壁纸库扫描完毕", "ok");
        } catch (err) {
          toast(err.message, "err");
        }
      });
    }
    if ($("#apply-media-btn")) {
      $("#apply-media-btn").addEventListener("click", async () => {
        const p = (($("#custom-media-path") && $("#custom-media-path").value) || "").trim();
        if (!p) return;
        try {
          await apiPost("/api/appearance", { custom_media_path: p });
          toast("自定义背景媒体已注册", "ok");
          refreshState();
        } catch (err) {
          toast(err.message, "err");
        }
      });
    }

    // Whale modal -> saved via POST /api/appearance
    const openWhaleModal = () => {
      if ($("#whale-modal")) $("#whale-modal").hidden = false;
    };
    if ($("#open-whale-cfg")) $("#open-whale-cfg").addEventListener("click", openWhaleModal);
    if ($("#whale-gear")) $("#whale-gear").addEventListener("click", openWhaleModal);
    if ($("#close-whale-modal")) {
      $("#close-whale-modal").addEventListener("click", () => {
        if ($("#whale-modal")) $("#whale-modal").hidden = true;
      });
    }
    if ($("#rng-whale-scale")) {
      $("#rng-whale-scale").addEventListener("input", (e) => {
        const v = Number(e.target.value);
        if ($("#lbl-whale-scale")) $("#lbl-whale-scale").textContent = v + "%";
        if ($("#whale-widget")) $("#whale-widget").style.setProperty("--whale-scale", String(v / 100));
      });
    }
    if ($("#save-whale-btn")) {
      $("#save-whale-btn").addEventListener("click", async () => {
        const quotes = (($("#txt-whale-quotes") && $("#txt-whale-quotes").value) || "")
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean);
        const payload = {
          whale_enabled: $("#chk-whale").checked,
          whale_snap: $("#chk-whale-snap").checked,
          whale_sound: $("#chk-whale-sound").checked,
          whale_scale: Number($("#rng-whale-scale").value) / 100,
          whale_quotes: quotes,
        };
        if (READONLY) {
          applyAppearance(Object.assign({}, (STATE && STATE.appearance) || {}, payload));
          if ($("#whale-modal")) $("#whale-modal").hidden = true;
          toast("鲸鱼桌宠设置已在当前预览生效", "ok");
          return;
        }
        try {
          await apiPost("/api/appearance", payload);
          if ($("#whale-modal")) $("#whale-modal").hidden = true;
          toast("鲸鱼桌宠配置已保存", "ok");
          refreshState();
        } catch (err) {
          toast(err.message, "err");
        }
      });
    }
    if ($("#hide-whale-now")) {
      $("#hide-whale-now").addEventListener("click", () => {
        if ($("#whale-widget")) $("#whale-widget").hidden = true;
        if ($("#whale-modal")) $("#whale-modal").hidden = true;
      });
    }
    if ($("#pet-hide")) {
      $("#pet-hide").addEventListener("click", async () => {
        if ($("#whale-widget")) $("#whale-widget").hidden = true;
        if (!READONLY) {
          try {
            await apiPost("/api/control", { name: "arena-desktop-pet", action: "hide" });
          } catch (_) {}
        }
        toast("桌宠已隐藏", "info");
      });
    }
    if ($("#pet-show")) {
      $("#pet-show").addEventListener("click", async () => {
        if ($("#whale-widget")) $("#whale-widget").hidden = false;
        if (!READONLY) {
          try {
            await apiPost("/api/control", { name: "arena-desktop-pet", action: "show" });
          } catch (_) {}
        }
        toast("桌宠已唤醒", "ok");
      });
    }

    // v2.8 Global Watcher 1-Click Start/Stop, Desktop Hub Sync & Embedded Tri-Account Chat
    document.addEventListener("click", async (ev) => {
      const wBtn = ev.target && ev.target.closest && ev.target.closest("[data-watcher-toggle]");
      if (wBtn) {
        const target = wBtn.getAttribute("data-watcher-toggle") || "ALL";
        const enabled = wBtn.getAttribute("data-watcher-enable") === "1";
        try {
          const r = await apiPost("/api/watcher/toggle", { target, enabled });
          toast(r.note || (enabled ? "已开启值守" : "已暂停值守"), "ok");
          refreshState(false);
        } catch (err) {
          toast("切换值守失败：" + err.message, "err");
        }
        return;
      }

      const ahBtn = ev.target && ev.target.closest && ev.target.closest("[data-autoheal-4step]");
      if (ahBtn) {
        toast("🚀 正在自动执行四步自愈与 Tailscale 双机同步…", "info");
        try {
          const r = await apiPost("/api/system/auto-heal-4step", {});
          if (STATE) {
            STATE.autoheal_4step = r;
            renderV28TriConsoleAndWatcher(STATE);
          }
          toast("✅ 四步全自动自愈与同步已执行完成！", "ok");
          refreshState(false);
        } catch (err) {
          toast("四步自愈执行失败：" + err.message, "err");
        }
        return;
      }

      const dBtn = ev.target && ev.target.closest && ev.target.closest("[data-sync-desktop-hub]");
      if (dBtn) {
        toast("正在探测台式机并同步默认基座与 hukeying85-ux/0fuye…", "info");
        try {
          const r = await apiPost("/api/desktop/sync-hub", {});
          toast(r.status || "同步探测已完成", "ok");
          refreshState(false);
        } catch (err) {
          toast("同步探测失败：" + err.message, "err");
        }
        return;
      }

      const fBtn = ev.target && ev.target.closest && ev.target.closest("[data-focus-chat]");
      if (fBtn) {
        const sl = fBtn.getAttribute("data-focus-chat") || "S1";
        const inp = document.getElementById("ovc-inp-" + sl) || document.getElementById("ghc-inp-" + sl);
        if (inp) {
          inp.scrollIntoView({ behavior: "smooth", block: "center" });
          inp.focus();
        }
        return;
      }

      const qBtn = ev.target && ev.target.closest && ev.target.closest("[data-tri-quick-msg]");
      if (qBtn) {
        const slot = qBtn.getAttribute("data-tri-quick-slot") || "S1";
        const message = qBtn.getAttribute("data-tri-quick-msg") || "";
        if (!message) return;
        try {
          toast(`[${slot}] 正在软件内直接执行：${message}`, "info");
          const r = await apiPost("/api/tri-chat/send", { slot, message });
          TRI_CHAT_DRAFTS[slot] = "";
          if (STATE) {
            STATE.tri_chat = { history: r.history, watcher: r.watcher };
            renderV28TriConsoleAndWatcher(STATE);
          }
          toast(`[${slot}] 已执行完成`, "ok");
          refreshState(false);
        } catch (err) {
          toast("执行失败：" + err.message, "err");
        }
      }
    });

    document.addEventListener("submit", async (ev) => {
      const form = ev.target && ev.target.closest && ev.target.closest("form[data-tri-chat-slot]");
      if (!form) return;
      ev.preventDefault();
      const slot = form.getAttribute("data-tri-chat-slot") || "S1";
      const inp = form.querySelector("input[data-tri-input]");
      const message = inp ? inp.value.trim() : "";
      if (!message) return;
      if (inp) inp.value = "";
      TRI_CHAT_DRAFTS[slot] = "";
      try {
        toast(`[${slot}] 正在执行…`, "info");
        const r = await apiPost("/api/tri-chat/send", { slot, message });
        if (STATE) {
          STATE.tri_chat = { history: r.history, watcher: r.watcher };
          renderV28TriConsoleAndWatcher(STATE);
        }
        toast(`[${slot}] 执行完毕`, "ok");
        refreshState(false);
      } catch (err) {
        toast("发送失败：" + err.message, "err");
      }
    });
  }

  async function refreshState(manual) {
    try {
      const data = await apiGet("/api/state");
      renderAll(data);
      if (manual) toast("工作站全量状态已同步", "ok");
    } catch (err) {
      if (manual) toast("刷新失败：" + err.message, "err");
    }
  }

  function startClock() {
    const tick = () => {
      const now = new Date();
      if ($("#clock")) {
        $("#clock").textContent = now.toLocaleString("zh-CN", { hour12: false });
      }
    };
    tick();
    setInterval(tick, 1000);
  }

  async function boot() {
    const hash = (location.hash || "").replace(/^#/, "");
    const qs = new URLSearchParams(location.search);
    const noBootParam = qs.get("noboot") === "1" || qs.get("boot") === "0";
    let autoBootPref = true;
    try {
      autoBootPref = localStorage.getItem("ad_boot_auto") !== "0";
    } catch (_) {}
    const shouldPlayBootOnOpen = !noBootParam && (hash === "boot" || qs.get("boot") === "1" || autoBootPref);

    if (!shouldPlayBootOnOpen) {
      dismissBootOverlay("direct_open_no_boot");
    }

    document.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape") dismissBootOverlay("escape_skip");
    });

    window.addEventListener("hashchange", () => {
      const h = (location.hash || "").replace(/^#/, "");
      if (h === "boot") {
        BOOT_RUNNING = false;
        triggerBootAnimation(true);
      } else if (h && TAB_META[h]) {
        if (!BOOT_RUNNING) {
          dismissBootOverlay();
        }
        switchTab(h, true);
      }
    });

    initCanvasSkin();
    initWhaleWidget();
    bindEvents();
    updateScriptBuilder();
    startClock();

    if (hash && TAB_META[hash]) {
      switchTab(hash, true);
    } else {
      switchTab("overview", true);
    }

    if (shouldPlayBootOnOpen) {
      triggerBootAnimation(true);
    }

    try {
      const bootMeta = await apiGet("/api/bootstrap");
      CSRF = bootMeta.csrf || "";
      READONLY = !!bootMeta.readonly;
    } catch (_) {}

    refreshState(false);

    setInterval(() => {
      if (!document.hidden) {
        refreshState(false);
      }
    }, 25000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
