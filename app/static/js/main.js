const root = document.documentElement;
const body = document.body;
const VIEW_STORAGE_KEY = "agarwood-view-mode";
const MOBILE_BREAKPOINT = 960;

const menuToggle = document.querySelector("[data-menu-toggle]");
const menuBackdrop = document.querySelector("[data-menu-backdrop]");
const menuCloseButton = document.querySelector("[data-menu-close]");
const sidebar = document.querySelector(".sidebar");
const viewModeButtons = document.querySelectorAll("[data-view-mode-option]");
const viewModeLabels = document.querySelectorAll("[data-view-mode-label]");
const viewModeNotes = document.querySelectorAll("[data-view-mode-note]");
const menuLinks = document.querySelectorAll("[data-menu-link]");
const navLinks = document.querySelectorAll("[data-nav-group][data-nav-key]");
const sidebarFolds = document.querySelectorAll("[data-sidebar-fold]");

let lockedScrollY = 0;
let scrollSpyPrimaryKey = "";
let scrollSpySectionId = "";

const resolveAutoViewMode = () => (window.innerWidth <= MOBILE_BREAKPOINT ? "mobile" : "desktop");
const isMobileView = () => root.dataset.viewMode === "mobile";
const getCurrentPage = () => body.dataset.currentPage || "";
const getCurrentHash = () => (window.location.hash || "").replace(/^#/, "");
const getCurrentSectionKey = () => body.dataset.currentSectionKey || "";
const getCurrentReadingKey = () => body.dataset.currentReadingKey || "";
const isDashboardHomePage = () => {
    const page = getCurrentPage();
    const path = window.location.pathname || "/";
    return page === "home" || path === "/" || path.startsWith("/day/");
};

const PRIMARY_HASH_MAP = {
    "today-focus": "today_focus",
    "today-new": "today_new",
    "reading-category-theme_track": "theme_track",
    "recent-versions": "recent_changes",
    "history-archive": "history_archive",
};

const HOME_SCROLL_SPY_SECTIONS = [
    { id: "today-focus", key: "today_focus" },
    { id: "today-new", key: "today_new" },
    { id: "recent-versions", key: "recent_changes" },
    { id: "history-archive", key: "history_archive" },
];

const BOTTOM_PAGE_MAP = {
    history: "history",
    library: "library",
    upload: "upload",
    access_manage: "access_manage",
    access_change: "access_change",
    debug: "debug",
};

const NAV_GROUP_FIELD_MAP = {
    primary: "primaryKey",
    reading: "readingKey",
    secondary: "secondaryKey",
    bottom: "bottomKey",
};

const resolveActiveNavState = () => {
    const page = getCurrentPage();
    const path = window.location.pathname || "/";
    const hash = getCurrentHash();
    const readingKey = getCurrentReadingKey();
    const sectionKey = getCurrentSectionKey();
    const state = {
        primaryKey: "",
        readingKey: "",
        secondaryKey: "",
        bottomKey: "",
    };

    if (page === "home" || path === "/" || path.startsWith("/day/")) {
        if (hash.startsWith("reading-category-")) {
            const hashReadingKey = hash.replace(/^reading-category-/, "");
            if (hashReadingKey === "reading_note") {
                state.secondaryKey = "reading_note";
            } else {
                state.readingKey = hashReadingKey;
                if (hashReadingKey === "theme_track") {
                    state.primaryKey = "theme_track";
                }
            }
        } else {
            state.primaryKey = scrollSpyPrimaryKey || PRIMARY_HASH_MAP[hash] || "today_focus";
        }
    }

    if (page === "history" || path.startsWith("/history")) {
        state.primaryKey = "history_archive";
    }

    if (page === "section") {
        if (sectionKey === "report_note" || readingKey === "reading_note") {
            state.secondaryKey = "reading_note";
        } else {
            state.readingKey = readingKey;
        }
        if (readingKey === "theme_track") {
            state.primaryKey = "theme_track";
        }
    }

    if (BOTTOM_PAGE_MAP[page]) {
        state.bottomKey = BOTTOM_PAGE_MAP[page];
    }

    return state;
};

const syncActiveNavState = () => {
    if (!navLinks.length) {
        return;
    }
    const state = resolveActiveNavState();
    navLinks.forEach((link) => {
        const group = link.dataset.navGroup || "";
        const groupField = NAV_GROUP_FIELD_MAP[group];
        const isActive = !!groupField && state[groupField] === link.dataset.navKey;
        link.classList.toggle("active", isActive);
        if (isActive) {
            link.setAttribute("aria-current", "page");
        } else {
            link.removeAttribute("aria-current");
        }
    });
};

const setHomeScrollSpyState = (primaryKey, sectionId, updateHash = false) => {
    if (!primaryKey) {
        return;
    }
    scrollSpyPrimaryKey = primaryKey;
    scrollSpySectionId = sectionId || "";
    if (
        updateHash &&
        sectionId &&
        isDashboardHomePage() &&
        !getCurrentHash().startsWith("reading-category-") &&
        window.location.hash !== `#${sectionId}`
    ) {
        const nextUrl = `${window.location.pathname}${window.location.search}#${sectionId}`;
        window.history.replaceState(window.history.state, "", nextUrl);
    }
    syncActiveNavState();
};

const bindHomePrimaryScrollSpy = () => {
    if (!isDashboardHomePage()) {
        return;
    }

    const trackedSections = HOME_SCROLL_SPY_SECTIONS
        .map((item) => {
            const element = document.getElementById(item.id);
            return element ? { ...item, element } : null;
        })
        .filter(Boolean);

    if (!trackedSections.length) {
        return;
    }

    const measureActiveSection = (updateHash = false) => {
        const offset = Math.max(128, Math.min(window.innerHeight * 0.22, 220));
        let activeSection = trackedSections[0];

        trackedSections.forEach((section) => {
            const rect = section.element.getBoundingClientRect();
            if (rect.top - offset <= 0) {
                activeSection = section;
            }
        });

        if (!activeSection) {
            return;
        }
        if (activeSection.key === scrollSpyPrimaryKey && activeSection.id === scrollSpySectionId) {
            return;
        }
        setHomeScrollSpyState(activeSection.key, activeSection.id, updateHash);
    };

    let ticking = false;
    const scheduleMeasure = (updateHash = false) => {
        if (ticking) {
            return;
        }
        ticking = true;
        window.requestAnimationFrame(() => {
            ticking = false;
            measureActiveSection(updateHash);
        });
    };

    navLinks.forEach((link) => {
        if ((link.dataset.navGroup || "") !== "primary") {
            return;
        }
        const href = link.getAttribute("href") || "";
        const matchedSection = trackedSections.find((section) => href.endsWith(`#${section.id}`));
        if (!matchedSection) {
            return;
        }
        link.addEventListener("click", () => {
            setHomeScrollSpyState(matchedSection.key, matchedSection.id, false);
        });
    });

    window.addEventListener(
        "scroll",
        () => {
            if (!getCurrentHash().startsWith("reading-category-")) {
                scheduleMeasure(true);
            }
        },
        { passive: true },
    );
    window.addEventListener("resize", () => scheduleMeasure(false));
    window.addEventListener("load", () => scheduleMeasure(false));
    scheduleMeasure(false);
};

const getStoredViewPreference = () => {
    try {
        return localStorage.getItem(VIEW_STORAGE_KEY) || "auto";
    } catch (error) {
        return "auto";
    }
};

const setStoredViewPreference = (preference) => {
    try {
        localStorage.setItem(VIEW_STORAGE_KEY, preference);
    } catch (error) {
        return;
    }
};

const setStoredFoldState = (key, isOpen) => {
    try {
        localStorage.setItem(`agarwood-sidebar-fold-${key}`, isOpen ? "open" : "closed");
    } catch (error) {
        return;
    }
};

const getStoredFoldState = (key) => {
    try {
        return localStorage.getItem(`agarwood-sidebar-fold-${key}`);
    } catch (error) {
        return null;
    }
};

const lockBodyScroll = () => {
    if (body.classList.contains("menu-open")) {
        return;
    }
    lockedScrollY = window.scrollY || window.pageYOffset || 0;
    body.style.position = "fixed";
    body.style.top = `-${lockedScrollY}px`;
    body.style.width = "100%";
    body.classList.add("menu-open");
};

const unlockBodyScroll = () => {
    if (!body.classList.contains("menu-open")) {
        return;
    }
    const top = body.style.top;
    body.classList.remove("menu-open");
    body.style.position = "";
    body.style.top = "";
    body.style.width = "";
    const restoreY = top ? Math.abs(parseInt(top, 10)) : lockedScrollY;
    window.scrollTo(0, restoreY);
};

const closeMobileMenu = () => {
    unlockBodyScroll();
    if (menuToggle) {
        menuToggle.setAttribute("aria-expanded", "false");
    }
};

const openMobileMenu = () => {
    if (!isMobileView()) {
        return;
    }
    lockBodyScroll();
    if (menuToggle) {
        menuToggle.setAttribute("aria-expanded", "true");
    }
};

const updateViewModeUi = (preference, resolvedMode) => {
    const modeLabel = resolvedMode === "mobile" ? "手机版" : "电脑版";
    const noteText = preference === "auto" ? `当前由系统自动适配为 ${modeLabel}` : `当前已手动锁定为 ${modeLabel}`;

    viewModeLabels.forEach((node) => {
        node.textContent = modeLabel;
    });
    viewModeNotes.forEach((node) => {
        node.textContent = noteText;
    });
    viewModeButtons.forEach((button) => {
        button.classList.toggle("active", button.dataset.viewModeOption === preference);
    });
};

const applyViewMode = (preference, persist = false) => {
    const safePreference = ["auto", "mobile", "desktop"].includes(preference) ? preference : "auto";
    const resolvedMode = safePreference === "auto" ? resolveAutoViewMode() : safePreference;

    root.classList.remove("view-mobile", "view-desktop", "view-manual");
    root.classList.add(resolvedMode === "mobile" ? "view-mobile" : "view-desktop");
    if (safePreference !== "auto") {
        root.classList.add("view-manual");
    }
    root.dataset.viewPreference = safePreference;
    root.dataset.viewMode = resolvedMode;
    updateViewModeUi(safePreference, resolvedMode);

    if (persist) {
        setStoredViewPreference(safePreference);
    }
    if (resolvedMode !== "mobile") {
        closeMobileMenu();
    }
};

applyViewMode(getStoredViewPreference(), false);
bindHomePrimaryScrollSpy();
syncActiveNavState();

if (menuToggle && sidebar) {
    menuToggle.addEventListener("click", () => {
        const isOpen = body.classList.contains("menu-open");
        if (isOpen) {
            closeMobileMenu();
            return;
        }
        openMobileMenu();
    });
}

if (menuBackdrop) {
    menuBackdrop.addEventListener("click", closeMobileMenu);
}

if (menuCloseButton) {
    menuCloseButton.addEventListener("click", closeMobileMenu);
}

if (sidebar) {
    sidebar.addEventListener("click", (event) => {
        event.stopPropagation();
    });
}

menuLinks.forEach((link) => {
    link.addEventListener("click", () => {
        closeMobileMenu();
        window.setTimeout(syncActiveNavState, 0);
    });
});

viewModeButtons.forEach((button) => {
    button.addEventListener("click", () => {
        applyViewMode(button.dataset.viewModeOption || "auto", true);
    });
});

sidebarFolds.forEach((fold) => {
    const key = fold.dataset.sidebarFold;
    if (!key) {
        return;
    }
    const storedState = getStoredFoldState(key);
    if (storedState === "open") {
        fold.open = true;
    } else if (storedState === "closed") {
        fold.open = false;
    }
    fold.addEventListener("toggle", () => {
        setStoredFoldState(key, fold.open);
    });
});

window.addEventListener("resize", () => {
    if (getStoredViewPreference() === "auto") {
        applyViewMode("auto", false);
    }
    if (!isMobileView()) {
        closeMobileMenu();
    }
});

window.addEventListener("hashchange", () => {
    syncActiveNavState();
});

window.addEventListener("popstate", () => {
    syncActiveNavState();
});

document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
        closeMobileMenu();
    }
});

const input = document.querySelector("#files");
const dropzone = document.querySelector(".dropzone");
const selectedFiles = document.querySelector("[data-selected-files]");

if (input && dropzone && selectedFiles) {
    const renderSelection = () => {
        if (!input.files || input.files.length === 0) {
            selectedFiles.textContent = "尚未选择文件";
            return;
        }
        const names = Array.from(input.files).map((file) => file.name);
        selectedFiles.textContent = `已选择 ${names.length} 个文件：${names.join(" / ")}`;
    };

    input.addEventListener("change", renderSelection);

    ["dragenter", "dragover"].forEach((eventName) => {
        dropzone.addEventListener(eventName, (event) => {
            event.preventDefault();
            dropzone.classList.add("dragover");
        });
    });

    ["dragleave", "drop"].forEach((eventName) => {
        dropzone.addEventListener(eventName, (event) => {
            event.preventDefault();
            dropzone.classList.remove("dragover");
        });
    });

    dropzone.addEventListener("drop", (event) => {
        if (!event.dataTransfer?.files?.length) {
            return;
        }
        const transfer = new DataTransfer();
        Array.from(event.dataTransfer.files).forEach((file) => transfer.items.add(file));
        input.files = transfer.files;
        renderSelection();
    });
}

const filterButtons = document.querySelectorAll("[data-card-filter]");
const filterCards = document.querySelectorAll(".insight-card[data-status]");

if (filterButtons.length && filterCards.length) {
    filterButtons.forEach((button) => {
        button.addEventListener("click", () => {
            const target = button.dataset.cardFilter || "all";
            filterButtons.forEach((item) => item.classList.toggle("active", item === button));
            filterCards.forEach((card) => {
                const status = card.dataset.status;
                const shouldShow = target === "all" || status === target;
                card.style.display = shouldShow ? "" : "none";
            });
        });
    });
}

document.querySelectorAll("[data-confirm]").forEach((element) => {
    element.addEventListener("click", (event) => {
        const message = element.dataset.confirm || "确认执行该操作吗？";
        if (!window.confirm(message)) {
            event.preventDefault();
        }
    });
});

document.querySelectorAll("[data-copy-url]").forEach((element) => {
    element.addEventListener("click", async () => {
        const value = element.dataset.copyUrl || "";
        if (!value) {
            return;
        }
        try {
            await navigator.clipboard.writeText(value);
            const originalText = element.textContent;
            element.textContent = "已复制";
            window.setTimeout(() => {
                element.textContent = originalText;
            }, 1600);
        } catch (error) {
            window.prompt("复制失败，请手动复制链接：", value);
        }
    });
});
