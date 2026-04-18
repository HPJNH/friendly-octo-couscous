document.addEventListener("click", (event) => {
    const toggle = event.target.closest("[data-mark-editor-toggle]");
    if (toggle) {
        const shell = toggle.closest(".entry-mark-shell");
        const panel = shell ? shell.querySelector(".entry-mark-editor") : null;
        if (!panel) {
            return;
        }
        const shouldShow = panel.hasAttribute("hidden");
        if (shouldShow) {
            panel.removeAttribute("hidden");
            const input = panel.querySelector("input[name='note']");
            if (input) {
                input.focus();
                input.select();
            }
        } else {
            panel.setAttribute("hidden", "");
        }
        return;
    }

    const cancel = event.target.closest("[data-mark-editor-cancel]");
    if (cancel) {
        const shell = cancel.closest(".entry-mark-shell");
        const panel = shell ? shell.querySelector(".entry-mark-editor") : null;
        if (panel) {
            panel.setAttribute("hidden", "");
        }
    }
});
