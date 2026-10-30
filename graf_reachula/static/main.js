const SOUNDS = ["heartbeat", "ghost", "door", "wind", "bells", "laugh"];
const MOVES = ["scared", "startled", "laughing", "dying", "surprised", "shocked", "angry"];
const TOGGLES = ["scares", "ambient", "talk", "wake_word"];
const FIELDS = ["language", "llm_provider", "llm_model", "llm_api_key", "llm_base_url",
    "stt_provider", "stt_model", "stt_api_key", "stt_base_url"];

const $ = (id) => document.getElementById(id);

// The web server starts before the app's routes exist; retry until they answer
async function api(path, options = {}, tries = 30) {
    for (let i = 0; i < tries; i++) {
        try {
            const resp = await fetch(path, options);
            if (resp.ok) return await resp.json();
        } catch (e) { /* not ready yet */ }
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
    for (const f of FIELDS) $(f).value = settings[f] ?? "";
    let text = "The Count haunts silently (no talking).";
    if (settings.talking) text = "🧛 The Count is listening.";
    else if (settings.talk_error) text = "Talking failed: " + settings.talk_error;
    else if (settings.talk && !settings.can_talk) text = "Add a chat key and a speech-to-text key to make the Count talk.";
    $("status").textContent = text;
}

async function save(changes) {
    $("status").textContent = "Saving…";
    try {
        show(await api("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ changes }),
        }, 3));
    } catch (e) {
        $("status").textContent = e.message;
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
    if (b) api(`/api/play/${b.dataset.kind}/${b.dataset.name}`, { method: "POST" }, 3).catch(() => {});
});

for (const t of ["scares", "ambient", "wake_word", "talk"]) {
    $(t).addEventListener("change", () => save({ [t]: $(t).checked }));
}
$("language").addEventListener("change", () => save({ language: $("language").value }));
$("save").addEventListener("click", () => {
    const changes = {};
    for (const f of FIELDS) changes[f] = $(f).value.trim();
    save(changes);
});

api("/api/settings").then(show).catch((e) => { $("status").textContent = e.message; });
