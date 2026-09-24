from __future__ import annotations

import base64
import io
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="GitHub Agent",
    page_icon="https://github.githubassets.com/favicons/favicon.svg",
    layout="wide",
    initial_sidebar_state="expanded",
)

# FULL_FILE_CONTINUES_IN_LOCAL_ARTIFACTS
