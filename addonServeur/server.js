const { serveHTTP } = require("stremio-addon-sdk");
const addonInterface = require("./addon");

// Serveur avec en-tête pour contourner l'avertissement LocalTunnel
serveHTTP(addonInterface, {
    port: 8000,
    onRequest: (req, res) => {
        // Ajouter l'en-tête requis pour LocalTunnel
        res.setHeader("bypass-tunnel-reminder", "true");
    },
});
