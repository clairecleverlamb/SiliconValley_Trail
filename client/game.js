const API = "/api/games";

/** Remembered between sessions for save / load prompts (not secret). */
const LS_LAST_SAVE_NAME = "svtLastSaveName";

/** Set from POST /api/games; required for all other game calls. */
let currentGameId = null;

const SAVE_ID_UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** @type {{ allowEmpty: boolean } | null} */
let _ioPromptConfig = null;
/** @type {((v: { cancelled: boolean; value: string }) => void) | null} */
let _ioPromptResolve = null;

/**
 * Styled in-page prompt (not window.prompt — avoids “127.0.0.1 says” browser chrome).
 * @param {{ title: string; description: string; label: string; defaultValue?: string; allowEmpty: boolean; confirmLabel: string }} config
 */
function openTextPromptModal(config) {
  return new Promise((resolve) => {
    _ioPromptConfig = config;
    _ioPromptResolve = resolve;

    const modal = document.getElementById("io-prompt-modal");
    const heading = document.getElementById("io-prompt-heading");
    const desc = document.getElementById("io-prompt-desc");
    const label = document.getElementById("io-prompt-label");
    const input = document.getElementById("io-prompt-input");
    const hint = document.getElementById("io-prompt-hint");
    const confirmBtn = document.getElementById("io-prompt-confirm");
    if (!modal || !heading || !desc || !label || !input || !hint || !confirmBtn) {
      resolve({ cancelled: true, value: "" });
      return;
    }

    heading.textContent = config.title;
    desc.textContent = config.description;
    label.textContent = config.label;
    input.value = config.defaultValue || "";
    confirmBtn.textContent = config.confirmLabel;
    hint.textContent = "";
    hint.classList.add("hidden");

    modal.classList.remove("hidden");
    requestAnimationFrame(() => {
      input.focus();
      input.select();
    });
  });
}

function finishIoPrompt(cancelled, value) {
  if (!_ioPromptResolve) return;
  const resolve = _ioPromptResolve;
  _ioPromptResolve = null;
  _ioPromptConfig = null;
  document.getElementById("io-prompt-modal")?.classList.add("hidden");
  resolve({ cancelled, value: value ?? "" });
}

function initIoPromptModal() {
  const modal = document.getElementById("io-prompt-modal");
  const input = document.getElementById("io-prompt-input");
  const hint = document.getElementById("io-prompt-hint");
  const cancelBtn = document.getElementById("io-prompt-cancel");
  const confirmBtn = document.getElementById("io-prompt-confirm");
  if (!modal || !input || !hint || !cancelBtn || !confirmBtn) return;

  cancelBtn.addEventListener("click", () => finishIoPrompt(true, ""));
  confirmBtn.addEventListener("click", () => {
    const v = input.value;
    if (_ioPromptConfig && !_ioPromptConfig.allowEmpty && !v.trim()) {
      hint.textContent = "Enter your save name.";
      hint.classList.remove("hidden");
      return;
    }
    finishIoPrompt(false, v);
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      confirmBtn.click();
    }
  });
  modal.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      e.preventDefault();
      finishIoPrompt(true, "");
    }
  });
  modal.addEventListener("click", (e) => {
    if (e.target === modal) finishIoPrompt(true, "");
  });
}

/** Event narrative text to prepend when a bonus minigame finishes (server only returns bonus outcome on POST). */
let pendingEventOutcomeForBonus = null;

/** Fired after event resolution so the outcome banner is readable before the bonus modal. */
let bonusMinigameScheduleId = null;

const BONUS_MODAL_DELAY_MS = 450;
const MINIGAME_OUTCOME_MS = 1700;

const LOCATIONS = [
  { name: "San Jose", abbr: "SJ", description: "Your startup's humble garage HQ" },
  { name: "Santa Clara", abbr: "SC", description: "Home of tech giants" },
  { name: "Sunnyvale", abbr: "SV", description: "Where the sun always shines on semiconductors" },
  { name: "Cupertino", abbr: "CP", description: "One Infinite Loop territory" },
  { name: "Mountain View", abbr: "MV", description: "Googleplex energy" },
  { name: "Palo Alto", abbr: "PA", description: "Sand Hill Road VC territory" },
  { name: "Menlo Park", abbr: "MP", description: "Meta HQ and quiet money" },
  { name: "Redwood City", abbr: "RC", description: "The unglamorous middle" },
  { name: "San Mateo", abbr: "SM", description: "Almost there, almost broke" },
  { name: "San Francisco", abbr: "SF", description: "DESTINATION — pitch Series A" },
];

const INTRO_PARAGRAPHS = [
  "202X: you’re in a San Jose garage; reach San Francisco before your day limit and keep the company alive.",
  "Track cash, morale, coffee, hype, and bugs. Travel, rest, pitch VCs, market, buy supplies, or hackathon—each uses one day and triggers daily bills plus a little coffee drain and bug creep.",
  "Traveling to a new city usually opens a short event—pick a choice, then sometimes a quick bonus game (mining, typing, or bean hunt). First event always gets a bonus; wins and losses are labeled in the report.",
  "You lose if time runs out, cash or morale hit zero, bugs go past the limit, or you end three turns in a row with no coffee. Good luck.",
];

const TURN_ACTIONS = [
  {
    id: "travel",
    label: "Travel — next city ($1,500 + morale hit, weather may add cost)",
  },
  { id: "rest", label: "Rest — morale up, coffee down, bugs creep (no free lunch)" },
  {
    id: "hackathon",
    label: "Hackathon — big bug cleanup + hype (costs morale & coffee)",
  },
  { id: "pitch_vc", label: "Pitch a VC — Zoom or room, anywhere on the trail" },
  { id: "marketing_push", label: "Marketing push — cash for hype & visibility" },
  { id: "buy_supplies", label: "Buy supplies — coffee & morale (costs cash)" },
];

const MINING_TARGET = 12;
const MINING_DURATION_SEC = 9;

const TYPING_TARGET = "COFFEECOFFEECOFFEE";
const TYPING_DURATION_SEC = 7;

const COFFEE_HUNT_GOAL = 7;
const COFFEE_HUNT_DURATION_SEC = 18;

let loading = false;
let miningTimerId = null;
let miningSpawnId = null;
let miningActive = false;
let miningCollected = 0;
let miningTimeLeft = MINING_DURATION_SEC;

let typingActive = false;
/** @type {"off" | "ready" | "run"} */
let typingPhase = "off";
let typingTimerId = null;
let typingTimeLeft = TYPING_DURATION_SEC;
/** @type {((e: Event) => void) | null} */
let typingInputHandler = null;

let coffeeHuntActive = false;
let coffeeHuntRafId = null;
let coffeeHuntTimerId = null;
/** @type {((e: KeyboardEvent) => void) | null} */
let coffeeHuntKeyDown = null;
/** @type {((e: KeyboardEvent) => void) | null} */
let coffeeHuntKeyUp = null;

function isMinigameActive() {
  return miningActive || typingPhase !== "off" || coffeeHuntActive;
}

function setLoading(isLoading) {
  loading = isLoading;
  document.querySelectorAll("button").forEach((btn) => {
    if (isMinigameActive() && btn.closest(".minigame-modal")) return;
    if (isLoading) btn.setAttribute("disabled", "disabled");
    else btn.removeAttribute("disabled");
  });
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function runIntroTypewriter() {
  const overlay = document.getElementById("intro-overlay");
  const el = document.getElementById("intro-text");
  const btn = document.getElementById("intro-continue");
  const skipBtn = document.getElementById("intro-skip");
  overlay.classList.remove("hidden");
  btn.classList.add("hidden");
  el.textContent = "";
  el.classList.remove("done");

  let introSkipRequested = false;

  const closeIntro = () => {
    overlay.classList.add("hidden");
    btn.classList.add("hidden");
    btn.onclick = null;
    if (skipBtn) skipBtn.onclick = null;
  };

  return new Promise((resolve) => {
    const finish = () => {
      closeIntro();
      resolve();
    };

    if (skipBtn) {
      skipBtn.onclick = () => {
        introSkipRequested = true;
        el.textContent = INTRO_PARAGRAPHS.join("\n\n");
        el.classList.add("done");
        finish();
      };
    }

    (async () => {
      outer: for (let p = 0; p < INTRO_PARAGRAPHS.length; p++) {
        const prefix = p > 0 ? "\n\n" : "";
        const chunk = prefix + INTRO_PARAGRAPHS[p];
        for (let i = 0; i < chunk.length; i++) {
          if (introSkipRequested) break outer;
          el.textContent += chunk[i];
          await sleep(16);
        }
      }
      if (introSkipRequested) return;
      el.classList.add("done");
      btn.classList.remove("hidden");
      btn.onclick = () => finish();
    })();
  });
}

async function apiRequest(method, path, body, options = {}) {
  const silent = options.silent === true;
  if (!silent) setLoading(true);
  try {
    const opts = { method, headers: {} };
    if (body !== undefined && body !== null) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const url = path === "" ? API : `${API}${path}`;
    const res = await fetch(url, opts);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      if (res.status === 404 && path !== "") {
        currentGameId = null;
        document.getElementById("game-screen")?.classList.add("hidden");
        document.getElementById("end-screen")?.classList.add("hidden");
        document.getElementById("splash-screen")?.classList.remove("hidden");
        setAppMode(null);
        throw new Error(
          "This game no longer exists on the server (often after restarting Flask). Click START VOYAGE again, or Load a saved file."
        );
      }
      const err = data.error || res.statusText;
      throw new Error(err);
    }
    return data;
  } finally {
    if (!silent) setLoading(false);
  }
}

function cancelScheduledBonusMinigame() {
  if (bonusMinigameScheduleId != null) {
    clearTimeout(bonusMinigameScheduleId);
    bonusMinigameScheduleId = null;
  }
}

/** Re-check server (player may have acted during the delay) before opening a modal. */
async function openBonusMinigameIfStillEligible() {
  if (!currentGameId) return;
  try {
    const live = await apiRequest("GET", `/${currentGameId}`, null, { silent: true });
    if (live.status !== "playing" || !live.mining_eligible) {
      pendingEventOutcomeForBonus = null;
      return;
    }
    const kind = live.minigame_type || "mining";
    startBonusMinigame({ ...live, minigame_type: kind });
  } catch {
    pendingEventOutcomeForBonus = null;
  }
}

function scheduleBonusMinigame() {
  cancelScheduledBonusMinigame();
  bonusMinigameScheduleId = window.setTimeout(() => {
    bonusMinigameScheduleId = null;
    void openBonusMinigameIfStillEligible();
  }, BONUS_MODAL_DELAY_MS);
}

function pctProgress(idx) {
  return Math.round((Math.min(idx, 9) / 9) * 100);
}

/** CSS classes for supply cells when close to lose thresholds (matches server conditions). */
function supplyCellClass(stat, r, state) {
  const base = "supply-cell";
  const cash = Number(r.cash ?? 0);
  const morale = Number(r.morale ?? 0);
  const coffee = Number(r.coffee ?? 0);
  const bugs = Number(r.bugs ?? 0);
  const coffeeEmergency = Number(state.coffee_emergency_turns ?? 0);

  if (stat === "cash") {
    if (cash <= 1000) return `${base} supply-cell--danger`;
    if (cash <= 5000) return `${base} supply-cell--warn`;
  }
  if (stat === "morale") {
    if (morale <= 5) return `${base} supply-cell--danger`;
    if (morale <= 20) return `${base} supply-cell--warn`;
  }
  if (stat === "coffee") {
    if (coffeeEmergency >= 1 || coffee <= 0) return `${base} supply-cell--danger`;
    if (coffee <= 10) return `${base} supply-cell--warn`;
  }
  if (stat === "bugs") {
    if (bugs >= 17) return `${base} supply-cell--danger`;
    if (bugs >= 12) return `${base} supply-cell--warn`;
  }
  return base;
}

function coffeeCellTooltip(r, state) {
  const c = Number(r.coffee ?? 0);
  const em = Number(state.coffee_emergency_turns ?? 0);
  if (c > 0) return "";
  if (em >= 2) return "Still no coffee — next end-of-turn at 0 and everyone quits.";
  if (em >= 1) {
    return "No coffee — use Buy supplies ($1,500+) or rest. You lose after 3 end-of-turn snapshots in a row at 0 coffee.";
  }
  return "";
}

function renderCoffeeCrisis(state) {
  const el = document.getElementById("coffee-crisis-note");
  if (!el) return;
  if (state.status !== "playing" || state.current_event) {
    el.hidden = true;
    el.textContent = "";
    return;
  }
  const r = state.resources || {};
  const coffee = Number(r.coffee ?? 0);
  const cash = Number(r.cash ?? 0);
  if (coffee > 0) {
    el.hidden = true;
    el.textContent = "";
    return;
  }
  el.hidden = false;
  if (cash >= 1500) {
    el.textContent =
      "You’re out of coffee. Choose Buy supplies below to restock (+20 coffee, −$1,500), or Rest for morale — you lose only if you end 3 turns in a row with no coffee.";
  } else {
    el.textContent =
      "You’re out of coffee and can’t afford supplies yet ($1,500 needed). Rest, earn cash, or travel — avoid ending three turns in a row at 0 coffee.";
  }
}

function renderSupplyTips(state) {
  const el = document.getElementById("supply-tips");
  if (!el) return;
  if (state.status !== "playing") {
    el.innerHTML = "";
    el.hidden = true;
    return;
  }
  el.hidden = false;
  const r = state.resources || {};
  const bugs = Number(r.bugs ?? 0);
  const cash = Number(r.cash ?? 0);
  const morale = Number(r.morale ?? 0);
  const coffee = Number(r.coffee ?? 0);
  const coffeeEmergency = Number(state.coffee_emergency_turns ?? 0);
  const maxDays = state.max_days ?? 20;
  const dayNum = state.day ?? 1;
  const daysLeft = maxDays - dayNum;

  const alerts = [];
  if (bugs >= 17) {
    alerts.push("Bugs are critical — above 20 bugs ends the run (game over).");
  } else if (bugs >= 12) {
    alerts.push("Bugs are stacking — you’re closing in on the technical-debt limit.");
  }
  if (cash <= 5000 && cash > 0) {
    alerts.push("Cash is low — at $0 you run out of funding.");
  }
  if (morale <= 20 && morale > 0) {
    alerts.push("Morale is shaky — at 0 the team quits.");
  }
  if ((coffee <= 10 && coffee > 0) || (coffee <= 0 && coffeeEmergency >= 1)) {
    alerts.push(
      "Coffee crisis — end three turns in a row with no coffee and everyone quits. Buy supplies or rest."
    );
  }
  if (daysLeft <= 7 && daysLeft >= 0) {
    alerts.push(`About ${daysLeft} full day(s) left on the calendar before time runs out.`);
  }

  const alertBlock =
    alerts.length > 0
      ? `<div class="supply-tips__alerts" role="status">${alerts.map((t) => `<p class="supply-tips__alert">${t}</p>`).join("")}</div>`
      : "";

  el.innerHTML = `
    <div class="supply-tips__box">
      <div class="supply-tips__heading">Game over if any of these happen</div>
      <ul class="supply-tips__list">
        <li><span class="supply-tips__stat">Cash</span> ≤ $0 — <span class="supply-tips__msg">You ran out of funding. Startup dead.</span></li>
        <li><span class="supply-tips__stat">Morale</span> = 0 — <span class="supply-tips__msg">Team quit. Morale collapsed.</span></li>
        <li><span class="supply-tips__stat">Coffee</span> = 0 at <strong>end of turn</strong>, <strong>3 times in a row</strong> — <span class="supply-tips__msg">No coffee for 3 turns in a row. Everyone quit.</span></li>
        <li><span class="supply-tips__stat">Bugs</span> &gt; 20 — <span class="supply-tips__msg">Technical debt buried you. App crashed.</span></li>
        <li><span class="supply-tips__stat">Calendar</span> passes your day limit — <span class="supply-tips__msg">Runway ran out before San Francisco.</span></li>
      </ul>
      ${alertBlock}
    </div>
  `;
}

function renderWeatherStrip(state) {
  const el = document.getElementById("weather-strip");
  const idx = state.current_location_index ?? 0;
  const city = LOCATIONS[idx]?.name || "Unknown";
  const cache = state.weather_cache || {};
  const w = cache[city] || { condition: "—", temp: "—" };
  el.textContent = `Weather: ${w.condition}, ${w.temp}°F · You are in ${city}`;
}

function weatherIconForCondition(conditionRaw) {
  const c = String(conditionRaw || "").toLowerCase();
  if (c.includes("thunder") || c.includes("rain") || c.includes("drizzle")) return "🌧️";
  if (c.includes("snow")) return "❄️";
  if (c.includes("mist") || c.includes("fog") || c.includes("haze")) return "🌫️";
  if (c === "clear" || c === "mainly clear") return "☀️";
  if (c.includes("cloud")) return "☁️";
  return "🌡️";
}

function renderHeaderWeather(state) {
  const wrap = document.getElementById("header-live-weather");
  const iconEl = document.getElementById("header-weather-icon");
  const txtEl = document.getElementById("header-weather-txt");
  if (!wrap || !iconEl || !txtEl) return;
  if (state.status !== "playing") {
    wrap.hidden = true;
    return;
  }
  const idx = state.current_location_index ?? 0;
  const city = LOCATIONS[idx]?.name;
  const w = city ? (state.weather_cache || {})[city] : null;
  if (!w || w.condition == null) {
    wrap.hidden = true;
    return;
  }
  wrap.hidden = false;
  const cond = w.condition ?? "—";
  iconEl.textContent = weatherIconForCondition(cond);
  const temp = w.temp != null && w.temp !== "" ? `${w.temp}°F` : "—";
  txtEl.textContent = `${cond} · ${temp}`;
  wrap.title = `Forecast for ${city} (Open-Meteo live forecast when online; set WEATHER_OFFLINE=1 or use fallback on errors — see README).`;
}

function renderTrail(state) {
  const track = document.getElementById("trail-track");
  const idx = state.current_location_index ?? 0;
  track.innerHTML = LOCATIONS.map((loc, i) => {
    let cls = "trail-stop";
    if (i < idx) cls += " trail-stop--past";
    else if (i === idx) cls += " trail-stop--here";
    else cls += " trail-stop--ahead";
    return `<div class="${cls}" title="${loc.name}">
      <span class="trail-stop__dot"></span>
      <span class="trail-stop__abbr">${loc.abbr}</span>
    </div>`;
  }).join("");
}

function renderResources(state) {
  const bar = document.getElementById("resource-bar");
  const r = state.resources || {};
  const idx = state.current_location_index ?? 0;
  const meta = LOCATIONS[idx] || { name: "—", description: "" };

  const maxDays = state.max_days ?? 20;
  const dayNum = state.day ?? 1;
  const dayPill = document.getElementById("header-day");
  dayPill.textContent = `Day ${dayNum} / ${maxDays}`;
  const daysRemaining = maxDays - dayNum;
  dayPill.classList.toggle("pill--warn", daysRemaining <= 5 && state.status === "playing");
  document.getElementById("header-location").textContent = meta.name;
  document.getElementById("game-subtitle").textContent = meta.description;
  renderHeaderWeather(state);

  renderSupplyTips(state);

  const cc = (k) => supplyCellClass(k, r, state);
  const cashN = Number(r.cash ?? 0);
  const moraleN = Number(r.morale ?? 0);
  const bugsVal = Number(r.bugs ?? 0);
  const bugsTitle =
    bugsVal >= 17 ? "Critical: more than 20 bugs ends the run." : bugsVal >= 12 ? "Warning: approaching 20 bugs." : "";

  bar.innerHTML = `
    <div class="${cc("cash")}" title="${cashN <= 5000 && cashN > 0 ? "Low cash — $0 means game over." : ""}"><span class="supply-cell__label">Cash</span><span class="supply-cell__value">${r.cash ?? 0}</span></div>
    <div class="${cc("morale")}" title="${moraleN <= 20 && moraleN > 0 ? "Low morale — 0 means game over." : ""}"><span class="supply-cell__label">Morale</span><span class="supply-cell__value">${r.morale ?? 0}</span></div>
    <div class="${cc("coffee")}" title="${coffeeCellTooltip(r, state)}"><span class="supply-cell__label">Coffee</span><span class="supply-cell__value">${r.coffee ?? 0}</span></div>
    <div class="supply-cell"><span class="supply-cell__label">Hype</span><span class="supply-cell__value">${r.hype ?? 0}</span></div>
    <div class="${cc("bugs")}" title="${bugsTitle}"><span class="supply-cell__label">Bugs</span><span class="supply-cell__value">${r.bugs ?? 0}</span></div>
    <div class="supply-cell"><span class="supply-cell__label">Trail</span><span class="supply-cell__value">${pctProgress(idx)}%</span></div>
  `;
}

function renderLog(state) {
  const ul = document.getElementById("log-list");
  ul.innerHTML = "";
  (state.log || []).forEach((line) => {
    const li = document.createElement("li");
    li.textContent = line;
    ul.appendChild(li);
  });
  ul.scrollTop = ul.scrollHeight;
}

function renderEvent(state) {
  const panel = document.getElementById("event-panel");
  const actionsPanel = document.getElementById("action-panel");
  const ev = state.current_event;
  if (ev && state.status === "playing") {
    panel.classList.remove("hidden");
    actionsPanel.classList.add("hidden");
    document.getElementById("event-title").textContent = ev.title || "Event";
    document.getElementById("event-desc").textContent = ev.description || "";
    const row = document.getElementById("event-choices");
    row.innerHTML = "";
    (ev.choices || []).slice(0, 3).forEach((ch, i) => {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "ot-btn";
      btn.dataset.choice = String(i + 1);
      btn.textContent = ch.label || "Choose";
      li.appendChild(btn);
      row.appendChild(li);
    });
  } else {
    panel.classList.add("hidden");
    actionsPanel.classList.remove("hidden");
  }
}

/** Turn raw outcome strings into short labeled sections (story vs daily burn vs bonus). */
function formatOutcomeBanner(raw) {
  if (!raw || typeof raw !== "string") return "";
  let bonus = "";
  let head = raw.trim();
  const bonusSep = "\n\n— Bonus round —\n";
  const bi = head.indexOf(bonusSep);
  if (bi >= 0) {
    bonus = head.slice(bi + bonusSep.length).trim();
    head = head.slice(0, bi).trim();
  } else {
    const alt = " — Bonus round — ";
    const j = head.indexOf(alt);
    if (j >= 0) {
      bonus = head.slice(j + alt.length).trim();
      head = head.slice(0, j).trim();
    }
  }

  const turnSep = " | Turn: ";
  const ti = head.indexOf(turnSep);
  let story = head;
  let daily = "";
  if (ti >= 0) {
    story = head.slice(0, ti).trim();
    daily = head.slice(ti + turnSep.length).trim();
  }

  const lines = [];
  if (story) {
    lines.push("Story result");
    lines.push(story);
    lines.push("");
  }
  if (daily) {
    lines.push("Daily upkeep (end of turn)");
    lines.push(daily);
    lines.push("");
  }
  if (bonus) {
    lines.push("Bonus round");
    lines.push(bonus);
  }
  return lines.join("\n").trim();
}

function renderOutcome(data) {
  const banner = document.getElementById("outcome-banner");
  if (data.outcome) {
    banner.textContent = formatOutcomeBanner(data.outcome);
    banner.classList.remove("narrative__box--empty");
  } else {
    banner.textContent = "";
    banner.classList.add("narrative__box--empty");
  }
}

function renderActionList(state) {
  const hint = document.getElementById("action-rules-hint");
  if (hint) {
    const overhead = state.daily_overhead_cash ?? 320;
    const cap = state.max_days ?? 20;
    hint.textContent = `Each command uses one day toward your ${cap}-day deadline. Every turn you also pay fixed daily bills (−$${overhead.toLocaleString()} cash) plus upkeep (−3 coffee, +1 bugs)—even if you only rest.`;
    hint.hidden = false;
  }
  const list = document.getElementById("action-list");
  list.innerHTML = "";
  TURN_ACTIONS.forEach((def) => {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ot-btn";
    btn.dataset.action = def.id;
    if (def.id === "pitch_vc") btn.id = "btn-pitch-vc";
    btn.textContent = def.label;
    li.appendChild(btn);
    list.appendChild(li);
  });
}

function applyActionButtonState(state) {
  const busy = loading || state.status !== "playing";
  const blocked = !!state.current_event;
  const idx = state.current_location_index ?? 0;
  const atEnd = idx >= 9;
  const coffee = Number(state.resources?.coffee ?? 0);
  const cash = Number(state.resources?.cash ?? 0);

  document.querySelectorAll("#action-list .ot-btn[data-action]").forEach((btn) => {
    const action = btn.dataset.action;
    let disabled = busy || blocked;
    if (action === "travel" && atEnd) disabled = true;
    if (action === "hackathon" && coffee < 10) disabled = true;
    if (action === "buy_supplies" && cash < 1500) disabled = true;
    btn.disabled = disabled;
    btn.classList.toggle(
      "ot-btn--urgent",
      action === "buy_supplies" && coffee === 0 && cash >= 1500 && !disabled
    );
    if (action === "hackathon" && coffee < 10) {
      btn.title = "Need at least 10 coffee — restock before a hackathon.";
    } else if (action === "buy_supplies" && cash < 1500) {
      btn.title = "Need $1,500 cash to buy supplies.";
    } else if (action === "buy_supplies" && coffee === 0 && cash >= 1500) {
      btn.title = "Restock coffee now.";
    } else {
      btn.title = "";
    }
  });

  document.querySelectorAll("#event-choices .ot-btn[data-choice]").forEach((btn) => {
    btn.disabled = busy || isMinigameActive();
  });
}

function setAppMode(mode) {
  const root = document.getElementById("app");
  root.classList.remove("app--playing", "app--end");
  if (mode === "playing") root.classList.add("app--playing");
  if (mode === "end") root.classList.add("app--end");
}

function showSection(status) {
  const splash = document.getElementById("splash-screen");
  const game = document.getElementById("game-screen");
  const end = document.getElementById("end-screen");
  splash.classList.add("hidden");
  game.classList.add("hidden");
  end.classList.add("hidden");
  if (status === "playing") {
    game.classList.remove("hidden");
    setAppMode("playing");
  } else if (status === "won" || status === "lost") {
    end.classList.remove("hidden");
    setAppMode("end");
  } else {
    splash.classList.remove("hidden");
    setAppMode(null);
  }
}

function renderEnd(state) {
  renderHeaderWeather(state);
  const msg = document.getElementById("end-message");
  const stats = document.getElementById("end-stats");
  const r = state.resources || {};
  if (state.status === "won") {
    msg.textContent = "You reached San Francisco!";
  } else {
    msg.textContent = `Game over — ${state.lost_reason || "Startup folded."}`;
  }
  stats.textContent = [
    `Day:        ${state.day ?? "—"} / ${state.max_days ?? "—"}`,
    `Cash:       ${r.cash ?? 0}`,
    `Morale:     ${r.morale ?? 0}`,
    `Coffee:     ${r.coffee ?? 0}`,
    `Hype:       ${r.hype ?? 0}`,
    `Bugs:       ${r.bugs ?? 0}`,
  ].join("\n");
}

/** Merge event narrative with the bonus-round outcome from the server (minigame POST only returns the latter). */
function withPendingEventOutcome(data) {
  if (!pendingEventOutcomeForBonus) return data;
  const bonus = (data.outcome || "").trim();
  const head = pendingEventOutcomeForBonus.trim();
  pendingEventOutcomeForBonus = null;
  const merged =
    bonus.length > 0 ? `${head}\n\n— Bonus round —\n${bonus}` : head;
  return { ...data, outcome: merged };
}

function renderFromServer(data) {
  if (!data || typeof data !== "object") return;
  if (data.game_id) currentGameId = data.game_id;
  renderOutcome(data);
  if (data.status === "playing") {
    showSection("playing");
    renderResources(data);
    renderTrail(data);
    renderWeatherStrip(data);
    renderLog(data);
    renderActionList(data);
    renderEvent(data);
    applyActionButtonState(data);
    renderCoffeeCrisis(data);
  } else if (data.status === "won" || data.status === "lost") {
    showSection(data.status);
    renderEnd(data);
  }
}

function updateMiningHud() {
  document.getElementById("mining-count").textContent = `Crystals: ${miningCollected} / ${MINING_TARGET}`;
  document.getElementById("mining-timer").textContent = `Time: ${miningTimeLeft}s`;
}

function clearMiningTimers() {
  if (miningTimerId) {
    clearInterval(miningTimerId);
    miningTimerId = null;
  }
  if (miningSpawnId) {
    clearInterval(miningSpawnId);
    miningSpawnId = null;
  }
}

function clearTypingTimers() {
  if (typingTimerId) {
    clearInterval(typingTimerId);
    typingTimerId = null;
  }
}

function updateTypingHud() {
  const input = document.getElementById("typing-input");
  const len =
    input && typingPhase === "run" && input instanceof HTMLInputElement ? input.value.length : 0;
  const prog = document.getElementById("typing-progress");
  const timerEl = document.getElementById("typing-timer");
  if (typingPhase === "ready") {
    prog.textContent = `Goal: ${TYPING_TARGET.length} characters (COFFEE × 3, no spaces)`;
    timerEl.textContent = "Press Start when you’re ready — the clock begins then.";
  } else {
    prog.textContent = `Progress: ${len} / ${TYPING_TARGET.length}`;
    timerEl.textContent = `Time: ${typingTimeLeft}s`;
  }
}

function spawnCrystal(field) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "mining-crystal";
  btn.setAttribute("aria-label", "Crystal");
  const pad = 8;
  const maxL = field.clientWidth - 28 - pad;
  const maxT = field.clientHeight - 28 - pad;
  btn.style.left = `${pad + Math.random() * maxL}px`;
  btn.style.top = `${pad + Math.random() * maxT}px`;
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    if (!miningActive) return;
    btn.remove();
    miningCollected += 1;
    updateMiningHud();
    if (miningCollected >= MINING_TARGET) {
      void finishMiningSession(true);
    }
  });
  field.appendChild(btn);
}

/** Brief win/lose message on the minigame panel before close + server sync. */
function showMinigameOutcomeThen(modalId, won, done) {
  const modal = document.getElementById(modalId);
  if (!modal) {
    done();
    return;
  }
  const panel = modal.querySelector(".mining-panel");
  if (!panel) {
    done();
    return;
  }
  let layer = panel.querySelector(".minigame-outcome");
  if (!layer) {
    layer = document.createElement("div");
    layer.className = "minigame-outcome hidden";
    layer.setAttribute("role", "status");
    panel.appendChild(layer);
  }
  layer.textContent = won ? "You won this bonus round." : "You lost this bonus round.";
  layer.classList.remove("hidden", "minigame-outcome--win", "minigame-outcome--lose");
  layer.classList.add(won ? "minigame-outcome--win" : "minigame-outcome--lose");
  window.setTimeout(() => {
    layer.classList.add("hidden");
    done();
  }, MINIGAME_OUTCOME_MS);
}

async function finishMiningSession(success) {
  if (!miningActive) return;
  miningActive = false;
  clearMiningTimers();
  document.getElementById("mining-field").innerHTML = "";
  showMinigameOutcomeThen("mining-modal", success, () => {
    void (async () => {
      document.getElementById("mining-modal").classList.add("hidden");
      if (!currentGameId) return;
      try {
        const data = await apiRequest("POST", `/${currentGameId}/minigames/mining`, { success });
        renderFromServer(withPendingEventOutcome(data));
      } catch (err) {
        pendingEventOutcomeForBonus = null;
        alert(err.message || String(err));
      }
    })();
  });
}

function handleTypingInput(e) {
  if (typingPhase !== "run") return;
  const el = e.target;
  if (!(el instanceof HTMLInputElement)) return;
  let v = el.value.toUpperCase();
  if (el.value !== v) el.value = v;
  v = el.value;
  if (!TYPING_TARGET.startsWith(v)) {
    el.value = "";
    v = "";
  }
  updateTypingHud();
  if (v === TYPING_TARGET) void finishTypingSession(true);
}

async function finishTypingSession(success) {
  if (typingPhase === "off") return;
  typingPhase = "off";
  typingActive = false;
  clearTypingTimers();
  const input = document.getElementById("typing-input");
  const startBtn = document.getElementById("typing-start");
  if (startBtn) startBtn.classList.remove("hidden");
  if (input instanceof HTMLInputElement) {
    if (typingInputHandler) {
      input.removeEventListener("input", typingInputHandler);
      typingInputHandler = null;
    }
    input.value = "";
    input.disabled = true;
    input.blur();
  }
  showMinigameOutcomeThen("typing-modal", success, () => {
    void (async () => {
      document.getElementById("typing-modal").classList.add("hidden");
      if (!currentGameId) return;
      try {
        const data = await apiRequest("POST", `/${currentGameId}/minigames/typing`, { success });
        renderFromServer(withPendingEventOutcome(data));
      } catch (err) {
        pendingEventOutcomeForBonus = null;
        alert(err.message || String(err));
      }
    })();
  });
}

function startBonusMinigame(data) {
  if (data.status !== "playing" || !data.mining_eligible) return;
  let kind = data.minigame_type || "mining";
  if (kind === "bug_squash") kind = "mining";
  if (kind === "typing") startTypingModal();
  else if (kind === "coffee_hunt") startCoffeeHuntModal();
  else startMiningModal();
}

function startMiningModal() {
  const modal = document.getElementById("mining-modal");
  const field = document.getElementById("mining-field");
  miningActive = true;
  miningCollected = 0;
  miningTimeLeft = MINING_DURATION_SEC;
  field.innerHTML = "";
  updateMiningHud();
  modal.classList.remove("hidden");
  spawnCrystal(field);
  miningSpawnId = setInterval(() => {
    if (!miningActive) return;
    if (field.querySelectorAll(".mining-crystal").length < 14) spawnCrystal(field);
  }, 380);
  miningTimerId = setInterval(() => {
    if (!miningActive) return;
    miningTimeLeft -= 1;
    updateMiningHud();
    if (miningTimeLeft <= 0) void finishMiningSession(false);
  }, 1000);
}

function beginTypingRound() {
  if (typingPhase !== "ready") return;
  typingPhase = "run";
  typingActive = true;
  typingTimeLeft = TYPING_DURATION_SEC;
  const input = document.getElementById("typing-input");
  const startBtn = document.getElementById("typing-start");
  if (startBtn) startBtn.classList.add("hidden");
  if (input instanceof HTMLInputElement) {
    input.disabled = false;
    input.value = "";
    if (!typingInputHandler) {
      typingInputHandler = handleTypingInput;
      input.addEventListener("input", typingInputHandler);
    }
    updateTypingHud();
    requestAnimationFrame(() => input.focus());
  }
  typingTimerId = setInterval(() => {
    if (typingPhase !== "run") return;
    typingTimeLeft -= 1;
    updateTypingHud();
    if (typingTimeLeft <= 0) void finishTypingSession(false);
  }, 1000);
}

function startTypingModal() {
  clearTypingTimers();
  typingPhase = "ready";
  typingActive = false;
  const modal = document.getElementById("typing-modal");
  const input = document.getElementById("typing-input");
  const startBtn = document.getElementById("typing-start");
  if (!(input instanceof HTMLInputElement)) return;
  if (typingInputHandler) input.removeEventListener("input", typingInputHandler);
  typingInputHandler = handleTypingInput;
  input.addEventListener("input", typingInputHandler);
  input.value = "";
  input.disabled = true;
  typingTimeLeft = TYPING_DURATION_SEC;
  if (startBtn) startBtn.classList.remove("hidden");
  updateTypingHud();
  modal.classList.remove("hidden");
  requestAnimationFrame(() => startBtn?.focus());
}

function clearCoffeeHuntSession() {
  if (coffeeHuntRafId != null) {
    cancelAnimationFrame(coffeeHuntRafId);
    coffeeHuntRafId = null;
  }
  if (coffeeHuntTimerId) {
    clearInterval(coffeeHuntTimerId);
    coffeeHuntTimerId = null;
  }
  if (coffeeHuntKeyDown) {
    window.removeEventListener("keydown", coffeeHuntKeyDown, true);
    coffeeHuntKeyDown = null;
  }
  if (coffeeHuntKeyUp) {
    window.removeEventListener("keyup", coffeeHuntKeyUp, true);
    coffeeHuntKeyUp = null;
  }
}

function updateCoffeeHuntHud(bagged, timeLeft) {
  const c = document.getElementById("coffee-hunt-count");
  const t = document.getElementById("coffee-hunt-timer");
  if (c) c.textContent = `Beans bagged: ${bagged} / ${COFFEE_HUNT_GOAL}`;
  if (t) t.textContent = `Time: ${timeLeft}s`;
}

function startCoffeeHuntModal() {
  clearCoffeeHuntSession();
  const modal = document.getElementById("coffee-hunt-modal");
  const canvas = document.getElementById("coffee-hunt-canvas");
  if (!modal || !canvas || !(canvas instanceof HTMLCanvasElement)) return;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  const W = 400;
  const H = 220;
  canvas.width = W;
  canvas.height = H;

  coffeeHuntActive = true;
  modal.classList.remove("hidden");

  let hits = 0;
  let timeLeft = COFFEE_HUNT_DURATION_SEC;
  let aim = -Math.PI / 2;
  const AIM_MIN = -Math.PI / 2 - 0.95;
  const AIM_MAX = -Math.PI / 2 + 0.95;
  /** @type {{ x: number; y: number; r: number; vx: number; vy: number }[]} */
  const beans = [];
  /** @type {{ x: number; y: number; vx: number; vy: number; life: number }[]} */
  const bullets = [];
  let lastShot = 0;
  const keys = { left: false, right: false };
  let spawnAcc = 0;
  let huntFinished = false;

  updateCoffeeHuntHud(hits, timeLeft);

  function spawnBean() {
    const edge = Math.floor(Math.random() * 4);
    let x;
    let y;
    let vx;
    let vy;
    const sp = 0.85 + Math.random() * 1.15;
    if (edge === 0) {
      x = -18;
      y = 28 + Math.random() * (H - 90);
      vx = sp;
      vy = (Math.random() - 0.5) * 0.85;
    } else if (edge === 1) {
      x = W + 18;
      y = 28 + Math.random() * (H - 90);
      vx = -sp;
      vy = (Math.random() - 0.5) * 0.85;
    } else if (edge === 2) {
      x = 36 + Math.random() * (W - 72);
      y = -18;
      vx = (Math.random() - 0.5) * 1.1;
      vy = sp;
    } else {
      x = 36 + Math.random() * (W - 72);
      y = H + 18;
      vx = (Math.random() - 0.5) * 1.1;
      vy = -sp * 0.65;
    }
    beans.push({ x, y, r: 13, vx, vy });
  }

  coffeeHuntTimerId = setInterval(() => {
    if (!coffeeHuntActive || huntFinished) return;
    timeLeft -= 1;
    updateCoffeeHuntHud(hits, timeLeft);
    if (timeLeft <= 0) {
      huntFinished = true;
      void finishCoffeeHuntSession(hits >= COFFEE_HUNT_GOAL);
    }
  }, 1000);

  function tryWin() {
    if (hits >= COFFEE_HUNT_GOAL && !huntFinished) {
      huntFinished = true;
      void finishCoffeeHuntSession(true);
    }
  }

  coffeeHuntKeyDown = (e) => {
    if (!coffeeHuntActive || huntFinished) return;
    if (e.code === "ArrowLeft") {
      keys.left = true;
      e.preventDefault();
    }
    if (e.code === "ArrowRight") {
      keys.right = true;
      e.preventDefault();
    }
    if (e.code === "Space") {
      e.preventDefault();
      const now = performance.now();
      if (now - lastShot < 260) return;
      lastShot = now;
      const px = W / 2;
      const py = H - 22;
      bullets.push({
        x: px + Math.cos(aim) * 34,
        y: py + Math.sin(aim) * 34,
        vx: Math.cos(aim) * 9,
        vy: Math.sin(aim) * 9,
        life: 48,
      });
    }
    if (e.code === "Escape") {
      e.preventDefault();
      huntFinished = true;
      void finishCoffeeHuntSession(false);
    }
  };

  coffeeHuntKeyUp = (e) => {
    if (e.code === "ArrowLeft") keys.left = false;
    if (e.code === "ArrowRight") keys.right = false;
  };
  window.addEventListener("keydown", coffeeHuntKeyDown, true);
  window.addEventListener("keyup", coffeeHuntKeyUp, true);

  function tick() {
    if (!coffeeHuntActive || huntFinished) return;

    if (keys.left) aim -= 0.085;
    if (keys.right) aim += 0.085;
    if (aim < AIM_MIN) aim = AIM_MIN;
    if (aim > AIM_MAX) aim = AIM_MAX;

    spawnAcc += 1;
    if (spawnAcc >= 48 && beans.length < 11) {
      spawnBean();
      spawnAcc = 0;
    }

    for (let i = beans.length - 1; i >= 0; i--) {
      const b = beans[i];
      b.x += b.vx;
      b.y += b.vy;
      if (b.x < -44 || b.x > W + 44 || b.y < -44 || b.y > H + 44) beans.splice(i, 1);
    }

    for (let i = bullets.length - 1; i >= 0; i--) {
      const u = bullets[i];
      u.x += u.vx;
      u.y += u.vy;
      u.life -= 1;
      if (u.life <= 0) bullets.splice(i, 1);
    }

    outer: for (let bi = bullets.length - 1; bi >= 0; bi--) {
      const u = bullets[bi];
      for (let j = beans.length - 1; j >= 0; j--) {
        const b = beans[j];
        const dx = u.x - b.x;
        const dy = u.y - b.y;
        if (dx * dx + dy * dy < (b.r + 4) * (b.r + 4)) {
          beans.splice(j, 1);
          bullets.splice(bi, 1);
          hits += 1;
          updateCoffeeHuntHud(hits, timeLeft);
          tryWin();
          break outer;
        }
      }
    }

    ctx.fillStyle = "#050806";
    ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = "rgba(35, 70, 42, 0.45)";
    for (let g = 0; g < 6; g++) {
      ctx.fillRect(12 + (g % 3) * 118, 36 + Math.floor(g / 3) * 72, 56, 18);
    }

    beans.forEach((b) => {
      ctx.fillStyle = "#5c3d22";
      ctx.beginPath();
      ctx.arc(b.x, b.y, b.r, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = "#8b5a2b";
      ctx.beginPath();
      ctx.arc(b.x - 3, b.y - 2, 4, 0, Math.PI * 2);
      ctx.fill();
    });

    const px = W / 2;
    const py = H - 22;
    ctx.strokeStyle = "#5cff8a";
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(px, py);
    ctx.lineTo(px + Math.cos(aim) * 38, py + Math.sin(aim) * 38);
    ctx.stroke();
    ctx.fillStyle = "#c8f5d4";
    ctx.fillRect(px - 7, py - 6, 14, 16);

    ctx.fillStyle = "#ffc14d";
    bullets.forEach((u) => {
      ctx.beginPath();
      ctx.arc(u.x, u.y, 3.5, 0, Math.PI * 2);
      ctx.fill();
    });

    coffeeHuntRafId = requestAnimationFrame(tick);
  }

  spawnBean();
  coffeeHuntRafId = requestAnimationFrame(tick);
}

async function finishCoffeeHuntSession(success) {
  if (!coffeeHuntActive) return;
  coffeeHuntActive = false;
  clearCoffeeHuntSession();
  showMinigameOutcomeThen("coffee-hunt-modal", success, () => {
    void (async () => {
      document.getElementById("coffee-hunt-modal")?.classList.add("hidden");
      if (!currentGameId) return;
      try {
        const data = await apiRequest("POST", `/${currentGameId}/minigames/coffee_hunt`, { success });
        renderFromServer(withPendingEventOutcome(data));
      } catch (err) {
        pendingEventOutcomeForBonus = null;
        alert(err.message || String(err));
      }
    })();
  });
}

/** Tell the server the bonus round failed and tear down UI — no win/lose splash delay (menu exit). */
async function closeActiveMinigameForMenuExit() {
  const gid = currentGameId;
  if (!gid) return;
  document.querySelectorAll(".minigame-outcome").forEach((el) => el.classList.add("hidden"));

  if (miningActive) {
    miningActive = false;
    clearMiningTimers();
    document.getElementById("mining-field").innerHTML = "";
    document.getElementById("mining-modal")?.classList.add("hidden");
    try {
      await apiRequest("POST", `/${gid}/minigames/mining`, { success: false }, { silent: true });
    } catch {
      /* ignore */
    }
    return;
  }

  if (typingPhase !== "off") {
    typingPhase = "off";
    typingActive = false;
    clearTypingTimers();
    const input = document.getElementById("typing-input");
    const startBtn = document.getElementById("typing-start");
    if (startBtn) startBtn.classList.remove("hidden");
    if (input instanceof HTMLInputElement) {
      if (typingInputHandler) {
        input.removeEventListener("input", typingInputHandler);
        typingInputHandler = null;
      }
      input.value = "";
      input.disabled = true;
      input.blur();
    }
    document.getElementById("typing-modal")?.classList.add("hidden");
    try {
      await apiRequest("POST", `/${gid}/minigames/typing`, { success: false }, { silent: true });
    } catch {
      /* ignore */
    }
    return;
  }

  if (coffeeHuntActive) {
    coffeeHuntActive = false;
    clearCoffeeHuntSession();
    document.getElementById("coffee-hunt-modal")?.classList.add("hidden");
    try {
      await apiRequest("POST", `/${gid}/minigames/coffee_hunt`, { success: false }, { silent: true });
    } catch {
      /* ignore */
    }
  }
}

async function returnToTitleScreen() {
  cancelScheduledBonusMinigame();
  pendingEventOutcomeForBonus = null;
  finishIoPrompt(true, "");
  if (currentGameId && isMinigameActive()) {
    await closeActiveMinigameForMenuExit();
  }
  currentGameId = null;
  showSection(null);
}

async function startVoyage() {
  cancelScheduledBonusMinigame();
  pendingEventOutcomeForBonus = null;
  try {
    const data = await apiRequest("POST", "", null);
    currentGameId = data.game_id;
    document.getElementById("splash-screen").classList.add("hidden");
    await runIntroTypewriter();
    renderFromServer(data);
  } catch (err) {
    alert(err.message || String(err));
    document.getElementById("splash-screen").classList.remove("hidden");
  }
}

async function loadGameFromTitleScreen(raw) {
  cancelScheduledBonusMinigame();
  pendingEventOutcomeForBonus = null;
  const id = raw.trim();
  let data;
  if (SAVE_ID_UUID_RE.test(id)) {
    data = await apiRequest("POST", `/${id}/loads`, null);
  } else {
    data = await apiRequest("POST", `/restore-save`, { save_name: id });
    try {
      localStorage.setItem(LS_LAST_SAVE_NAME, id);
    } catch {
      /* ignore quota / private mode */
    }
  }
  if (data.game_id) currentGameId = data.game_id;
  document.getElementById("splash-screen").classList.add("hidden");
  renderFromServer(data);
}

async function doAction(name) {
  if (!currentGameId) throw new Error("No active game");
  cancelScheduledBonusMinigame();
  pendingEventOutcomeForBonus = null;
  const data = await apiRequest("POST", `/${currentGameId}/moves`, { action: name });
  renderFromServer(data);
}

async function resolveEvent(choice) {
  if (!currentGameId) throw new Error("No active game");
  const data = await apiRequest("POST", `/${currentGameId}/events/choices`, { choice });
  if (data.status === "playing" && data.mining_eligible) {
    pendingEventOutcomeForBonus = data.outcome || "";
  } else {
    pendingEventOutcomeForBonus = null;
  }
  renderFromServer(data);
  if (data.status === "playing" && data.mining_eligible) {
    scheduleBonusMinigame();
  } else {
    cancelScheduledBonusMinigame();
  }
}

async function saveGame() {
  if (!currentGameId) throw new Error("No active game");
  let defaultName = "";
  try {
    defaultName = localStorage.getItem(LS_LAST_SAVE_NAME) || "";
  } catch {
    defaultName = "";
  }
  const result = await openTextPromptModal({
    title: "Save progress",
    description:
      "Pick a name you’ll remember — you’ll type that same name on the title screen to load this run.",
    label: "Save name",
    defaultValue: defaultName,
    allowEmpty: false,
    confirmLabel: "Save",
  });
  if (result.cancelled) return;
  const trimmed = result.value.trim();
  const data = await apiRequest("PUT", `/${currentGameId}/saves`, { save_name: trimmed });
  try {
    localStorage.setItem(LS_LAST_SAVE_NAME, trimmed);
  } catch {
    /* ignore */
  }
  renderFromServer(data);
}

document.body.addEventListener("click", async (e) => {
  const t = e.target instanceof HTMLElement ? e.target.closest("button, [data-action], [data-choice], [data-menu]") : null;
  if (!(t instanceof HTMLElement)) return;

  if (t.id === "btn-start-voyage") {
    e.preventDefault();
    await startVoyage();
  }
  if (t.dataset.menu === "load") {
    e.preventDefault();
    let hint = "";
    try {
      hint = localStorage.getItem(LS_LAST_SAVE_NAME) || "";
    } catch {
      hint = "";
    }
    try {
      const result = await openTextPromptModal({
        title: "Load saved game",
        description: "Enter the same save name you used when you clicked Save progress.",
        label: "Save name",
        defaultValue: hint,
        allowEmpty: false,
        confirmLabel: "Load",
      });
      if (result.cancelled) return;
      const id = result.value.trim();
      if (!id) return;
      await loadGameFromTitleScreen(id);
    } catch (err) {
      alert(err.message || String(err));
    }
  }
  if (t.dataset.action) {
    e.preventDefault();
    try {
      await doAction(t.dataset.action);
    } catch (err) {
      alert(err.message || String(err));
    }
  }
  if (t.dataset.choice) {
    e.preventDefault();
    try {
      await resolveEvent(Number(t.dataset.choice));
    } catch (err) {
      alert(err.message || String(err));
    }
  }
  if (t.id === "btn-save") {
    e.preventDefault();
    try {
      await saveGame();
    } catch (err) {
      alert(err.message || String(err));
    }
  }
  if (t.id === "btn-exit") {
    e.preventDefault();
    try {
      await returnToTitleScreen();
    } catch (err) {
      alert(err.message || String(err));
    }
  }
  if (t.id === "btn-play-again") {
    e.preventDefault();
    currentGameId = null;
    document.getElementById("end-screen").classList.add("hidden");
    document.getElementById("splash-screen").classList.remove("hidden");
    setAppMode(null);
  }
});

document.getElementById("mining-abort")?.addEventListener("click", () => {
  void finishMiningSession(false);
});

document.getElementById("typing-start")?.addEventListener("click", () => beginTypingRound());

document.getElementById("typing-abort")?.addEventListener("click", () => {
  void finishTypingSession(false);
});

document.getElementById("coffee-hunt-abort")?.addEventListener("click", () => {
  void finishCoffeeHuntSession(false);
});

document.addEventListener("DOMContentLoaded", () => {
  initIoPromptModal();
  showSection(null);
  const banner = document.getElementById("outcome-banner");
  if (banner) banner.classList.add("narrative__box--empty");
});
