# CyberLab Agent v4.5
# intent/normalizer.py

import re

def normalize(text: str) -> str:
    text = text.strip()
    text = re.sub("[أإآا]", "ا", text)
    text = re.sub("[يى]", "ي", text)
    text = re.sub("ة", "ه", text)
    text = re.sub("[ً-ٟ]", "", text)
    text = re.sub(r"ال", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
