// =========================================================
// Sooqify Image Updater - Frontend
// Developer: Yousef Alhamzy
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
// Bootstrap
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
    document.getElementById("settingsScreen").classList.add("hidden");
    document.getElementById("mainScreen").classList.add("hidden");
}

function showMainScreen() {
    document.getElementById("setupScreen").classList.add("hidden");
    document.getElementById("settingsScreen").classList.add("hidden");
    document.getElementById("mainScreen").classList.remove("hidden");
    updateDevBadge();
}

function showSettingsScreen() {
    const cfg = state.config || {};
    document.getElementById("settingsRootFolder").value = cfg.RootFolder || "";
    document.getElementById("settingsBrowser").value = cfg.Browser || "chrome";
    document.getElementById("settingsOperatorName").value = cfg.OperatorName || "";
    document.getElementById("settingsSyncUrl").value = cfg.SyncServerUrl || "";
    document.getElementById("settingsSyncToken").value = "";
    document.getElementById("settingsSyncToken").placeholder = cfg.HasSyncToken
        ? "•••••••• (اتركه فاضياً للإبقاء عليه)"
        : "اتركه فاضياً للإبقاء على الحالي";
    document.getElementById("settingsBatchLimit").value = cfg.BatchLimit ?? 0;
    document.getElementById("settingsHeadless").checked = !!cfg.Headless;
    document.getElementById("settingsSound").checked = cfg.SoundOnComplete !== false;

    document.getElementById("setupScreen").classList.add("hidden");
    document.getElementById("mainScreen").classList.add("hidden");
    document.getElementById("settingsScreen").classList.remove("hidden");
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
// First-run setup handlers
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
    await runScan();
});

// -----------------------------------------------------
// Scanning and rendering products
// -----------------------------------------------------

async function runScan() {
    log("جارِ فحص المجلد...");
    const result = await api().scan_products();
    if (!result.success) {
        log(result.error, "error");
        return;
    }
    state.products = result.products;
    state.selected = new Set(result.products.map(p => p.path));
    renderProductList();
    log(`تم العثور على ${result.count} منتج.`, "success");
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
// Settings
// -----------------------------------------------------

document.getElementById("settingsBtn").addEventListener("click", showSettingsScreen);
document.getElementById("settingsCancelBtn").addEventListener("click", showMainScreen);

document.getElementById("settingsPickFolderBtn").addEventListener("click", async () => {
    const folder = await api().choose_root_folder();
    if (folder) {
        document.getElementById("settingsRootFolder").value = folder;
    }
});

document.getElementById("settingsSaveBtn").addEventListener("click", async () => {
    const rootFolder = document.getElementById("settingsRootFolder").value.trim();
    const operatorName = document.getElementById("settingsOperatorName").value.trim();
    const batchLimitRaw = document.getElementById("settingsBatchLimit").value.trim();
    const batchLimit = batchLimitRaw === "" ? 0 : Math.max(0, parseInt(batchLimitRaw, 10) || 0);
    const tokenInput = document.getElementById("settingsSyncToken").value;

    const payload = {
        RootFolder: rootFolder,
        Browser: document.getElementById("settingsBrowser").value,
        OperatorName: operatorName,
        SyncServerUrl: document.getElementById("settingsSyncUrl").value.trim(),
        SyncEnabled: !!document.getElementById("settingsSyncUrl").value.trim(),
        BatchLimit: batchLimit,
        Headless: document.getElementById("settingsHeadless").checked,
        SoundOnComplete: document.getElementById("settingsSound").checked,
    };
    // Only send SyncToken if the user actually typed a new value - an empty field means "keep the current one".
    if (tokenInput) {
        payload.SyncToken = tokenInput;
    }

    const newConfig = await api().save_config(payload);
    state.config = newConfig;
    log("تم حفظ الإعدادات.", "success");
    showMainScreen();
    await runScan();
});

document.getElementById("startLoginBtn").addEventListener("click", async () => {
    const result = await api().start_login();
    if (!result.success) {
        log(result.error, "error");
        return;
    }
    const hint = document.getElementById("loginStatusHint");
    hint.textContent = "جارِ فتح المتصفح... سجّل دخولك بلوحة سوقيفاي، ثم أغلق نافذة المتصفح لما تخلص.";
    document.getElementById("startLoginBtn").disabled = true;
    log("جارِ فتح متصفح تسجيل الدخول...");
});

// -----------------------------------------------------
// Run
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
    log(dryRun ? "بدأ وضع المعاينة..." : "بدأ الرفع الفعلي...");
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
// Live events from the backend (main.py calls this function directly)
// -----------------------------------------------------

window.onBackendEvent = function (msg) {
    const { event, payload } = msg;

    if (event === "run_started") {
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
    } else if (event === "run_stopped") {
        setRunningState(false);
        log(`تم الإيقاف بعد ${payload.completed} من ${payload.total}.`);
    } else if (event === "run_error") {
        setRunningState(false);
        log(`خطأ: ${payload.error}`, "error");
    } else if (event === "login_started") {
        log("جارِ فتح متصفح تسجيل الدخول...");
    } else if (event === "login_finished") {
        log("انتهت جلسة تسجيل الدخول - تم الحفظ.", "success");
        resetLoginButton();
    } else if (event === "login_error") {
        log(`تعذّر فتح متصفح تسجيل الدخول: ${payload.error}`, "error");
        resetLoginButton();
    }
};

function resetLoginButton() {
    const btn = document.getElementById("startLoginBtn");
    const hint = document.getElementById("loginStatusHint");
    if (btn) btn.disabled = false;
    if (hint) {
        hint.textContent = "يفتح بروفايل متصفح خاص بالتطبيق (منفصل تماماً عن متصفحك الشخصي) - سجّل دخولك فيه وأغلقه، ويُحفظ تلقائياً لكل مرة بعدها.";
    }
}

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