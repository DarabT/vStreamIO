const { addonBuilder } = require("stremio-addon-sdk");
const fetch = require("node-fetch");

const manifest = { 
    "id": "org.stremio.dtstream",
    "version": "0.0.3",
    "name": "vStreamIO",
    "description": "vStream addon for StremIO",
    "resources": [
        "stream"
    ],
    "types": ["movie", "series"],
    "idPrefixes": ["tt", "kitsu"],
    "catalogs": []
};

const builder = new addonBuilder(manifest);
const appName = "vStream";
const API_URL = "http://127.0.0.2:8001/process/"; // URL du serveur FastAPI

// Fonction de parsing utilisant une expression régulière pour extraire les tuples
function parsePythonOutput(output) {
    // console.log("Debug: Raw Python output received:", output);

    const startParseTime = Date.now();

    // Expression régulière pour extraire les groupes de valeurs dans les tuples
    const tupleRegex = /\('([^']*)', '([^']*)', '([^']*)', '([^']*)', '([^']*)'\)/g;
    let match;
    const parsedData = [];

    // Extraction des informations en utilisant la regex
    while ((match = tupleRegex.exec(output)) !== null) {
        const [_, siteName, hostName, language, fileName, streamUrl] = match;
        parsedData.push({ siteName, hostName, language, fileName, streamUrl });
    }

    const endParseTime = Date.now();
    // console.log("Debug: Parsed data from Python output:", parsedData);
    console.log(`Parsing completed in ${(endParseTime - startParseTime) / 1000} seconds`);
    return parsedData;
}

// Handler pour les streams
builder.defineStreamHandler(async function(args) {
    const { id } = args;
    if (!id.match(/tt\d+/i) && !id.match(/kitsu:\d+/i)) {
        console.log("Invalid ID format:", id);
        return Promise.resolve({ streams: [] });
    }

    console.log(`Handling stream request for ID: ${id}`);

    try {
        const startTime = Date.now();

        // Appel à l'API FastAPI
        const response = await fetch(API_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ requestId: id }),
        });

        if (!response.ok) {
            throw new Error(`API error: ${response.status} - ${response.statusText}`);
        }

        const data = await response.json();
        const pythonOutput = data.output;

        const endTime = Date.now();
        console.log(`Python API response received in ${(endTime - startTime) / 1000} seconds`);

        // Parsing de la réponse Python
        const pythonData = parsePythonOutput(pythonOutput);

        // Construction des streams pour Stremio
        const streams = pythonData.map(({ siteName, hostName, language, fileName, streamUrl }) => ({
            name: `${appName} - ${siteName}`,
            description: `${fileName}\n${hostName}\n${language}`,
            url: streamUrl
        }));

        return { streams };
    } catch (error) {
        console.error("Error calling Python API:", error);
        return {
            streams: [{
                name: `${appName} - Error`,
                description: `Failed to call Python API\nError: ${error.message}`,
                url: ""
            }]
        };
    }
});

module.exports = builder.getInterface();
