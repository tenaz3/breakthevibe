/**
 * Step-by-step test replay with tree-based network inspector.
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
    const panel = document.getElementById("replay-panel");

    if (prevBtn) prevBtn.addEventListener("click", () => navigate(-1));
    if (nextBtn) nextBtn.addEventListener("click", () => navigate(1));

    function navigate(delta) {
        const newIndex = currentIndex + delta;
        if (newIndex >= 0 && newIndex < steps.length) {
            currentIndex = newIndex;
            renderStep();
        }
    }

    /** Extract a short readable name from a test function name. */
    function humanizeName(name) {
        if (!name) return "Step";
        // test_home_page_load -> Home Page Load
        return name
            .replace(/^test_/, "")
            .replace(/_/g, " ")
            .replace(/\b\w/g, function (c) { return c.toUpperCase(); });
    }

    /** Extract domain + path from a full URL, truncating query params. */
    function shortUrl(url) {
        if (!url) return "";
        try {
            var u = new URL(url);
            var path = u.pathname;
            if (path.length > 40) path = path.substring(0, 37) + "...";
            return u.hostname + path;
        } catch (e) {
            return url.length > 60 ? url.substring(0, 57) + "..." : url;
        }
    }

    /** Get status code color class. */
    function statusClass(code) {
        if (!code) return "net-status-pending";
        if (code >= 200 && code < 300) return "net-status-ok";
        if (code >= 300 && code < 400) return "net-status-redirect";
        if (code >= 400 && code < 500) return "net-status-client-err";
        if (code >= 500) return "net-status-server-err";
        return "net-status-pending";
    }

    /** Get method badge class. */
    function methodClass(method) {
        var m = (method || "GET").toUpperCase();
        if (m === "GET") return "method-get";
        if (m === "POST") return "method-post";
        if (m === "PUT" || m === "PATCH") return "method-put";
        if (m === "DELETE") return "method-del";
        return "method-get";
    }

    /** Group network requests by domain. */
    function groupByDomain(requests) {
        var groups = {};
        var order = [];
        requests.forEach(function (req) {
            var domain;
            try { domain = new URL(req.url).hostname; } catch (e) { domain = "other"; }
            if (!groups[domain]) {
                groups[domain] = [];
                order.push(domain);
            }
            groups[domain].push(req);
        });
        return { groups: groups, order: order };
    }

    function renderStep() {
        if (!steps.length) {
            if (panel) panel.style.display = "none";
            return;
        }
        if (panel) panel.style.display = "";
        var step = steps[currentIndex];

        // Counter + button states
        if (counter) counter.textContent = (currentIndex + 1) + " / " + steps.length;
        if (prevBtn) prevBtn.disabled = currentIndex === 0;
        if (nextBtn) nextBtn.disabled = currentIndex === steps.length - 1;

        // Step name
        if (stepInfo) {
            stepInfo.textContent = "";
            var badge = document.createElement("span");
            badge.className = "step-badge";
            badge.textContent = "Step " + (currentIndex + 1);
            stepInfo.appendChild(badge);
            var title = document.createElement("span");
            title.className = "step-title";
            title.textContent = humanizeName(step.name);
            stepInfo.appendChild(title);
        }

        // Screenshot — only show if path looks like a served URL or valid path
        if (screenshot) {
            var ssUrl = step.screenshot_url || "";
            if (ssUrl && (ssUrl.startsWith("http") || ssUrl.startsWith("/static") || ssUrl.startsWith("/artifacts"))) {
                screenshot.src = ssUrl;
                screenshot.style.display = "block";
                screenshot.onerror = function () { screenshot.style.display = "none"; };
            } else {
                screenshot.style.display = "none";
            }
        }

        // Network requests — tree view grouped by domain
        if (networkDiv) {
            networkDiv.textContent = "";
            var requests = step.network_requests || [];

            if (requests.length === 0) {
                var empty = document.createElement("div");
                empty.className = "net-empty";
                empty.textContent = "No network calls captured";
                networkDiv.appendChild(empty);
            } else {
                var result = groupByDomain(requests);
                var headerEl = document.createElement("div");
                headerEl.className = "net-header";
                headerEl.textContent = requests.length + " request" + (requests.length === 1 ? "" : "s");
                networkDiv.appendChild(headerEl);

                result.order.forEach(function (domain) {
                    var reqs = result.groups[domain];
                    var group = document.createElement("details");
                    group.className = "net-group";
                    group.open = true;

                    var summary = document.createElement("summary");
                    summary.className = "net-domain";
                    var domainText = document.createElement("span");
                    domainText.textContent = domain;
                    summary.appendChild(domainText);
                    var count = document.createElement("span");
                    count.className = "net-count";
                    count.textContent = reqs.length;
                    summary.appendChild(count);
                    group.appendChild(summary);

                    reqs.forEach(function (req) {
                        var row = document.createElement("div");
                        row.className = "net-row";

                        var methodEl = document.createElement("span");
                        methodEl.className = "net-method " + methodClass(req.method);
                        methodEl.textContent = (req.method || "GET").toUpperCase();
                        row.appendChild(methodEl);

                        var pathEl = document.createElement("span");
                        pathEl.className = "net-path";
                        try {
                            pathEl.textContent = new URL(req.url).pathname;
                        } catch (e) {
                            pathEl.textContent = req.url || "";
                        }
                        pathEl.title = req.url || "";
                        row.appendChild(pathEl);

                        var statusEl = document.createElement("span");
                        statusEl.className = "net-status " + statusClass(req.status);
                        statusEl.textContent = req.status || "...";
                        row.appendChild(statusEl);

                        group.appendChild(row);
                    });

                    networkDiv.appendChild(group);
                });
            }
        }

        // Console logs — color-coded by level
        if (consoleDiv) {
            consoleDiv.textContent = "";
            var logs = step.console_logs || step.console || [];
            if (logs.length > 0) {
                consoleDiv.style.display = "block";
                logs.forEach(function (log) {
                    var line = document.createElement("div");
                    line.className = "console-line";
                    if (log.indexOf("[error]") === 0 || log.indexOf("[Error]") === 0) {
                        line.className += " console-error";
                    } else if (log.indexOf("[warning]") === 0 || log.indexOf("[warn]") === 0) {
                        line.className += " console-warn";
                    } else {
                        line.className += " console-log";
                    }
                    line.textContent = log;
                    consoleDiv.appendChild(line);
                });
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
