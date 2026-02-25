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
            const components = page.components || [];
            components.forEach((comp) => {
                routeNode.children.push({ name: comp.name, type: "component" });
            });
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
            .attr("stroke", "#4b5563")
            .attr("stroke-width", 1.5)
            .attr("d", d3.linkHorizontal().x((d) => d.y).y((d) => d.x));

        // Nodes
        const node = g
            .selectAll(".node")
            .data(hierData.descendants())
            .join("g")
            .attr("class", "node")
            .attr("transform", (d) => `translate(${d.y},${d.x})`);

        node.append("circle")
            .attr("r", 5)
            .attr("fill", (d) =>
                d.data.type === "component" ? "#22c55e" : "#6366f1"
            );

        node.append("text")
            .attr("dy", "0.31em")
            .attr("x", (d) => (d.children ? -8 : 8))
            .attr("text-anchor", (d) => (d.children ? "end" : "start"))
            .attr("fill", "#e4e4e7")
            .attr("font-size", "12px")
            .text((d) => d.data.name);

        // Pan & zoom
        const zoom = d3.zoom().scaleExtent([0.3, 3]).on("zoom", (event) => {
            g.attr("transform", event.transform);
        });
        svg.call(zoom);
    }
})();
