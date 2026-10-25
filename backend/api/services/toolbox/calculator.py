"""Exact arithmetic for agents, evaluated over a whitelisted AST — never ``eval``.

Every operation must stay cheap whatever its arguments, because CPython runs a
huge integer operation in one call that holds the GIL: no timeout interrupts
it, and the whole server stalls. ``**`` and ``round`` therefore refuse
arguments whose cost grows with their value; the other operations only ever
see integers of bounded size, and the float functions overflow at once.
"""

from __future__ import annotations

import ast
import math
import operator
from collections.abc import Callable

from langchain_core.tools import ToolException

Number = int | float

MAX_EXPRESSION_LENGTH = 200
#: Integer results stay far below Python's 4300-digit str() limit.
MAX_RESULT_BITS = 4096
#: ``round(x, n)`` computes 10**|n|: enough digits for any allowed integer, no more.
MAX_ROUND_DIGITS = math.ceil(MAX_RESULT_BITS * math.log10(2)) + 1


def _power(base: Number, exponent: Number) -> Number:
    """``**`` that refuses results too large to compute quickly."""
    if (
        isinstance(base, int)
        and isinstance(exponent, int)
        and exponent > 0
        and abs(base).bit_length() * exponent > MAX_RESULT_BITS
    ):
        raise ValueError("the result is too large")
    return base**exponent


def _round(number: Number, ndigits: Number | None = None) -> Number:
    """``round`` with a bounded, integer ``ndigits``: round(5, -10**9) would
    compute 10**(10**9) and freeze the server."""
    if ndigits is None:
        return round(number)
    if not isinstance(ndigits, int):
        raise ValueError("round() takes a whole number of digits")
    if abs(ndigits) > MAX_ROUND_DIGITS:
        raise ValueError(f"round() takes at most {MAX_ROUND_DIGITS} digits")
    return round(number, ndigits)


_BINARY: dict[type[ast.operator], Callable[[Number, Number], Number]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: _power,
}
_UNARY: dict[type[ast.unaryop], Callable[[Number], Number]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
_FUNCTIONS: dict[str, Callable[..., Number]] = {
    "abs": abs,
    "round": _round,
    "sqrt": math.sqrt,
    "exp": math.exp,
    "log": math.log,
    "log10": math.log10,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "floor": math.floor,
    "ceil": math.ceil,
}
_CONSTANTS: dict[str, Number] = {"pi": math.pi, "e": math.e}


def _evaluate(node: ast.expr) -> Number:
    value = node.value if isinstance(node, ast.Constant) else None
    # bool is an int subclass; True + True is not arithmetic a user meant.
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    if isinstance(node, ast.Name) and node.id in _CONSTANTS:
        return _CONSTANTS[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        return _BINARY[type(node.op)](_evaluate(node.left), _evaluate(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_evaluate(node.operand))
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _FUNCTIONS
        and not node.keywords
    ):
        return _FUNCTIONS[node.func.id](*(_evaluate(arg) for arg in node.args))
    raise ValueError("only numbers, + - * / // % **, parentheses and math functions are allowed")


def evaluate(expression: str) -> Number:
    """Evaluate an arithmetic expression; a bad one raises ``ToolException``,
    which the agent receives as an error result it can correct."""
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise ToolException(f"Expressions are limited to {MAX_EXPRESSION_LENGTH} characters.")
    try:
        result = _evaluate(ast.parse(expression.strip(), mode="eval").body)
    except (SyntaxError, ArithmeticError, ValueError, TypeError) as cause:
        raise ToolException(f"Cannot evaluate {expression!r}: {cause}") from cause
    if isinstance(result, int) and result.bit_length() > MAX_RESULT_BITS:
        raise ToolException(f"Cannot evaluate {expression!r}: the result is too large")
    return result
