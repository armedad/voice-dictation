/**
 * Dictation SSE client: update Dictate button on hotkey start/stop.
 */

import { debugLog, debugWarn } from './debug-flags.js';
import { refreshDictationLastContext } from './context-tab.js';

let sse = null;

function setDictateButtonState(state) {
    const btn = document.getElementById('dictate-10s-btn');
    if (!btn) return;
    const defaultLabel = btn.dataset.defaultLabel || btn.textContent || 'Dictate';
    if (!btn.dataset.defaultLabel) {
        btn.dataset.defaultLabel = defaultLabel;
    }
    if (state === 'recording') {
        btn.textContent = 'Recording… (click to stop)';
    } else if (state === 'stopping') {
        btn.textContent = 'Stopping…';
    } else if (state === 'done') {
        btn.textContent = 'Done';
        setTimeout(() => {
            btn.textContent = btn.dataset.defaultLabel || 'Dictate';
        }, 1500);
    } else if (state === 'cancelled') {
        btn.textContent = 'Cancelled';
        setTimeout(() => {
            btn.textContent = btn.dataset.defaultLabel || 'Dictate';
        }, 1500);
    } else if (state === 'empty') {
        btn.textContent = 'No speech detected';
        setTimeout(() => {
            btn.textContent = btn.dataset.defaultLabel || 'Dictate';
        }, 1500);
    } else {
        btn.textContent = btn.dataset.defaultLabel || 'Dictate';
    }
}

export function startDictationEvents() {
    if (sse) return;
    sse = new EventSource('/api/dictation/events');
    sse.addEventListener('dictation', (evt) => {
        try {
            const payload = JSON.parse(evt.data || '{}');
            debugLog('DICTATION', 'SSE event', payload);
            switch (payload.type) {
                case 'dictation_start':
                    setDictateButtonState('recording');
                    break;
                case 'dictation_stop':
                case 'dictation_cancel_signal':
                    setDictateButtonState('stopping');
                    break;
                case 'dictation_done':
                    setDictateButtonState('done');
                    break;
                case 'dictation_cancelled':
                    setDictateButtonState('cancelled');
                    break;
                case 'dictation_empty':
                    setDictateButtonState('empty');
                    break;
                case 'dictation_overlap':
                    alert('Dictation overlap detected. A recording was already active.');
                    break;
                case 'dictation_context_updated':
                    refreshDictationLastContext({ resetToLatest: true }).catch((e) =>
                        debugWarn('DICTATION', 'context refresh after SSE failed', e)
                    );
                    break;
                default:
                    break;
            }
        } catch (e) {
            debugWarn('DICTATION', 'SSE parse failed', e);
        }
    });
    sse.addEventListener('error', () => {
        debugWarn('DICTATION', 'SSE connection error');
    });
}

export function stopDictationEvents() {
    if (sse) {
        sse.close();
        sse = null;
    }
}
