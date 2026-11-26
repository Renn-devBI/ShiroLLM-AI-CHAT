(function () {
    // Mesin tema bersama (index.html dan pipeline.html). Tema "default" tidak
    // menimpa apa pun, jadi tampilan awal persis seperti di style.css.
    var KEY = 'shiro_theme_v1';
    var PRESETS = [
        { id: 'default',  name: 'Grafit',       bg: '#121315', fg: '#ececef', accent: '#94a3b8' },
        { id: 'shiro',    name: 'Shiro',        bg: '#f4f4f2', fg: '#1d1e21', accent: '#3d6a8c' },
        { id: 'midnight', name: 'Tengah malam', bg: '#10151d', fg: '#e4e8ef', accent: '#6f9cc4' },
        { id: 'forest',   name: 'Hutan',        bg: '#121713', fg: '#e4eae3', accent: '#8fce9e' },
        { id: 'dusk',     name: 'Senja',        bg: '#191615', fg: '#ece5e0', accent: '#d9a066' },
        { id: 'sakura',   name: 'Sakura',       bg: '#191416', fg: '#eee5e9', accent: '#e596b2' }
    ];
    var TOKENS = [
        '--bg-base', '--bg-surface', '--bg-elevated', '--bg-input', '--bg-code',
        '--border-subtle', '--border-default', '--border-hover',
        '--text-primary', '--text-secondary', '--text-muted',
        '--accent', '--accent-soft', '--ok', '--warn', '--danger', '--danger-soft',
        '--wire', '--wire-done', '--grid-dot', '--grid-line',
        '--code-fg', '--code-secondary', '--code-muted', '--code-border', '--code-hover'
    ];
    var HEX = /^#[0-9a-f]{6}$/i;

    function toRgb(h) { var n = parseInt(h.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
    function toHex(r) { return '#' + r.map(function (v) { return Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, '0'); }).join(''); }
    function mix(a, b, t) { var A = toRgb(a), B = toRgb(b); return toHex(A.map(function (v, i) { return v + (B[i] - v) * t; })); }
    function rgba(h, a) { var c = toRgb(h); return 'rgba(' + c[0] + ',' + c[1] + ',' + c[2] + ',' + a + ')'; }
    function lum(h) {
        var c = toRgb(h).map(function (v) { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
    }
    function contrast(a, b) { var x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); }
    function isLight(h) { return lum(h) > 0.35; }

    function derive(bg, fg, ac) {
        var light = isLight(bg);
        var surface = light ? mix(bg, '#ffffff', 0.55) : mix(bg, fg, 0.035);
        var ok = light ? '#2e9467' : '#5fbf8f';
        var warn = light ? '#b57a14' : '#e0a84a';
        var danger = light ? '#d04a45' : '#e5736f';
        var secondary = mix(fg, bg, 0.35);
        var muted = mix(fg, bg, 0.58);
        var codeBg = light ? '#1f2126' : mix(bg, '#000000', 0.28);
        var codeFg = light ? '#e8e8ea' : fg;
        return {
            '--bg-base': bg,
            '--bg-surface': surface,
            '--bg-elevated': mix(bg, fg, light ? 0.07 : 0.075),
            '--bg-input': surface,
            '--bg-code': codeBg,
            '--border-subtle': mix(bg, fg, 0.09),
            '--border-default': mix(bg, fg, 0.17),
            '--border-hover': mix(bg, fg, 0.3),
            '--text-primary': fg,
            '--text-secondary': secondary,
            '--text-muted': muted,
            '--accent': ac,
            '--accent-soft': rgba(ac, 0.16),
            '--ok': ok,
            '--warn': warn,
            '--danger': danger,
            '--danger-soft': rgba(danger, 0.12),
            '--wire': mix(bg, fg, 0.2),
            '--wire-done': light ? '#3f8a68' : '#4f8f72',
            '--grid-dot': mix(bg, fg, light ? 0.18 : 0.12),
            '--grid-line': mix(bg, fg, 0.07),
            '--code-fg': codeFg,
            '--code-secondary': light ? '#a3a5ab' : secondary,
            '--code-muted': light ? '#80848c' : muted,
            '--code-border': light ? '#2c2e33' : mix(codeBg, fg, 0.1),
            '--code-hover': light ? '#2a2c31' : mix(codeBg, fg, 0.09)
        };
    }

    function defaults() { var p = PRESETS[0]; return { preset: 'default', custom: { bg: p.bg, fg: p.fg, accent: p.accent } }; }
    function validCustom(c) { return c && HEX.test(c.bg) && HEX.test(c.fg) && HEX.test(c.accent); }

    function get() {
        try {
            var s = JSON.parse(localStorage.getItem(KEY));
            if (s) {
                var custom = validCustom(s.custom) ? s.custom : defaults().custom;
                if (s.preset === 'custom' && validCustom(s.custom)) return { preset: 'custom', custom: custom };
                if (PRESETS.some(function (p) { return p.id === s.preset; })) return { preset: s.preset, custom: custom };
            }
        } catch (e) { /* pakai default */ }
        return defaults();
    }

    function resolve(theme) {
        if (theme.preset === 'custom') return theme.custom;
        var p = PRESETS.filter(function (x) { return x.id === theme.preset; })[0] || PRESETS[0];
        return { bg: p.bg, fg: p.fg, accent: p.accent };
    }

    function apply(theme) {
        var root = document.documentElement;
        if (theme.preset === 'default') {
            TOKENS.forEach(function (k) { root.style.removeProperty(k); });
            root.style.colorScheme = '';
            return;
        }
        var c = resolve(theme), t = derive(c.bg, c.fg, c.accent);
        Object.keys(t).forEach(function (k) { root.style.setProperty(k, t[k]); });
        root.style.colorScheme = isLight(c.bg) ? 'light' : 'dark';
    }

    function set(theme) {
        try { localStorage.setItem(KEY, JSON.stringify(theme)); } catch (e) { /* penyimpanan dinonaktifkan */ }
        apply(theme);
    }

    window.ShiroTheme = {
        presets: PRESETS,
        get: get,
        set: set,
        apply: apply,
        resolve: resolve,
        derive: derive,
        defaults: defaults,
        contrast: contrast,
        isLight: isLight,
        key: KEY
    };
    apply(get());
})();
