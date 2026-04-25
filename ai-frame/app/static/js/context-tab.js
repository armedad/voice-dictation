/**
 * Main-window Context tab: dictation system base prompt + last LLM request/response.
 */

import { api } from './api.js';
import { saveSettings, getCurrentSettings } from './settings.js';
import { debugLog, debugError } from './debug-flags.js';

let contextBaseDebounce = null;

export async function refreshDictationLastContext() {
    const reqEl = document.getElementById('dictation-last-request');
    const resEl = document.getElementById('dictation-last-response');
    if (!reqEl || !resEl) return;
    try {
        const data = await api('dictation/last-context');
        reqEl.value = data.verbatim_request || '';
        resEl.value = data.response_text_full || '';
    } catch (e) {
        debugError('CONTEXT', 'Failed to load last dictation context:', e);
    }
}

export async function syncContextTabFromSettings() {
    const cb = document.getElementById('dictation-use-default-prompt');
    const ta = document.getElementById('dictation-context-base-prompt');
    if (!cb || !ta) return;

    const s = getCurrentSettings();
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
        await syncContextTabFromSettings();
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
    const navCtx = document.getElementById('nav-context-tab');
    const viewChat = document.getElementById('view-chat');
    const viewCtx = document.getElementById('view-context');
    if (!navChat || !navCtx || !viewChat || !viewCtx) {
        debugLog('CONTEXT', 'Context tab DOM missing; skip init');
        return;
    }

    const showChat = () => {
        navChat.classList.add('active');
        navCtx.classList.remove('active');
        viewChat.style.display = '';
        viewCtx.style.display = 'none';
    };

    const showContext = async () => {
        navCtx.classList.add('active');
        navChat.classList.remove('active');
        viewCtx.style.display = '';
        viewChat.style.display = 'none';
        await syncContextTabFromSettings();
        await refreshDictationLastContext();
    };

    navChat.addEventListener('click', showChat);
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

    window.addEventListener('aiframe-settings-saved', () => {
        syncContextTabFromSettings().catch(() => {});
    });
}
