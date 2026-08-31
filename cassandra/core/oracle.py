"""The calculation oracle: ground truth for every claim Cassandra makes.

This module is what separates Cassandra from a linter. A static analyzer emits
a warning and asks a human to judge it. Cassandra applies its proposed fix to a
copy of the workbook, recalculates the whole file, and checks two things:

  1. the target cell moved exactly as the patcher predicted
  2. nothing else moved that was not supposed to

A patch failing either check is rejected and returned to the patcher with the
reason. Nothing reaches the user that has not passed through here.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import warnings
from dataclasses import dataclass, field
from typing import Any

import formulas
import openpyxl

warnings.filterwarnings("ignore")

# Excel arithmetic is binary floating point, so 1.15 times 100 is not exactly
# 115. Comparison is relative, with an absolute floor for values near zero.
REL_TOL = 1e-9
ABS_TOL = 1e-9


@dataclass
class CalcResult:
    """Computed values for every cell in a workbook, keyed Sheet!A1."""

    values: dict[str, Any] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    unevaluated: set[str] = field(default_factory=set)

    def get(self, key: str) -> Any:
        return self.values.get(key)


@dataclass
class Delta:
    """One cell whose computed value moved between two calculations."""

    key: str
    before: Any
    after: Any


@dataclass
class Verdict:
    """The outcome of verifying one proposed patch."""

    passed: bool
    reason: str
    target: str
    predicted: Any = None
    observed: Any = None
    intended_deltas: list[Delta] = field(default_factory=list)
    collateral_deltas: list[Delta] = field(default_factory=list)

    def summary(self) -> str:
        if self.passed:
            return (
                f"VERIFIED  {self.target}  "
                f"{len(self.intended_deltas)} cells moved as predicted"
            )
        return f"REJECTED  {self.target}  {self.reason}"


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def equal(a: Any, b: Any) -> bool:
    """Tolerance aware equality. Floating point noise is not a real change."""
    na, nb = _numeric(a), _numeric(b)
    if na is not None and nb is not None:
        if na == nb:
            return True
        return abs(na - nb) <= max(ABS_TOL, REL_TOL * max(abs(na), abs(nb)))
    if a is None and b is None:
        return True
    return str(a) == str(b)


def calculate(path: str, sheet_names: list[str] | None = None) -> CalcResult:
    """Recalculate an entire workbook headlessly and return every cell value."""
    result = CalcResult()
    canonical = {name.upper(): name for name in (sheet_names or [])}

    try:
        model = formulas.ExcelModel().loads(path).finish()
        solution = model.calculate()
    except Exception as exc:
        # Surfaced to the caller as a soft failure. A workbook the oracle cannot
        # evaluate must degrade to "unverified", never to a false claim.
        result.errors["__workbook__"] = f"{type(exc).__name__}: {exc}"
        return result

    for raw_key, cell in solution.items():
        if "!" not in raw_key:
            continue
        ref = raw_key.rsplit("!", 1)[-1].replace("$", "")
        if ":" in ref:
            continue
        upper_sheet = raw_key.split("]")[-1].split("'")[0]
        sheet = canonical.get(upper_sheet.upper(), upper_sheet)
        key = f"{sheet}!{ref}"
        try:
            value = cell.value[0, 0]
        except Exception:
            result.unevaluated.add(key)
            continue
        if hasattr(value, "name"):
            value = value.name
        if isinstance(value, str) and value.startswith("#"):
            result.errors[key] = value
        result.values[key] = value
    return result


def apply_patch(src: str, patches: dict[str, str], dest: str | None = None) -> str:
    """Write patches to a copy of the workbook. The original is never touched."""
    if dest is None:
        handle, dest = tempfile.mkstemp(suffix=".xlsx", prefix="cassandra_patch_")
        os.close(handle)
    shutil.copy(src, dest)

    book = openpyxl.load_workbook(dest)
    for key, formula in patches.items():
        sheet, ref = key.split("!", 1)
        if sheet not in book.sheetnames:
            raise KeyError(f"sheet not in workbook: {sheet}")
        book[sheet][ref] = formula
    book.save(dest)
    book.close()
    return dest


def diff(before: CalcResult, after: CalcResult) -> list[Delta]:
    """Every cell whose computed value moved between two calculations."""
    deltas: list[Delta] = []
    for key in sorted(set(before.values) | set(after.values)):
        b, a = before.values.get(key), after.values.get(key)
        if not equal(b, a):
            deltas.append(Delta(key=key, before=b, after=a))
    return deltas


def verify(
    src: str,
    target: str,
    patch_formula: str,
    predicted_value: Any,
    allowed_downstream: set[str],
    baseline: CalcResult | None = None,
    sheet_names: list[str] | None = None,
) -> Verdict:
    """Prove or reject a proposed patch by recalculating the workbook.

    allowed_downstream is the target's blast radius taken from the dependency
    graph. Any cell moving outside that set is collateral damage and fails the
    patch, because it means the patch did something its author did not predict.
    """
    base = baseline if baseline is not None else calculate(src, sheet_names)
    if "__workbook__" in base.errors:
        return Verdict(
            False,
            f"baseline calculation failed: {base.errors['__workbook__']}",
            target,
        )

    patched_path = apply_patch(src, {target: patch_formula})
    try:
        after = calculate(patched_path, sheet_names)
        if "__workbook__" in after.errors:
            return Verdict(
                False,
                f"patched workbook failed to calculate: {after.errors['__workbook__']}",
                target,
            )

        observed = after.values.get(target)

        if isinstance(observed, str) and observed.startswith("#"):
            return Verdict(
                False,
                f"patch produced Excel error {observed} at {target}",
                target,
                predicted_value,
                observed,
            )

        deltas = diff(base, after)
        intended = [d for d in deltas if d.key == target or d.key in allowed_downstream]
        collateral = [
            d for d in deltas if d.key != target and d.key not in allowed_downstream
        ]

        if not any(d.key == target for d in deltas):
            return Verdict(
                False,
                f"patch changed nothing at {target}",
                target,
                predicted_value,
                observed,
                intended,
                collateral,
            )

        if predicted_value is not None and not equal(observed, predicted_value):
            return Verdict(
                False,
                f"predicted {predicted_value} at {target} but recalculation "
                f"produced {observed}",
                target,
                predicted_value,
                observed,
                intended,
                collateral,
            )

        if collateral:
            shown = ", ".join(
                f"{d.key} {d.before} to {d.after}" for d in collateral[:3]
            )
            return Verdict(
                False,
                f"patch moved {len(collateral)} cells outside the dependency "
                f"graph of {target}: {shown}",
                target,
                predicted_value,
                observed,
                intended,
                collateral,
            )

        return Verdict(
            True,
            "recalculation confirms the predicted change with no collateral movement",
            target,
            predicted_value,
            observed,
            intended,
            collateral,
        )
    finally:
        try:
            os.unlink(patched_path)
        except OSError:
            pass


def verify_latent(
    src: str,
    target: str,
    patch_formula: str,
    driver: str,
    perturbed_value: Any,
    baseline: CalcResult | None = None,
    sheet_names: list[str] | None = None,
) -> Verdict:
    """Prove a latent defect by perturbing the driver it should have referenced.

    A hardcoded constant that happens to equal the assumption it replaced
    produces the correct answer today, so no amount of recalculating the
    workbook as it stands will reveal it. It is still a real defect: the cell
    has been silently decoupled from its driver and will go stale the moment
    somebody updates the assumption.

    The proof is a differential counterfactual. Comparing the original workbook
    against the patched one, twice:

      as the workbook stands  the two must AGREE     (which is why it is latent)
      with the driver moved   the two must DIVERGE   (which is why it is a defect)

    Both conditions are required. Agreement today is what makes the defect
    invisible to every static check and to the person who wrote it. Divergence
    under perturbation is what proves the cell has been cut off from its driver.

    Note that asking only whether the target moves when the driver moves is not
    sound, because the target may still respond through an indirect path. Here
    Revenue!D12 hardcodes the growth rate yet reaches it anyway via the customer
    count, so it moves under perturbation while remaining thoroughly defective.
    Comparing the two workbooks against each other isolates the hardcode itself.
    """
    base = baseline if baseline is not None else calculate(src, sheet_names)
    if "__workbook__" in base.errors:
        return Verdict(
            False, f"baseline calculation failed: {base.errors['__workbook__']}", target
        )

    patched_now = apply_patch(src, {target: patch_formula})
    original_moved = apply_patch(src, {driver: perturbed_value})
    patched_moved = apply_patch(src, {driver: perturbed_value, target: patch_formula})

    try:
        results = {
            "patched as it stands": calculate(patched_now, sheet_names),
            "original with driver moved": calculate(original_moved, sheet_names),
            "patched with driver moved": calculate(patched_moved, sheet_names),
        }
        for label, result in results.items():
            if "__workbook__" in result.errors:
                return Verdict(
                    False,
                    f"{label} failed to calculate: {result.errors['__workbook__']}",
                    target,
                )

        today_original = base.get(target)
        today_patched = results["patched as it stands"].get(target)
        moved_original = results["original with driver moved"].get(target)
        moved_patched = results["patched with driver moved"].get(target)

        if not equal(today_original, today_patched):
            return Verdict(
                False,
                f"this is not a latent defect: the patch changes {target} from "
                f"{today_original} to {today_patched} today, so it must be "
                f"verified directly rather than by counterfactual",
                target,
                observed=today_patched,
            )

        if equal(moved_original, moved_patched):
            return Verdict(
                False,
                f"patch does not reconnect {target} to {driver}: with the driver "
                f"moved to {perturbed_value}, patched and unpatched workbooks "
                f"still agree at {moved_patched}",
                target,
                observed=moved_patched,
            )

        return Verdict(
            True,
            f"counterfactual proves a latent defect: {target} is identical at "
            f"{today_original} today, but with {driver} moved to "
            f"{perturbed_value} the unpatched workbook reports {moved_original} "
            f"while the repaired one reports {moved_patched}",
            target,
            predicted=moved_patched,
            observed=today_patched,
            intended_deltas=[Delta(target, moved_original, moved_patched)],
        )
    finally:
        for path in (patched_now, original_moved, patched_moved):
            try:
                os.unlink(path)
            except OSError:
                pass
