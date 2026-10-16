const app = require('./api/index.js');

const PORT = process.env.PORT || 7474;

app.listen(PORT, () => {
    console.log(`======================================================`);
    console.log(` Shiro AI Web UI Static Preview (Node.js Server)`);
    console.log(` Running at: http://localhost:${PORT}`);
    console.log(` Template: templates/index.html`);
    console.log(` Static Assets: static/ (style.css, script.js)`);
    console.log(` Ready for Vercel deployment & local preview`);
    console.log(`======================================================`);
});
