/**
 * Main-window Context tab: dictation system base prompt + last LLM request/response.
 */

import { api } from './api.js';
import { saveSettings, getCurrentSettings } from './settings.js';
import { debugLog, debugError } from './debug-flags.js';

let contextBaseDebounce = null;
/** Resolved server index for the row shown in the Context tab (0 = oldest). */
let contextHistoryIndex = null;
/** Total dictation snapshots (from last API response). */
let contextHistoryTotal = 0;

function _formatCtxTs(iso) {
    if (!iso || typeof iso !== 'string') return '—';
    const d = Date.parse(iso);
    if (Number.isNaN(d)) return iso;
    try {
        return new Date(d).toLocaleString(undefined, {
            dateStyle: 'medium',
            timeStyle: 'short',
        });
    } catch (_e) {
        return iso;
    }
}

function _updateContextHistoryChrome(data) {
    const lastEl = document.getElementById('dictation-last-done-at');
    const posEl = document.getElementById('dictation-context-position');
    const backBtn = document.getElementById('dictation-context-back');
    const fwdBtn = document.getElementById('dictation-context-forward');
    const total = typeof data.history_total === 'number' ? data.history_total : 0;
    const idx = typeof data.history_index === 'number' ? data.history_index : null;

    if (lastEl) {
        if (total === 0) {
            lastEl.textContent = 'Last dictation: none yet';
        } else {
            lastEl.textContent = `Last dictation: ${_formatCtxTs(data.last_dictation_timestamp)}`;
        }
    }
    if (posEl) {
        if (total === 0) {
            posEl.textContent = 'No saved dictations';
        } else if (idx != null) {
            posEl.textContent = `${idx + 1} of ${total} · ${_formatCtxTs(data.current_timestamp)}`;
        } else {
            posEl.textContent = '—';
        }
    }
    if (backBtn) {
        backBtn.disabled = total === 0 || idx == null || idx <= 0;
    }
    if (fwdBtn) {
        fwdBtn.disabled = total === 0 || idx == null || idx >= total - 1;
    }
}

/**
 * @param {{ resetToLatest?: boolean }} [options]
 */
export async function refreshDictationLastContext(options = {}) {
    const { resetToLatest = false } = options;
    const sysEl = document.getElementById('dictation-last-system');
    const userEl = document.getElementById('dictation-last-user');
    const resEl = document.getElementById('dictation-last-response');
    if (!sysEl || !userEl || !resEl) return;
    if (resetToLatest) {
        contextHistoryIndex = null;
    }
    const q =
        contextHistoryIndex != null ? `dictation/last-context?index=${contextHistoryIndex}` : 'dictation/last-context';
    try {
        const data = await api(q);
        sysEl.value = data.cleanup_system_sent || '';
        userEl.value = data.cleanup_user_sent || '';
        resEl.value = data.response_text_full || '';
        if (typeof data.history_index === 'number') {
            contextHistoryIndex = data.history_index;
        } else {
            contextHistoryIndex = null;
        }
        contextHistoryTotal = typeof data.history_total === 'number' ? data.history_total : 0;
        _updateContextHistoryChrome(data);
    } catch (e) {
        debugError('CONTEXT', 'Failed to load last dictation context:', e);
    }
}

export async function syncContextTabFromSettings(forceRefresh = false) {
    const cb = document.getElementById('dictation-use-default-prompt');
    const ta = document.getElementById('dictation-context-base-prompt');
    if (!cb || !ta) return;

    let s = getCurrentSettings();
    if (forceRefresh || !Object.keys(s).length) {
        try {
            s = await api('/api/settings');
        } catch (e) {
            debugError('CONTEXT', 'Failed to refresh settings:', e);
        }
    }
    const useDefault = s.dictation_use_default_system_prompt !== false;
    cb.checked = useDefault;

    try {
        if (useDefault) {
            const d = await api('dictation/prompt-defaults');
            ta.value = d.default_cleanup_base_prompt || '';
            ta.readOnly = true;
        } else {
            ta.readOnly = false;
            ta.value =
                s.dictation_custom_system_prompt_base != null
                    ? s.dictation_custom_system_prompt_base
                    : '';
        }

    } catch (e) {
        debugError('CONTEXT', 'Failed to sync prompt defaults:', e);
    }
}

async function onToggleUseDefault() {
    const cb = document.getElementById('dictation-use-default-prompt');
    if (!cb) return;
    try {
        await saveSettings({ dictation_use_default_system_prompt: cb.checked });
        await syncContextTabFromSettings(true);
    } catch (e) {
        debugError('CONTEXT', 'Toggle save failed:', e);
    }
}

function scheduleSaveCustomBase() {
    if (contextBaseDebounce) clearTimeout(contextBaseDebounce);
    contextBaseDebounce = setTimeout(async () => {
        contextBaseDebounce = null;
        const ta = document.getElementById('dictation-context-base-prompt');
        if (!ta || ta.readOnly) return;
        try {
            await saveSettings({
                dictation_custom_system_prompt_base: ta.value,
            });
            const hint = document.getElementById('dictation-context-base-saved');
            if (hint) {
                hint.hidden = false;
                setTimeout(() => {
                    hint.hidden = true;
                }, 1200);
            }
        } catch (e) {
            debugError('CONTEXT', 'Custom base save failed:', e);
        }
    }, 600);
}

export function initContextTab() {
    const navChat = document.getElementById('nav-chat-tab');
    const navProfile = document.getElementById('nav-profile-tab');
    const navCtx = document.getElementById('nav-context-tab');
    const viewChat = document.getElementById('view-chat');
    const viewProfile = document.getElementById('view-profile');
    const viewCtx = document.getElementById('view-context');
    if (!navChat || !navCtx || !viewChat || !viewCtx || !navProfile || !viewProfile) {
        debugLog('CONTEXT', 'Context tab DOM missing; skip init');
        return;
    }

    const showChat = () => {
        navChat.classList.add('active');
        navProfile.classList.remove('active');
        navCtx.classList.remove('active');
        viewChat.style.display = '';
        viewProfile.style.display = 'none';
        viewCtx.style.display = 'none';
    };

    const showProfile = async () => {
        navProfile.classList.add('active');
        navChat.classList.remove('active');
        navCtx.classList.remove('active');
        viewProfile.style.display = '';
        viewChat.style.display = 'none';
        viewCtx.style.display = 'none';
        await syncContextTabFromSettings();
    };

    const showContext = async () => {
        navCtx.classList.add('active');
        navChat.classList.remove('active');
        navProfile.classList.remove('active');
        viewCtx.style.display = '';
        viewChat.style.display = 'none';
        viewProfile.style.display = 'none';
        await syncContextTabFromSettings();
        await refreshDictationLastContext();
    };

    navChat.addEventListener('click', showChat);
    navProfile.addEventListener('click', () => {
        showProfile().catch((e) => debugError('PROFILE', e));
    });
    navCtx.addEventListener('click', () => {
        showContext().catch((e) => debugError('CONTEXT', e));
    });

    document.getElementById('dictation-use-default-prompt')?.addEventListener('change', () => {
        onToggleUseDefault().catch((e) => debugError('CONTEXT', e));
    });

    document.getElementById('dictation-context-base-prompt')?.addEventListener('input', () => {
        scheduleSaveCustomBase();
    });

    document.getElementById('dictation-last-response-copy')?.addEventListener('click', async () => {
        const resEl = document.getElementById('dictation-last-response');
        const text = resEl?.value || '';
        try {
            await navigator.clipboard.writeText(text);
        } catch (e) {
            debugError('CONTEXT', 'Clipboard copy failed:', e);
        }
    });

    document.getElementById('dictation-context-back')?.addEventListener('click', () => {
        if (contextHistoryIndex == null || contextHistoryIndex <= 0) return;
        contextHistoryIndex -= 1;
        refreshDictationLastContext({ resetToLatest: false }).catch((e) => debugError('CONTEXT', e));
    });
    document.getElementById('dictation-context-forward')?.addEventListener('click', () => {
        if (contextHistoryIndex == null) return;
        if (contextHistoryTotal <= 0 || contextHistoryIndex >= contextHistoryTotal - 1) return;
        contextHistoryIndex += 1;
        refreshDictationLastContext({ resetToLatest: false }).catch((e) => debugError('CONTEXT', e));
    });

    window.addEventListener('aiframe-settings-saved', () => {
        syncContextTabFromSettings().catch(() => {});
    });
}
