"""CONDITION stage executor — evaluates a boolean expression and routes to branch A or B."""

from __future__ import annotations

import ast
import operator
import time
from typing import TYPE_CHECKING, Any

from anythink.exceptions import WorkflowStageError
from anythink.workflow.models import StageResult, StageType

if TYPE_CHECKING:
    from anythink.app.context import AppContext
    from anythink.workflow.models import Stage, WorkflowCallbacks, WorkflowState

# Mapping from AST comparison/operator node types to callables.
# Only arithmetic and comparison ops are allowed — no function calls, no imports.
_COMPARE_OPS: dict[type, Any] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
    ast.Is: operator.is_,
    ast.IsNot: operator.is_not,
}


def _safe_eval(expr: str, context: dict[str, Any]) -> bool:
    """Evaluate a simple boolean expression against *context*.

    Supports: comparisons, boolean ops (and/or/not), attribute-style dot-path
    lookups (``stage_1.field``), subscripts, and string/numeric literals.
    No function calls, no imports, no arbitrary Python.
    """
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError as exc:
        raise WorkflowStageError(
            f"Condition syntax error in '{expr}': {exc}",
            stage_id="condition",
            user_message=f"Invalid condition expression: {expr}",
        ) from exc

    return bool(_eval_node(tree.body, context))


def _eval_node(node: ast.AST, ctx: dict[str, Any]) -> Any:
    """Recursively evaluate an AST node against *ctx*."""
    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.Name):
        name = node.id
        if name in ctx:
            return ctx[name]
        # Underscore-encoded dot path: "stage_1_field" → look for "stage_1.field"
        for key, value in ctx.items():
            if key.replace(".", "_") == name:
                return value
        # Boolean keywords
        if name == "True":
            return True
        if name == "False":
            return False
        if name == "None":
            return None
        return None

    if isinstance(node, ast.Attribute):
        # Handles dot-notation: stage_1.email_list → ctx["stage_1.email_list"]
        if isinstance(node.value, ast.Name):
            key = f"{node.value.id}.{node.attr}"
            if key in ctx:
                return ctx[key]
        obj = _eval_node(node.value, ctx)
        if obj is not None and hasattr(obj, node.attr):
            return getattr(obj, node.attr)
        return None

    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, ctx)
        result = True
        for op, comparator in zip(node.ops, node.comparators, strict=False):
            right = _eval_node(comparator, ctx)
            op_fn = _COMPARE_OPS.get(type(op))
            if op_fn is None:
                raise WorkflowStageError(
                    f"Unsupported comparison operator: {type(op).__name__}",
                    stage_id="condition",
                    user_message="Condition uses an unsupported comparison operator.",
                )
            try:
                result = result and op_fn(left, right)
            except TypeError:
                result = False
            left = right
        return result

    if isinstance(node, ast.BoolOp):
        values = [_eval_node(v, ctx) for v in node.values]
        if isinstance(node.op, ast.And):
            return all(values)
        return any(values)

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _eval_node(node.operand, ctx)

    if isinstance(node, ast.Subscript):
        obj = _eval_node(node.value, ctx)
        key = _eval_node(node.slice, ctx)
        try:
            return obj[key]
        except (KeyError, IndexError, TypeError):
            return None

    # Fall back to literal_eval for numbers, strings, lists, dicts, etc.
    try:
        return ast.literal_eval(ast.unparse(node))
    except (ValueError, TypeError):
        return None


async def execute(
    stage: Stage,
    state: WorkflowState,
    ctx: AppContext,
    callbacks: WorkflowCallbacks,
) -> StageResult:
    """Evaluate the condition expression and return branch 'a' (True) or 'b' (False)."""
    start = time.monotonic()
    error: str | None = None

    try:
        result = _safe_eval(stage.condition_expr, state.accumulated_results)
        branch = "a" if result else "b"
    except WorkflowStageError as exc:
        branch = "b"
        error = str(exc)

    return StageResult(
        stage_id=stage.id,
        stage_type=StageType.CONDITION,
        output={"branch": branch, "condition_result": branch == "a"},
        raw_content=f"branch_{branch}",
        duration_s=time.monotonic() - start,
        error=error,
    )
