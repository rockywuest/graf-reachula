const SOUNDS = ["heartbeat", "ghost", "door", "wind", "bells", "laugh"];
const MOVES = ["scared", "startled", "laughing", "dying", "surprised", "shocked", "angry"];
const TOGGLES = ["scares", "ambient", "talk", "wake_word"];
const FIELDS = ["language", "llm_provider", "llm_model", "llm_api_key", "llm_base_url",
    "stt_provider", "stt_model", "stt_api_key", "stt_base_url"];
const VOICE_FIELDS = ["tts_provider", "elevenlabs_api_key", "elevenlabs_voice", "elevenlabs_model"];

const $ = (id) => document.getElementById(id);

function pin() {
    return $("pin").value || "";
}

// HTTP headers carry only plain ASCII; anything else would break every request
const ascii = (value) => (/^[\x20-\x7e]*$/.test(value) ? value : "");

// The web server starts before the app's routes exist; retry until they answer
async function api(path, options = {}, tries = 30) {
    options.headers = { ...(options.headers || {}), "X-Graf-Reachula": "1",
        "X-Graf-Pin": ascii(pin()), "X-Graf-Setup": ascii($("setup_code").value.trim()) };
    for (let i = 0; i < tries; i++) {
        let resp = null;
        try {
            resp = await fetch(path, options);
        } catch (e) { /* not ready yet */ }
        if (resp && resp.ok) return await resp.json();
        if (resp && (resp.status === 400 || resp.status === 403 || resp.status === 429)) {
            // A refusal (wrong PIN, busy) won't change by retrying
            const body = await resp.json().catch(() => ({}));
            throw new Error(body.detail || "Refused");
        }
        await new Promise((r) => setTimeout(r, 1000));
    }
    throw new Error("The Count does not answer");
}

function fillSelect(id, values) {
    const select = $(id);
    if (select.options.length) return;
    for (const v of values) select.add(new Option(v, v));
}

function show(settings) {
    fillSelect("llm_provider", settings.llm_providers);
    fillSelect("stt_provider", settings.stt_providers);
    for (const t of TOGGLES) $(t).checked = !!settings[t];
    for (const f of [...FIELDS, ...VOICE_FIELDS]) $(f).value = settings[f] ?? "";
    $("pin-state").textContent = settings.pin_set
        ? "🔒 Locked: enter the PIN to change providers, keys or the voice."
        : "🔓 No PIN yet: set one first. Providers, keys and the voice unlock once a PIN exists.";
    $("setup").hidden = !!settings.pin_set;
    showStatus(settings);
}

// Status lines only: refreshed regularly without touching what the user is typing
function showStatus(settings) {
    let text = "The Count haunts with sounds and moves (talking is off).";
    if (settings.talking) text = "🧛 The Count is listening.";
    if (settings.talking && settings.listen_error) text = "⚠️ " + settings.listen_error;
    else if (settings.talk_error) text = "Talking failed: " + settings.talk_error;
    else if (settings.talk && !settings.can_talk) text = "Add a chat key and a speech-to-text key to make the Count talk.";
    $("status").textContent = text;
    $("voice-status").textContent = settings.voice_status ? "Current voice: " + settings.voice_status : "";
}

async function save(changes) {
    $("status").textContent = "Saving…";
    try {
        show(await api("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ changes }),
        }, 3));
        return true;
    } catch (e) {
        $("status").textContent = e.message;
        return false;
    }
}

function addButtons(id, kind, names) {
    for (const name of names) {
        const b = document.createElement("button");
        b.textContent = name;
        b.dataset.kind = kind;
        b.dataset.name = name;
        $(id).appendChild(b);
    }
}

addButtons("sound-buttons", "sound", SOUNDS);
addButtons("move-buttons", "move", MOVES);

document.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-kind]");
    if (b) api(`/api/play/${b.dataset.kind}/${b.dataset.name}`, { method: "POST" }, 1).catch(() => {});
});

for (const t of ["scares", "ambient", "wake_word", "talk"]) {
    $(t).addEventListener("change", () => save({ [t]: $(t).checked }));
}
$("language").addEventListener("change", () => save({ language: $("language").value }));
$("save-voice").addEventListener("click", () => {
    const changes = {};
    for (const f of VOICE_FIELDS) changes[f] = $(f).value.trim();
    save(changes);
});
$("save-pin").addEventListener("click", () => {
    const value = $("new_pin").value.trim();
    if (value && !ascii(value)) { $("status").textContent = "Use letters, digits and ASCII symbols only."; return; }
    if (value) save({ new_pin: value }).then((ok) => { if (ok) { $("pin").value = value; $("new_pin").value = ""; $("setup_code").value = ""; } });
});
$("save").addEventListener("click", () => {
    const changes = {};
    for (const f of FIELDS) changes[f] = $(f).value.trim();
    save(changes);
});

api("/api/settings").then(show).catch((e) => { $("status").textContent = e.message; });
setInterval(() => { api("/api/settings", {}, 1).then(showStatus).catch(() => {}); }, 10000);
