/**
 * Debug Flags - Feature-based logging control
 *
 * Primary source of truth is server settings.debug_flags.
 * localStorage is fallback during early bootstrap/offline.
 */

const FLAG_DEFINITIONS = {
    AUTH: { default: true, desc: 'Login & sessions' },
    API: { default: false, desc: 'API requests' },
    CHAT: { default: true, desc: 'Chat & messages' },
    SETTINGS: { default: false, desc: 'Settings' },
    MODELS: { default: false, desc: 'Model loading' },
    NOTIFICATIONS: { default: true, desc: 'Notifications' },
    APP: { default: false, desc: 'General app' },
    DICTATION: { default: false, desc: 'Dictate button & hotkey UI traces' },
    CONTEXT: { default: false, desc: 'Context tab' },
    PROFILE: { default: false, desc: 'Profile tab' },
    SPEECH: { default: false, desc: 'Speech model discovery' },
};

const STORAGE_KEY = 'twim_debug_flags';
const FLUSH_DELAY_MS = 100;
const SERVER_ENDPOINT = '/api/log';

const _DEBUG_FLAGS = {
    SEND_TO_SERVER: true,
    SERVER_ENDPOINT,
};

for (const [key, def] of Object.entries(FLAG_DEFINITIONS)) {
    _DEBUG_FLAGS[key] = !!def.default;
}

let logBuffer = [];
let flushTimeout = null;
let saveFlagsTimeout = null;
let flagsReady = false;
let suppressSettingsSync = false;

function _flagsPayload() {
    const out = {};
    for (const key of Object.keys(FLAG_DEFINITIONS)) {
        out[key] = !!_DEBUG_FLAGS[key];
    }
    return out;
}

function _applyFlags(raw) {
    const next = raw && typeof raw === 'object' ? raw : {};
    for (const [key, def] of Object.entries(FLAG_DEFINITIONS)) {
        _DEBUG_FLAGS[key] = Object.prototype.hasOwnProperty.call(next, key) ? !!next[key] : !!def.default;
    }
}

function _saveFlagsToLocalStorage() {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(_flagsPayload()));
    } catch (_e) {
        // Ignore localStorage failures in constrained environments.
    }
}

function _loadFlagsFromLocalStorage() {
    try {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (!saved) return;
        const parsed = JSON.parse(saved);
        _applyFlags(parsed);
    } catch (_e) {
        // Ignore malformed localStorage values.
    }
}

async function _saveFlagsToServer() {
    try {
        const response = await fetch('/api/settings', {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ debug_flags: _flagsPayload() }),
        });
        if (!response.ok) {
            throw new Error(`PATCH /api/settings failed (${response.status})`);
        }
    } catch (_e) {
        // Server sync is best effort; localStorage remains fallback.
    }
}

function _scheduleFlagsServerSync() {
    if (suppressSettingsSync || !flagsReady) return;
    clearTimeout(saveFlagsTimeout);
    saveFlagsTimeout = setTimeout(() => {
        _saveFlagsToServer().catch(() => {});
    }, 150);
}

async function flushLogsToServer() {
    if (logBuffer.length === 0) return;
    const logsToSend = [...logBuffer];
    logBuffer = [];
    try {
        const response = await fetch(_DEBUG_FLAGS.SERVER_ENDPOINT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ logs: logsToSend }),
            credentials: 'same-origin',
        });
        if (!response.ok) {
            console.warn('[DEBUG] Failed to send logs to server:', response.status);
        }
    } catch (e) {
        if (!e.message?.includes('Failed to fetch')) {
            console.warn('[DEBUG] Error sending logs:', e.message);
        }
    }
}

function queueLogForServer(level, message, data = null) {
    if (!_DEBUG_FLAGS.SEND_TO_SERVER) return;
    logBuffer.push({ level, message, data });
    clearTimeout(flushTimeout);
    flushTimeout = setTimeout(flushLogsToServer, FLUSH_DELAY_MS);
}

function formatArgs(args) {
    return args
        .map((a) => {
            if (a === null) return 'null';
            if (a === undefined) return 'undefined';
            if (typeof a === 'object') {
                try {
                    return JSON.stringify(a);
                } catch {
                    return String(a);
                }
            }
            return String(a);
        })
        .join(' ');
}

export async function syncDebugFlagsFromServer(settingsSnapshot = null) {
    try {
        const settings =
            settingsSnapshot && typeof settingsSnapshot === 'object'
                ? settingsSnapshot
                : await fetch('/api/settings', { credentials: 'same-origin' }).then((r) => r.json());
        suppressSettingsSync = true;
        _applyFlags(settings?.debug_flags || null);
        _saveFlagsToLocalStorage();
        flagsReady = true;
    } catch (_e) {
        // Keep current/local fallback flags.
    } finally {
        suppressSettingsSync = false;
    }
}

const DEBUG_STATE = _DEBUG_FLAGS;
export const DEBUG = DEBUG_STATE;
export const DEBUG_FLAGS_READY = () => flagsReady;

export async function setDebugFlag(flag, enabled) {
    if (!(flag in FLAG_DEFINITIONS)) return;
    _DEBUG_FLAGS[flag] = !!enabled;
    _saveFlagsToLocalStorage();
    _scheduleFlagsServerSync();
}

export async function setAllDebugFlags(enabled) {
    for (const key of Object.keys(FLAG_DEFINITIONS)) {
        _DEBUG_FLAGS[key] = !!enabled;
    }
    _saveFlagsToLocalStorage();
    _scheduleFlagsServerSync();
}

export function getDebugFlagDefinitions() {
    return FLAG_DEFINITIONS;
}

export function debugLog(flag, ...args) {
    if (!_DEBUG_FLAGS[flag]) return;
    const prefix = `[${flag}]`;
    console.log(prefix, ...args);
    queueLogForServer('info', `${prefix} ${formatArgs(args)}`);
}

export function debugWarn(flag, ...args) {
    if (!_DEBUG_FLAGS[flag]) return;
    const prefix = `[${flag}]`;
    console.warn(prefix, ...args);
    queueLogForServer('warn', `${prefix} ${formatArgs(args)}`);
}

export function debugError(flag, ...args) {
    if (!_DEBUG_FLAGS[flag]) return;
    const prefix = `[${flag}]`;
    console.error(prefix, ...args);
    queueLogForServer('error', `${prefix} ${formatArgs(args)}`);
}

export function serverLog(level, message, data = null) {
    queueLogForServer(level, message, data);
}

export function isDebugEnabled(flag) {
    return !!_DEBUG_FLAGS[flag];
}

export function flushLogs() {
    clearTimeout(flushTimeout);
    flushLogsToServer();
}

_loadFlagsFromLocalStorage();

if (typeof window !== 'undefined') {
    window.addEventListener('beforeunload', flushLogs);
}

queueLogForServer('info', '[DEBUG] Frontend debug logging initialized');
