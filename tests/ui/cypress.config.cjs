const fs = require('node:fs');

// Run from the repository root with --config-file tests/ui/cypress.config.cjs.
// Supply a temporary LAB login through RELIABILITY_SESSION_FILE (private JSON).
// JS and CSS are served from this checkout via request interception; no deploy
// or change to the active reporting checkout is needed for UI validation.
module.exports = {
 e2e: {
  baseUrl: 'https://juan.isambane.co.za',
  specPattern: 'tests/ui/problem_machines.cy.js',
  supportFile: false,
  setupNodeEvents(on, config) {
   if (!process.env.RELIABILITY_SESSION_FILE) throw new Error('Set RELIABILITY_SESSION_FILE to a private LAB session JSON');
   config.env.sid = JSON.parse(fs.readFileSync(process.env.RELIABILITY_SESSION_FILE, 'utf8')).sid;
   return config;
  }
 },
 hosts: {'juan.isambane.co.za': '127.0.0.1'},
 video: false,
 screenshotsFolder: process.env.RELIABILITY_SCREENSHOTS_DIR || '/tmp/engineering-reliability-ui-screenshots',
 chromeWebSecurity: false,
 defaultCommandTimeout: 20000
};
