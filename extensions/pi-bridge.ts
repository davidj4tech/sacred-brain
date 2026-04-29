/**
 * sacred-brain-bridge: pi ↔ Memory Governor integration
 *
 * Sibling of the codex / opencode / claude-code bridges in /opt/sacred-brain.
 * Pi has a typed event API instead of a shell-hook config slot, so this is a
 * TypeScript extension rather than a launcher wrapper.
 *
 * Lifecycle wiring:
 *   session_start          → POST /recall, cache + write .agents/CONTEXT_MEMORY.md
 *   before_agent_start     → inject cached memory block into the system prompt
 *                            (every turn; stable text → prompt-cache friendly)
 *   session_before_compact → POST /observe with the to-be-summarised tail
 *                            (source: pi:precompact, capped at 0.35 salience)
 *   session_shutdown       → drain ~/.cache/sacred-brain/pi-pending-outcome.jsonl
 *
 * Env (loaded from process.env, then ~/.config/hippocampus.env, then
 * ~/.config/sacred-brain.env, in that order):
 *   GOVERNOR_URL       (default: http://127.0.0.1:54323; HIPPOCAMPUS_URL accepted as fallback)
 *   GOVERNOR_API_KEY   (HIPPOCAMPUS_API_KEY accepted as fallback)
 *   GOVERNOR_USER_ID   (HIPPOCAMPUS_USER_ID accepted; default: sam)
 *   PI_BRIDGE_K        (default: 20)
 *   PI_BRIDGE_INJECT   "0" disables system-prompt injection (default: enabled)
 *   PI_BRIDGE_DISABLE  "1" disables the whole bridge
 *
 * Logs to ~/.cache/sacred-brain/claude-bridge.log (shared bridge log).
 *
 * All operations swallow errors — bridge failure must never break a pi session.
 */

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { basename, dirname, join } from "node:path";
import { homedir } from "node:os";

// ---------- env -------------------------------------------------------------

function parseEnvFile(p: string): Record<string, string> {
	if (!existsSync(p)) return {};
	const out: Record<string, string> = {};
	let txt: string;
	try { txt = readFileSync(p, "utf8"); } catch { return {}; }
	for (const raw of txt.split(/\r?\n/)) {
		const line = raw.replace(/^\s*export\s+/, "").trim();
		if (!line || line.startsWith("#")) continue;
		const m = /^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/.exec(line);
		if (!m) continue;
		let v = m[2];
		if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) {
			v = v.slice(1, -1);
		}
		out[m[1]] = v;
	}
	return out;
}

const HOME = homedir();
const FILE_ENV: Record<string, string> = (() => {
	for (const f of [join(HOME, ".config/hippocampus.env"), join(HOME, ".config/sacred-brain.env")]) {
		if (existsSync(f)) return parseEnvFile(f);
	}
	return {};
})();

function envOf(...names: string[]): string {
	for (const n of names) {
		const v = process.env[n] ?? FILE_ENV[n];
		if (v) return v;
	}
	return "";
}

const GOVERNOR_URL = envOf("GOVERNOR_URL", "HIPPOCAMPUS_URL") || "http://127.0.0.1:54323";
const API_KEY = envOf("GOVERNOR_API_KEY", "HIPPOCAMPUS_API_KEY");
const USER_ID = envOf("GOVERNOR_USER_ID", "HIPPOCAMPUS_USER_ID") || "sam";
const RECALL_K = Number(envOf("PI_BRIDGE_K") || "20") || 20;
const DISABLED = envOf("PI_BRIDGE_DISABLE") === "1";
const INJECT = envOf("PI_BRIDGE_INJECT") !== "0";

const CACHE_DIR = join(HOME, ".cache/sacred-brain");
const OUTCOME_QUEUE = join(CACHE_DIR, "pi-pending-outcome.jsonl");
const LOG_FILE = join(CACHE_DIR, "claude-bridge.log");

// ---------- helpers ---------------------------------------------------------

function log(line: string): void {
	try {
		mkdirSync(CACHE_DIR, { recursive: true });
		appendFileSync(LOG_FILE, `${new Date().toISOString()} pi-bridge ${line}\n`);
	} catch { /* never throw */ }
}

function authHeaders(): Record<string, string> {
	const h: Record<string, string> = { "Content-Type": "application/json" };
	if (API_KEY) h["X-API-Key"] = API_KEY;
	return h;
}

function buildScope(scopePath: string): unknown {
	// "project:foo/user:sam" → nested {kind,id,parent} JSON, outermost first.
	const segs = scopePath.split("/").filter(Boolean);
	let scope: unknown = null;
	for (let i = segs.length - 1; i >= 0; i--) {
		const idx = segs[i].indexOf(":");
		if (idx < 0) continue;
		scope = {
			kind: segs[i].slice(0, idx),
			id: segs[i].slice(idx + 1),
			parent: scope,
		};
	}
	return scope;
}

function projectScopePath(cwd: string): string {
	const project = basename(cwd) || "global";
	return `project:${project}/user:${USER_ID}`;
}

async function safeFetch(url: string, init: RequestInit, timeoutMs: number): Promise<Response | null> {
	try {
		return await fetch(url, { ...init, signal: AbortSignal.timeout(timeoutMs) });
	} catch (e: any) {
		log(`fetch ${url} failed: ${e?.message ?? e}`);
		return null;
	}
}

// ---------- recall ----------------------------------------------------------

interface RecallResult {
	text?: string;
	kind?: string;
	confidence?: number;
	disputed?: boolean;
	provenance?: { source?: string };
}

function formatMemoryBlock(scopePath: string, results: RecallResult[]): string {
	const lines: string[] = [];
	lines.push(`<!-- generated by sacred-brain-bridge (pi); scope=${scopePath} -->`);
	lines.push("# Relevant memory");
	lines.push("");
	lines.push(
		"> Search long-term memory on demand: `sacred-search <query> [user_id] [limit]` " +
		"(defaults: `user_id=sam`, `limit=5`). See `docs/SACRED_SEARCH.md` in the sacred-brain repo.",
	);
	lines.push("");
	if (!results.length) {
		lines.push("_(no memories for this scope yet)_");
	} else {
		for (const r of results) {
			const text = (r.text ?? "").trim().replace(/\s*\n\s*/g, " ");
			const kind = r.kind ?? "?";
			const conf = typeof r.confidence === "number" ? r.confidence.toFixed(2) : "?";
			const disputed = r.disputed ? " ⚠disputed" : "";
			const src = r.provenance?.source ?? "?";
			lines.push(`- ${text}  `);
			lines.push(`  <!-- kind=${kind} conf=${conf} src=${src}${disputed} -->`);
		}
	}
	return lines.join("\n") + "\n";
}

let cachedMemoryBlock = "";
let cachedScopePath = "";

async function pullRecall(cwd: string): Promise<void> {
	const scopePath = projectScopePath(cwd);
	const body = {
		user_id: USER_ID,
		query: "",
		k: RECALL_K,
		filters: { scope: buildScope(scopePath), min_confidence: 0.5 },
	};
	const res = await safeFetch(
		`${GOVERNOR_URL}/recall`,
		{ method: "POST", headers: authHeaders(), body: JSON.stringify(body) },
		2000,
	);
	if (!res) { cachedMemoryBlock = ""; cachedScopePath = ""; return; }
	if (!res.ok) {
		log(`recall: http ${res.status}`);
		cachedMemoryBlock = ""; cachedScopePath = "";
		return;
	}
	let data: any = {};
	try { data = await res.json(); } catch { /* fall through */ }
	const results: RecallResult[] = Array.isArray(data?.results) ? data.results : [];

	cachedMemoryBlock = formatMemoryBlock(scopePath, results);
	cachedScopePath = scopePath;

	// Mirror the file-based convention used by the sibling bridges.
	try {
		const outDir = join(cwd, ".agents");
		mkdirSync(outDir, { recursive: true });
		writeFileSync(join(outDir, "CONTEXT_MEMORY.md"), cachedMemoryBlock);
	} catch (e: any) {
		log(`recall: write CONTEXT_MEMORY.md failed: ${e?.message ?? e}`);
	}

	log(`recall: ${results.length} memories for ${scopePath}`);
}

// ---------- precompact /observe --------------------------------------------

function extractText(entries: any[]): string {
	const chunks: string[] = [];
	for (const e of entries) {
		const m = e?.message ?? e;
		if (!m?.content) continue;
		const role = m.role ?? "?";
		if (Array.isArray(m.content)) {
			for (const c of m.content) {
				if (c?.type === "text" && typeof c.text === "string") {
					chunks.push(`[${role}] ${c.text}`);
				}
			}
		} else if (typeof m.content === "string") {
			chunks.push(`[${role}] ${m.content}`);
		}
	}
	return chunks.join("\n\n");
}

async function observePrecompact(cwd: string, entries: any[]): Promise<void> {
	let text = extractText(entries);
	if (!text) return;
	if (text.length > 4000) text = "…\n" + text.slice(-4000);
	const scopePath = projectScopePath(cwd);
	const body = {
		user_id: USER_ID,
		text,
		source: "pi:precompact",
		scope: buildScope(scopePath),
		metadata: { project: basename(cwd) || "global", cwd },
	};
	const res = await safeFetch(
		`${GOVERNOR_URL}/observe`,
		{ method: "POST", headers: authHeaders(), body: JSON.stringify(body) },
		3000,
	);
	log(`precompact: http ${res?.status ?? "ERR"} bytes=${text.length}`);
}

// ---------- outcome drain ---------------------------------------------------

async function drainOutcomes(): Promise<void> {
	if (!existsSync(OUTCOME_QUEUE)) return;
	let raw = "";
	try { raw = readFileSync(OUTCOME_QUEUE, "utf8"); } catch { return; }
	const lines = raw.split(/\r?\n/).filter((l) => l.length > 0);
	if (!lines.length) return;
	const remaining: string[] = [];
	let posted = 0;
	let failed = 0;
	for (const line of lines) {
		const res = await safeFetch(
			`${GOVERNOR_URL}/outcome`,
			{ method: "POST", headers: authHeaders(), body: line },
			3000,
		);
		if (res && res.ok) posted++;
		else { remaining.push(line); failed++; }
	}
	try {
		writeFileSync(OUTCOME_QUEUE, remaining.length ? remaining.join("\n") + "\n" : "");
	} catch { /* best-effort */ }
	log(`drain(pi-pending-outcome.jsonl): posted=${posted} failed=${failed}`);
}

// ---------- entrypoint ------------------------------------------------------

export default function (pi: ExtensionAPI) {
	if (DISABLED) {
		log("disabled via PI_BRIDGE_DISABLE=1");
		return;
	}

	pi.on("session_start", async (_event: any, _ctx: any) => {
		try { await pullRecall(process.cwd()); }
		catch (e: any) { log(`session_start: ${e?.message ?? e}`); }
	});

	if (INJECT) {
		pi.on("before_agent_start", (event: any, _ctx: any) => {
			if (!cachedMemoryBlock) return;
			const sep = event?.systemPrompt?.endsWith("\n") ? "\n" : "\n\n";
			return { systemPrompt: (event?.systemPrompt ?? "") + sep + cachedMemoryBlock };
		});
	}

	pi.on("session_before_compact", async (event: any, _ctx: any) => {
		try {
			const entries = event?.preparation?.messagesToSummarize ?? event?.branchEntries ?? [];
			await observePrecompact(process.cwd(), entries);
		} catch (e: any) { log(`before_compact: ${e?.message ?? e}`); }
		// Don't override pi's compaction result.
		return undefined;
	});

	pi.on("session_shutdown", async (_event: any, _ctx: any) => {
		try { await drainOutcomes(); }
		catch (e: any) { log(`session_shutdown: ${e?.message ?? e}`); }
	});

	log(`loaded; governor=${GOVERNOR_URL} user=${USER_ID} k=${RECALL_K} inject=${INJECT}`);
}
