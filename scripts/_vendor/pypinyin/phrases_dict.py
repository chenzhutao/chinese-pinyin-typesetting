# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from codecs import open
import json
import os

_current_dir = os.path.dirname(os.path.realpath(__file__))
_json_path = os.path.join(_current_dir, 'phrases_dict.json')

phrases_dict = {}


def _load_phrases_dict():
    global phrases_dict
    with open(_json_path, encoding='utf8') as fp:
        phrases_dict = json.loads(fp.read())


_load_phrases_dict()

# chinese-pinyin-typesetting vendored copy: after the base dictionary loads,
# merge curated entries from a sibling data file (if present). No mmseg
# retraining here — the embedding skill calls load_phrases_dict() once, which
# retrains the segmenter on the combined vocabulary.
try:
    _curated_path = os.path.join(_current_dir, 'curated_phrases.json')
    with open(_curated_path, encoding='utf8') as _fp:
        phrases_dict.update(json.loads(_fp.read()))
except OSError:
    pass
