// Router: one page at a time, each page returns an optional cleanup function.
import { loadCore, parseHash, esc, PAGE } from "./core.js";
import { renderFindings } from "./findings.js";
import { renderStart, renderAtlas, renderExplore } from "./pages.js";
import { renderCompare, renderStories, renderPipeline, renderAbout } from "./pages2.js";
import { initTour, startTour, startTourAt, tourOnNavigate } from "./tour.js";

const ROUTES = {
  start: renderStart, atlas: renderAtlas, explore: renderExplore,
  compare: renderCompare, stories: renderStories, pipeline: renderPipeline, about: renderAbout,
  findings: renderFindings,
  // earlier addresses still work
  discover: renderStart, methods: renderAbout,
};
const main = document.getElementById("view");
let cleanup = null;
let current = "";

function route() {
  const r = parseHash();
  if (r.route === "tour") { location.hash = "#/start"; startTour(); return; }
  const key = `${r.route}/${r.args.join("/")}`;
  // Pages rewrite their own query string (replaceState) to stay shareable; only re-render on path changes.
  if (key === current && !route.force) return;
  route.force = false;
  current = key;
  if (cleanup) { try { cleanup(); } catch (e) { console.warn(e); } cleanup = null; }
  PAGE.current = null;
  const page = ROUTES[r.route] || renderStart;
  const navKey = { discover: "start", methods: "about" }[r.route] || r.route;
  document.querySelectorAll(".nav a").forEach((a) => a.classList.toggle("active", a.dataset.route === navKey));
  document.body.dataset.route = navKey;
  main.innerHTML = "";
  window.scrollTo(0, 0);
  try {
    cleanup = page(main, r) || null;
    if (r.params.tour) setTimeout(() => startTourAt(r.params.tour), 50);
  } catch (e) {
    console.error(e);
    main.innerHTML = `<div class="page"><div class="empty">Something went wrong rendering this page: ${esc(e.message)}</div></div>`;
  }
}

window.addEventListener("hashchange", () => {
  tourOnNavigate(); route.force = true; route();
  // move focus to the new page unless the user is in a control (screen readers otherwise stay on the old page)
  const ae = document.activeElement;
  if (!ae || ae === document.body || ae.closest(".nav")) main.focus({ preventScroll: true });
});
document.getElementById("nav-tour").addEventListener("click", startTour);
document.querySelector(".skip").addEventListener("click", (e) => { e.preventDefault(); main.focus(); });   // "#view" is not a route
document.getElementById("nav-toggle").addEventListener("click", () => {
  const open = document.body.classList.toggle("nav-open");
  document.getElementById("nav-toggle").setAttribute("aria-expanded", String(open));
});
document.querySelector(".nav").addEventListener("click", (e) => { if (e.target.closest("a")) document.body.classList.remove("nav-open"); });

loadCore()
  .then(() => { initTour(); route(); })
  .catch((e) => {
    main.innerHTML = `<div class="page"><h2>The Atlas data could not be loaded</h2>
      <p class="secondary">${esc(e.message)}</p>
      <p class="secondary">Serve this folder over HTTP — run <code>python atlas/serve.py</code> from the repository root — rather than opening index.html directly, and make sure <code>python atlas/build_atlas.py</code> has generated <code>atlas/web/data/</code>.</p></div>`;
  });
