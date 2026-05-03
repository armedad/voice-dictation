#!/bin/bash
cd "$(dirname "$0")/.."
exec ./start.sh --skip-hotkey-agent
