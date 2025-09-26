#!/usr/bin/env bash
python3 -m venv .venv
source .venv/bin/activate
pip3 install -q --upgrade pip
pip3 install -q -r requirements.txt

