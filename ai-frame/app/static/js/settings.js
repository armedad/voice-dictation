/**
 * Settings management
 */

import { api } from './api.js';
import { debugLog, debugError, getDebugFlagDefinitions, setDebugFlag, setAllDebugFlags, DEBUG } from './debug-flags.js';

let currentSettings = {};

/** Latest settings object from server (read-only snapshot for other modules). */
export function getCurrentSettings() {
    return { ...currentSettings };
}
let providersCache = [];
let modelsCache = { groups: [], default: {} };
let speechModelsCache = { groups: [], default: {}, errors: [] };
let dictationInstructionsDebounce = null;
let dictationVocabularyDebounce = null;

/** @type {'toggle' | 'cancel' | null} */
let dictationHotkeyCaptureField = null;

/** Abort previous window keydown listener when starting a new capture or closing settings. */
let dictationHotkeyKeydownAbort = null;

function stopDictationHotkeyCapture() {
    dictationHotkeyKeydownAbort?.abort();
    dictationHotkeyKeydownAbort = null;
    dictationHotkeyCaptureField = null;
    const st = document.getElementById('dictation-hotkey-capture-status');
    if (st) {
        st.hidden = true;
        st.textContent = '';
    }
}

/**
 * @param {'toggle' | 'cancel'} field
 */
function startDictationHotkeyCapture(field) {
    stopDictationHotkeyCapture();
    dictationHotkeyCaptureField = field;

    const st = document.getElementById('dictation-hotkey-capture-status');
    if (st) {
        st.style.color = '';
        st.hidden = false;
        st.textContent =
            'Listening… Hold at least one modifier (⌘ / Ctrl / ⌥ / Shift) and press a letter or key. Press Esc alone to cancel. If keys never register, open this URL in Safari or Chrome (some embedded previews reserve shortcuts).';
    }

    const onKeyDown = async (e) => {
        if (!dictationHotkeyCaptureField) return;

        if (
            e.key === 'Escape' &&
            !e.metaKey &&
            !e.ctrlKey &&
            !e.altKey &&
            !e.shiftKey
        ) {
            e.preventDefault();
            e.stopPropagation();
            stopDictationHotkeyCapture();
            return;
        }

        const chord = eventToChord(e);
        if (!chord) return;

        e.preventDefault();
        e.stopPropagation();

        const which = dictationHotkeyCaptureField;
        stopDictationHotkeyCapture();

        const payload =
            which === 'toggle'
                ? { dictation_hotkey_toggle: chord }
                : { dictation_hotkey_cancel: chord };
        try {
            await saveSettings(payload);
        } catch (err) {
            debugError('SETTINGS', 'Hotkey save failed:', err);
            const stEl = document.getElementById('dictation-hotkey-capture-status');
            if (stEl) {
                stEl.hidden = false;
                stEl.style.color = 'var(--error, #f87171)';
                stEl.textContent =
                    (err && err.message) ||
                    'Could not save hotkey. Check that you are logged in.';
            }
        }
    };

    const ac = new AbortController();
    dictationHotkeyKeydownAbort = ac;
    window.addEventListener('keydown', onKeyDown, { capture: true, signal: ac.signal });

    queueMicrotask(() => {
        const ae = document.activeElement;
        if (ae instanceof HTMLElement && ae.id !== 'dictation-hotkey-capture-sink') {
            ae.blur();
        }
        document.getElementById('dictation-hotkey-capture-sink')?.focus({ preventScroll: true });
    });
}

/**
 * @param {Record<string, unknown> | null | undefined} chord
 * @returns {string}
 */
function formatChordDisplay(chord) {
    if (!chord || typeof chord !== 'object' || !Array.isArray(chord.modifiers)) return '(none)';
    const isApple =
        typeof navigator !== 'undefined' &&
        /Mac|iPhone|iPad|iPod/i.test(navigator.userAgent || '');
    const labels = {
        cmd: 'Cmd',
        ctrl: 'Ctrl',
        alt: isApple ? 'Option (⌥)' : 'Alt',
        shift: 'Shift',
    };
    const parts = chord.modifiers.map((m) => labels[m] || m);
    const k = chord.key;
    if (typeof k !== 'string' || !k) return '(none)';
    if (k.length === 1) {
        parts.push(/[a-z]/.test(k) ? k.toUpperCase() : k);
    } else {
        parts.push(k.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()));
    }
    return parts.join('+');
}

/**
 * Physical / layout-stable key from ``event.code`` (prefer this when Option/Alt is held,
 * because ``event.key`` may be a dead key or a special character on macOS).
 * @param {KeyboardEvent} e
 * @returns {string | null}
 */
function logicalKeyFromCode(e) {
    const c = e.code || '';
    if (c.startsWith('Key') && c.length === 4) return c.slice(3).toLowerCase();
    if (c.startsWith('Digit')) return c.slice(5);

    const named = {
        Space: 'space',
        Minus: 'minus',
        Equal: 'equal',
        BracketLeft: 'bracket_left',
        BracketRight: 'bracket_right',
        Backslash: 'backslash',
        Semicolon: 'semicolon',
        Quote: 'quote',
        Comma: 'comma',
        Period: 'period',
        Slash: 'slash',
        Backquote: 'backquote',
        IntlBackslash: 'intl_backslash',
        Tab: 'tab',
    };
    if (named[c]) return named[c];

    return null;
}

/**
 * @param {string} key from event.key
 * @returns {string | null}
 */
function normalizeSpecialKey(key) {
    if (!key || key === 'Dead') return null;
    if (key === ' ') return 'space';
    if (key.length === 1) {
        const k = key.toLowerCase();
        if (/^[a-z0-9]$/.test(k)) return k;
        return null;
    }
    const map = {
        Escape: 'escape',
        Tab: 'tab',
        Enter: 'enter',
        Backspace: 'backspace',
        Delete: 'delete',
        Home: 'home',
        End: 'end',
        PageUp: 'page_up',
        PageDown: 'page_down',
    };
    if (map[key]) return map[key];
    if (key.startsWith('Arrow')) {
        const d = key.slice(5).toLowerCase();
        if (d === 'up' || d === 'down' || d === 'left' || d === 'right') return d;
    }
    if (/^f\d{1,2}$/i.test(key)) return key.toLowerCase();
    return null;
}

/**
 * @param {KeyboardEvent} e
 * @returns {{ modifiers: string[], key: string } | null}
 */
function eventToChord(e) {
    const gm =
        typeof e.getModifierState === 'function'
            ? (/** @type {string} */ s) => e.getModifierState(s)
            : () => false;

    const mods = [];
    if (e.metaKey || gm('Meta')) mods.push('cmd');
    if (e.ctrlKey || gm('Control')) mods.push('ctrl');
    // macOS Option: usually ``altKey``; ``getModifierState('Alt')`` catches WebKit / embedded cases.
    if (e.altKey || gm('Alt') || gm('AltGraph')) mods.push('alt');
    if (e.shiftKey || gm('Shift')) mods.push('shift');
    if (!mods.length) return null;

    // Prefer ``code`` so Option/Alt + letter still yields the base letter (``key`` may be "Dead" or "∂").
    let key = logicalKeyFromCode(e);
    if (!key) key = normalizeSpecialKey(e.key);
    if (!key) return null;

    const order = { alt: 0, cmd: 1, ctrl: 2, shift: 3 };
    const uniq = [...new Set(mods)].sort((a, b) => order[a] - order[b]);
    return { modifiers: uniq, key };
}

/** Defaults for local provider URLs (matches server defaults / _default/settings.json). */
export const LM_STUDIO_DEFAULT_URL = 'http://localhost:1234';
export const OLLAMA_DEFAULT_URL = 'http://127.0.0.1:11434';

/**
 * Load settings from server
 */
export async function loadSettings() {
    try {
        currentSettings = await api('/api/settings');
        debugLog('SETTINGS', 'Loaded settings:', currentSettings);
        applySettings(currentSettings);
        return currentSettings;
    } catch (e) {
        debugError('SETTINGS', 'Failed to load:', e);
        return {};
    }
}

/**
 * Save settings to server
 */
export async function saveSettings(updates) {
    try {
        currentSettings = await api('/api/settings', {
            method: 'PATCH',
            body: updates
        });
        debugLog('SETTINGS', 'Saved settings');
        applySettings(currentSettings);
        window.dispatchEvent(
            new CustomEvent('aiframe-settings-saved', { detail: { ...currentSettings } })
        );
        return currentSettings;
    } catch (e) {
        debugError('SETTINGS', 'Failed to save:', e);
        throw e;
    }
}

/**
 * Apply settings to UI
 */
function applySettings(settings) {
    // Theme
    document.documentElement.setAttribute('data-theme', settings.theme || 'dark');
    
    // Theme select
    const themeSelect = document.getElementById('theme-select');
    if (themeSelect) themeSelect.value = settings.theme || 'dark';
    
    // URLs
    const ollamaUrl = document.getElementById('ollama-url');
    const lmStudioUrl = document.getElementById('lm-studio-url');
    
    if (ollamaUrl) ollamaUrl.value = settings.ollama_url || 'http://localhost:11434';
    if (lmStudioUrl) lmStudioUrl.value = settings.lm_studio_url || 'http://localhost:1234';

    const speechSel = document.getElementById('speech-model-select');
    if (speechSel && settings.speech_model && speechSel.options.length) {
        const v = settings.speech_model;
        if ([...speechSel.options].some((o) => o.value === v)) {
            speechSel.value = v;
        }
    }

    const dictationLlm = document.getElementById('dictation-llm-cleanup-enabled');
    if (dictationLlm) {
        dictationLlm.checked =
            settings.dictation_llm_cleanup_enabled !== false;
    }
    const dictationInstr = document.getElementById('dictation-instructions');
    if (dictationInstr) {
        dictationInstr.value =
            settings.dictation_instructions != null
                ? settings.dictation_instructions
                : '';
    }
    const dictationVocab = document.getElementById('dictation-vocabulary');
    if (dictationVocab) {
        dictationVocab.value =
            settings.dictation_vocabulary != null ? settings.dictation_vocabulary : '';
    }

    const hotToggleDisp = document.getElementById('dictation-hotkey-toggle-display');
    if (hotToggleDisp) {
        hotToggleDisp.textContent = formatChordDisplay(settings.dictation_hotkey_toggle);
    }
    const hotCancelDisp = document.getElementById('dictation-hotkey-cancel-display');
    if (hotCancelDisp) {
        hotCancelDisp.textContent = formatChordDisplay(settings.dictation_hotkey_cancel);
    }
}

/**
 * Populate a model select element with available models
 */
function populateModelSelect(selectElement, defaultValue) {
    if (!selectElement) return;
    
    selectElement.innerHTML = '';
    
    if (modelsCache.groups.length === 0) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = 'No models available';
        selectElement.appendChild(option);
        return;
    }
    
    for (const group of modelsCache.groups) {
        const optgroup = document.createElement('optgroup');
        optgroup.label = group.name;
        
        for (const model of group.models) {
            const option = document.createElement('option');
            option.value = `${group.provider}:${model.id}`;
            option.textContent = model.name;
            optgroup.appendChild(option);
        }
        
        selectElement.appendChild(optgroup);
    }
    
    // Set value
    if (defaultValue) {
        selectElement.value = defaultValue;
    }
}

/**
 * Load models into selectors (header and settings)
 */
export async function loadModels() {
    try {
        modelsCache = await api('/api/models');
        debugLog('MODELS', 'Loaded models:', modelsCache.groups.length, 'groups');
        
        const defaultValue = modelsCache.default.model && modelsCache.default.provider
            ? `${modelsCache.default.provider}:${modelsCache.default.model}`
            : '';
        
        // Header model select
        populateModelSelect(document.getElementById('model-select'), defaultValue);
        
        // Settings default model select
        populateModelSelect(document.getElementById('default-model-select'), defaultValue);

        const errEl = document.getElementById('models-discovery-errors');
        if (errEl) {
            const errs = modelsCache.errors || [];
            if (errs.length) {
                errEl.textContent = errs.map((x) => `${x.provider}: ${x.detail}`).join(' · ');
                errEl.hidden = false;
            } else {
                errEl.textContent = '';
                errEl.hidden = true;
            }
        }
        
    } catch (e) {
        debugError('MODELS', 'Failed to load:', e);
    }
}

function speechModelsSelectionKey(defaultObj) {
    if (!defaultObj || defaultObj.model == null || defaultObj.model === '') {
        return '';
    }
    const p = defaultObj.provider || 'faster_whisper';
    return `${p}:${defaultObj.model}`;
}

function populateSpeechModelSelect(selectElement, selectedValue) {
    if (!selectElement) return;

    selectElement.innerHTML = '';
    const groups = speechModelsCache.groups || [];
    if (groups.length === 0) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = 'No speech models listed';
        selectElement.appendChild(option);
        return;
    }

    for (const group of groups) {
        const optgroup = document.createElement('optgroup');
        optgroup.label = group.name;
        for (const model of group.models) {
            const option = document.createElement('option');
            option.value = `${group.provider}:${model.id}`;
            option.textContent = `${model.name} (${group.provider})`;
            optgroup.appendChild(option);
        }
        selectElement.appendChild(optgroup);
    }

    const want =
        (selectedValue || '').trim() ||
        speechModelsSelectionKey(speechModelsCache.default);
    if (want && [...selectElement.options].some((o) => o.value === want)) {
        selectElement.value = want;
    } else if (selectElement.options.length) {
        selectElement.selectedIndex = 0;
    }
}

/**
 * Load speech/STT model list (Settings + dictation).
 */
export async function loadSpeechModels() {
    try {
        speechModelsCache = await api('speech-models');
        debugLog(
            'SPEECH',
            'Loaded speech model groups:',
            (speechModelsCache.groups || []).length
        );

        const sel = document.getElementById('speech-model-select');
        if (sel) {
            const stored = (currentSettings.speech_model || '').trim();
            const fromDefault = speechModelsSelectionKey(speechModelsCache.default);
            populateSpeechModelSelect(sel, stored || fromDefault);
        }

        const errEl = document.getElementById('speech-models-errors');
        if (errEl) {
            const errs = speechModelsCache.errors || [];
            if (errs.length) {
                errEl.textContent = errs.map((x) => `${x.provider}: ${x.detail}`).join(' · ');
                errEl.hidden = false;
            } else {
                errEl.textContent = '';
                errEl.hidden = true;
            }
        }

        return speechModelsCache;
    } catch (e) {
        debugError('SPEECH', 'Failed to load speech models:', e);
        return speechModelsCache;
    }
}

/**
 * Load and render providers
 */
export async function loadProviders() {
    try {
        const result = await api('/api/providers');
        providersCache = result.providers || [];
        debugLog('SETTINGS', 'Loaded providers:', providersCache.length);
        renderProviders();
        return result;
    } catch (e) {
        debugError('SETTINGS', 'Failed to load providers:', e);
        return { providers: [], local: {} };
    }
}

/**
 * Render providers list
 */
function renderProviders() {
    const container = document.getElementById('providers-list');
    if (!container) return;
    
    if (providersCache.length === 0) {
        container.innerHTML = '<p class="text-muted">No providers configured</p>';
        return;
    }
    
    container.innerHTML = providersCache.map(provider => `
        <div class="provider-item" data-provider="${provider.id}">
            <div class="provider-header">
                <span class="provider-name">${provider.name}</span>
                <span class="provider-status ${provider.configured ? 'configured' : 'not-configured'}">
                    ${provider.configured ? 'Configured' : 'Not configured'}
                </span>
            </div>
            <div class="provider-fields">
                <div class="provider-field">
                    <label>API Key</label>
                    <input type="password" 
                           id="provider-key-${provider.id}" 
                           placeholder="${provider.configured ? '••••••••' : 'Enter API key'}"
                           data-provider="${provider.id}">
                </div>
            </div>
            <div class="provider-actions">
                <button class="btn-small" onclick="window.saveProviderKey('${provider.id}')">
                    ${provider.configured ? 'Update' : 'Save'}
                </button>
                ${provider.configured ? `
                    <button class="btn-small" onclick="window.removeProviderKey('${provider.id}')">Remove</button>
                ` : ''}
            </div>
        </div>
    `).join('');
}

/**
 * Save provider API key
 */
window.saveProviderKey = async function(providerId) {
    const input = document.getElementById(`provider-key-${providerId}`);
    if (!input || !input.value.trim()) {
        return;
    }
    
    try {
        await api(`/api/providers/${providerId}`, {
            method: 'PUT',
            body: { api_key: input.value.trim() }
        });
        input.value = '';
        await loadProviders();
        await loadModels();
        debugLog('SETTINGS', 'Provider key saved:', providerId);
    } catch (e) {
        debugError('SETTINGS', 'Failed to save provider key:', e);
    }
};

/**
 * Remove provider API key
 */
window.removeProviderKey = async function(providerId) {
    try {
        await api(`/api/providers/${providerId}`, {
            method: 'PUT',
            body: { api_key: '' }
        });
        await loadProviders();
        await loadModels();
        debugLog('SETTINGS', 'Provider key removed:', providerId);
    } catch (e) {
        debugError('SETTINGS', 'Failed to remove provider key:', e);
    }
};

/**
 * Check provider connection status
 */
async function checkProviderStatus() {
    try {
        const status = await api('/api/models/status');
        updateProviderStatusUI(status);
    } catch (e) {
        debugError('SETTINGS', 'Failed to check provider status:', e);
    }
}

/**
 * Update provider status in UI
 */
function updateProviderStatusUI(status) {
    const lmStatus = document.getElementById('lm-studio-status');
    const ollamaStatus = document.getElementById('ollama-status');
    
    if (lmStatus) {
        if (status.lm_studio?.connected) {
            lmStatus.textContent = `Connected (${status.lm_studio.model_count} models)`;
            lmStatus.className = 'status-indicator connected';
        } else {
            lmStatus.textContent = 'Not connected';
            lmStatus.className = 'status-indicator disconnected';
        }
    }
    
    if (ollamaStatus) {
        if (status.ollama?.connected) {
            ollamaStatus.textContent = `Connected (${status.ollama.model_count} models)`;
            ollamaStatus.className = 'status-indicator connected';
        } else {
            ollamaStatus.textContent = 'Not connected';
            ollamaStatus.className = 'status-indicator disconnected';
        }
    }
}

/**
 * Test LM Studio connection
 */
async function testLMStudio() {
    const statusEl = document.getElementById('lm-studio-status');
    if (statusEl) {
        statusEl.textContent = 'Testing...';
        statusEl.className = 'status-indicator';
    }
    
    try {
        const status = await api('/api/models/status');
        if (status.lm_studio?.connected) {
            statusEl.textContent = `Connected (${status.lm_studio.model_count} models)`;
            statusEl.className = 'status-indicator connected';
        } else {
            statusEl.textContent = status.lm_studio?.error || 'Not connected';
            statusEl.className = 'status-indicator disconnected';
        }
        await loadModels();
    } catch (e) {
        statusEl.textContent = 'Test failed';
        statusEl.className = 'status-indicator disconnected';
    }
}

/**
 * Test Ollama connection
 */
async function testOllama() {
    const statusEl = document.getElementById('ollama-status');
    if (statusEl) {
        statusEl.textContent = 'Testing...';
        statusEl.className = 'status-indicator';
    }
    
    try {
        const status = await api('/api/models/status');
        if (status.ollama?.connected) {
            statusEl.textContent = `Connected (${status.ollama.model_count} models)`;
            statusEl.className = 'status-indicator connected';
        } else {
            statusEl.textContent = status.ollama?.error || 'Not connected';
            statusEl.className = 'status-indicator disconnected';
        }
        await loadModels();
    } catch (e) {
        statusEl.textContent = 'Test failed';
        statusEl.className = 'status-indicator disconnected';
    }
}

/**
 * Render debug flags UI
 */
export function renderDebugFlags() {
    const container = document.getElementById('debug-flags-list');
    if (!container) return;
    
    const definitions = getDebugFlagDefinitions();
    
    container.innerHTML = Object.entries(definitions)
        .map(([flag, def]) => `
            <div class="debug-flag-item">
                <label class="debug-flag-label">
                    <input type="checkbox" data-flag="${flag}" ${DEBUG[flag] ? 'checked' : ''}>
                    <span class="debug-flag-name">${flag}</span>
                </label>
                <span class="debug-flag-desc">${def.desc}</span>
            </div>
        `).join('');
    
    // Add event listeners
    container.querySelectorAll('input[data-flag]').forEach(checkbox => {
        checkbox.addEventListener('change', (e) => {
            setDebugFlag(e.target.dataset.flag, e.target.checked);
        });
    });
    
    // Update count
    const count = document.getElementById('debug-flags-count');
    if (count) {
        const enabled = Object.keys(definitions).filter(f => DEBUG[f]).length;
        count.textContent = `(${enabled}/${Object.keys(definitions).length})`;
    }
}

/**
 * Open settings modal
 */
async function openSettings() {
    const modal = document.getElementById('settings-modal');
    const overlay = document.getElementById('settings-overlay');
    
    if (modal && overlay) {
        modal.classList.add('show');
        overlay.classList.add('show');
        renderDebugFlags();
        loadProviders();
        checkProviderStatus();
        await loadSpeechModels();
    }
}

/**
 * Close settings modal
 */
function closeSettings() {
    stopDictationHotkeyCapture();
    const modal = document.getElementById('settings-modal');
    const overlay = document.getElementById('settings-overlay');
    
    if (modal && overlay) {
        modal.classList.remove('show');
        overlay.classList.remove('show');
    }
}

/**
 * Initialize settings UI
 */
export function initSettings() {
    const settingsBtn = document.getElementById('settings-btn');
    const settingsClose = document.getElementById('settings-close');
    const settingsOverlay = document.getElementById('settings-overlay');
    
    // Open/close modal
    if (settingsBtn) {
        settingsBtn.addEventListener('click', openSettings);
    }
    
    if (settingsClose) {
        settingsClose.addEventListener('click', closeSettings);
    }
    
    if (settingsOverlay) {
        settingsOverlay.addEventListener('click', closeSettings);
    }
    
    // Tab switching (VS Code style - sidebar tabs)
    document.querySelectorAll('.settings-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            // Update tabs
            document.querySelectorAll('.settings-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            
            // Update pages
            document.querySelectorAll('.settings-page').forEach(p => p.classList.remove('active'));
            const page = document.getElementById(`settings-${tab.dataset.tab}`);
            if (page) page.classList.add('active');
            
            // Save last tab
            localStorage.setItem('aiframe_settings_tab', tab.dataset.tab);
        });
    });
    
    // Restore last tab
    const lastTab = localStorage.getItem('aiframe_settings_tab');
    if (lastTab) {
        const tab = document.querySelector(`.settings-tab[data-tab="${lastTab}"]`);
        if (tab) tab.click();
    }
    
    // Theme toggle
    const themeSelect = document.getElementById('theme-select');
    if (themeSelect) {
        themeSelect.addEventListener('change', async () => {
            await saveSettings({ theme: themeSelect.value });
        });
    }
    
    // URL inputs
    const ollamaUrl = document.getElementById('ollama-url');
    const lmStudioUrl = document.getElementById('lm-studio-url');
    
    if (ollamaUrl) {
        ollamaUrl.addEventListener('change', async () => {
            await saveSettings({ ollama_url: ollamaUrl.value });
            await loadModels();
            checkProviderStatus();
        });
    }
    
    if (lmStudioUrl) {
        lmStudioUrl.addEventListener('change', async () => {
            await saveSettings({ lm_studio_url: lmStudioUrl.value });
            await loadModels();
            checkProviderStatus();
        });
    }

    const lmStudioUrlDefault = document.getElementById('lm-studio-url-default');
    if (lmStudioUrlDefault && lmStudioUrl) {
        lmStudioUrlDefault.addEventListener('click', async () => {
            lmStudioUrl.value = LM_STUDIO_DEFAULT_URL;
            await saveSettings({ lm_studio_url: LM_STUDIO_DEFAULT_URL });
            await loadModels();
            checkProviderStatus();
        });
    }

    const ollamaUrlDefault = document.getElementById('ollama-url-default');
    if (ollamaUrlDefault && ollamaUrl) {
        ollamaUrlDefault.addEventListener('click', async () => {
            ollamaUrl.value = OLLAMA_DEFAULT_URL;
            await saveSettings({ ollama_url: OLLAMA_DEFAULT_URL });
            await loadModels();
            checkProviderStatus();
        });
    }
    
    // Test connection buttons
    const lmStudioTest = document.getElementById('lm-studio-test');
    const ollamaTest = document.getElementById('ollama-test');
    
    if (lmStudioTest) {
        lmStudioTest.addEventListener('click', testLMStudio);
    }
    
    if (ollamaTest) {
        ollamaTest.addEventListener('click', testOllama);
    }
    
    // Default model select in settings
    const defaultModelSelect = document.getElementById('default-model-select');
    if (defaultModelSelect) {
        defaultModelSelect.addEventListener('change', async () => {
            const value = defaultModelSelect.value;
            if (value) {
                const [provider, ...modelParts] = value.split(':');
                const model = modelParts.join(':');
                await saveSettings({ 
                    default_provider: provider, 
                    default_model: model 
                });
                // Sync header selector
                const headerSelect = document.getElementById('model-select');
                if (headerSelect) headerSelect.value = value;
            }
        });
    }
    
    // Header model select syncs to settings
    const headerModelSelect = document.getElementById('model-select');
    if (headerModelSelect) {
        headerModelSelect.addEventListener('change', async () => {
            const value = headerModelSelect.value;
            if (value) {
                const [provider, ...modelParts] = value.split(':');
                const model = modelParts.join(':');
                await saveSettings({ 
                    default_provider: provider, 
                    default_model: model 
                });
                // Sync settings selector
                const settingsSelect = document.getElementById('default-model-select');
                if (settingsSelect) settingsSelect.value = value;
            }
        });
    }

    const speechModelSelect = document.getElementById('speech-model-select');
    if (speechModelSelect) {
        speechModelSelect.addEventListener('change', async () => {
            const value = speechModelSelect.value;
            if (value) {
                await saveSettings({ speech_model: value });
            }
        });
    }

    const dictationLlmCheckbox = document.getElementById('dictation-llm-cleanup-enabled');
    if (dictationLlmCheckbox) {
        dictationLlmCheckbox.addEventListener('change', async () => {
            await saveSettings({
                dictation_llm_cleanup_enabled: dictationLlmCheckbox.checked,
            });
        });
    }

    const dictationInstructions = document.getElementById('dictation-instructions');
    const dictationSavedHint = document.getElementById('dictation-instructions-saved');
    if (dictationInstructions) {
        dictationInstructions.addEventListener('input', () => {
            if (dictationInstructionsDebounce) {
                clearTimeout(dictationInstructionsDebounce);
            }
            dictationInstructionsDebounce = setTimeout(async () => {
                dictationInstructionsDebounce = null;
                try {
                    await saveSettings({
                        dictation_instructions: dictationInstructions.value,
                    });
                    if (dictationSavedHint) {
                        dictationSavedHint.hidden = false;
                        setTimeout(() => {
                            dictationSavedHint.hidden = true;
                        }, 1200);
                    }
                } catch (e) {
                    debugError('SETTINGS', 'Dictation instructions save failed:', e);
                }
            }, 600);
        });
    }

    const settingsModal = document.getElementById('settings-modal');
    if (settingsModal) {
        settingsModal.addEventListener('click', (e) => {
            const btn = e.target instanceof Element ? e.target.closest('button') : null;
            const id = btn?.id || '';
            if (id === 'dictation-hotkey-toggle-select') {
                e.preventDefault();
                startDictationHotkeyCapture('toggle');
                return;
            }
            if (id === 'dictation-hotkey-cancel-select') {
                e.preventDefault();
                startDictationHotkeyCapture('cancel');
                return;
            }
            if (id === 'dictation-hotkey-toggle-clear') {
                e.preventDefault();
                void (async () => {
                    try {
                        await saveSettings({ dictation_hotkey_toggle: null });
                    } catch (err) {
                        debugError('SETTINGS', 'Hotkey clear failed:', err);
                    }
                })();
                return;
            }
            if (id === 'dictation-hotkey-cancel-clear') {
                e.preventDefault();
                void (async () => {
                    try {
                        await saveSettings({ dictation_hotkey_cancel: null });
                    } catch (err) {
                        debugError('SETTINGS', 'Hotkey clear failed:', err);
                    }
                })();
            }
        });
    }

    const dictationVocabulary = document.getElementById('dictation-vocabulary');
    const dictationVocabularySaved = document.getElementById('dictation-vocabulary-saved');
    if (dictationVocabulary) {
        dictationVocabulary.addEventListener('input', () => {
            if (dictationVocabularyDebounce) {
                clearTimeout(dictationVocabularyDebounce);
            }
            dictationVocabularyDebounce = setTimeout(async () => {
                dictationVocabularyDebounce = null;
                try {
                    await saveSettings({
                        dictation_vocabulary: dictationVocabulary.value,
                    });
                    if (dictationVocabularySaved) {
                        dictationVocabularySaved.hidden = false;
                        setTimeout(() => {
                            dictationVocabularySaved.hidden = true;
                        }, 1200);
                    }
                } catch (e) {
                    debugError('SETTINGS', 'Vocabulary save failed:', e);
                }
            }, 600);
        });
    }
    
    // Debug flags all on/off
    const allOn = document.getElementById('debug-flags-all-on');
    const allOff = document.getElementById('debug-flags-all-off');
    
    if (allOn) {
        allOn.addEventListener('click', () => {
            setAllDebugFlags(true);
            renderDebugFlags();
        });
    }
    
    if (allOff) {
        allOff.addEventListener('click', () => {
            setAllDebugFlags(false);
            renderDebugFlags();
        });
    }
}
