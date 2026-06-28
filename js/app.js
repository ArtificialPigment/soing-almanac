/* 醺谱 · SOING ALMANAC — SPA engine */
(function () {
  "use strict";
  const DATA = (window.ALMANAC || []).slice();
  const byId = Object.fromEntries(DATA.map(d => [d.id, d]));
  const app = document.getElementById("app");

  const FAMILIES = [
    ["all", "全部"], ["gin", "金酒"], ["whisky", "威士忌"], ["rum", "朗姆 / 卡莎萨"],
    ["vodka", "伏特加"], ["tequila", "龙舌兰"], ["brandy", "白兰地"], ["bitter", "餐前苦酒"],
  ];

  const EMBLEM = `<svg class="cb-emblem" viewBox="0 0 100 100" fill="none" stroke="currentColor" stroke-width="1.4">
    <path d="M26 30 L74 30 L52 56 L52 76 M40 76 L64 76" stroke-linecap="round"/>
    <circle cx="50" cy="20" r="3.2" fill="currentColor" stroke="none"/>
    <path d="M50 20 L52 56" stroke-width="1"/>
    <path d="M18 30 Q50 44 82 30" stroke-width=".8" opacity=".6"/>
    <path d="M14 24 L86 24" stroke-width=".7" opacity=".4"/>
    <path d="M14 84 L86 84" stroke-width=".7" opacity=".4"/>
  </svg>`;

  const h = (tag, attrs = {}, kids) => {
    const e = document.createElement(tag);
    for (const k in attrs) {
      if (k === "class") e.className = attrs[k];
      else if (k === "html") e.innerHTML = attrs[k];
      else if (k.startsWith("on") && typeof attrs[k] === "function") e.addEventListener(k.slice(2), attrs[k]);
      else if (attrs[k] != null) e.setAttribute(k, attrs[k]);
    }
    if (kids != null) (Array.isArray(kids) ? kids : [kids]).forEach(k => k != null && e.appendChild(typeof k === "string" ? document.createTextNode(k) : k));
    return e;
  };
  const frag = html => { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content; };
  const dots = (n, max = 5) => Array.from({ length: max }, (_, i) => `<span class="dot ${i < n ? "on" : ""}"></span>`).join("");
  const cardBack = () => `<div class="card-back">${EMBLEM}<div class="cb-word">SOING</div><div class="cb-sub">醺 谱</div></div>`;

  /* ---------------- ROUTER ---------------- */
  function router() {
    const hash = location.hash || "#/";
    const parts = hash.replace(/^#\//, "").split("/");
    const route = parts[0] || "home";
    window.scrollTo({ top: 0, behavior: "auto" });
    app.innerHTML = "";
    if (route === "blindbox") viewBlindbox(parts[1] === "auto");
    else if (route === "menu") viewMenu();
    else if (route === "cocktail") viewDetail(parts[1]);
    else if (route === "about") viewAbout();
    else viewHome();
    setNav(route);
  }
  function setNav(route) {
    document.querySelectorAll(".nav a").forEach(a => a.classList.toggle("active", a.dataset.nav === route));
  }

  /* ---------------- HOME ---------------- */
  function viewHome() {
    const picks = shuffle(DATA.slice()).slice(0, 4);
    const names = DATA.map(d => `<span>${d.en}</span>`).join("");
    const v = h("section", { class: "view view-wide" });
    v.appendChild(frag(`
      <div class="hero">
        <div class="hero-spot"></div>
        <div class="hero-motifs">
          ${picks.map(p => `<img src="${p.illu}" alt="">`).join("")}
        </div>
        <p class="hero-eyebrow rise">Twenty hand-drawn pours</p>
        <h1 class="hero-title rise" style="animation-delay:.08s">二十味手作酒谱</h1>
        <div class="hero-script rise" style="animation-delay:.16s">the midnight almanac</div>
        <p class="hero-lede rise" style="animation-delay:.24s">二十张手绘鸡尾酒卡，被收进一册可以抽签、可以翻阅的午夜酒谱。今夜，让命运替你点单。</p>
        <div class="hero-cta rise" style="animation-delay:.32s">
          <a class="btn btn-primary" href="#/blindbox" data-link>抽一杯盲盒</a>
          <a class="btn btn-ghost" href="#/menu" data-link>翻开酒单</a>
        </div>
        <div class="hero-count rise" style="animation-delay:.4s">20 RECIPES · 1 DECK · ENDLESS NIGHTS</div>
      </div>
      <div class="ticker"><div class="ticker-track">${names}${names}</div></div>
    `));

    const f1 = DATA.find(d => d.id === "negroni") || DATA[0];
    const f2 = DATA.find(d => d.id === "mojito") || DATA[1];
    const f3 = DATA.find(d => d.id === "aviation") || DATA[2];
    const feat = (item, side, label, en, text) => `
      <div class="home-feature ${side}">
        <div class="hf-art">
          <img src="${item[0].illu}" alt="${item[0].cn} 手绘插画"><img src="${item[1].illu}" alt="${item[1].cn} 手绘插画">
        </div>
        <div class="hf-text">
          <span class="en">${en}</span>
          <h2>${label}</h2>
          <p>${text}</p>
          <a class="btn btn-ghost" href="${side === 'rev' ? '#/menu' : '#/blindbox'}" data-link>${side === 'rev' ? '浏览全部二十味' : '现在就抽一张'}</a>
        </div>
      </div>`;
    v.appendChild(frag(feat([f1, f2], "", "盲盒 · 命运点单", "blind draw",
      "不知道今晚想喝什么？翻开牌堆，抽出一张，看它从卡册里缓缓亮相——从尼格罗尼的猩红到莫吉托的青翠，惊喜由抽签决定。")));
    v.appendChild(frag(feat([f3, f1], "rev", "酒单 · 一册收藏", "the menu",
      "二十味经典，逐一手绘成卡。原料、配比、做法与背后的故事都被一并收录，像翻一本旧酒志，按图索骥地调出一杯。")));
    app.appendChild(v);
    bindReveal(v);
  }

  /* ---------------- BLIND BOX ---------------- */
  let lastDrawn = null, drawing = false;
  function viewBlindbox(auto) {
    const v = h("section", { class: "view view-bb" });
    v.appendChild(frag(`
      <div class="menu-head rise">
        <span class="kicker both">命运点单</span>
        <h1 class="menu-title">今夜，抽一杯</h1>
        <p class="menu-sub">轻触牌堆，让这二十味之一，从卡册中现身。</p>
      </div>
      <div class="bb-stage" id="stage">
        <div class="bb-spot"></div>
        <div class="bb-deck" id="deck" role="button" tabindex="0" aria-label="抽一张鸡尾酒卡">
          <div class="deck-layer card-back-mini"></div>
          <div class="deck-layer card-back-mini"></div>
          <div class="card-back-wrap">${cardBack()}</div>
        </div>
        <div class="bb-drawn" id="drawn">
          <div class="flip">
            <div class="flip-face flip-back">${cardBack()}</div>
            <div class="flip-face flip-front"><img id="drawnImg" src="" alt=""></div>
          </div>
          <div class="flip-glow"></div>
        </div>
        <div class="bb-reveal" id="reveal"></div>
        <p class="bb-hint">轻触牌堆 · 让命运点单</p>
      </div>
    `));
    app.appendChild(v);
    // make stacked layers look like card backs
    v.querySelectorAll(".card-back-mini").forEach(l => l.style.cssText += ";background:linear-gradient(160deg,var(--paper),var(--paper-2));box-shadow:var(--shadow-card)");
    const wrap = v.querySelector(".card-back-wrap"); wrap.style.cssText = "position:absolute;inset:0";
    const deck = v.querySelector("#deck");
    deck.addEventListener("click", drawCard);
    deck.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); drawCard(); } });
    bindReveal(v);
    if (auto) setTimeout(drawCard, 250);
  }

  function drawCard() {
    if (drawing) return;
    drawing = true;
    const stage = document.getElementById("stage");
    const deck = document.getElementById("deck");
    const drawn = document.getElementById("drawn");
    const reveal = document.getElementById("reveal");
    // reset (for redraws)
    stage.classList.remove("revealed");
    drawn.classList.remove("show", "grow", "flipped");
    reveal.innerHTML = "";
    let pool = DATA;
    if (lastDrawn) pool = DATA.filter(d => d.id !== lastDrawn);
    const pick = pool[Math.floor(Math.random() * pool.length)];
    lastDrawn = pick.id;
    const drawnImg = document.getElementById("drawnImg");
    drawnImg.src = pick.illu;
    drawnImg.alt = `${pick.cn} 手绘插画`;

    void drawn.offsetWidth;
    stage.classList.add("drawing");
    deck.classList.add("spent");
    requestAnimationFrame(() => {
      drawn.classList.add("show");
      requestAnimationFrame(() => drawn.classList.add("grow"));
    });
    setTimeout(() => drawn.classList.add("flipped"), 880);
    setTimeout(() => {
      reveal.innerHTML = `
        <div class="en">${pick.en}</div>
        <div class="cn">${pick.cn}</div>
        <div class="tags">${(pick.flavorTags || []).slice(0, 4).map(t => `<span class="tag">${t}</span>`).join("")}</div>
        <div class="bb-actions">
          <a class="btn btn-primary" href="#/cocktail/${pick.id}" data-link>查看这一杯</a>
          <button class="btn btn-ghost" id="redraw">再抽一张</button>
        </div>`;
      stage.classList.add("revealed");
      const rd = document.getElementById("redraw");
      rd && rd.addEventListener("click", () => {
        deck.classList.remove("spent");
        stage.classList.remove("drawing");
        drawing = false;
        setTimeout(drawCard, 80);
      });
      drawing = false;
    }, 1780);
  }

  /* ---------------- MENU ---------------- */
  let activeFilter = "all";
  function viewMenu() {
    const v = h("section", { class: "view view-wide" });
    v.appendChild(frag(`
      <div class="menu-head rise">
        <span class="kicker both">THE MENU</span>
        <h1 class="menu-title">酒单 · 二十味</h1>
        <p class="menu-sub">手绘成卡的经典，点一张，读它的来路与做法。</p>
      </div>
      <div class="filters" id="filters">
        ${FAMILIES.map(([k, l]) => `<button class="chip ${k === activeFilter ? "active" : ""}" data-fam="${k}">${l}</button>`).join("")}
      </div>
      <div class="grid" id="grid"></div>
    `));
    app.appendChild(v);
    const grid = v.querySelector("#grid");
    renderTiles(grid);
    v.querySelector("#filters").addEventListener("click", e => {
      const b = e.target.closest(".chip"); if (!b) return;
      activeFilter = b.dataset.fam;
      v.querySelectorAll(".chip").forEach(c => c.classList.toggle("active", c.dataset.fam === activeFilter));
      renderTiles(grid);
    });
  }
  function renderTiles(grid) {
    const list = activeFilter === "all" ? DATA : DATA.filter(d => d.family === activeFilter);
    grid.innerHTML = "";
    list.forEach((d, i) => {
      const tile = h("a", { class: "tile rise", href: `#/cocktail/${d.id}`, "data-link": "", style: `animation-delay:${Math.min(i * 0.045, .5)}s` });
      tile.appendChild(frag(`
        <div class="tile-art">
          <span class="tile-no">No.${String(d.index).padStart(2, "0")}</span>
          <span class="tile-fam">${d.base}</span>
          <img src="${d.illu}" alt="${d.cn} 手绘插画" loading="lazy">
        </div>
        <div class="tile-body">
          <div class="tile-en">${d.en}</div>
          <div class="tile-cn">${d.cn}</div>
          <div class="tile-tags">${(d.flavorTags || []).slice(0, 3).map(t => `<span class="tile-tag">${t}</span>`).join("")}</div>
          <div class="tile-strength">${dots(d.strength)}</div>
        </div>`));
      grid.appendChild(tile);
    });
  }

  /* ---------------- DETAIL ---------------- */
  function viewDetail(id) {
    const d = byId[id];
    if (!d) { location.hash = "#/menu"; return; }
    const idx = DATA.findIndex(x => x.id === id);
    const prev = DATA[(idx - 1 + DATA.length) % DATA.length];
    const next = DATA[(idx + 1) % DATA.length];
    const v = h("section", { class: "view view-wide" });
    v.appendChild(frag(`
      <div class="detail-top rise">
        <a class="back-link" href="#/menu" data-link>← 返回酒单</a>
        <div class="detail-nav">
          <a class="dnav" href="#/cocktail/${prev.id}" data-link title="${prev.cn}">‹</a>
          <a class="dnav" href="#/cocktail/${next.id}" data-link title="${next.cn}">›</a>
        </div>
      </div>
      <div class="detail">
        <div class="detail-art rise" style="animation-delay:.06s">
          <div class="card-frame illu-frame" id="frame"><img src="${d.illu}" alt="${d.cn} 手绘插画"></div>
          <div class="art-cap">No.${String(d.index).padStart(2, "0")} · 重绘插画 · SOING</div>
        </div>
        <div class="detail-info">
          <div class="detail-head rise" style="animation-delay:.12s">
            <div class="kicker">${d.familyLabel} · ${d.method}</div>
            <div class="en">${d.en}</div>
            <div class="cn">${d.cn}</div>
            ${d.tagline ? `<div class="tagline">「${d.tagline}」</div>` : ""}
          </div>
          <div class="flavor-row rise" style="animation-delay:.18s">
            ${(d.flavorTags || []).map(t => `<span class="tag">${t}</span>`).join("")}
          </div>
          <div class="meta-grid rise" style="animation-delay:.22s">
            ${metaCell("酒精", d.abv)}
            ${metaCell("酒体", `<span class="strength-cell">${dots(d.strength)}</span>`, true)}
            ${metaCell("杯型", d.glass)}
            ${metaCell("手法", d.method)}
            ${metaCell("耗时", d.prepTime)}
            ${metaCell("适饮", d.bestTime)}
          </div>

          <div class="sec rise">
            <div class="sec-h"><span class="cnh">故事</span> the story</div>
            ${(d.story || "").split(/\n\n+/).map(p => `<p class="story-p">${p}</p>`).join("")}
          </div>

          <div class="sec rise">
            <div class="sec-h"><span class="cnh">材料</span> ingredients</div>
            <ul class="ing-list">
              ${d.ingredients.map(ig => `<li><span class="nm">${ig.name}</span><span class="leader"></span><span class="amt">${ig.amount}</span></li>`).join("")}
            </ul>
          </div>

          <div class="sec rise">
            <div class="sec-h"><span class="cnh">做法</span> method</div>
            <ol class="steps">${d.steps.map(s => `<li>${s}</li>`).join("")}</ol>
          </div>

          <div class="sec rise">
            <div class="sec-h"><span class="cnh">点缀 · 笔记</span> garnish &amp; notes</div>
            <ul class="ing-list" style="margin-bottom:1rem">
              <li><span class="nm">装饰</span><span class="leader"></span><span class="amt" style="font-style:normal;font-family:var(--han);color:var(--paper)">${d.garnish || "—"}</span></li>
              <li><span class="nm">香气</span><span class="leader"></span><span class="amt" style="font-style:normal;font-family:var(--han);color:var(--cream-dim);max-width:60%;text-align:right;white-space:normal">${d.aroma || "—"}</span></li>
              <li><span class="nm">口感</span><span class="leader"></span><span class="amt" style="font-style:normal;font-family:var(--han);color:var(--cream-dim);max-width:60%;text-align:right;white-space:normal">${d.palate || "—"}</span></li>
            </ul>
            <div class="note-card"><span class="ql">“</span><p>${d.note || ""}</p></div>
            ${d.imagePrompt ? `<details class="imgprompt">
              <summary>配图提示词 · 用 ChatGPT / DALL·E 生成原料配图</summary>
              <p id="ip">${d.imagePrompt}</p>
              <button class="copy" data-copy="ip">复制提示词</button>
            </details>` : ""}
          </div>
        </div>
      </div>
    `));
    app.appendChild(v);
    bindReveal(v);
    tiltCard(v.querySelector("#frame"));
    const copyBtn = v.querySelector(".copy");
    if (copyBtn) copyBtn.addEventListener("click", () => {
      const txt = v.querySelector("#" + copyBtn.dataset.copy).textContent;
      navigator.clipboard && navigator.clipboard.writeText(txt);
      copyBtn.textContent = "已复制 ✓";
      setTimeout(() => copyBtn.textContent = "复制提示词", 1600);
    });
  }
  const metaCell = (k, v, raw) => `<div class="meta-cell"><div class="k">${k}</div><div class="v">${raw ? v : (v || "—")}</div></div>`;

  function tiltCard(frame) {
    if (!frame || matchMedia("(prefers-reduced-motion:reduce)").matches) return;
    const card = frame;
    frame.parentElement.addEventListener("mousemove", e => {
      const r = card.getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width - 0.5;
      const py = (e.clientY - r.top) / r.height - 0.5;
      card.style.transform = `perspective(1000px) rotateY(${px * 5}deg) rotateX(${-py * 5}deg)`;
    });
    frame.parentElement.addEventListener("mouseleave", () => card.style.transform = "");
  }

  /* ---------------- ABOUT ---------------- */
  function viewAbout() {
    const v = h("section", { class: "view" });
    v.appendChild(frag(`
      <div class="about rise">
        <span class="kicker both">ABOUT</span>
        <h1 class="menu-title" style="margin-top:.6rem">关于这册酒谱</h1>
        <p class="big">二十张手绘鸡尾酒卡，一次重新装订。</p>
        <p>起点是二十张实体卡片——牛皮纸的底色，暗红的花体名，每一张都配着一杯水彩手绘的酒。我们把卡面一张张校正、提炼，连同原料、配比与做法，重新收进这册可以抽签、也可以慢慢翻阅的线上酒谱。</p>
        <div class="about-stats">
          <div><div class="n">20</div><div class="l">手绘酒卡</div></div>
          <div><div class="n">8</div><div class="l">基酒门类</div></div>
          <div><div class="n">∞</div><div class="l">今夜可能</div></div>
        </div>
        <p>手绘原卡来自品牌 <strong style="color:var(--gold)">SOING</strong>。文字内容据卡面提炼并补全背景故事，仅供学习与佐酒消遣之用。</p>
        <p style="color:var(--cream-faint);font-size:.92rem;margin-top:2rem">未满法定饮酒年龄者请勿饮酒 · 请适量 · DRINK RESPONSIBLY</p>
        <div class="hero-cta" style="justify-content:center;margin-top:2rem">
          <a class="btn btn-primary" href="#/blindbox" data-link>抽一杯试试</a>
          <a class="btn btn-ghost" href="#/menu" data-link>翻开酒单</a>
        </div>
      </div>
    `));
    app.appendChild(v);
    bindReveal(v);
  }

  /* ---------------- utils ---------------- */
  function shuffle(a) { for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1));[a[i], a[j]] = [a[j], a[i]]; } return a; }
  function bindReveal(scope) {
    // All .rise elements animate on mount via CSS and always end visible.
    // For elements far below the fold we add a small scroll-staggered delay so
    // the entrance is seen on scroll — without ever risking hidden content.
    if (matchMedia("(prefers-reduced-motion:reduce)").matches) return;
    if (!("IntersectionObserver" in window)) return;
    scope.querySelectorAll(".rise").forEach(el => {
      const r = el.getBoundingClientRect();
      if (r.top > window.innerHeight + 80 && !el.style.animationDelay) {
        el.classList.remove("rise");           // hold it
        el.dataset.reveal = "1";
        el.style.opacity = "0";
      }
    });
    const io = new IntersectionObserver(ents => {
      ents.forEach(en => {
        if (en.isIntersecting) {
          const el = en.target; el.style.opacity = "";
          el.classList.add("rise"); io.unobserve(el);
        }
      });
    }, { threshold: 0.04, rootMargin: "0px 0px -6% 0px" });
    scope.querySelectorAll('[data-reveal="1"]').forEach(el => io.observe(el));
  }
  function onScroll() { document.getElementById("topbar").classList.toggle("scrolled", window.scrollY > 30); }

  window.addEventListener("hashchange", router);
  window.addEventListener("scroll", onScroll, { passive: true });
  document.addEventListener("DOMContentLoaded", () => { router(); onScroll(); });
  if (document.readyState !== "loading") { router(); onScroll(); }
})();
