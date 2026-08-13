"""Tests for in-memory specifications (domino.core.specification)."""

from __future__ import annotations

from dataclasses import dataclass

from domino import eq, ge, gt, in_, le, like, lt, ne


@dataclass
class Widget:
    name: str
    size: int
    tags: tuple[str, ...] = ()


red = Widget(name="red-1", size=10, tags=("a", "b"))
blue = Widget(name="blue-2", size=20, tags=("b",))


class TestFieldCriteria:
    def test_eq(self):
        assert eq("size", 10).is_satisfied_by(red)
        assert not eq("size", 99).is_satisfied_by(red)

    def test_ne(self):
        assert ne("size", 99).is_satisfied_by(red)
        assert not ne("size", 10).is_satisfied_by(red)

    def test_lt_le(self):
        assert lt("size", 20).is_satisfied_by(red)
        assert not lt("size", 10).is_satisfied_by(red)
        assert le("size", 10).is_satisfied_by(red)

    def test_gt_ge(self):
        assert gt("size", 5).is_satisfied_by(red)
        assert not gt("size", 10).is_satisfied_by(red)
        assert ge("size", 10).is_satisfied_by(red)

    def test_in(self):
        assert in_("size", [10, 20]).is_satisfied_by(red)
        assert not in_("size", [20, 30]).is_satisfied_by(red)

    def test_like(self):
        assert like("name", "red-%").is_satisfied_by(red)
        assert like("name", "%-1").is_satisfied_by(red)
        assert like("name", "red-_").is_satisfied_by(red)  # _ = one char
        assert not like("name", "blue-%").is_satisfied_by(red)


class TestComposition:
    def test_and(self):
        spec = gt("size", 5) & eq("name", "red-1")
        assert spec.is_satisfied_by(red)
        assert not spec.is_satisfied_by(blue)

    def test_or(self):
        spec = eq("name", "red-1") | eq("name", "blue-2")
        assert spec.is_satisfied_by(red)
        assert spec.is_satisfied_by(blue)
        assert not spec.is_satisfied_by(Widget(name="x", size=0))

    def test_not(self):
        assert (~eq("name", "red-1")).is_satisfied_by(blue)
        assert not (~eq("name", "red-1")).is_satisfied_by(red)

    def test_chained_and(self):
        spec = gt("size", 5) & lt("size", 15) & like("name", "red%")
        assert spec.is_satisfied_by(red)
        assert not spec.is_satisfied_by(blue)

    def test_mixed(self):
        # (small OR named-blue) AND size != 0
        spec = (lt("size", 15) | eq("name", "blue-2")) & ne("size", 0)
        assert spec.is_satisfied_by(red)  # size 10 < 15
        assert spec.is_satisfied_by(blue)  # name matches
        assert not spec.is_satisfied_by(Widget(name="x", size=0))  # size == 0
