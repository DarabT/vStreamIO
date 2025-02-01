const { addonBuilder } = require("stremio-addon-sdk");
const { spawn } = require("child_process");

const manifest = { 
    "id": "org.stremio.dtstream",
    "version": "0.0.1",
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

// Fonction de parsing utilisant une expression régulière pour extraire les tuples
function parsePythonOutput(output) {
    console.log("Debug: Raw Python output received:", output);

    const startParseTime = Date.now();

    // Expression régulière pour extraire les groupes de valeurs dans les tuples
    const tupleRegex = /\('([^']*)', '([^']*)', '([^']*)', '([^']*)'\)/g;
    let match;
    const parsedData = [];

    // Extraction des informations en utilisant la regex
    while ((match = tupleRegex.exec(output)) !== null) {
        const [_, siteName, hostName, language, streamUrl] = match;
        parsedData.push({ siteName, hostName, language, streamUrl });
    }

    const endParseTime = Date.now();
    console.log("Debug: Parsed data from Python output:", parsedData);
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

    const startTime = Date.now();
    const pythonArgs = [id, "?function=DoNothing"];
    console.log("Starting Python script with args:", pythonArgs);

    return new Promise((resolve, reject) => {
        const pythonProcess = spawn('python', ["../addonPythonScript/main.py", ...pythonArgs]);
        let pythonOutput = "";

        pythonProcess.stdout.on('data', (data) => {
            pythonOutput += data.toString();
        });

        pythonProcess.stderr.on('data', (data) => {
            console.error("Python Error:", data.toString());
        });

        pythonProcess.on('close', (code) => {
            const endTime = Date.now();
            console.log(`Python script completed in ${(endTime - startTime) / 1000} seconds with code: ${code}`);
            
            if (code !== 0) {
                console.error("Python script failed with exit code:", code);
                return resolve({ 
									streams: [{
										name: `${appName} - Error`,
										description: `Python script failed\nExit code: ${code}`,
										url: ""
									}] 
								});
            }

            try {
                // Utilisation de la fonction `parsePythonOutput` pour interpréter les données
                const pythonData = parsePythonOutput(pythonOutput);

                // Construction de la structure `streams` pour Stremio
                const streams = pythonData.map(({ siteName, hostName, language, streamUrl }) => ({
                    name: `${appName} - ${siteName}`,
                    description: `${hostName}\n${language}`,
                    url: streamUrl
                }));

                console.log("Debug: Final streams to be returned to Stremio:", streams);
                resolve({ streams });
            } catch (error) {
                console.error("Failed to parse Python output:", error);
                resolve({ 
							streams: [{
								name: `${appName} - Error`,
								description: `Failed to parse Python output\nError: ${error.message}`,
								url: ""
							}] 
						});
            }
        });
    });
});

module.exports = builder.getInterface();
