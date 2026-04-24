/**
 * Debug Flags - Feature-based logging control
 * 
 * Flags can be toggled in Settings > Debug > Debug Flags.
 * Settings are saved to localStorage.
 * 
 * Usage:
 *   import { DEBUG, debugLog, debugWarn, debugError } from './debug-flags.js';
 *   debugLog('AUTH', 'User logged in:', username);
 */

// Flag definitions with defaults and descriptions
const FLAG_DEFINITIONS = {
    AUTH: { default: true, desc: 'Login & sessions' },
    API: { default: false, desc: 'API requests' },
    CHAT: { default: true, desc: 'Chat & messages' },
    SETTINGS: { default: false, desc: 'Settings' },
    MODELS: { default: false, desc: 'Model loading' },
    NOTIFICATIONS: { default: true, desc: 'Notifications' },
    APP: { default: false, desc: 'General app' },
};

const STORAGE_KEY = 'aiframe_debug_flags';

// Load flags from localStorage (or use defaults)
function loadFlags() {
    const flags = {};
    
    // Start with defaults
    for (const [key, def] of Object.entries(FLAG_DEFINITIONS)) {
        flags[key] = def.default;
    }
    
    // Override with saved values
    try {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved) {
            const parsed = JSON.parse(saved);
            for (const [key, value] of Object.entries(parsed)) {
                if (key in flags) {
                    flags[key] = !!value;
                }
            }
        }
    } catch (e) {
        console.warn('[DEBUG] Failed to load debug flags from localStorage:', e);
    }
    
    // Non-configurable flags
    flags.SEND_TO_SERVER = true;
    flags.SERVER_ENDPOINT = '/api/log';
    
    return flags;
}

export const DEBUG = loadFlags();

// Save flags to localStorage
function saveFlags() {
    try {
        const toSave = {};
        for (const key of Object.keys(FLAG_DEFINITIONS)) {
            toSave[key] = DEBUG[key];
        }
        localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave));
    } catch (e) {
        console.warn('[DEBUG] Failed to save debug flags:', e);
    }
}

/**
 * Set a debug flag and save to localStorage
 */
export function setDebugFlag(flag, enabled) {
    if (flag in FLAG_DEFINITIONS) {
        DEBUG[flag] = !!enabled;
        saveFlags();
    }
}

/**
 * Set all debug flags at once
 */
export function setAllDebugFlags(enabled) {
    for (const key of Object.keys(FLAG_DEFINITIONS)) {
        DEBUG[key] = !!enabled;
    }
    saveFlags();
}

/**
 * Get flag definitions for UI rendering
 */
export function getDebugFlagDefinitions() {
    return FLAG_DEFINITIONS;
}

// Log buffer for batching server sends
let logBuffer = [];
let flushTimeout = null;
const FLUSH_DELAY_MS = 100;

async function flushLogsToServer() {
    if (logBuffer.length === 0) return;
    
    const logsToSend = [...logBuffer];
    logBuffer = [];
    
    try {
        const response = await fetch(DEBUG.SERVER_ENDPOINT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ logs: logsToSend }),
            credentials: 'same-origin'
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
    if (!DEBUG.SEND_TO_SERVER) return;
    
    logBuffer.push({ level, message, data });
    clearTimeout(flushTimeout);
    flushTimeout = setTimeout(flushLogsToServer, FLUSH_DELAY_MS);
}

function formatArgs(args) {
    return args.map(a => {
        if (a === null) return 'null';
        if (a === undefined) return 'undefined';
        if (typeof a === 'object') {
            try { return JSON.stringify(a); } catch { return String(a); }
        }
        return String(a);
    }).join(' ');
}

export function debugLog(flag, ...args) {
    if (!DEBUG[flag]) return;
    
    const prefix = `[${flag}]`;
    console.log(prefix, ...args);
    queueLogForServer('info', `${prefix} ${formatArgs(args)}`);
}

export function debugWarn(flag, ...args) {
    if (!DEBUG[flag]) return;
    
    const prefix = `[${flag}]`;
    console.warn(prefix, ...args);
    queueLogForServer('warn', `${prefix} ${formatArgs(args)}`);
}

export function debugError(flag, ...args) {
    if (!DEBUG[flag]) return;
    
    const prefix = `[${flag}]`;
    console.error(prefix, ...args);
    queueLogForServer('error', `${prefix} ${formatArgs(args)}`);
}

export function serverLog(level, message, data = null) {
    queueLogForServer(level, message, data);
}

export function isDebugEnabled(flag) {
    return !!DEBUG[flag];
}

export function flushLogs() {
    clearTimeout(flushTimeout);
    flushLogsToServer();
}

// Flush logs before page unload
if (typeof window !== 'undefined') {
    window.addEventListener('beforeunload', flushLogs);
}

// Test log on module load
if (DEBUG.SEND_TO_SERVER) {
    queueLogForServer('info', '[DEBUG] Frontend debug logging initialized');
}
