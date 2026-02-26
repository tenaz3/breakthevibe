/**
 * Mind-map visualization using D3.js.
 * Fetches sitemap data and renders a horizontal tree layout.
 */
(function () {
    "use strict";

    const container = document.getElementById("mindmap-container");
    if (!container) return;

    const url = container.getAttribute("data-sitemap-url");
    if (!url) return;

    fetch(url)
        .then((r) => r.json())
        .then((data) => render(data))
        .catch((err) => {
            container.textContent = "Failed to load sitemap: " + err.message;
        });

    function buildHierarchy(data) {
        const root = { name: data.project_id || "Site", children: [] };
        const pages = data.pages || [];

        pages.forEach((page) => {
            const routeNode = { name: page.path || page.url, children: [] };

            // Components group
            const components = page.components || [];
            if (components.length > 0) {
                const compGroup = { name: "Components", type: "group_components", children: [] };
                components.forEach((comp) => {
                    compGroup.children.push({ name: comp.name, type: "component" });
                });
                routeNode.children.push(compGroup);
            }

            // Interactions group
            const interactions = page.interactions || [];
            if (interactions.length > 0) {
                const intGroup = { name: "Interactions", type: "group_interactions", children: [] };
                interactions.forEach((intr) => {
                    intGroup.children.push({ name: intr.name + " (" + intr.action_type + ")", type: "interaction" });
                });
                routeNode.children.push(intGroup);
            }

            // API calls group
            const apiCalls = page.api_calls || [];
            if (apiCalls.length > 0) {
                const apiGroup = { name: "API Calls", type: "group_api", children: [] };
                apiCalls.forEach((call) => {
                    const label = (call.method || "GET") + " " + (call.url || "").split("?")[0];
                    apiGroup.children.push({ name: label, type: "api_call" });
                });
                routeNode.children.push(apiGroup);
            }

            // Screenshot/Video reference
            if (page.screenshot_path || page.video_path) {
                const mediaGroup = { name: "Screenshots/Video", type: "group_media", children: [] };
                if (page.screenshot_path) {
                    mediaGroup.children.push({ name: "Screenshot", type: "screenshot" });
                }
                if (page.video_path) {
                    mediaGroup.children.push({ name: "Video", type: "video" });
                }
                routeNode.children.push(mediaGroup);
            }

            root.children.push(routeNode);
        });

        if (root.children.length === 0) {
            root.children.push({ name: "(no pages crawled)", children: [] });
        }
        return root;
    }

    function render(data) {
        const width = container.clientWidth;
        const height = container.clientHeight;
        const margin = { top: 20, right: 120, bottom: 20, left: 120 };

        const svg = d3
            .select(container)
            .append("svg")
            .attr("width", width)
            .attr("height", height);

        const g = svg
            .append("g")
            .attr("transform", `translate(${margin.left},${margin.top})`);

        const hierData = d3.hierarchy(buildHierarchy(data));
        const treeLayout = d3.tree().size([
            height - margin.top - margin.bottom,
            width - margin.left - margin.right,
        ]);
        treeLayout(hierData);

        // Links
        g.selectAll(".link")
            .data(hierData.links())
            .join("path")
            .attr("class", "link")
            .attr("fill", "none")
            .attr("stroke", getComputedStyle(document.documentElement).getPropertyValue('--border').trim())
            .attr("stroke-width", 1.5)
            .attr("d", d3.linkHorizontal().x((d) => d.y).y((d) => d.x));

        // Nodes
        const node = g
            .selectAll(".node")
            .data(hierData.descendants())
            .join("g")
            .attr("class", "node")
            .attr("transform", (d) => `translate(${d.y},${d.x})`);

        const typeColors = {
            component: "#22c55e",
            interaction: "#eab308",
            api_call: "#ef4444",
            screenshot: "#8b5cf6",
            video: "#ec4899",
            group_components: "#22c55e",
            group_interactions: "#eab308",
            group_api: "#ef4444",
            group_media: "#8b5cf6",
        };

        node.append("circle")
            .attr("r", (d) => d.data.type && d.data.type.startsWith("group_") ? 6 : 4)
            .attr("fill", (d) => typeColors[d.data.type] || getComputedStyle(document.documentElement).getPropertyValue('--muted-foreground').trim());

        node.append("text")
            .attr("dy", "0.31em")
            .attr("x", (d) => (d.children ? -8 : 8))
            .attr("text-anchor", (d) => (d.children ? "end" : "start"))
            .attr("fill", getComputedStyle(document.documentElement).getPropertyValue('--foreground').trim())
            .attr("font-size", "11px")
            .attr("font-family", "'Inter', system-ui, sans-serif")
            .text((d) => d.data.name);

        // Pan & zoom
        const zoom = d3.zoom().scaleExtent([0.3, 3]).on("zoom", (event) => {
            g.attr("transform", event.transform);
        });
        svg.call(zoom);
    }
})();
