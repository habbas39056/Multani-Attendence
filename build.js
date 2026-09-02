const fs = require('fs');
const path = require('path');

console.log("=== BUILDING MULTANI TRADERS NETLIFY BUNDLE ===");

const targets = ['static', 'dist', 'public', 'netlify_deploy'];

targets.forEach(dir => {
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    if (!fs.existsSync(path.join(dir, 'css'))) fs.mkdirSync(path.join(dir, 'css'), { recursive: true });
    if (!fs.existsSync(path.join(dir, 'js'))) fs.mkdirSync(path.join(dir, 'js'), { recursive: true });

    // Copy index.html
    fs.copyFileSync('index.html', path.join(dir, 'index.html'));
    
    // Copy css
    if (fs.existsSync('css/style.css')) {
        fs.copyFileSync('css/style.css', path.join(dir, 'css', 'style.css'));
    }
    
    // Copy js
    if (fs.existsSync('js/app.js')) {
        fs.copyFileSync('js/app.js', path.join(dir, 'js', 'app.js'));
    }
    if (fs.existsSync('js/multani_core.js')) {
        fs.copyFileSync('js/multani_core.js', path.join(dir, 'js', 'multani_core.js'));
    }

    // Copy _redirects
    if (fs.existsSync('_redirects')) {
        fs.copyFileSync('_redirects', path.join(dir, '_redirects'));
    }

    console.log(`[SUCCESS] Prepared folder: ${dir}/`);
});

console.log("=== BUILD COMPLETE FOR ALL NETLIFY TARGETS ===");
