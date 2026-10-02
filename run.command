#!/bin/bash
# 더블클릭으로 실행할 수 있는 런처 (macOS)
cd "$(dirname "$0")"

if [ ! -d venv ]; then
    echo "최초 실행: 가상환경을 만들고 필요한 패키지를 설치합니다…"
    python3 -m venv venv
    ./venv/bin/pip install --upgrade pip
    ./venv/bin/pip install -r requirements.txt
fi

exec ./venv/bin/python transcribe_gui.py
