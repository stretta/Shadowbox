#!/usr/bin/env python3
"""
Core UI structure models for Shadowbox.

This module intentionally defines structure only:
- no rendering
- no OSC/OSCquery transport
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Parameter:
    """Conceptual parameter model derived from OSCquery metadata."""

    name: str
    osc_path: str
    type: str
    value: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Preset:
    """Read-only preset option exposed by OSCquery."""

    name: str
    identifier: Any


@dataclass
class MenuNode:
    """Tree node used to represent menu hierarchy."""

    label: str
    type: str
    children: list["MenuNode"] = field(default_factory=list)
    reference: Optional[Any] = None


@dataclass
class NavigationStack:
    """Simple stack used for screen/menu navigation state."""

    _stack: list[Any] = field(default_factory=list)

    def push(self, item: Any) -> None:
        self._stack.append(item)

    def pop(self) -> Optional[Any]:
        if not self._stack:
            return None
        return self._stack.pop()

    def current(self) -> Optional[Any]:
        if not self._stack:
            return None
        return self._stack[-1]


class Screen:
    """
    Base screen contract.

    Subclasses define visible items and input handling.
    """

    def get_items(self) -> list[Any]:
        return []

    def on_encoder(self, delta: int) -> None:
        _ = delta

    def on_press(self) -> None:
        return None


def _placeholder_leaf(label: str, reference: Optional[str] = None) -> MenuNode:
    return MenuNode(label=label, type="action", reference=reference)


def build_static_menu_tree() -> MenuNode:
    """
    Build the static hierarchy from the UI spec.

    Placeholder leaves are used until OSCquery wiring is implemented.
    """
    patch_node = MenuNode(
        label="PATCH",
        type="menu",
        children=[
            MenuNode(
                label="PRESETS",
                type="menu",
                children=[
                    _placeholder_leaf("preset_1", reference="placeholder:preset"),
                    _placeholder_leaf("preset_2", reference="placeholder:preset"),
                ],
            ),
            MenuNode(
                label="PARAMETERS",
                type="menu",
                children=[
                    _placeholder_leaf("parameter_1", reference="placeholder:param"),
                    _placeholder_leaf("parameter_2", reference="placeholder:param"),
                ],
            ),
        ],
    )

    graphs_node = MenuNode(
        label="GRAPHS",
        type="menu",
        children=[
            MenuNode(
                label="PRESETS",
                type="menu",
                children=[
                    _placeholder_leaf("graph_preset_1", reference="placeholder:preset"),
                    _placeholder_leaf("graph_preset_2", reference="placeholder:preset"),
                ],
            ),
            MenuNode(
                label="PARAMETERS",
                type="menu",
                children=[
                    _placeholder_leaf("graph_parameter_1", reference="placeholder:param"),
                    _placeholder_leaf("graph_parameter_2", reference="placeholder:param"),
                ],
            ),
        ],
    )

    audio_node = MenuNode(
        label="AUDIO",
        type="menu",
        children=[
            _placeholder_leaf("sample_rate", reference="placeholder:audio"),
            _placeholder_leaf("buffer_size", reference="placeholder:audio"),
        ],
    )

    return MenuNode(
        label="TOP",
        type="menu",
        children=[patch_node, graphs_node, audio_node],
    )


class MenuScreen(Screen):
    """
    Stack-based menu navigation using encoder + button input.

    Behavior:
    - encoder moves selection
    - button enters submenu or selects item
    - first entry in submenus is ".." for back navigation
    """

    def __init__(self, root: Optional[MenuNode] = None):
        self.root = root if root is not None else build_static_menu_tree()
        self.navigation = NavigationStack()
        self.navigation.push(self.root)
        self.selected_index = 0
        self.last_selected_leaf: Optional[MenuNode] = None

    def _current_node(self) -> MenuNode:
        current = self.navigation.current()
        if isinstance(current, MenuNode):
            return current
        return self.root

    def _has_parent(self) -> bool:
        # The root node is the first item on the stack.
        return len(self.navigation._stack) > 1

    def _visible_entries(self) -> list[MenuNode]:
        entries = list(self._current_node().children)
        if self._has_parent():
            entries = [MenuNode(label="..", type="action", reference="back")] + entries
        return entries

    def get_items(self) -> list[MenuNode]:
        return self._visible_entries()

    def on_encoder(self, delta: int) -> None:
        items = self.get_items()
        if not items or delta == 0:
            return

        step = 1 if delta > 0 else -1
        self.selected_index = (self.selected_index + step) % len(items)

    def on_press(self) -> None:
        items = self.get_items()
        if not items:
            return

        node = items[self.selected_index]

        if node.label == ".." and node.reference == "back":
            self.navigation.pop()
            self.selected_index = 0
            return

        if node.children:
            self.navigation.push(node)
            self.selected_index = 0
            return

        # Leaf selection is stored for callers to react to later.
        self.last_selected_leaf = node


def _clamp_number(value: float, minimum: Optional[float], maximum: Optional[float]) -> float:
    if minimum is not None and value < minimum:
        value = minimum
    if maximum is not None and value > maximum:
        value = maximum
    return value


def _ttid_from_root_scale(root: int, scale_intervals: list[int]) -> int:
    mask = 0
    for interval in scale_intervals:
        pc = (root + int(interval)) % 12
        mask |= 1 << pc
    return mask


class BaseParameterEditor:
    """Type-specific parameter editor contract."""

    def __init__(self, parameter: Parameter):
        self.parameter = parameter

    def on_encoder(self, delta: int) -> None:
        _ = delta

    def get_value(self) -> Any:
        return self.parameter.value

    def commit(self) -> Any:
        return self.get_value()


class NumericParameterEditor(BaseParameterEditor):
    def __init__(self, parameter: Parameter):
        super().__init__(parameter)
        self.value = parameter.value

    def on_encoder(self, delta: int) -> None:
        if delta == 0:
            return
        if self.value is None:
            self.value = self.parameter.metadata.get("min", 0)

        step = float(self.parameter.metadata.get("step", 1.0))
        minimum = self.parameter.metadata.get("min")
        maximum = self.parameter.metadata.get("max")
        new_value = float(self.value) + (step * (1 if delta > 0 else -1))
        new_value = _clamp_number(new_value, minimum, maximum)

        if self.parameter.metadata.get("integer", False):
            self.value = int(round(new_value))
        else:
            self.value = new_value

    def get_value(self) -> Any:
        return self.value


class BoolParameterEditor(BaseParameterEditor):
    """
    Bool editor is selection-based (true/false), never numeric.
    """

    OPTIONS = [False, True]

    def __init__(self, parameter: Parameter):
        super().__init__(parameter)
        self.index = 1 if bool(parameter.value) else 0

    def on_encoder(self, delta: int) -> None:
        if delta == 0:
            return
        self.index = (self.index + (1 if delta > 0 else -1)) % len(self.OPTIONS)

    def get_value(self) -> bool:
        return self.OPTIONS[self.index]


class EnumParameterEditor(BaseParameterEditor):
    """
    Enum editor uses explicit option list selection.
    """

    def __init__(self, parameter: Parameter):
        super().__init__(parameter)
        options = parameter.metadata.get("options", [])
        self.options: list[Any] = list(options)
        if not self.options:
            self.options = [parameter.value]

        if parameter.value in self.options:
            self.index = self.options.index(parameter.value)
        else:
            self.index = 0

    def on_encoder(self, delta: int) -> None:
        if delta == 0 or not self.options:
            return
        self.index = (self.index + (1 if delta > 0 else -1)) % len(self.options)

    def get_value(self) -> Any:
        return self.options[self.index]


class AudioParameterEditor(EnumParameterEditor):
    """
    Audio settings are constrained to explicit allowed values.
    """


class TtidParameterEditor(BaseParameterEditor):
    """
    TTID editor exposes root + scale selection, then derives integer mask.
    """

    def __init__(self, parameter: Parameter):
        super().__init__(parameter)
        scales = parameter.metadata.get("scales", {"major": [0, 2, 4, 5, 7, 9, 11]})
        self.scale_names = list(scales.keys()) if scales else ["major"]
        self.scales: dict[str, list[int]] = {
            str(name): [int(v) for v in values] for name, values in scales.items()
        }
        if not self.scales:
            self.scales = {"major": [0, 2, 4, 5, 7, 9, 11]}
            self.scale_names = ["major"]

        self.root = int(parameter.metadata.get("root", 0)) % 12
        preferred_scale = str(parameter.metadata.get("scale", self.scale_names[0]))
        self.scale_index = (
            self.scale_names.index(preferred_scale)
            if preferred_scale in self.scale_names
            else 0
        )
        # 0 selects root, 1 selects scale.
        self.field_index = 0

    def on_encoder(self, delta: int) -> None:
        if delta == 0:
            return

        step = 1 if delta > 0 else -1
        if self.field_index == 0:
            self.root = (self.root + step) % 12
            return

        self.scale_index = (self.scale_index + step) % len(self.scale_names)

    def on_press(self) -> None:
        # Move from root to scale; next press confirms at controller level.
        if self.field_index == 0:
            self.field_index = 1

    def get_value(self) -> int:
        scale_name = self.scale_names[self.scale_index]
        intervals = self.scales.get(scale_name, [0, 2, 4, 5, 7, 9, 11])
        return _ttid_from_root_scale(self.root, intervals)

    def get_state(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "scale": self.scale_names[self.scale_index],
            "field": "root" if self.field_index == 0 else "scale",
        }


class ParameterEditor:
    """
    Modal parameter editor controller.

    Lifecycle:
    - enter_edit_mode(parameter)
    - on_encoder(delta)
    - on_press() confirms value and exits edit mode
    """

    def __init__(self):
        self.in_edit_mode = False
        self.parameter: Optional[Parameter] = None
        self.editor: Optional[BaseParameterEditor] = None
        self.last_committed_value: Any = None

    def _create_editor(self, parameter: Parameter) -> BaseParameterEditor:
        ptype = parameter.type
        if ptype == "numeric":
            return NumericParameterEditor(parameter)
        if ptype == "bool":
            return BoolParameterEditor(parameter)
        if ptype == "enum":
            return EnumParameterEditor(parameter)
        if ptype == "ttid":
            return TtidParameterEditor(parameter)
        if ptype == "audio":
            return AudioParameterEditor(parameter)
        raise ValueError(f"Unsupported parameter type: {ptype}")

    def enter_edit_mode(self, parameter: Parameter) -> None:
        self.parameter = parameter
        self.editor = self._create_editor(parameter)
        self.in_edit_mode = True

    def on_encoder(self, delta: int) -> None:
        if not self.in_edit_mode or self.editor is None:
            return
        self.editor.on_encoder(delta)

    def on_press(self) -> Optional[Any]:
        """
        Confirm current value and exit edit mode.

        TTID uses first press to move root -> scale, then second press to confirm.
        """
        if not self.in_edit_mode or self.editor is None or self.parameter is None:
            return None

        if isinstance(self.editor, TtidParameterEditor) and self.editor.field_index == 0:
            self.editor.on_press()
            return None

        value = self.editor.commit()
        self.parameter.value = value
        self.last_committed_value = value

        self.parameter = None
        self.editor = None
        self.in_edit_mode = False
        return value

    def get_edit_state(self) -> dict[str, Any]:
        if not self.in_edit_mode or self.editor is None or self.parameter is None:
            return {"in_edit_mode": False}

        state: dict[str, Any] = {
            "in_edit_mode": True,
            "parameter_name": self.parameter.name,
            "parameter_type": self.parameter.type,
            "value": self.editor.get_value(),
        }

        if isinstance(self.editor, EnumParameterEditor):
            state["options"] = list(self.editor.options)
        if isinstance(self.editor, TtidParameterEditor):
            state.update(self.editor.get_state())

        return state
