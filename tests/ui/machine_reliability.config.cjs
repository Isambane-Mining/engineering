const fs = require('node:fs');
module.exports = {
    e2e: {
        baseUrl: 'https://juan.isambane.co.za',
        specPattern: 'tests/ui/machine_reliability.cy.js',
        supportFile: false,
        setupNodeEvents(on, config) {
            if (!process.env.RELIABILITY_SESSION_FILE) throw new Error('Supply a temporary LAB session via RELIABILITY_SESSION_FILE');
            config.env.sid = JSON.parse(fs.readFileSync(process.env.RELIABILITY_SESSION_FILE, 'utf8')).sid;
            return config;
        }
    },
    hosts: {'juan.isambane.co.za': '127.0.0.1'},
    video: false,
    screenshotsFolder: '/tmp/machine-reliability-screenshots',
    chromeWebSecurity: false,
    defaultCommandTimeout: 25000
};
