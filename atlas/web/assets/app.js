// Router: one page at a time, each page returns an optional cleanup function.
import { loadCore, parseHash, esc } from "./core.js";
import { renderDiscover, renderAtlas, renderExplore } from "./pages.js";
import { renderCompare, renderStories, renderMethods } from "./pages2.js";

const ROUTES = {
  discover: renderDiscover, atlas: renderAtlas, explore: renderExplore,
  compare: renderCompare, stories: renderStories, methods: renderMethods,
};
const main = document.getElementById("view");
let cleanup = null;
let current = "";

function route() {
  const r = parseHash();
  const key = `${r.route}/${r.args.join("/")}`;
  // Pages rewrite their own query string (replaceState) to stay shareable; only re-render on path changes.
  if (key === current && !route.force) return;
  route.force = false;
  current = key;
  if (cleanup) { try { cleanup(); } catch (e) { console.warn(e); } cleanup = null; }
  const page = ROUTES[r.route] || renderDiscover;
  document.querySelectorAll(".nav a").forEach((a) => a.classList.toggle("active", a.dataset.route === r.route));
  main.innerHTML = "";
  window.scrollTo(0, 0);
  try {
    cleanup = page(main, r) || null;
  } catch (e) {
    console.error(e);
    main.innerHTML = `<div class="page"><div class="empty">Something went wrong rendering this page: ${esc(e.message)}</div></div>`;
  }
}

window.addEventListener("hashchange", () => { route.force = true; route(); });
loadCore()
  .then(route)
  .catch((e) => {
    main.innerHTML = `<div class="page"><h2>The Atlas data could not be loaded</h2>
      <p class="secondary">${esc(e.message)}</p>
      <p class="secondary">Serve this folder over HTTP — run <code>python atlas/serve.py</code> from the repository root — rather than opening index.html directly, and make sure <code>python atlas/build_atlas.py</code> has generated <code>atlas/web/data/</code>.</p></div>`;
  });
