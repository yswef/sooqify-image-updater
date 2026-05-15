// =========================================================
// Sooqify Image Updater - Frontend
// تطوير: يوسف الحمزي
// =========================================================

let state = {
    config: null,
    products: [],
    selected: new Set(),
    running: false,
};

function api() {
    return window.pywebview.api;
}

function log(message, level = "info") {
    const el = document.getElementById("logOutput");
    const line = document.createElement("div");
    line.className = `log-line ${level}`;
    const time = new Date().toLocaleTimeString("ar-SA", { hour12: false });
    line.textContent = `[${time}] ${message}`;
    el.appendChild(line);
    el.scrollTop = el.scrollHeight;
}

// -----------------------------------------------------
// الإقلاع
// -----------------------------------------------------

window.addEventListener("pywebviewready", async () => {
    const config = await api().get_config();
    state.config = config;

    if (config.SetupCompleted && config.RootFolder) {
        showMainScreen();
        await runScan();
    } else {
        showSetupScreen();
    }
});

function showSetupScreen() {
    document.getElementById("setupScreen").classList.remove("hidden");
    document.getElementById("mainScreen").classList.add("hidden");
}

function showMainScreen() {
    document.getElementById("setupScreen").classList.add("hidden");
    document.getElementById("mainScreen").classList.remove("hidden");
    updateDevBadge();
}

function updateDevBadge() {
    const badge = document.getElementById("devBadge");
    if (state.config && state.config.DeveloperMode) {
        badge.classList.remove("hidden");
    } else {
        badge.classList.add("hidden");
    }
}

// -----------------------------------------------------
// معالج الإعداد الأول
// -----------------------------------------------------

document.getElementById("pickFolderBtn").addEventListener("click", async () => {
    const folder = await api().choose_root_folder();
    if (folder) {
        document.getElementById("setupRootFolder").value = folder;
    }
});

document.getElementById("completeSetupBtn").addEventListener("click", async () => {
    const rootFolder = document.getElementById("setupRootFolder").value.trim();
    const operatorName = document.getElementById("setupOperatorName").value.trim();

    if (!rootFolder) {
        log("لازم تختار مجلد الصور الرئيسي أولاً.", "error");
        return;
    }
    if (!operatorName) {
        log("لازم تكتب اسمك.", "error");
        return;
    }

    const browser = document.getElementById("setupBrowser").value;

    const newConfig = await api().save_config({
        RootFolder: rootFolder,
        Browser: browser,
        OperatorName: operatorName,
        SyncServerUrl: document.getElementById("setupSyncUrl").value.trim(),
        SyncToken: document.getElementById("setupSyncToken").value.trim(),
        SyncEnabled: !!document.getElementById("setupSyncUrl").value.trim(),
        Headless: document.getElementById("setupHeadless").checked,
        SetupCompleted: true,
    });

    state.config = newConfig;
    showMainScreen();
    log("تمام! قبل أول رفع فعلي، اضغط زر 'تسجيل الدخول' بالأعلى وسجّل دخولك لسوقيفاي مرة وحدة.");
    await runScan();
});

// -----------------------------------------------------
// الفحص وعرض المنتجات
// -----------------------------------------------------

async function runScan() {
    log("بدء الفحص بالمنظف الخلفي...");
    const result = await api().scan_products();
    if (!result.success) {
        log(result.error, "error");
    }
}

function renderProductList() {
    const container = document.getElementById("productList");
    const emptyState = document.getElementById("emptyState");
    container.innerHTML = "";

    if (state.products.length === 0) {
        emptyState.classList.remove("hidden");
        updateSelectionSummary();
        return;
    }
    emptyState.classList.add("hidden");

    for (const product of state.products) {
        const row = document.createElement("div");
        row.className = "product-row";
        row.dataset.path = product.path;

        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.checked = state.selected.has(product.path);
        checkbox.addEventListener("change", () => {
            if (checkbox.checked) state.selected.add(product.path);
            else state.selected.delete(product.path);
            updateSelectionSummary();
        });

        const name = document.createElement("span");
        name.className = "name";
        name.textContent = product.name_ar || product.name_en || product.folder_name;

        const meta = document.createElement("span");
        meta.className = "meta";
        meta.textContent = `${product.images_count} صورة${product.style_code ? " · " + product.style_code : ""}`;

        row.append(checkbox, name, meta);

        if (!product.has_search_key) {
            const warn = document.createElement("span");
            warn.className = "status-tag";
            warn.textContent = "بلا مفتاح بحث";
            row.appendChild(warn);
        }

        container.appendChild(row);
    }
    updateSelectionSummary();
}

function updateSelectionSummary() {
    document.getElementById("selectionSummary").textContent =
        `${state.selected.size} من ${state.products.length} منتج محدَّد`;
}

document.getElementById("selectAllCheck").addEventListener("change", (e) => {
    if (e.target.checked) {
        state.selected = new Set(state.products.map(p => p.path));
    } else {
        state.selected.clear();
    }
    renderProductList();
});

document.getElementById("rescanBtn").addEventListener("click", runScan);
document.getElementById("emptyRescanBtn").addEventListener("click", runScan);

// -----------------------------------------------------
// تسجيل الدخول لمرة وحدة (بروفايل التطبيق المخصص)
// -----------------------------------------------------

document.getElementById("loginBtn").addEventListener("click", async () => {
    const result = await api().login_browser();
    if (!result.success) {
        log(result.error, "error");
        return;
    }
    document.getElementById("loginBtn").disabled = true;
    log("جارِ فتح نافذة تسجيل الدخول... سجّل دخولك بلوحة سوقيفاي بالنافذة اللي تفتح، وبعدها أغلقها عادي.");
});

// -----------------------------------------------------
// التشغيل
// -----------------------------------------------------

document.getElementById("startRunBtn").addEventListener("click", async () => {
    if (state.selected.size === 0) {
        log("اختر منتج واحد على الأقل أولاً.", "error");
        return;
    }
    const dryRun = document.getElementById("dryRunCheck").checked;
    const result = await api().start_run(Array.from(state.selected), dryRun);
    if (!result.success) {
        log(result.error, "error");
        return;
    }
    setRunningState(true);
    log(dryRun ? "بدأ وضع المراجعة — المتصفح سيفتح وتعتمد كل منتج يدوياً..." : "بدأ الرفع التلقائي بالخلفية...");
});

document.getElementById("stopRunBtn").addEventListener("click", async () => {
    await api().stop_run();
    log("طلب إيقاف - سينتهي بعد المنتج الحالي...");
});

function setRunningState(running) {
    state.running = running;
    document.getElementById("startRunBtn").disabled = running;
    document.getElementById("stopRunBtn").disabled = !running;
    document.getElementById("progressWrap").classList.toggle("hidden", !running);
}

// -----------------------------------------------------
// نافذة الإعدادات المنبثقة
// -----------------------------------------------------

const settingsModal = document.getElementById("settingsModal");

document.getElementById("settingsBtn").addEventListener("click", () => {
    populateSettingsInputs();
    settingsModal.classList.remove("hidden");
});

document.getElementById("closeSettingsBtn").addEventListener("click", () => {
    settingsModal.classList.add("hidden");
});

document.getElementById("cancelSettingsBtn").addEventListener("click", () => {
    settingsModal.classList.add("hidden");
});

document.getElementById("changeFolderBtn").addEventListener("click", async () => {
    const folder = await api().choose_root_folder();
    if (folder) {
        document.getElementById("settingsRootFolder").value = folder;
    }
});

document.getElementById("saveSettingsBtn").addEventListener("click", async () => {
    const rootFolder = document.getElementById("settingsRootFolder").value.trim();
    const operatorName = document.getElementById("settingsOperatorName").value.trim();

    if (!rootFolder) {
        alert("يجب اختيار مجلد الصور.");
        return;
    }
    if (!operatorName) {
        alert("يجب تحديد اسم المشغل.");
        return;
    }

    const browser = document.getElementById("settingsBrowser").value;
    const batchLimit = parseInt(document.getElementById("settingsBatchLimit").value) || 0;
    const soundOnComplete = document.getElementById("settingsSoundOnComplete").checked;
    const moveFolders = document.getElementById("settingsMoveFolders").checked;
    const syncEnabled = document.getElementById("settingsSyncEnabled").checked;
    const syncUrl = document.getElementById("settingsSyncUrl").value.trim();
    const syncToken = document.getElementById("settingsSyncToken").value.trim();

    const newConfig = await api().save_config({
        RootFolder: rootFolder,
        Browser: browser,
        OperatorName: operatorName,
        BatchLimit: batchLimit,
        SoundOnComplete: soundOnComplete,
        MoveFoldersAfterUpload: moveFolders,
        SyncEnabled: syncEnabled,
        SyncServerUrl: syncUrl,
        SyncToken: syncToken,
        SetupCompleted: true
    });

    const rootChanged = state.config.RootFolder !== newConfig.RootFolder;
    state.config = newConfig;
    updateDevBadge();
    settingsModal.classList.add("hidden");
    log("تم حفظ الإعدادات بنجاح.", "success");

    if (rootChanged) {
        await runScan();
    }
});

function populateSettingsInputs() {
    const cfg = state.config;
    if (!cfg) return;

    document.getElementById("settingsRootFolder").value = cfg.RootFolder || "";
    document.getElementById("settingsOperatorName").value = cfg.OperatorName || "";
    document.getElementById("settingsBrowser").value = cfg.Browser || "chrome";
    document.getElementById("settingsBatchLimit").value = cfg.BatchLimit !== undefined ? cfg.BatchLimit : 0;
    document.getElementById("settingsSoundOnComplete").checked = !!cfg.SoundOnComplete;
    document.getElementById("settingsMoveFolders").checked = cfg.MoveFoldersAfterUpload !== undefined ? !!cfg.MoveFoldersAfterUpload : true;
    document.getElementById("settingsSyncEnabled").checked = !!cfg.SyncEnabled;
    document.getElementById("settingsSyncUrl").value = cfg.SyncServerUrl || "";
    document.getElementById("settingsSyncToken").value = cfg.SyncToken || "";
}

// -----------------------------------------------------
// نغمة الصوت باستخدام Web Audio API
// -----------------------------------------------------

function playCompletionBeep() {
    try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();

        // النغمة الأولى (F-note: 880Hz)
        const osc1 = audioCtx.createOscillator();
        const gain1 = audioCtx.createGain();
        osc1.connect(gain1);
        gain1.connect(audioCtx.destination);
        osc1.frequency.setValueAtTime(880, audioCtx.currentTime);
        gain1.gain.setValueAtTime(0.12, audioCtx.currentTime);
        gain1.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.3);
        osc1.start(audioCtx.currentTime);
        osc1.stop(audioCtx.currentTime + 0.3);

        // النغمة الثانية (Higher F-note: 1100Hz)
        setTimeout(() => {
            const osc2 = audioCtx.createOscillator();
            const gain2 = audioCtx.createGain();
            osc2.connect(gain2);
            gain2.connect(audioCtx.destination);
            osc2.frequency.setValueAtTime(1100, audioCtx.currentTime);
            gain2.gain.setValueAtTime(0.12, audioCtx.currentTime);
            gain2.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.4);
            osc2.start(audioCtx.currentTime);
            osc2.stop(audioCtx.currentTime + 0.4);
        }, 300);
    } catch (e) {
        console.error("فشل تشغيل التنبيه الصوتي عبر الويب:", e);
    }
}

// -----------------------------------------------------
// أحداث حيّة من الخلفية (main.py يستدعي هذي الدالة مباشرة)
// -----------------------------------------------------

window.onBackendEvent = function (msg) {
    const { event, payload } = msg;

    if (event === "scan_started") {
        log("جارِ فحص مجلد الصور بالخلفية...");
        document.getElementById("rescanBtn").disabled = true;
    } else if (event === "scan_progress") {
        // تحديث بسيط للنشاط دون إغراق السجل بكل المجلدات لو كانت بالآلاف
        if (payload.count % 5 === 0) {
            log(`جاري المسح... تم رصد ${payload.count} منتج حتى الآن.`);
        }
    } else if (event === "scan_finished") {
        document.getElementById("rescanBtn").disabled = false;
        if (payload.success) {
            state.products = payload.products;
            state.selected = new Set(payload.products.map(p => p.path));
            renderProductList();
            log(`اكتمل الفحص: تم رصد ${payload.count} منتج.`, "success");
        } else {
            log(`فشل فحص الملفات: ${payload.error}`, "error");
        }
    } else if (event === "run_started") {
        updateProgress(0, payload.total);
    } else if (event === "product_started") {
        log(`جارِ معالجة: ${payload.folder} (${payload.index}/${payload.total})`);
    } else if (event === "product_done") {
        updateProgress(payload.index, payload.total);
        markProductStatus(payload.folder, payload.status);
        if (payload.message) {
            log(`${payload.folder}: ${payload.message}`, payload.status === "failed" ? "error" : "success");
        }
    } else if (event === "run_finished") {
        setRunningState(false);
        log(`انتهى: ${payload.success.length} نجح، ${payload.failed.length} فشل، ${payload.skipped?.length || 0} تخطّي.`, "success");
        if (state.config && state.config.SoundOnComplete) {
            playCompletionBeep();
        }
        // تحديث فوري لقائمة المنتجات المتبقية بعد النقل
        runScan();
    } else if (event === "run_stopped") {
        setRunningState(false);
        log(`تم الإيقاف بعد ${payload.completed} من ${payload.total}.`);
        // تحديث فوري لقائمة المنتجات المتبقية بعد النقل
        runScan();
    } else if (event === "run_error") {
        setRunningState(false);
        log(`خطأ: ${payload.error}`, "error");
        runScan();
    } else if (event === "waiting_approval") {
        log(`⏳ بانتظار اعتمادك اليدوي لـ ${payload.folder} من المتصفح... (${payload.index}/${payload.total})`);
    } else if (event === "login_ready") {
        log("النافذة فتحت - سجّل دخولك وأغلقها لما تخلص.", "success");
    } else if (event === "login_finished") {
        document.getElementById("loginBtn").disabled = false;
        if (payload.success) {
            log("تم حفظ تسجيل الدخول بنجاح. تقدر تبدأ الرفع الفعلي الحين.", "success");
        } else {
            log(`فشل تسجيل الدخول: ${payload.error}`, "error");
        }
    }
};

function updateProgress(current, total) {
    const percent = total ? Math.round((current / total) * 100) : 0;
    document.getElementById("progressFill").style.width = `${percent}%`;
    document.getElementById("progressLabel").textContent = `${current} / ${total}`;
}

function markProductStatus(folderName, status) {
    const row = Array.from(document.querySelectorAll(".product-row"))
        .find(r => r.querySelector(".name")?.textContent && r.dataset.path.includes(folderName));
    if (row) {
        row.classList.remove("status-success", "status-failed", "status-preview");
        row.classList.add(`status-${status}`);
    }
}