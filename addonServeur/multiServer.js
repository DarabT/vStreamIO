const express = require("express");
const fs = require("fs");
const fetch = require("node-fetch"); // si Node >=18, fetch est natif
const { addonBuilder, getRouter } = require("stremio-addon-sdk");

// Config
const sites = JSON.parse(fs.readFileSync(
    "../vStreamKodi/plugin.video.vstream/resources/sites.json"
));
const excludedSites = ["dnspython", 
						"adkami_com",
						"alldebrid",
						"debrid_link",
						"freebox",
						"siteonefichier",
						"topimdb"
						];
const app = express();
const port = 8000;

// CORS
app.use((req, res, next) => {
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
    res.setHeader("Access-Control-Allow-Headers", "Content-Type");
    next();
});

// Python API
const PYTHON_API = "http://127.0.0.2:8001/process/";
// Fonction de parsing utilisant une expression régulière pour extraire les tuples
function parsePythonOutput(output) {
    // console.log("Debug: Raw Python output received:", output);

    const startParseTime = Date.now();

    // Expression régulière pour extraire les groupes de valeurs dans les tuples
    const tupleRegex = /\('([^']*)', '([^']*)', '([^']*)', '([^']*)', '([^']*)', ('[^']*'|False), ('[^']*'|False)\)/g;
    let match;
    const parsedData = [];

    // Extraction des informations en utilisant la regex
    while ((match = tupleRegex.exec(output)) !== null) {
        const [_, siteName, hostName, language, fileName, streamUrl, userAgent, referer] = match;
        parsedData.push([
            siteName,
            hostName,
            language,
            fileName,
            streamUrl,
            userAgent !== "False" ? userAgent.replace(/^'|'$/g, '') : false,
            referer !== "False" ? referer.replace(/^'|'$/g, '') : false
        ]);
    }

    const endParseTime = Date.now();
    // console.log("Debug: Parsed data from Python output:", parsedData);
    console.log(`Parsing completed in ${(endParseTime - startParseTime) / 1000} seconds`);
    return parsedData;
}


// Liste des addons
const addons = [];

Object.entries(sites.sites).forEach(([key, site]) => {
    if (site.active === "True" && !excludedSites.includes(key)) {

        const manifest = {
            id: "org.stremio.dtstream_" + key,
            name: "vStreamIO - " + site.label,
            version: "0.0.4",
            description: "Addon auto-généré pour " + site.label,
            resources: ["stream"],
            types: ["movie", "series"],
            idPrefixes: ["tt", "kitsu"],
            catalogs: [
                { type: "movie", id: key + "_movies", name: "Films " + site.label }
            ]
        };

        const builder = new addonBuilder(manifest);

        // Catalog vide pour l'instant
        builder.defineCatalogHandler(() => Promise.resolve({ metas: [] }));

        // StreamHandler → envoi au serveur Python
        builder.defineStreamHandler(async (args) => {
            const { id } = args;

            if (!id.match(/tt\d+/i) && !id.match(/kitsu:\d+/i)) {
                console.log("ID invalide:", id);
                return { streams: [] };
            }
			
			console.log(`Handling stream request for ID: ${id}`);
			
            try {
				const startTime = Date.now();
				
				// Appel à l'API FastAPI
                const response = await fetch(PYTHON_API, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ 
                        requestId: id, 
                        addonKey: key
                    }),
                });

                if (!response.ok) throw new Error(`API Python erreur: ${response.status}`);

                const data = await response.json();
                const pythonOutput = data.output;

				const endTime = Date.now();
				console.log(`Python API ${key} response received in ${(endTime - startTime) / 1000} seconds`);
				
				// Parsing de la réponse Python
				const pythonData = parsePythonOutput(pythonOutput);
		
                const streams = pythonData.map(
                    ([siteName, hostName, language, fileName, streamUrl, userAgent, referer], index) => {
                        const behaviorHints = {};
                        if (userAgent || referer) {
                            behaviorHints.notWebReady = true;
                            behaviorHints.proxyHeaders = { request: {} };
                            if (userAgent) behaviorHints.proxyHeaders.request["User-Agent"] = userAgent;
                            if (referer) behaviorHints.proxyHeaders.request["Referer"] = referer;
                        }

                        return {
                            name: `${manifest.name}\n[${index + 1}]`,
                            description: `${fileName}\n${hostName}\n${language}`,
                            url: streamUrl,
                            behaviorHints: Object.keys(behaviorHints).length > 0 ? behaviorHints : undefined
                        };
                    }
                );

                return { streams };
            } catch (err) {
                console.error("Erreur API Python:", err);
                return {
					streams: [{
						name: `${manifest.name} - Error`,
						description: `Failed to call Python API\nError: ${err.message}`,
						url: ""
					}]
				};
            }
        });

        const router = getRouter(builder.getInterface());

        // Manifest JSON
        app.get(`/${key}/manifest.json`, (req, res) => res.json(manifest));

        // Addon complet
        app.use(`/${key}`, router);

        addons.push({ key, site, manifest });
    }
});

// Page d’accueil
app.get("/", (req, res) => {
    const host = req.headers.host;
    let html = `
        <html>
        <head>
            <meta charset="utf-8"/>
            <title>vStreamIO Addons</title>
            <style>
                body { font-family: sans-serif; }
                .addon { margin: 10px 0; }
                .installed { color: green; font-weight: bold; }
            </style>
        </head>
        <body>
            <h1>vStreamIO Addons</h1>
            <ul id="addons">
    `;

    addons.forEach(({ key, site }) => {
        html += `
            <li class="addon" id="addon-${key}">
                ${site.label} -
                <a href="stremio://${host}/${key}/manifest.json" class="install-link" data-key="${key}">
                    Installer
                </a>
                <span class="status"></span>
            </li>
        `;
    });

    html += `
            </ul>
            <script>
                document.querySelectorAll(".install-link").forEach(link => {
                    link.addEventListener("click", (e) => {
                        const key = e.target.dataset.key;
                        localStorage.setItem("installed-" + key, "true"); // Sauvegarde
                        updateStatus(key);
                    });
                });

                function updateStatus(key) {
                    const statusEl = document.querySelector("#addon-" + key + " .status");
                    if (localStorage.getItem("installed-" + key) === "true") {
                        statusEl.textContent = " ✅ Installé";
                        statusEl.className = "status installed";
                    }
                }

                // Au chargement de la page → restaure l’état
                window.addEventListener("DOMContentLoaded", () => {
                    document.querySelectorAll(".install-link").forEach(link => {
                        updateStatus(link.dataset.key);
                    });
                });
            </script>
        </body>
        </html>
    `;
    res.send(html);
});

app.listen(port, () => console.log(`Serveur addons actif: http://localhost:${port}`));
