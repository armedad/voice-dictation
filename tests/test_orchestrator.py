"""Tests for core.orchestrator.run_pipeline (mocked adapters)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from core.models import AdapterEndpoint, VoiceDictationConfig
from core.orchestrator import run_pipeline


@pytest.fixture
def ollama_cleanup_ep() -> AdapterEndpoint:
    return AdapterEndpoint(
        provider="ollama_chat",
        baseURL="http://127.0.0.1:11434",
        model="llama3.2",
    )


@pytest.fixture
def openai_cleanup_ep() -> AdapterEndpoint:
    return AdapterEndpoint(
        provider="openai_compatible_chat",
        baseURL="https://api.openai.com/v1",
        model="gpt-4o-mini",
    )


@pytest.fixture
def faster_whisper_ep() -> AdapterEndpoint:
    return AdapterEndpoint(provider="faster_whisper", baseURL="", model="base")


@pytest.fixture
def openai_audio_ep() -> AdapterEndpoint:
    return AdapterEndpoint(
        provider="openai_compatible_audio",
        baseURL="https://api.openai.com/v1",
        model="whisper-1",
    )


class TestRunPipeline:
    async def test_raw_transcript_override_skips_stt(
        self,
        sample_wav: bytes,
        voice_config: VoiceDictationConfig,
        ollama_cleanup_ep: AdapterEndpoint,
    ) -> None:
        with (
            patch("core.orchestrator.load_config", return_value=voice_config),
            patch(
                "core.orchestrator.transcribe_faster_whisper",
                new_callable=AsyncMock,
            ) as mock_fw,
            patch(
                "core.orchestrator.cleanup_ollama_chat",
                new_callable=AsyncMock,
                return_value="cleaned",
            ) as mock_cleanup,
        ):
            out = await run_pipeline(
                sample_wav,
                raw_transcript_override="raw from override",
                cleanup_endpoint=ollama_cleanup_ep,
                cleanup_system_prompt="sys",
            )
        assert out == "cleaned"
        mock_fw.assert_not_called()
        mock_cleanup.assert_awaited_once()
        assert mock_cleanup.await_args.kwargs["system_prompt"] == "sys"

    async def test_skip_llm_cleanup_returns_raw(
        self,
        sample_wav: bytes,
        voice_config: VoiceDictationConfig,
    ) -> None:
        debug_calls: list[dict] = []

        with (
            patch("core.orchestrator.load_config", return_value=voice_config),
            patch(
                "core.orchestrator.cleanup_ollama_chat",
                new_callable=AsyncMock,
            ) as mock_cleanup,
        ):
            out = await run_pipeline(
                sample_wav,
                raw_transcript_override="keep me",
                skip_llm_cleanup=True,
                cleanup_debug_log=debug_calls.append,
            )
        assert out == "keep me"
        mock_cleanup.assert_not_called()
        assert debug_calls[0]["cleanup_llm_skip_reason"] == "skip_llm_cleanup"

    async def test_empty_transcript_returns_empty(
        self,
        sample_wav: bytes,
        voice_config: VoiceDictationConfig,
    ) -> None:
        debug_calls: list[dict] = []

        with patch("core.orchestrator.load_config", return_value=voice_config):
            out = await run_pipeline(
                sample_wav,
                raw_transcript_override="   ",
                cleanup_debug_log=debug_calls.append,
            )
        assert out == ""
        assert debug_calls[0]["cleanup_llm_skip_reason"] == "empty_raw_transcript"

    async def test_faster_whisper_path(
        self,
        sample_wav: bytes,
        voice_config: VoiceDictationConfig,
        faster_whisper_ep: AdapterEndpoint,
        ollama_cleanup_ep: AdapterEndpoint,
    ) -> None:
        with (
            patch("core.orchestrator.load_config", return_value=voice_config),
            patch(
                "core.orchestrator.transcribe_faster_whisper",
                new_callable=AsyncMock,
                return_value="raw stt",
            ) as mock_fw,
            patch(
                "core.orchestrator.cleanup_ollama_chat",
                new_callable=AsyncMock,
                return_value="clean stt",
            ),
        ):
            out = await run_pipeline(
                sample_wav,
                transcription_endpoint=faster_whisper_ep,
                cleanup_endpoint=ollama_cleanup_ep,
                transcription_initial_prompt="Terms: Zapier.",
            )
        assert out == "clean stt"
        mock_fw.assert_awaited_once()
        assert mock_fw.await_args.kwargs["initial_prompt"] == "Terms: Zapier."

    async def test_openai_audio_path(
        self,
        sample_wav: bytes,
        voice_config: VoiceDictationConfig,
        openai_audio_ep: AdapterEndpoint,
        ollama_cleanup_ep: AdapterEndpoint,
    ) -> None:
        with (
            patch("core.orchestrator.load_config", return_value=voice_config),
            patch(
                "core.orchestrator.api_key_for_transcription",
                return_value="sk-transcribe",
            ),
            patch(
                "core.orchestrator.transcribe_openai_whisper",
                new_callable=AsyncMock,
                return_value="openai raw",
            ) as mock_openai_stt,
            patch(
                "core.orchestrator.cleanup_ollama_chat",
                new_callable=AsyncMock,
                return_value="done",
            ),
        ):
            out = await run_pipeline(
                sample_wav,
                transcription_endpoint=openai_audio_ep,
                cleanup_endpoint=ollama_cleanup_ep,
            )
        assert out == "done"
        mock_openai_stt.assert_awaited_once()
        assert mock_openai_stt.await_args.args[3] == "sk-transcribe"

    async def test_ollama_cleanup_forwards_prompts(
        self,
        sample_wav: bytes,
        voice_config: VoiceDictationConfig,
        ollama_cleanup_ep: AdapterEndpoint,
    ) -> None:
        with (
            patch("core.orchestrator.load_config", return_value=voice_config),
            patch(
                "core.orchestrator.cleanup_ollama_chat",
                new_callable=AsyncMock,
                return_value="polished",
            ) as mock_cleanup,
        ):
            out = await run_pipeline(
                sample_wav,
                raw_transcript_override="uh hello",
                cleanup_endpoint=ollama_cleanup_ep,
                cleanup_system_prompt="Be concise.",
                cleanup_user_prompt="User said: uh hello",
            )
        assert out == "polished"
        mock_cleanup.assert_awaited_once_with(
            "User said: uh hello",
            ollama_cleanup_ep,
            system_prompt="Be concise.",
        )

    async def test_openai_cleanup_explicit_empty_key(
        self,
        sample_wav: bytes,
        voice_config: VoiceDictationConfig,
        openai_cleanup_ep: AdapterEndpoint,
    ) -> None:
        with (
            patch("core.orchestrator.load_config", return_value=voice_config),
            patch(
                "core.orchestrator.api_key_for_cleanup",
                return_value="should-not-use",
            ),
            patch(
                "core.orchestrator.cleanup_openai_chat",
                new_callable=AsyncMock,
                return_value="lm studio out",
            ) as mock_cleanup,
        ):
            out = await run_pipeline(
                sample_wav,
                raw_transcript_override="text",
                cleanup_endpoint=openai_cleanup_ep,
                cleanup_openai_api_key="",
            )
        assert out == "lm studio out"
        assert mock_cleanup.await_args.args[2] == ""

    async def test_unknown_transcription_provider(
        self,
        sample_wav: bytes,
        voice_config: VoiceDictationConfig,
    ) -> None:
        bad = AdapterEndpoint(provider="unknown_stt", baseURL="", model="x")
        with (
            patch("core.orchestrator.load_config", return_value=voice_config),
            pytest.raises(ValueError, match="Unknown transcription.provider"),
        ):
            await run_pipeline(sample_wav, transcription_endpoint=bad)

    async def test_unknown_cleanup_provider(
        self,
        sample_wav: bytes,
        voice_config: VoiceDictationConfig,
    ) -> None:
        bad = AdapterEndpoint(provider="unknown_cleanup", baseURL="", model="x")
        with (
            patch("core.orchestrator.load_config", return_value=voice_config),
            pytest.raises(ValueError, match="Unknown cleanup.provider"),
        ):
            await run_pipeline(
                sample_wav,
                raw_transcript_override="hi",
                cleanup_endpoint=bad,
            )

    async def test_capture_audit(
        self,
        sample_wav: bytes,
        voice_config: VoiceDictationConfig,
        ollama_cleanup_ep: AdapterEndpoint,
    ) -> None:
        audit: dict = {}
        with (
            patch("core.orchestrator.load_config", return_value=voice_config),
            patch(
                "core.orchestrator.cleanup_ollama_chat",
                new_callable=AsyncMock,
                return_value="x",
            ),
        ):
            await run_pipeline(
                sample_wav,
                raw_transcript_override="audit me",
                cleanup_endpoint=ollama_cleanup_ep,
                capture_audit=audit,
                skip_llm_cleanup=True,
            )
        assert audit["raw_transcript"] == "audit me"

    async def test_cleanup_debug_log_truncation(
        self,
        sample_wav: bytes,
        voice_config: VoiceDictationConfig,
        ollama_cleanup_ep: AdapterEndpoint,
    ) -> None:
        debug_calls: list[dict] = []
        long_prompt = "x" * 50_000

        with (
            patch("core.orchestrator.load_config", return_value=voice_config),
            patch(
                "core.orchestrator.cleanup_ollama_chat",
                new_callable=AsyncMock,
                return_value="ok",
            ),
        ):
            await run_pipeline(
                sample_wav,
                raw_transcript_override="short",
                cleanup_endpoint=ollama_cleanup_ep,
                cleanup_system_prompt=long_prompt,
                cleanup_debug_log=debug_calls.append,
            )
        assert debug_calls[0]["cleanup_system_truncated"] is True
        assert len(debug_calls[0]["cleanup_system_message"]) < 50_000

    async def test_cleanup_user_prompt_builder(
        self,
        sample_wav: bytes,
        voice_config: VoiceDictationConfig,
        ollama_cleanup_ep: AdapterEndpoint,
    ) -> None:
        with (
            patch("core.orchestrator.load_config", return_value=voice_config),
            patch(
                "core.orchestrator.cleanup_ollama_chat",
                new_callable=AsyncMock,
                return_value="built",
            ) as mock_cleanup,
        ):
            await run_pipeline(
                sample_wav,
                raw_transcript_override="raw",
                cleanup_endpoint=ollama_cleanup_ep,
                cleanup_user_prompt="ignored static",
                cleanup_user_prompt_builder=lambda r: f"built:{r}",
            )
        mock_cleanup.assert_awaited_once()
        assert mock_cleanup.await_args.args[0] == "built:raw"
