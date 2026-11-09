#!/bin/zsh
cd -- "${0:A:h}"
if [[ -x /opt/anaconda3/bin/python ]]; then
    /opt/anaconda3/bin/python run_mobile.py
else
    python3 run_mobile.py
fi
