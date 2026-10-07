"""
THE EVALS PACKAGE
A Play in One Scene
===================

PROLOGUE
--------
Model-behaviour evals built on the CCL-F scenarios.

An "eval" (short for evaluation) is a small, repeatable experiment that asks
a language model the same kinds of questions many times and scores its
answers, so we can measure how the model behaves instead of guessing. The
scenarios themselves live in the `scenarios/` package; this package holds the
experiments that reuse that evidence.

THE PLAYBILL (what lives in this package)
    authority_pressure.py   Does a model keep a correct safety judgment when
                            someone with a stake in the answer pushes back?

READER'S NOTE
    A file named `__init__.py` turns its folder into a Python "package", so
    other code can write `import evals.authority_pressure`. This one holds
    only the docstring above: no imports, no variables, no code. Each eval is
    run as its own module, e.g. `python -m evals.authority_pressure`.
"""

# EXEUNT — end of file.
