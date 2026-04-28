#!/usr/bin/env python3
"""Single-process launcher for Voice Dictation MVP (ai-frame + optional global hotkeys).

Modes:
  Default (macOS / Windows): main thread = hotkey runtime; background thread = uvicorn (no reload).
  --skip-hotkey-agent: main thread = uvicorn only (--reload allowed for dev).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path
import socket
from urllib.request import urlopen
from urllib.error import URLError, HTTPError

# #region agent log
_DEBUG_LOG_PATH = "/Users/chee/zapier ai project/.cursor/debug-55f014.log"
_DEBUG_SESSION_ID = "55f014"


def _debug_emit(
    *,
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict,
    run_id: str = "combined-startup",
) -> None:
    line = json.dumps(
        {
            "sessionId": _DEBUG_SESSION_ID,
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        },
        ensure_ascii=True,
    )
    try:
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# #endregion


def main() -> None:
    p = argparse.ArgumentParser(description="Single-process Voice Dictation MVP launcher.")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument(
        "--skip-hotkey-agent",
        action="store_true",
        help="Run only the FastAPI app on the main thread (no global hotkeys).",
    )
    p.add_argument(
        "--reload",
        action="store_true",
        help="Enable uvicorn autoreload (only with --skip-hotkey-agent).",
    )
    args = p.parse_args()

    if args.reload and not args.skip_hotkey_agent:
        print("error: --reload is only supported with --skip-hotkey-agent.", file=sys.stderr)
        sys.exit(2)

    repo_root = Path(__file__).resolve().parent
    ai_frame = repo_root / "ai-frame"
    os.chdir(ai_frame)
    ai_frame_s = str(ai_frame)
    if ai_frame_s not in sys.path:
        sys.path.insert(0, ai_frame_s)

    # #region agent log
    _debug_emit(
        hypothesis_id="H1",
        location="run_combined_app.py:main",
        message="cwd and sys.path head after ai-frame setup",
        data={"cwd": os.getcwd(), "path0": sys.path[0] if sys.path else None},
    )
    # #endregion

    host = os.environ.get("VOICE_DICTATION_HOST", "::")
    os.environ["VOICE_DICTATION_PORT"] = str(args.port)
    if args.skip_hotkey_agent:
        os.environ["VOICE_DICTATION_DISABLE_EMBEDDED_HOTKEY_AGENT"] = "1"
    else:
        os.environ.pop("VOICE_DICTATION_DISABLE_EMBEDDED_HOTKEY_AGENT", None)

    # #region agent log
    try:
        localhost_addrs = [
            addr[4][0] for addr in socket.getaddrinfo("localhost", args.port, proto=socket.IPPROTO_TCP)
        ]
    except Exception as e:  # pragma: no cover - diagnostics only
        localhost_addrs = [f"error:{type(e).__name__}:{e}"]
    _debug_emit(
        hypothesis_id="H_LOCALHOST",
        location="run_combined_app.py:main",
        message="localhost addrinfo",
        data={"port": args.port, "host": host, "localhost_addrs": localhost_addrs},
        run_id="combined-watchdog",
    )
    # #endregion

    dualstack_sock: socket.socket | None = None
    dualstack_err: str | None = None
    dualstack_v6only: int | None = None
    if host == "::":
        try:
            dualstack_sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            dualstack_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                dualstack_sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
                dualstack_v6only = dualstack_sock.getsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY)
            except OSError as e:
                dualstack_v6only = None
                dualstack_err = f"v6only:{type(e).__name__}:{e}"
            dualstack_sock.bind(("::", args.port))
            dualstack_sock.listen(2048)
        except OSError as e:
            dualstack_err = f"bind:{type(e).__name__}:{e}"
            if dualstack_sock is not None:
                dualstack_sock.close()
            dualstack_sock = None
        # #region agent log
        _debug_emit(
            hypothesis_id="H_DUALSTACK",
            location="run_combined_app.py:main",
            message="dualstack socket setup",
            data={
                "enabled": dualstack_sock is not None,
                "v6only": dualstack_v6only,
                "error": dualstack_err,
            },
            run_id="combined-watchdog",
        )
        # #endregion

    import uvicorn

    if args.skip_hotkey_agent:
        _debug_emit(
            hypothesis_id="H1",
            location="run_combined_app.py:main",
            message="uvicorn-only mode (main thread)",
            data={"port": args.port, "reload": args.reload},
        )
        uvicorn.run(
            "app.main:app",
            host=host,
            port=args.port,
            reload=args.reload,
            fd=dualstack_sock.fileno() if dualstack_sock else None,
        )
        return

    if sys.platform not in ("darwin", "win32"):
        print(
            "error: embedded global hotkeys are only supported on macOS and Windows. "
            "Use --skip-hotkey-agent for API-only.",
            file=sys.stderr,
        )
        sys.exit(1)

    def _run_uvicorn() -> None:
        # #region agent log
        _debug_emit(
            hypothesis_id="H2",
            location="run_combined_app.py:_run_uvicorn",
            message="uvicorn thread entry",
            data={"cwd": os.getcwd()},
        )
        # #endregion
        try:
            uvicorn.run(
                "app.main:app",
                host=host,
                port=args.port,
                reload=False,
                fd=dualstack_sock.fileno() if dualstack_sock else None,
            )
        except Exception as e:
            # #region agent log
            _debug_emit(
                hypothesis_id="H3",
                location="run_combined_app.py:_run_uvicorn",
                message="uvicorn.run failed",
                data={"exc_type": type(e).__name__, "exc": str(e)},
            )
            # #endregion
            raise
        # #region agent log
        _debug_emit(
            hypothesis_id="H1",
            location="run_combined_app.py:_run_uvicorn",
            message="uvicorn.run returned",
            data={},
            run_id="combined-watchdog",
        )
        # #endregion

    t = threading.Thread(target=_run_uvicorn, name="uvicorn-server", daemon=True)
    t.start()

    def _watchdog() -> None:
        while True:
            t0 = time.time()
            status = None
            err = None
            status_localhost = None
            err_localhost = None
            status_ipv6 = None
            err_ipv6 = None
            try:
                with urlopen(f"http://127.0.0.1:{args.port}/health", timeout=0.35) as resp:
                    status = resp.status
            except HTTPError as e:
                status = e.code
                err = f"HTTPError:{e.code}"
            except URLError as e:
                err = f"URLError:{getattr(e, 'reason', '')}"
            except Exception as e:  # pragma: no cover - defensive
                err = f"{type(e).__name__}:{e}"
            try:
                with urlopen(f"http://localhost:{args.port}/health", timeout=0.35) as resp:
                    status_localhost = resp.status
            except HTTPError as e:
                status_localhost = e.code
                err_localhost = f"HTTPError:{e.code}"
            except URLError as e:
                err_localhost = f"URLError:{getattr(e, 'reason', '')}"
            except Exception as e:  # pragma: no cover - defensive
                err_localhost = f"{type(e).__name__}:{e}"
            try:
                with urlopen(f"http://[::1]:{args.port}/health", timeout=0.35) as resp:
                    status_ipv6 = resp.status
            except HTTPError as e:
                status_ipv6 = e.code
                err_ipv6 = f"HTTPError:{e.code}"
            except URLError as e:
                err_ipv6 = f"URLError:{getattr(e, 'reason', '')}"
            except Exception as e:  # pragma: no cover - defensive
                err_ipv6 = f"{type(e).__name__}:{e}"
            # #region agent log
            _debug_emit(
                hypothesis_id="H2",
                location="run_combined_app.py:_watchdog",
                message="server watchdog tick",
                data={
                    "uvicorn_alive": t.is_alive(),
                    "probe_status": status,
                    "probe_error": err,
                    "probe_target": f"http://127.0.0.1:{args.port}/health",
                    "probe_status_localhost": status_localhost,
                    "probe_error_localhost": err_localhost,
                    "probe_target_localhost": f"http://localhost:{args.port}/health",
                    "probe_status_ipv6": status_ipv6,
                    "probe_error_ipv6": err_ipv6,
                    "probe_target_ipv6": f"http://[::1]:{args.port}/health",
                    "probe_elapsed_ms": int((time.time() - t0) * 1000),
                    "thread_count": len(threading.enumerate()),
                },
                run_id="combined-watchdog",
            )
            # #endregion
            time.sleep(5)

    threading.Thread(target=_watchdog, name="server-watchdog", daemon=True).start()

    if sys.platform == "darwin":
        from platform_mac.hotkey_agent import main as hotkey_main
    else:
        from platform_win.hotkey_agent import main as hotkey_main

    hotkey_main()


if __name__ == "__main__":
    main()
