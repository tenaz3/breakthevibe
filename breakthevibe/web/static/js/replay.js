/**
 * Step-by-step test replay navigation.
 * Uses safe DOM manipulation (no innerHTML) to prevent XSS.
 */
(function () {
    "use strict";

    let steps = [];
    let currentIndex = 0;

    const prevBtn = document.getElementById("replay-prev");
    const nextBtn = document.getElementById("replay-next");
    const counter = document.getElementById("replay-counter");
    const stepInfo = document.getElementById("replay-step-info");
    const screenshot = document.getElementById("replay-screenshot");
    const networkDiv = document.getElementById("replay-network");
    const consoleDiv = document.getElementById("replay-console");

    if (prevBtn) prevBtn.addEventListener("click", () => navigate(-1));
    if (nextBtn) nextBtn.addEventListener("click", () => navigate(1));

    function navigate(delta) {
        const newIndex = currentIndex + delta;
        if (newIndex >= 0 && newIndex < steps.length) {
            currentIndex = newIndex;
            renderStep();
        }
    }

    function renderStep() {
        if (!steps.length) return;
        const step = steps[currentIndex];

        if (counter) {
            counter.textContent = (currentIndex + 1) + " / " + steps.length;
        }

        if (stepInfo) {
            stepInfo.textContent = "";
            const action = document.createElement("strong");
            action.textContent = step.action || "unknown";
            stepInfo.appendChild(action);
            if (step.description) {
                const desc = document.createElement("span");
                desc.textContent = " — " + step.description;
                desc.className = "text-muted-foreground";
                stepInfo.appendChild(desc);
            }
        }

        if (screenshot && step.screenshot_url) {
            screenshot.src = step.screenshot_url;
            screenshot.style.display = "block";
        } else if (screenshot) {
            screenshot.style.display = "none";
        }

        if (networkDiv) {
            networkDiv.textContent = "";
            const requests = step.network_requests || [];
            requests.forEach(function (req) {
                const entry = document.createElement("div");
                entry.className = "text-muted-foreground";
                const method = document.createElement("strong");
                method.textContent = req.method || "GET";
                entry.appendChild(method);
                const url = document.createTextNode(" " + (req.url || ""));
                entry.appendChild(url);
                const status = document.createElement("span");
                status.textContent = " → " + (req.status || "");
                entry.appendChild(status);
                networkDiv.appendChild(entry);
            });
        }

        if (consoleDiv) {
            const logs = step.console_logs || step.console || [];
            if (logs.length > 0) {
                consoleDiv.textContent = logs.join("\n");
                consoleDiv.style.display = "block";
            } else {
                consoleDiv.style.display = "none";
            }
        }
    }

    window.loadReplaySteps = function (data) {
        steps = data || [];
        currentIndex = 0;
        renderStep();
    };
})();
