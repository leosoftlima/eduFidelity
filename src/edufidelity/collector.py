"""In-page collector: turns a rendered DOM into a flat list of interface elements.

Rules (kept deliberately small and explicit):

* control  - button, input, select, textarea, a[href], or an interactive ARIA role.
             A control is a leaf: nothing inside it is collected.
* graphic  - img, svg, canvas, video, or an element with a background image and no text.
             A graphic is a leaf, so a multi-path icon counts once.
* text     - an element that owns at least one non-empty text node. Inline children
             (strong, em, span...) are folded into it. Its box hugs the text.
* invisible elements and zero-area boxes are dropped; pure containers are not collected.

The collector never depends on instrumentation of the generated page. In
``referenceMode`` it additionally reports ``data-ref-id`` / ``data-salience``, which
exist only in hand-authored synthetic references.
"""

COLLECTOR_JS = r"""
(opts) => {
  const W = opts.frameWidth, H = opts.frameHeight;
  const CONTROL_TAGS = new Set(['button', 'input', 'select', 'textarea']);
  const CONTROL_ROLES = new Set(['button', 'link', 'checkbox', 'radio', 'textbox', 'tab',
                                 'switch', 'menuitem', 'option', 'combobox']);
  const GRAPHIC_TAGS = new Set(['img', 'svg', 'canvas', 'video']);
  const SKIP_TAGS = new Set(['script', 'style', 'noscript', 'template', 'head', 'meta', 'link']);
  const out = [];

  const hash = (s) => {
    let h = 0x811c9dc5;
    for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 0x01000193); }
    return (h >>> 0).toString(16).padStart(8, '0');
  };
  const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const box = (r) => ({
    x: (r.left + window.scrollX) / W, y: (r.top + window.scrollY) / H,
    w: r.width / W, h: r.height / H,
  });
  const push = (el, type, text, rect, asset) => {
    if (rect.width <= 0 || rect.height <= 0) return;
    const item = { type, text, asset, tag: el.tagName.toLowerCase(), ...box(rect) };
    if (opts.referenceMode) {
      item.refId = el.getAttribute('data-ref-id');
      item.salience = el.getAttribute('data-salience');
    }
    out.push(item);
  };
  const controlLabel = (el) => clean(
    el.getAttribute('aria-label') || el.innerText || el.value || el.getAttribute('placeholder')
  );
  const graphicAsset = (el, tag) => {
    if (tag === 'img') {
      const src = el.currentSrc || el.getAttribute('src') || '';
      return src ? hash(src.startsWith('data:') ? src : src.split('/').pop()) : null;
    }
    if (tag === 'svg') return hash(el.innerHTML.replace(/\s+/g, ' '));
    return null;
  };
  const ownsText = (el) => {
    for (const node of el.childNodes) {
      if (node.nodeType === Node.TEXT_NODE && node.textContent.trim()) return true;
    }
    return false;
  };

  const walk = (el, insideText) => {
    const tag = el.tagName.toLowerCase();
    if (SKIP_TAGS.has(tag)) return;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return;
    if (tag === 'input' && el.type === 'hidden') return;

    const role = el.getAttribute('role');
    if (CONTROL_TAGS.has(tag) || (tag === 'a' && el.hasAttribute('href')) ||
        (role && CONTROL_ROLES.has(role))) {
      push(el, 'control', controlLabel(el), el.getBoundingClientRect(), null);
      return;
    }
    if (GRAPHIC_TAGS.has(tag)) {
      push(el, 'graphic', clean(el.getAttribute('alt') || el.getAttribute('aria-label')),
           el.getBoundingClientRect(), graphicAsset(el, tag));
      return;
    }
    let textHere = insideText;
    if (!insideText && ownsText(el)) {
      const range = document.createRange();
      range.selectNodeContents(el);
      push(el, 'text', clean(el.innerText), range.getBoundingClientRect(), null);
      textHere = true;
    } else if (!insideText && cs.backgroundImage.includes('url(') && !clean(el.innerText)) {
      push(el, 'graphic', clean(el.getAttribute('aria-label')), el.getBoundingClientRect(),
           hash(cs.backgroundImage));
      return;
    }
    for (const child of el.children) walk(child, textHere);
  };

  walk(document.body, false);
  return { pageHeight: document.documentElement.scrollHeight, elements: out };
}
"""

LAYOUT_SIGNATURE_JS = r"""
() => {
  const parts = [document.documentElement.scrollHeight, document.images.length];
  const all = document.body.querySelectorAll('*');
  parts.push(all.length);
  for (let i = 0; i < all.length; i += Math.max(1, Math.floor(all.length / 200))) {
    const r = all[i].getBoundingClientRect();
    parts.push(Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height));
  }
  return parts.join(',');
}
"""

FREEZE_CSS = """
*, *::before, *::after {
  animation: none !important;
  transition: none !important;
  scroll-behavior: auto !important;
  caret-color: transparent !important;
}
"""
