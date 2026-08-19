from __future__ import annotations

import flet as ft

from models.field_def import FieldDef, FieldType


def _fd(ftype: FieldType) -> FieldDef:
    return FieldDef(key="k", label="K", type=ftype)


def test_is_int():
    assert _fd(FieldType.INT).is_int()
    assert not _fd(FieldType.TEXT).is_int()
    assert not _fd(FieldType.FLOAT).is_int()


def test_is_float():
    assert _fd(FieldType.FLOAT).is_float()
    assert not _fd(FieldType.INT).is_float()


def test_is_bool():
    assert _fd(FieldType.BOOL).is_bool()
    assert not _fd(FieldType.TEXT).is_bool()
    assert not _fd(FieldType.FLAG).is_bool()


def test_is_text_still_true_only_for_text():
    assert _fd(FieldType.TEXT).is_text()
    assert not _fd(FieldType.INT).is_text()
    assert not _fd(FieldType.FLOAT).is_text()
    assert not _fd(FieldType.BOOL).is_text()


def test_is_single_named_unchanged():
    assert _fd(FieldType.SINGLE_NAMED).is_single_named()
    assert not _fd(FieldType.INT).is_single_named()


def test_is_flag_unchanged():
    assert _fd(FieldType.FLAG).is_flag()
    assert not _fd(FieldType.BOOL).is_flag()
