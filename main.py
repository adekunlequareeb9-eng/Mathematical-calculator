import ast
import json
import math
import operator
import os
import re
import tempfile
import time
from fractions import Fraction

try:
    import sympy
    from sympy.parsing.sympy_parser import (
        parse_expr,
        standard_transformations,
        implicit_multiplication_application,
    )
    _SYMPY_TRANSFORMATIONS = standard_transformations + (implicit_multiplication_application,)
    SYMPY_AVAILABLE = True
except Exception:
    SYMPY_AVAILABLE = False

from kivy.app import App
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.graphics import Color, Line
from kivy.animation import Animation


Window.clearcolor = (0.04, 0.04, 0.06, 1)

APP_VERSION = "1.7"


class MathEngine:
    """Safe AST-based expression evaluator.

    Only a fixed set of operators, functions and constants are supported,
    so arbitrary code can never be executed through eval().
    """

    operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.Mod: operator.mod,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    constants = {
        "pi": math.pi,
        "e": math.e,
    }

    def __init__(self):
        self.angle_mode = "deg"  # "deg", "rad", or "grad"

        self.functions = {
            "sqrt": self._sqrt,
            "log": self._log10,
            "ln": self._ln,
            "logb": self._log_base,
            "fact": self._factorial,
            "abs": abs,
            "sin": lambda x: self._trig(math.sin, x),
            "cos": lambda x: self._trig(math.cos, x),
            "tan": lambda x: self._trig(math.tan, x),
            "asin": lambda x: self._inverse_trig(math.asin, x),
            "acos": lambda x: self._inverse_trig(math.acos, x),
            "atan": lambda x: self._inverse_trig(math.atan, x),
        }

    def _to_radians(self, x):
        if self.angle_mode == "deg":
            return math.radians(x)
        if self.angle_mode == "grad":
            return x * math.pi / 200
        return x

    def _from_radians(self, x):
        if self.angle_mode == "deg":
            return math.degrees(x)
        if self.angle_mode == "grad":
            return x * 200 / math.pi
        return x

    def _trig(self, func, x):
        return func(self._to_radians(x))

    def _inverse_trig(self, func, x):
        return self._from_radians(func(x))

    def _sqrt(self, x):
        if x < 0:
            raise ValueError("Cannot take square root of a negative number")
        return math.sqrt(x)

    def _log10(self, x):
        if x <= 0:
            raise ValueError("Logarithm requires a positive number")
        return math.log10(x)

    def _ln(self, x):
        if x <= 0:
            raise ValueError("Logarithm requires a positive number")
        return math.log(x)

    def _log_base(self, x, base):
        if x <= 0:
            raise ValueError("Logarithm requires a positive number")
        if base <= 0 or base == 1:
            raise ValueError("Logarithm base must be positive and not 1")
        return math.log(x) / math.log(base)

    def _factorial(self, x):
        if x < 0 or int(x) != x:
            raise ValueError("Factorial requires a non-negative whole number")
        if x > 170:
            raise ValueError("Number too large for factorial")
        return math.factorial(int(x))

    def evaluate(self, expression, variables=None, trace=None):
        self._variables = variables or {}

        expression = expression.strip()
        expression = expression.replace("×", "*")
        expression = expression.replace("÷", "/")
        expression = expression.replace("^", "**")
        expression = expression.replace("π", "pi")
        expression = self._insert_implicit_multiplication(expression)

        if not expression:
            raise ValueError("Empty expression")

        tree = ast.parse(expression, mode="eval")
        return self._solve(tree.body, trace)

    @staticmethod
    def _insert_implicit_multiplication(expression):
        """Lets people type '3x' or '2(x+1)' instead of forcing an
        explicit '3*x' / '2*(x+1)' everywhere - common calculator shorthand."""
        # digit directly followed by a letter, e.g. 3x -> 3*x, 2pi -> 2*pi
        expression = re.sub(r"(\d)([a-zA-Z])", r"\1*\2", expression)
        # digit directly followed by an opening parenthesis, e.g. 2( -> 2*(
        expression = re.sub(r"(\d)(\()", r"\1*\2", expression)
        # closing parenthesis directly followed by a digit, letter or '(',
        # e.g. (x+1)(x-1) -> (x+1)*(x-1), (x+1)2 -> (x+1)*2
        expression = re.sub(r"(\))([0-9a-zA-Z(])", r"\1*\2", expression)
        # a bare variable (x or y) directly followed by '(' - but NOT the
        # last letter of a known function name like sin(, sqrt(, etc.
        expression = re.sub(r"(?<![a-zA-Z])([xy])\(", r"\1*(", expression)
        return expression

    _OP_SYMBOLS = {
        ast.Add: "+", ast.Sub: "-", ast.Mult: "\u00d7",
        ast.Div: "\u00f7", ast.Pow: "^", ast.Mod: "%",
    }

    def _solve(self, node, trace=None):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError("Invalid value")

        if isinstance(node, ast.BinOp):
            operation = self.operators.get(type(node.op))
            if operation is None:
                raise ValueError("Unsupported operation")

            left = self._solve(node.left, trace)
            right = self._solve(node.right, trace)

            if isinstance(node.op, (ast.Div, ast.Mod)) and right == 0:
                raise ZeroDivisionError("Cannot divide by zero")

            if isinstance(node.op, ast.Pow) and abs(right) > 1000:
                raise ValueError("Power too large")

            result = operation(left, right)

            if trace is not None:
                symbol = self._OP_SYMBOLS.get(type(node.op), "?")
                trace.append(
                    f"{format_plain_number(left)} {symbol} "
                    f"{format_plain_number(right)} = {format_plain_number(result)}"
                )

            return result

        if isinstance(node, ast.UnaryOp):
            operation = self.operators.get(type(node.op))
            if operation is None:
                raise ValueError("Unsupported operation")
            operand = self._solve(node.operand, trace)
            result = operation(operand)
            if trace is not None and isinstance(node.op, ast.USub):
                trace.append(f"negate {format_plain_number(operand)} = {format_plain_number(result)}")
            return result

        if isinstance(node, ast.Name):
            if node.id in self.constants:
                return self.constants[node.id]
            if node.id in getattr(self, "_variables", {}):
                return self._variables[node.id]
            raise ValueError("Unknown constant")

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Invalid function")

            function = self.functions.get(node.func.id)
            if function is None:
                raise ValueError("Unknown function")

            arguments = [self._solve(arg, trace) for arg in node.args]
            result = function(*arguments)

            if trace is not None:
                args_str = ", ".join(format_plain_number(a) for a in arguments)
                trace.append(f"{node.func.id}({args_str}) = {format_plain_number(result)}")

            return result

        raise ValueError("Invalid expression")


# ----------------------------------------------------------------------
# Number theory (Phase 3) - pure Python, no new dependencies
# ----------------------------------------------------------------------

def is_prime(n):
    n = int(n)
    if n < 2:
        return False
    if n in (2, 3):
        return True
    if n % 2 == 0:
        return False
    i = 3
    while i * i <= n:
        if n % i == 0:
            return False
        i += 2
    return True


def prime_factorize(n):
    n = int(n)
    if n < 2:
        raise ValueError("Enter a whole number greater than 1")

    factors = []
    d = 2
    while d * d <= n:
        count = 0
        while n % d == 0:
            n //= d
            count += 1
        if count:
            factors.append((d, count))
        d += 1
    if n > 1:
        factors.append((n, 1))
    return factors


def format_prime_factors(factors):
    return " x ".join(
        f"{base}^{exp}" if exp > 1 else f"{base}"
        for base, exp in factors
    )


def gcd_of(a, b):
    return math.gcd(int(a), int(b))


def lcm_of(a, b):
    a, b = int(a), int(b)
    if a == 0 or b == 0:
        return 0
    return abs(a * b) // math.gcd(a, b)


def simplify_fraction(numerator, denominator):
    if denominator == 0:
        raise ZeroDivisionError("Cannot divide by zero")
    frac = Fraction(int(numerator), int(denominator))
    return frac.numerator, frac.denominator


# --- Step-narrating versions for the "Steps" feature. Kept separate from
# the plain versions above so existing call sites are untouched. ---

def is_prime_steps(n):
    n = int(n)
    steps = []
    if n < 2:
        steps.append(f"{n} is less than 2, so it isn't prime")
        return False, steps
    if n in (2, 3):
        steps.append(f"{n} is one of the smallest primes")
        return True, steps
    if n % 2 == 0:
        steps.append(f"{n} is even, so it's divisible by 2 - not prime")
        return False, steps

    limit = math.isqrt(n)
    steps.append(f"Only need to check odd divisors up to \u221a{n} \u2248 {limit}")
    i = 3
    shown = 0
    while i * i <= n:
        if n % i == 0:
            steps.append(f"{n} \u00f7 {i} = {n // i} exactly - not prime")
            return False, steps
        if shown < 6:
            steps.append(f"{n} \u00f7 {i} is not a whole number")
            shown += 1
        elif shown == 6:
            steps.append("... continuing to check the remaining divisors")
            shown += 1
        i += 2
    steps.append(f"No divisors found up to \u221a{n} - {n} is prime")
    return True, steps


def prime_factorize_steps(n):
    n = int(n)
    if n < 2:
        raise ValueError("Enter a whole number greater than 1")

    steps = []
    original = n
    factors = []
    d = 2
    while d * d <= n:
        count = 0
        while n % d == 0:
            steps.append(f"{n} \u00f7 {d} = {n // d}")
            n //= d
            count += 1
        if count:
            factors.append((d, count))
        d += 1
    if n > 1:
        factors.append((n, 1))
        if n != original:
            steps.append(f"{n} is prime - stop here")
    return factors, steps


def gcd_steps(a, b):
    a, b = int(a), int(b)
    steps = []
    x, y = a, b
    while y != 0:
        q, r = divmod(x, y)
        steps.append(f"{x} = {y} \u00d7 {q} + {r}")
        x, y = y, r
    steps.append(f"GCD({a}, {b}) = {x}")
    return x, steps


def lcm_steps(a, b):
    a, b = int(a), int(b)
    if a == 0 or b == 0:
        return 0, ["One of the numbers is 0, so the LCM is 0"]
    g, gcd_trace = gcd_steps(a, b)
    result = abs(a * b) // g
    steps = gcd_trace + [
        f"LCM({a}, {b}) = |{a} \u00d7 {b}| \u00f7 GCD({a},{b}) "
        f"= {abs(a * b)} \u00f7 {g} = {result}"
    ]
    return result, steps


def simplify_fraction_steps(numerator, denominator):
    if denominator == 0:
        raise ZeroDivisionError("Cannot divide by zero")
    numerator, denominator = int(numerator), int(denominator)
    g = math.gcd(abs(numerator), abs(denominator))
    frac = Fraction(numerator, denominator)
    steps = [
        f"GCD({numerator}, {denominator}) = {g}",
        f"{numerator} \u00f7 {g} = {frac.numerator}",
        f"{denominator} \u00f7 {g} = {frac.denominator}",
    ]
    return (frac.numerator, frac.denominator), steps


def to_mixed_number(numerator, denominator):
    """Converts an improper fraction to a mixed number, e.g. 5/3 -> (1, 2, 3)
    meaning '1 2/3'. Returns None for the whole-number part if the
    fraction is already proper (abs value < 1)."""
    if denominator == 0:
        raise ZeroDivisionError("Cannot divide by zero")

    frac = Fraction(int(numerator), int(denominator))
    sign = -1 if frac < 0 else 1
    whole = abs(frac.numerator) // frac.denominator
    remainder = abs(frac.numerator) % frac.denominator

    if remainder == 0:
        return sign * whole, 0, 1

    return sign * whole, remainder, frac.denominator


def format_mixed_number(whole, remainder_numerator, remainder_denominator):
    if remainder_numerator == 0:
        return str(whole)
    if whole == 0:
        return f"{remainder_numerator}/{remainder_denominator}"
    sign = "-" if whole < 0 else ""
    return f"{sign}{abs(whole)} {remainder_numerator}/{remainder_denominator}"


# ----------------------------------------------------------------------
# Algebra - equation solving via numerical coefficient extraction
# (no symbolic engine needed: we sample the user's expression at a few
# points and fit the polynomial coefficients from those samples)
# ----------------------------------------------------------------------

def _equation_sides(equation):
    if "=" not in equation:
        raise ValueError("Equation must contain '='")
    left, right = equation.split("=", 1)
    return left.strip(), right.strip()


def _format_linear_form(coefficient, constant):
    """Formats a×x + b as a clean string like '2x - 4' instead of the
    awkward '2x + -4'."""
    coeff_str = format_plain_number(coefficient)
    if constant == 0:
        return f"{coeff_str}x"
    sign = "+" if constant > 0 else "-"
    return f"{coeff_str}x {sign} {format_plain_number(abs(constant))}"


def _format_quadratic_form(a, b, c):
    """Formats a×x² + b×x + c as a clean string like 'x² - 5x + 6'
    instead of the awkward '1x² + -5x + 6'."""
    a_num = format_plain_number(abs(a))
    a_term = "x\u00b2" if abs(a) == 1 else f"{a_num}x\u00b2"
    if a < 0:
        a_term = "-" + a_term

    parts = [a_term]

    if b != 0:
        b_num = format_plain_number(abs(b))
        b_term = "x" if abs(b) == 1 else f"{b_num}x"
        parts.append(("+ " if b > 0 else "- ") + b_term)

    if c != 0:
        parts.append(("+ " if c > 0 else "- ") + format_plain_number(abs(c)))

    return " ".join(parts)


def solve_linear(engine, equation, steps=None):
    left, right = _equation_sides(equation)

    def f(x):
        return engine.evaluate(f"({left})-({right})", variables={"x": x})

    y0 = f(0)
    y1 = f(1)
    y2 = f(2)

    a = y1 - y0
    if abs((y2 - y1) - a) > 1e-6 * (abs(a) + 1):
        raise ValueError("That doesn't look linear in x")

    if abs(a) < 1e-12:
        if abs(y0) < 1e-9:
            raise ValueError("Infinitely many solutions (always true)")
        raise ValueError("No solution")

    result = -y0 / a
    b = y0

    if steps is not None:
        steps.append(f"Start: {equation}")
        steps.append(
            f"Move everything to one side so it says '(a number)\u00d7x plus "
            f"(a number) = 0'. Here that's: {_format_linear_form(a, b)} = 0"
        )
        if b != 0:
            if b > 0:
                move_phrase = f"Subtract {format_plain_number(b)} from both sides"
            else:
                move_phrase = f"Add {format_plain_number(abs(b))} to both sides"
            steps.append(
                f"{move_phrase} to get x's term alone: "
                f"{format_plain_number(a)}x = {format_plain_number(-b)}"
            )
        steps.append(
            f"Divide both sides by {format_plain_number(a)} to get x by "
            f"itself: x = {format_plain_number(-b)} \u00f7 {format_plain_number(a)} "
            f"= {format_plain_number(result)}"
        )

    return result


def solve_quadratic(engine, equation, steps=None):
    left, right = _equation_sides(equation)

    def f(x):
        return engine.evaluate(f"({left})-({right})", variables={"x": x})

    y_m1 = f(-1)
    y0 = f(0)
    y1 = f(1)

    coeff_a = (y1 - 2 * y0 + y_m1) / 2
    coeff_b = (y1 - y_m1) / 2
    coeff_c = y0

    if abs(coeff_a) < 1e-9:
        if abs(coeff_b) < 1e-12:
            raise ValueError("No unique solution")
        result = [-coeff_c / coeff_b]
        if steps is not None:
            steps.append("There's no x\u00b2 in this equation once simplified - it's actually a simple, one-solution equation")
            steps.append(f"x = {format_plain_number(result[0])}")
        return result

    discriminant = coeff_b * coeff_b - 4 * coeff_a * coeff_c
    a_str = format_plain_number(coeff_a)
    b_str = format_plain_number(coeff_b)
    c_str = format_plain_number(coeff_c)

    if steps is not None:
        steps.append(f"Start: {equation}")
        steps.append(
            f"Move everything to one side, in the form "
            f"(a number)\u00d7x\u00b2 + (a number)\u00d7x + (a number) = 0. "
            f"Here that's: {_format_quadratic_form(coeff_a, coeff_b, coeff_c)} = 0"
        )
        steps.append(
            "There's a standard formula for exactly this shape of equation: "
            "x = (-b \u00b1 \u221a(b\u00b2-4ac)) \u00f7 (2a) - using the three numbers "
            "above as a, b, and c"
        )
        steps.append(
            f"First work out what's under the square root sign: "
            f"b\u00b2 - 4ac = {b_str}\u00b2 - 4\u00d7{a_str}\u00d7{c_str} "
            f"= {format_plain_number(discriminant)}"
        )

    if discriminant < 0:
        if steps is not None:
            steps.append(
                "That number came out negative, and you can't take the "
                "square root of a negative number (not with ordinary "
                "numbers, anyway) - so there's no real answer to this one"
            )
        raise ValueError("No real roots")

    sqrt_d = math.sqrt(discriminant)
    x1 = (-coeff_b + sqrt_d) / (2 * coeff_a)
    x2 = (-coeff_b - sqrt_d) / (2 * coeff_a)
    result = sorted({round(x1, 10), round(x2, 10)})

    if steps is not None:
        steps.append(
            f"That's positive, so there'll be two answers. Its square "
            f"root is {format_plain_number(sqrt_d)}"
        )
        steps.append(
            f"Plug everything into the formula: x = (-({b_str}) \u00b1 "
            f"{format_plain_number(sqrt_d)}) \u00f7 (2\u00d7{a_str})"
        )
        steps.append(
            "The \u00b1 means do it once with + and once with - to get "
            "both answers: x = " + " or x = ".join(format_plain_number(r) for r in result)
        )

    return result


def solve_simultaneous(engine, equation1, equation2, steps=None):
    def make_f(equation):
        left, right = _equation_sides(equation)

        def f(x, y):
            return engine.evaluate(f"({left})-({right})", variables={"x": x, "y": y})

        return f

    f1 = make_f(equation1)
    f2 = make_f(equation2)

    c1 = -f1(0, 0)
    a1 = f1(1, 0) - f1(0, 0)
    b1 = f1(0, 1) - f1(0, 0)

    c2 = -f2(0, 0)
    a2 = f2(1, 0) - f2(0, 0)
    b2 = f2(0, 1) - f2(0, 0)

    det = a1 * b2 - a2 * b1
    if abs(det) < 1e-12:
        if steps is not None:
            steps.append("The two equations are parallel or identical - no unique solution")
        raise ValueError("No unique solution (equations are parallel or identical)")

    x = (c1 * b2 - c2 * b1) / det
    y = (a1 * c2 - a2 * c1) / det

    if steps is not None:
        a1_str, b1_str, c1_str = format_plain_number(a1), format_plain_number(b1), format_plain_number(c1)
        a2_str, b2_str, c2_str = format_plain_number(a2), format_plain_number(b2), format_plain_number(c2)
        steps.append(f"Equation 1, simplified: {a1_str}\u00d7x + {b1_str}\u00d7y = {c1_str}")
        steps.append(f"Equation 2, simplified: {a2_str}\u00d7x + {b2_str}\u00d7y = {c2_str}")
        steps.append(
            "With two equations and two unknowns (x and y), there's a "
            "shortcut formula that solves both at once by combining the "
            "numbers above - you don't need to follow the formula itself, "
            "just know it takes those 6 numbers and produces x and y directly"
        )
        steps.append(
            f"That gives: x = {format_plain_number(x)}, y = {format_plain_number(y)}"
        )
        steps.append(
            "You can check this yourself: put these x and y values back "
            "into both original equations and they should both come out true"
        )

    return x, y


# ----------------------------------------------------------------------
# Calculus - numerical methods (Phase 4). No symbolic engine, so results
# are close numerical approximations rather than exact algebraic forms.
# ----------------------------------------------------------------------

def numerical_derivative(engine, expression, x0, h=1e-5):
    def f(x):
        return engine.evaluate(expression, variables={"x": x})

    return (f(x0 + h) - f(x0 - h)) / (2 * h)


def numerical_second_derivative(engine, expression, x0, h=1e-4):
    def f(x):
        return engine.evaluate(expression, variables={"x": x})

    return (f(x0 + h) - 2 * f(x0) + f(x0 - h)) / (h * h)


def numerical_integral(engine, expression, a, b, n=1000):
    if n % 2 == 1:
        n += 1

    def f(x):
        return engine.evaluate(expression, variables={"x": x})

    h = (b - a) / n
    total = f(a) + f(b)
    for i in range(1, n):
        x = a + i * h
        total += (4 if i % 2 == 1 else 2) * f(x)
    return total * h / 3


def numerical_limit(engine, expression, x0, h=1e-6):
    def f(x):
        return engine.evaluate(expression, variables={"x": x})

    left = f(x0 - h)
    right = f(x0 + h)

    if abs(left - right) > 1e-3 * (abs(left) + abs(right) + 1):
        raise ValueError("Limit does not appear to converge from both sides")

    return (left + right) / 2


# ----------------------------------------------------------------------
# Symbolic algebra & calculus, via sympy - pure Python, no C extensions,
# so no cross-compilation risk for the Android build. Kept fully separate
# from the numerical methods above: if sympy is unavailable for any
# reason, SYMPY_AVAILABLE is False and every function below raises a
# clear, friendly error instead of crashing the app.
# ----------------------------------------------------------------------

def _require_sympy():
    if not SYMPY_AVAILABLE:
        raise ValueError("Symbolic math isn't available on this device")


def _sympy_local_dict():
    x, y = sympy.symbols("x y")
    return {
        "x": x,
        "y": y,
        "pi": sympy.pi,
        "e": sympy.E,
        "sqrt": sympy.sqrt,
        "sin": sympy.sin,
        "cos": sympy.cos,
        "tan": sympy.tan,
        "asin": sympy.asin,
        "acos": sympy.acos,
        "atan": sympy.atan,
        # Match our own calculator's convention: "log" = base 10,
        # "ln" = natural log (sympy's native log() defaults to natural).
        "log": lambda z: sympy.log(z, 10),
        "ln": sympy.log,
        "logb": lambda z, b: sympy.log(z, b),
        "fact": sympy.factorial,
        "abs": sympy.Abs,
    }


def sympy_parse(expression):
    _require_sympy()
    expression = expression.strip()
    expression = expression.replace("×", "*")
    expression = expression.replace("÷", "/")
    expression = expression.replace("^", "**")
    expression = expression.replace("π", "pi")
    return parse_expr(
        expression,
        transformations=_SYMPY_TRANSFORMATIONS,
        local_dict=_sympy_local_dict(),
    )


def format_sympy(value):
    return str(value).replace("**", "^")


def symbolic_solve(equation, solve_for="x"):
    """Solves ANY equation exactly - any degree, trig, logs, etc. - not
    just linear/quadratic/2-variable-linear like the numeric solver.
    Can also return complex solutions where they exist.

    solve_for lets you solve an equation with two unknowns (e.g.
    '6x+15-3y=0') for whichever one you actually want isolated - the
    other variable is treated as a parameter and appears in the answer,
    e.g. solving for y gives 'y = 2x + 5'."""
    _require_sympy()
    if "=" not in equation:
        raise ValueError("Equation must contain '='")

    solve_for = solve_for.strip() or "x"
    left, right = equation.split("=", 1)
    target = sympy.symbols(solve_for)
    lhs = sympy_parse(left)
    rhs = sympy_parse(right)

    if target not in lhs.free_symbols and target not in rhs.free_symbols:
        raise ValueError(f"'{solve_for}' doesn't appear in that equation")

    try:
        solutions = sympy.solve(sympy.Eq(lhs, rhs), target)
    except NotImplementedError:
        raise ValueError("No exact solution found - try a numeric Solve option instead")

    if not solutions:
        raise ValueError("No solution found")

    return [format_sympy(s) for s in solutions]


def symbolic_simplify(expression):
    _require_sympy()
    return format_sympy(sympy.simplify(sympy_parse(expression)))


def symbolic_expand(expression):
    _require_sympy()
    return format_sympy(sympy.expand(sympy_parse(expression)))


def symbolic_derivative(expression, order=1):
    _require_sympy()
    x = sympy.symbols("x")
    expr = sympy_parse(expression)
    try:
        return format_sympy(sympy.diff(expr, x, order))
    except NotImplementedError:
        raise ValueError("No exact derivative found")


def symbolic_integral(expression, a=None, b=None):
    _require_sympy()
    x = sympy.symbols("x")
    expr = sympy_parse(expression)
    try:
        if a is None or b is None:
            return format_sympy(sympy.integrate(expr, x))
        return format_sympy(
            sympy.integrate(expr, (x, sympy.sympify(a), sympy.sympify(b)))
        )
    except NotImplementedError:
        raise ValueError("No exact integral found - try the numeric Integrate option instead")


# ----------------------------------------------------------------------
# Matrices & Vectors (Phase 5) - pure Python, Gaussian elimination etc.
# ----------------------------------------------------------------------

def parse_matrix(text):
    text = text.strip()
    if not text:
        raise ValueError("Enter a matrix, e.g. 1,2;3,4")

    rows = [r for r in text.split(";") if r.strip() != ""]
    matrix = []
    width = None
    for row in rows:
        values = [float(v.strip()) for v in row.split(",")]
        if width is None:
            width = len(values)
        elif len(values) != width:
            raise ValueError("Every row must have the same number of values")
        matrix.append(values)
    return matrix


def matrix_add(a, b, sign=1):
    if len(a) != len(b) or len(a[0]) != len(b[0]):
        raise ValueError("Matrices must be the same size")
    return [
        [a[i][j] + sign * b[i][j] for j in range(len(a[0]))]
        for i in range(len(a))
    ]


def matrix_multiply(a, b):
    if len(a[0]) != len(b):
        raise ValueError("Columns of A must match rows of B")
    rows_a, cols_a, cols_b = len(a), len(a[0]), len(b[0])
    result = [[0.0] * cols_b for _ in range(rows_a)]
    for i in range(rows_a):
        for j in range(cols_b):
            result[i][j] = sum(a[i][k] * b[k][j] for k in range(cols_a))
    return result


def matrix_transpose(a):
    return [list(row) for row in zip(*a)]


def matrix_determinant(a):
    n = len(a)
    if any(len(row) != n for row in a):
        raise ValueError("Determinant requires a square matrix")

    if n == 1:
        return a[0][0]
    if n == 2:
        return a[0][0] * a[1][1] - a[0][1] * a[1][0]

    total = 0.0
    for col in range(n):
        minor = [row[:col] + row[col + 1:] for row in a[1:]]
        sign = 1 if col % 2 == 0 else -1
        total += sign * a[0][col] * matrix_determinant(minor)
    return total


def matrix_inverse(a):
    n = len(a)
    if any(len(row) != n for row in a):
        raise ValueError("Inverse requires a square matrix")

    aug = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(a)]

    for col in range(n):
        pivot_row = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot_row][col]) < 1e-12:
            raise ValueError("Matrix is singular (no inverse)")
        aug[col], aug[pivot_row] = aug[pivot_row], aug[col]

        pivot = aug[col][col]
        aug[col] = [v / pivot for v in aug[col]]

        for r in range(n):
            if r != col:
                factor = aug[r][col]
                aug[r] = [aug[r][k] - factor * aug[col][k] for k in range(2 * n)]

    return [row[n:] for row in aug]


def matrix_rank(a):
    m = [row[:] for row in a]
    rows, cols = len(m), len(m[0])
    rank = 0
    for col in range(cols):
        pivot_row = None
        for r in range(rank, rows):
            if abs(m[r][col]) > 1e-9:
                pivot_row = r
                break
        if pivot_row is None:
            continue
        m[rank], m[pivot_row] = m[pivot_row], m[rank]
        pivot = m[rank][col]
        m[rank] = [v / pivot for v in m[rank]]
        for r in range(rows):
            if r != rank:
                factor = m[r][col]
                m[r] = [m[r][k] - factor * m[rank][k] for k in range(cols)]
        rank += 1
        if rank == rows:
            break
    return rank


def format_plain_number(v):
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, float):
        return f"{v:.6g}"
    return str(v)


def format_matrix(m):
    return "\n".join(
        "[" + ", ".join(format_plain_number(v) for v in row) + "]"
        for row in m
    )


def parse_vector(text):
    text = text.strip()
    if not text:
        raise ValueError("Enter a vector, e.g. 1,2,3")
    return [float(v.strip()) for v in text.split(",")]


def vector_add(a, b, sign=1):
    if len(a) != len(b):
        raise ValueError("Vectors must be the same length")
    return [a[i] + sign * b[i] for i in range(len(a))]


def vector_dot(a, b):
    if len(a) != len(b):
        raise ValueError("Vectors must be the same length")
    return sum(a[i] * b[i] for i in range(len(a)))


def vector_cross(a, b):
    if len(a) != 3 or len(b) != 3:
        raise ValueError("Cross product requires two 3D vectors")
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]


def vector_magnitude(a):
    return math.sqrt(sum(v * v for v in a))


def vector_unit(a):
    mag = vector_magnitude(a)
    if mag == 0:
        raise ValueError("Cannot normalize a zero vector")
    return [v / mag for v in a]


def format_vector(v):
    return "(" + ", ".join(format_plain_number(x) for x in v) + ")"


# ----------------------------------------------------------------------
# Unit conversions (Phase 7) - pure Python conversion factor tables
# ----------------------------------------------------------------------

LENGTH_UNITS = {
    "m": 1.0, "km": 1000.0, "cm": 0.01, "mm": 0.001,
    "mile": 1609.344, "yard": 0.9144, "ft": 0.3048, "in": 0.0254,
}
MASS_UNITS = {
    "kg": 1.0, "g": 0.001, "mg": 0.000001,
    "lb": 0.45359237, "oz": 0.028349523125, "ton": 1000.0,
}
TIME_UNITS = {
    "s": 1.0, "ms": 0.001, "min": 60.0, "hour": 3600.0, "day": 86400.0,
}
AREA_UNITS = {
    "m2": 1.0, "km2": 1000000.0, "cm2": 0.0001, "hectare": 10000.0,
    "acre": 4046.8564224, "sqft": 0.09290304, "sqmile": 2589988.110336,
}
VOLUME_UNITS = {
    "L": 1.0, "mL": 0.001, "m3": 1000.0, "gallon": 3.785411784,
    "quart": 0.946352946, "cup": 0.2365882365, "floz": 0.0295735295625,
}
SPEED_UNITS = {
    "m/s": 1.0, "km/h": 0.277777778, "mph": 0.44704, "knot": 0.514444444,
}
PRESSURE_UNITS = {
    "Pa": 1.0, "bar": 100000.0, "atm": 101325.0,
    "psi": 6894.757293168, "mmHg": 133.322387415,
}
ENERGY_UNITS = {
    "J": 1.0, "cal": 4.184, "kJ": 1000.0, "kWh": 3600000.0, "BTU": 1055.05585262,
}
DATA_UNITS = {
    "byte": 1.0, "bit": 0.125,
    "KB": 1024.0, "MB": 1024.0 ** 2, "GB": 1024.0 ** 3, "TB": 1024.0 ** 4,
}
ANGLE_UNITS = {
    "deg": 1.0, "rad": 180.0 / math.pi, "grad": 0.9,
}

CONVERSION_CATEGORIES = {
    "Length": LENGTH_UNITS,
    "Mass": MASS_UNITS,
    "Time": TIME_UNITS,
    "Area": AREA_UNITS,
    "Volume": VOLUME_UNITS,
    "Speed": SPEED_UNITS,
    "Temperature": None,  # handled specially, see convert_temperature
    "Pressure": PRESSURE_UNITS,
    "Energy": ENERGY_UNITS,
    "Data": DATA_UNITS,
    "Angle": ANGLE_UNITS,
}

TEMPERATURE_UNITS = ["C", "F", "K"]


def convert_units(category, value, from_unit, to_unit):
    if category == "Temperature":
        return convert_temperature(value, from_unit, to_unit)

    units = CONVERSION_CATEGORIES[category]
    base_value = value * units[from_unit]
    return base_value / units[to_unit]


def convert_temperature(value, from_unit, to_unit):
    if from_unit == "C":
        celsius = value
    elif from_unit == "F":
        celsius = (value - 32) * 5.0 / 9.0
    elif from_unit == "K":
        celsius = value - 273.15
    else:
        raise ValueError("Unknown temperature unit")

    if to_unit == "C":
        return celsius
    if to_unit == "F":
        return celsius * 9.0 / 5.0 + 32
    if to_unit == "K":
        return celsius + 273.15
    raise ValueError("Unknown temperature unit")


# ----------------------------------------------------------------------
# Camera math scanning (Tier 1) - reads a single line of printed/typed
# math from a photo using the phone's on-device text recognizer (Google
# ML Kit via pyjnius). This section is fundamentally different from
# everything else in this file: pyjnius and Android's native APIs only
# exist on an actual Android device, so NONE of this could be run or
# verified in the sandbox this app was otherwise built and tested in.
# Every other feature in this app was verified against real, correct
# output. This one could not be - it needs on-device testing, and
# realistically some debugging, before it's fully reliable.
# ----------------------------------------------------------------------

class ScanUnavailable(Exception):
    """Raised whenever camera scanning can't run - not on Android, ML Kit
    missing, permission denied, cancelled, or the native call failed."""
    pass


def is_scan_available():
    try:
        import jnius  # noqa: F401
        return True
    except Exception:
        return False


def clean_scanned_text(text):
    """Light cleanup of raw OCR output before showing it for review.
    OCR commonly introduces a few specific issues with math text."""
    if not text:
        return ""

    cleaned = text.replace("X", "x")
    cleaned = cleaned.replace("\u2212", "-")   # unicode minus -> hyphen
    cleaned = cleaned.replace("\u2044", "/")   # fraction slash -> /
    cleaned = cleaned.replace("\u00d7", "\u00d7")
    cleaned = cleaned.replace(" ", "")
    cleaned = cleaned.replace("\n", " ")
    return cleaned.strip()


def pick_image_from_gallery(on_result):
    """Launches Android's system photo picker. Calls on_result(path) with
    a local file path once the user picks an image, or on_result(None) if
    they cancel or something goes wrong.

    Deliberately uses the gallery picker rather than live camera capture
    for this first version - it's simpler, more standard, and doesn't
    depend on Kivy's Camera widget (which has a history of inconsistent
    behavior across Android manufacturers). The workflow is: take a photo
    normally with the phone's own camera app first, then pick it here.
    """
    try:
        from jnius import autoclass
        from android import activity
    except Exception as exc:
        raise ScanUnavailable("Camera scanning only works on Android.") from exc

    Intent = autoclass("android.content.Intent")
    PythonActivity = autoclass("org.kivy.android.PythonActivity")

    request_code = 9001

    def _on_activity_result(request, result_code, data):
        if request != request_code:
            return
        activity.unbind(on_activity_result=_on_activity_result)
        if data is None:
            on_result(None)
            return
        try:
            uri = data.getData()
            path = _uri_to_file_path(uri)
            on_result(path)
        except Exception:
            on_result(None)

    activity.bind(on_activity_result=_on_activity_result)

    intent = Intent(Intent.ACTION_GET_CONTENT)
    intent.setType("image/*")
    PythonActivity.mActivity.startActivityForResult(intent, request_code)


def _uri_to_file_path(uri):
    """Resolves a content:// URI to an actual file path, copying the
    image to a temp file if Android won't give a direct path (common on
    newer Android versions with scoped storage)."""
    from jnius import autoclass

    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    MediaStore = autoclass("android.provider.MediaStore")
    context = PythonActivity.mActivity

    cursor = context.getContentResolver().query(uri, None, None, None, None)
    if cursor is not None:
        try:
            cursor.moveToFirst()
            column_index = cursor.getColumnIndex(MediaStore.Images.Media.DATA)
            if column_index != -1:
                path = cursor.getString(column_index)
                if path:
                    return path
        finally:
            cursor.close()

    input_stream = context.getContentResolver().openInputStream(uri)
    fd, temp_path = tempfile.mkstemp(suffix=".jpg")
    with os.fdopen(fd, "wb") as f:
        buffer = bytearray(4096)
        while True:
            read = input_stream.read(buffer)
            if read == -1:
                break
            f.write(bytes(buffer[:read]))
    input_stream.close()
    return temp_path


def recognize_text_from_image(image_path):
    """Runs Google ML Kit's on-device text recognizer against an image
    file and returns the recognized text as a single string.

    Uses a short blocking wait rather than a true async callback chain -
    bridging Java's Task<T> async API into Python reliably via pyjnius is
    one of the more fragile parts of this kind of integration, and a
    simple bounded wait loop is easier to reason about and debug on a
    real device than a fully async callback graph.
    """
    try:
        from jnius import autoclass, PythonJavaClass, java_method
    except Exception as exc:
        raise ScanUnavailable("Camera scanning only works on Android.") from exc

    try:
        BitmapFactory = autoclass("android.graphics.BitmapFactory")
        InputImage = autoclass("com.google.mlkit.vision.common.InputImage")
        TextRecognition = autoclass("com.google.mlkit.vision.text.TextRecognition")
        TextRecognizerOptions = autoclass(
            "com.google.mlkit.vision.text.latin.TextRecognizerOptions"
        )

        bitmap = BitmapFactory.decodeFile(image_path)
        if bitmap is None:
            raise ScanUnavailable("Could not read that image file.")

        image = InputImage.fromBitmap(bitmap, 0)
        recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
        task = recognizer.process(image)

        result_holder = {"text": None, "error": None, "done": False}

        class SuccessListener(PythonJavaClass):
            __javainterfaces__ = ["com/google/android/gms/tasks/OnSuccessListener"]

            @java_method("(Ljava/lang/Object;)V")
            def onSuccess(self, result):
                result_holder["text"] = result.getText()
                result_holder["done"] = True

        class FailureListener(PythonJavaClass):
            __javainterfaces__ = ["com/google/android/gms/tasks/OnFailureListener"]

            @java_method("(Ljava/lang/Exception;)V")
            def onFailure(self, exception):
                result_holder["error"] = str(exception.getMessage())
                result_holder["done"] = True

        task.addOnSuccessListener(SuccessListener())
        task.addOnFailureListener(FailureListener())

        waited = 0.0
        while not result_holder["done"] and waited < 10.0:
            time.sleep(0.1)
            waited += 0.1

        if result_holder["error"]:
            raise ScanUnavailable(f"Text recognition failed: {result_holder['error']}")
        if not result_holder["done"]:
            raise ScanUnavailable("Text recognition timed out.")

        return result_holder["text"] or ""

    except ScanUnavailable:
        raise
    except Exception as exc:
        raise ScanUnavailable(f"Scanning failed: {exc}") from exc


OPERATOR_CHARS = {"+", "-", "×", "÷", "^", "%"}

SCIENTIFIC_COLOR_LABELS = {
    "sin", "cos", "tan", "asin", "acos", "atan",
    "√", "log", "ln", "logb", "π", "e", "n!",
    "x²", "x³", "xʸ", "1/x",
}


def sample_function(engine, expression, x_min, x_max, samples=400):
    """Evaluates expression at evenly spaced x values, returning a list of
    (x, y) pairs. y is None where the function is undefined/invalid there."""
    points = []
    for i in range(samples + 1):
        x = x_min + (x_max - x_min) * i / samples
        try:
            y = engine.evaluate(expression, variables={"x": x})
        except Exception:
            y = None

        if isinstance(y, complex):
            y = None
        if isinstance(y, float) and (math.isnan(y) or math.isinf(y)):
            y = None

        points.append((x, y))
    return points


def find_roots(engine, expression, x_min, x_max, samples=400, tolerance=1e-9):
    """Finds x-values where expression == 0 within [x_min, x_max], by
    scanning for sign changes between samples and refining each with
    bisection. Pure numerical method - no symbolic solving needed."""
    def f(x):
        try:
            return engine.evaluate(expression, variables={"x": x})
        except Exception:
            return None

    roots = []
    step = (x_max - x_min) / samples
    prev_x = x_min
    prev_y = f(prev_x)

    for i in range(1, samples + 1):
        x = x_min + i * step
        y = f(x)

        if prev_y is not None and y is not None:
            if prev_y == 0:
                roots.append(prev_x)
            elif prev_y * y < 0:
                lo, hi, f_lo = prev_x, x, prev_y
                for _ in range(60):
                    mid = (lo + hi) / 2
                    f_mid = f(mid)
                    if f_mid is None:
                        break
                    if abs(f_mid) < tolerance:
                        lo = hi = mid
                        break
                    if f_lo * f_mid < 0:
                        hi = mid
                    else:
                        lo, f_lo = mid, f_mid
                roots.append((lo + hi) / 2)

        prev_x, prev_y = x, y

    deduped = []
    for r in roots:
        if not any(abs(r - existing) < 1e-6 for existing in deduped):
            deduped.append(r)
    return deduped


def find_intersections(engine, expression1, expression2, x_min, x_max, samples=400):
    """Finds where two functions cross, by finding roots of their
    difference. Returns a list of (x, y) points."""
    combined = f"({expression1})-({expression2})"
    xs = find_roots(engine, combined, x_min, x_max, samples)

    points = []
    for x in xs:
        try:
            y = engine.evaluate(expression1, variables={"x": x})
            points.append((x, y))
        except Exception:
            continue
    return points


class GraphCanvas(Widget):
    """Draws y = f(x), and optionally a second y = g(x), using plain Kivy
    graphics primitives - no matplotlib or any other plotting dependency
    needed."""

    def __init__(self, engine, expression, expression2=None, x_min=-10, x_max=10, **kwargs):
        super().__init__(**kwargs)
        self.engine = engine
        self.expression = expression
        self.expression2 = expression2
        self.x_min = x_min
        self.x_max = x_max
        self.error = None
        self.bind(size=self.redraw, pos=self.redraw)
        self.redraw()

    def redraw(self, *args):
        self.canvas.clear()
        self.error = None

        width, height = self.size
        origin_x, origin_y = self.pos

        if width <= 0 or height <= 0:
            return

        points_data = sample_function(self.engine, self.expression, self.x_min, self.x_max)
        y_values = [y for _, y in points_data if y is not None]

        points_data2 = []
        if self.expression2:
            points_data2 = sample_function(self.engine, self.expression2, self.x_min, self.x_max)
            y_values.extend(y for _, y in points_data2 if y is not None)

        if not y_values:
            self.error = "Could not plot this function over that range"
            return

        y_min, y_max = min(y_values), max(y_values)
        if y_min == y_max:
            y_min -= 1
            y_max += 1
        pad = (y_max - y_min) * 0.1
        y_min -= pad
        y_max += pad

        def to_screen(x, y):
            sx = origin_x + (x - self.x_min) / (self.x_max - self.x_min) * width
            sy = origin_y + (y - y_min) / (y_max - y_min) * height
            return sx, sy

        def draw_curve(points):
            segment_points = []
            for x, y in points:
                if y is None:
                    if len(segment_points) >= 4:
                        Line(points=segment_points, width=1.5)
                    segment_points = []
                    continue
                sx, sy = to_screen(x, y)
                segment_points.extend([sx, sy])
            if len(segment_points) >= 4:
                Line(points=segment_points, width=1.5)

        with self.canvas:
            Color(0.35, 0.35, 0.4, 1)

            if y_min <= 0 <= y_max:
                ax0, ay0 = to_screen(self.x_min, 0)
                ax1, ay1 = to_screen(self.x_max, 0)
                Line(points=[ax0, ay0, ax1, ay1], width=1)

            if self.x_min <= 0 <= self.x_max:
                bx0, by0 = to_screen(0, y_min)
                bx1, by1 = to_screen(0, y_max)
                Line(points=[bx0, by0, bx1, by1], width=1)

            Color(0.2, 0.75, 0.95, 1)
            draw_curve(points_data)

            if points_data2:
                Color(0.95, 0.55, 0.2, 1)
                draw_curve(points_data2)


class Calculator(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.orientation = "vertical"
        self.padding = dp(8)
        self.spacing = dp(6)

        self.expression = ""
        self.cursor_pos = 0
        self.memory = 0
        self.engine = MathEngine()
        self.history = []
        self.just_calculated = False

        self.memory_label = None
        self.mode_button = None
        self.dark_mode = True

        self.title_label = Label(
            text="MATHEMATICAL CALCULATOR",
            size_hint_y=0.07,
            font_size="22sp",
            bold=True,
        )
        self.add_widget(self.title_label)

        version_bar = BoxLayout(
            orientation="horizontal",
            size_hint_y=0.04,
            spacing=dp(5),
        )

        self.version_label = Label(
            text=f"Version {APP_VERSION}",
            font_size="12sp",
            halign="left",
            valign="middle",
        )
        self.version_label.bind(size=self.update_text_size)

        info_button = Button(
            text="i",
            size_hint=(None, 1),
            width=dp(35),
        )
        info_button.bind(on_press=self.show_about)

        version_bar.add_widget(self.version_label)
        version_bar.add_widget(info_button)
        self.add_widget(version_bar)

        self.history_label = Label(
            text="Welcome.\n\nLet's calculate something.",
            size_hint_y=0.10,
            font_size="12sp",
            halign="right",
            valign="middle",
        )
        self.history_label.bind(size=self.update_text_size)
        self.add_widget(self.history_label)

        self.memory_indicator = Label(
            text="",
            size_hint_y=0.05,
            font_size="12sp",
            halign="right",
            valign="middle",
        )
        self.memory_indicator.bind(size=self.update_text_size)
        self.add_widget(self.memory_indicator)

        self.display = Label(
            text="0",
            size_hint_y=0.22,
            font_size="40sp",
            halign="right",
            valign="middle",
        )
        self.display.bind(size=self.update_text_size)
        self.add_widget(self.display)

        self.preview_label = Label(
            text="",
            size_hint_y=0.05,
            font_size="16sp",
            halign="right",
            valign="middle",
            color=(0.55, 0.55, 0.6, 1),
        )
        self.preview_label.bind(size=self.update_text_size)

        preview_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=0.05,
            spacing=dp(4),
        )
        cursor_left = Button(text="\u25c0", size_hint_x=None, width=dp(36), font_size="14sp")
        cursor_right = Button(text="\u25b6", size_hint_x=None, width=dp(36), font_size="14sp")
        cursor_left.bind(on_press=self.move_cursor_left)
        cursor_right.bind(on_press=self.move_cursor_right)
        preview_row.add_widget(cursor_left)
        preview_row.add_widget(self.preview_label)
        preview_row.add_widget(cursor_right)
        self.add_widget(preview_row)

        buttons = [
            ["C", "⌫", "(", ")", "More"],
            ["7", "8", "9", "%", "÷"],
            ["4", "5", "6", ".", "×"],
            ["1", "2", "3", "HIST", "-"],
            ["0", "±", "", "=", "+"],
        ]

        grid = GridLayout(
            cols=5,
            spacing=dp(5),
            size_hint_y=0.62,
        )

        for row in buttons:
            for text in row:
                if text == "":
                    grid.add_widget(Label())
                    continue

                button = Button(
                    text=text,
                    font_size="18sp",
                    background_normal="",
                    background_color=self.button_color(text),
                )
                button.bind(on_press=self.button_pressed)
                button.bind(on_press=self._flash_button)
                grid.add_widget(button)

        self.add_widget(grid)

        self.load_state()
        self.apply_theme()

    # ------------------------------------------------------------------
    # Theme (Phase 8) - light/dark mode
    # ------------------------------------------------------------------

    def apply_theme(self):
        if self.dark_mode:
            Window.clearcolor = (0.04, 0.04, 0.06, 1)
            text_color = (1, 1, 1, 1)
            muted_color = (0.55, 0.55, 0.6, 1)
        else:
            Window.clearcolor = (0.93, 0.93, 0.95, 1)
            text_color = (0.05, 0.05, 0.08, 1)
            muted_color = (0.35, 0.35, 0.4, 1)

        self.title_label.color = text_color
        self.version_label.color = muted_color
        self.history_label.color = muted_color
        self.memory_indicator.color = text_color
        self.display.color = text_color
        self.preview_label.color = muted_color

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self.apply_theme()
        self.save_state()

    # ------------------------------------------------------------------
    # Persistence - memory & history survive an app restart
    # ------------------------------------------------------------------

    def _state_file_path(self):
        app = App.get_running_app()
        if app is None:
            return None
        try:
            os.makedirs(app.user_data_dir, exist_ok=True)
        except Exception:
            return None
        return os.path.join(app.user_data_dir, "calculator_state.json")

    def save_state(self):
        path = self._state_file_path()
        if not path:
            return
        try:
            with open(path, "w") as f:
                json.dump({
                    "memory": self.memory,
                    "history": self.history,
                    "dark_mode": self.dark_mode,
                }, f)
        except Exception:
            pass

    def load_state(self):
        path = self._state_file_path()
        if not path or not os.path.exists(path):
            return

        try:
            with open(path) as f:
                data = json.load(f)
        except Exception:
            return

        self.memory = data.get("memory", 0)
        self.dark_mode = data.get("dark_mode", True)
        raw_history = data.get("history", [])
        self.history = [
            tuple(item) for item in raw_history
            if isinstance(item, (list, tuple)) and len(item) == 2
        ]

        self.update_memory_indicator()

        # Deliberately NOT restoring the on-screen "last calculation"
        # preview here - that would mean the welcome message never comes
        # back once you've calculated anything once, ever. The actual
        # history data is still fully restored above (for the History
        # popup, Steps, tap-to-reuse, etc.) - only this small preview
        # label stays on its default "Welcome" text until you do a new
        # calculation in the current session.

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------

    def update_text_size(self, widget, size):
        widget.text_size = size

    def _flash_button(self, instance):
        """Brief visual feedback on tap - purely cosmetic, wrapped in a
        try/except so it can never interfere with the actual button
        action even if something about the animation goes wrong."""
        try:
            original = instance.background_color
            lighter = tuple(min(1.0, c + 0.25) for c in original[:3]) + (original[3],)
            Animation.cancel_all(instance, "background_color")
            (
                Animation(background_color=lighter, duration=0.05)
                + Animation(background_color=original, duration=0.15)
            ).start(instance)
        except Exception:
            pass

    def make_sheet_popup(self, title, content, height=0.5):
        """A popup that behaves like a keyboard sheet - docked to the
        bottom of the screen, full width, and only as tall as it needs
        to be - instead of a centered box covering most of the screen."""
        return Popup(
            title=title,
            content=content,
            size_hint=(1, height),
            pos_hint={"x": 0, "y": 0},
            auto_dismiss=True,
        )

    def button_color(self, text):
        if text == "=":
            return (0.1, 0.55, 0.9, 1)

        if text in ("C", "⌫"):
            return (0.7, 0.15, 0.18, 1)

        if text in ("DEG", "RAD", "GRAD"):
            return (0.1, 0.55, 0.9, 1)

        if text in OPERATOR_CHARS:
            return (0.25, 0.25, 0.55, 1)

        if text in SCIENTIFIC_COLOR_LABELS:
            return (0.18, 0.35, 0.35, 1)

        return (0.15, 0.15, 0.18, 1)

    # ------------------------------------------------------------------
    # Main keypad dispatch
    # ------------------------------------------------------------------

    def button_pressed(self, button):
        value = button.text

        if self.display.text in ("Math Error", "Cannot divide by zero"):
            if value not in ("C", "⌫"):
                self.expression = ""
                self.cursor_pos = 0
                self.display.text = "0"

        if value == "C":
            self.clear_all()
            return

        if value == "⌫":
            self.backspace()
            return

        if value == "=":
            self.calculate()
            return

        if value == "More":
            self.open_more_menu()
            return

        if value == "HIST":
            self.show_history()
            return

        if value == "±":
            self.toggle_sign()
            return

        if value == ".":
            self.append_decimal()
            return

        if value in OPERATOR_CHARS:
            self.append_operator(value)
            return

        if value in ("(", ")"):
            self.reset_if_calculated()
            self._insert_at_cursor(value)
            self.update_display()
            return

        if value.isdigit():
            self.reset_if_calculated()
            self._insert_at_cursor(value)
            self.update_display()
            return

        # Fallback for any unexpected label - just insert it as typed.
        self.reset_if_calculated()
        self._insert_at_cursor(value)
        self.update_display()

    def _insert_at_cursor(self, text):
        self.expression = (
            self.expression[:self.cursor_pos] + text + self.expression[self.cursor_pos:]
        )
        self.cursor_pos += len(text)

    # ------------------------------------------------------------------
    # Expression editing helpers (Phase 1 reliability)
    # ------------------------------------------------------------------

    def reset_if_calculated(self):
        if self.just_calculated:
            self.expression = ""
            self.cursor_pos = 0
            self.just_calculated = False

    def clear_all(self):
        self.expression = ""
        self.cursor_pos = 0
        self.display.text = "0"
        self.preview_label.text = ""
        self.just_calculated = False

    def backspace(self):
        if self.cursor_pos > 0:
            self.expression = (
                self.expression[:self.cursor_pos - 1] + self.expression[self.cursor_pos:]
            )
            self.cursor_pos -= 1
        self.just_calculated = False
        self.update_display()

    def append_decimal(self):
        self.reset_if_calculated()

        before_cursor = self.expression[:self.cursor_pos]
        segment = re.split(r"[+\-\u00d7\u00f7^%(]", before_cursor)[-1] if before_cursor else ""
        if "." in segment:
            return

        insertion = "0." if not segment else "."
        self.expression = (
            self.expression[:self.cursor_pos] + insertion + self.expression[self.cursor_pos:]
        )
        self.cursor_pos += len(insertion)
        self.update_display()

    def append_operator(self, op):
        if not self.expression:
            if op == "-":
                self.expression = "-"
                self.cursor_pos = 1
                self.update_display()
            return

        char_before = self.expression[self.cursor_pos - 1] if self.cursor_pos > 0 else ""

        if char_before in OPERATOR_CHARS:
            if op == "-" and char_before != "-":
                # allow forming a negative number, e.g. 5x-3
                self.expression = (
                    self.expression[:self.cursor_pos] + op + self.expression[self.cursor_pos:]
                )
                self.cursor_pos += 1
            else:
                self.expression = (
                    self.expression[:self.cursor_pos - 1] + op + self.expression[self.cursor_pos:]
                )
        else:
            self.expression = (
                self.expression[:self.cursor_pos] + op + self.expression[self.cursor_pos:]
            )
            self.cursor_pos += 1

        self.just_calculated = False
        self.update_display()

    def toggle_sign(self):
        self.reset_if_calculated()

        before_cursor = self.expression[:self.cursor_pos]
        match = re.search(r"(-?\d*\.?\d+)$", before_cursor)

        if not match:
            # No number ends right at the cursor - the cursor might be
            # sitting right before a number instead (e.g. between an
            # operator and the next digit), so check just after it too.
            after_cursor = self.expression[self.cursor_pos:]
            match_after = re.match(r"(-?\d*\.?\d+)", after_cursor)
            if match_after:
                number = match_after.group(1)
                start = self.cursor_pos
                end = self.cursor_pos + len(number)
            elif not self.expression:
                self.expression = "-"
                self.cursor_pos = 1
                self.update_display()
                return
            else:
                return
        else:
            number = match.group(1)
            start = match.start(1)
            end = match.end(1)

        if number.startswith("-"):
            new_number = number[1:]
        else:
            new_number = "-" + number

        self.expression = self.expression[:start] + new_number + self.expression[end:]
        self.cursor_pos = start + len(new_number)
        self.update_display()

    def wrap_whole(self, prefix, suffix=")"):
        if self.expression:
            self.expression = f"{prefix}{self.expression}{suffix}"
        else:
            self.expression = prefix
        self.cursor_pos = len(self.expression)
        self.just_calculated = False
        self.update_display()

    def append_power(self, digit):
        self.append_operator("^")
        self.expression = (
            self.expression[:self.cursor_pos] + digit + self.expression[self.cursor_pos:]
        )
        self.cursor_pos += len(digit)
        self.update_display()

    def update_display(self):
        self.cursor_pos = max(0, min(self.cursor_pos, len(self.expression)))

        if not self.expression:
            self.display.text = "0"
        elif self.cursor_pos >= len(self.expression):
            self.display.text = self.expression
        else:
            self.display.text = (
                self.expression[:self.cursor_pos] + "\u2502" + self.expression[self.cursor_pos:]
            )

        self.update_preview()

    def move_cursor_left(self, instance):
        self.cursor_pos = max(0, self.cursor_pos - 1)
        self.update_display()

    def move_cursor_right(self, instance):
        self.cursor_pos = min(len(self.expression), self.cursor_pos + 1)
        self.update_display()

    def update_preview(self):
        """Shows a live '= result' preview as the expression is typed,
        without requiring '=' to be pressed. Silently shows nothing if
        the expression isn't complete/valid yet (e.g. still mid-typing)."""
        if self.just_calculated or not self.expression:
            self.preview_label.text = ""
            return

        try:
            result = self.engine.evaluate(self.expression)

            if isinstance(result, float) and result.is_integer():
                result = int(result)

            formatted = self.format_number(result)

            # Don't show a redundant preview for a bare number that
            # hasn't had any operation applied to it yet.
            if formatted == self.expression:
                self.preview_label.text = ""
            else:
                self.preview_label.text = f"= {formatted}"
        except Exception:
            self.preview_label.text = ""

    # ------------------------------------------------------------------
    # Calculation
    # ------------------------------------------------------------------

    def calculate(self):
        if not self.expression:
            return

        try:
            original = self.expression
            result = self.engine.evaluate(self.expression)

            if isinstance(result, float) and result.is_integer():
                result = int(result)

            if isinstance(result, float):
                result = round(result, 10)

            self.history.append((original, result))
            self.history = self.history[-50:]

            self.expression = self.format_number(result)
            self.cursor_pos = len(self.expression)
            self.display.text = self.expression
            self.preview_label.text = ""
            self.just_calculated = True

            self.history_label.text = "\n".join(
                f"{expr} = {self.format_number(ans)}"
                for expr, ans in self.history[-3:]
            )

            self.save_state()

        except ZeroDivisionError:
            self.display.text = "Cannot divide by zero"
            self.preview_label.text = ""
            self.expression = ""
            self.cursor_pos = 0
            self.just_calculated = False

        except (ValueError, SyntaxError, TypeError, OverflowError):
            self.display.text = "Math Error"
            self.preview_label.text = ""
            self.expression = ""
            self.cursor_pos = 0
            self.just_calculated = False

        except Exception:
            self.display.text = "Math Error"
            self.preview_label.text = ""
            self.expression = ""
            self.cursor_pos = 0
            self.just_calculated = False

    def format_number(self, number):
        if isinstance(number, float) and number.is_integer():
            number = int(number)

        if isinstance(number, float):
            if number != 0 and (abs(number) >= 1e9 or abs(number) < 1e-6):
                return f"{number:.6e}"
            return str(number)

        if isinstance(number, int) and abs(number) >= 10 ** 15:
            return f"{float(number):.6e}"

        return str(number)

    def add_to_history(self, expression, answer):
        """Records a calculation from ANY tool - not just the main
        keypad's '=' - so every popup (Number Theory, Algebra, Calculus,
        Matrices/Vectors, Conversions) shows up in History too, and
        survives an app restart the same way main-keypad calculations
        already did."""
        self.history.append((expression, answer))
        self.history = self.history[-50:]
        self.save_state()

    # ------------------------------------------------------------------
    # More menu (Scientific / Memory / History)
    # ------------------------------------------------------------------

    def open_more_menu(self):
        outer = BoxLayout(
            orientation="vertical",
            spacing=dp(6),
            padding=dp(10),
        )

        scroll = ScrollView()
        menu_grid = GridLayout(
            cols=1,
            spacing=dp(6),
            size_hint_y=None,
        )
        menu_grid.bind(minimum_height=menu_grid.setter("height"))
        scroll.add_widget(menu_grid)
        outer.add_widget(scroll)

        close = Button(
            text="Close",
            size_hint_y=None,
            height=dp(45),
        )
        outer.add_widget(close)

        popup = self.make_sheet_popup("More", outer, height=0.65)

        tools = [
            ("\U0001F9EE Scientific", self.show_scientific),
            ("\U0001F522 Number Theory", self.show_number_theory),
            ("\U0001F4D0 Algebra", self.show_algebra),
            ("\u222B Calculus", self.show_calculus),
            ("\U0001F9EE Matrices & Vectors", self.show_matrices_vectors),
            ("\U0001F4CF Conversions", self.show_conversions),
            ("\U0001F4C8 Graph", self.show_graph),
            ("\U0001F4BE Memory", self.show_memory),
            ("\U0001F4DC History", self.show_history),
            ("\u2699 Settings", self.show_settings),
            ("\U0001F4F7 Scan", self.show_scan),
        ]

        for label, opener in tools:
            button = Button(
                text=label,
                size_hint_y=None,
                height=dp(45),
            )

            def make_handler(fn):
                def handler(instance):
                    popup.dismiss()
                    fn()
                return handler

            button.bind(on_press=make_handler(opener))
            menu_grid.add_widget(button)

        close.bind(on_press=popup.dismiss)

        popup.open()

    # ------------------------------------------------------------------
    # Scientific popup (Phase 2)
    # ------------------------------------------------------------------

    def show_scientific(self):
        layout = BoxLayout(
            orientation="vertical",
            spacing=dp(10),
            padding=dp(10),
        )

        grid = GridLayout(
            cols=3,
            spacing=dp(5),
        )

        buttons = [
            "sin", "cos", "tan",
            "asin", "acos", "atan",
            "x²", "x³", "√",
            "xʸ", "1/x", "n!",
            "log", "ln", "logb",
            "π", "e", "DEG",
        ]

        self.mode_button = None

        for text in buttons:
            button = Button(
                text=text,
                font_size="16sp",
                background_normal="",
                background_color=self.button_color(text),
            )

            if text == "DEG":
                button.text = self.engine.angle_mode.upper()
                self.mode_button = button

            button.bind(on_press=self.scientific_button_pressed)
            grid.add_widget(button)

        layout.add_widget(grid)

        close_button = Button(
            text="Close",
            size_hint_y=None,
            height=dp(45),
        )
        layout.add_widget(close_button)

        popup = self.make_sheet_popup("Scientific", layout, height=0.6)

        close_button.bind(on_press=popup.dismiss)
        popup.open()

    def scientific_button_pressed(self, button):
        text = button.text

        if text in ("DEG", "RAD", "GRAD"):
            self.toggle_angle_mode(button)
            return

        function_tokens = {
            "sin": "sin(",
            "cos": "cos(",
            "tan": "tan(",
            "asin": "asin(",
            "acos": "acos(",
            "atan": "atan(",
            "√": "sqrt(",
            "log": "log(",
            "ln": "ln(",
            "logb": "logb(",
        }

        if text in function_tokens:
            self.reset_if_calculated()
            self._insert_at_cursor(function_tokens[text])
            self.update_display()
            return

        if text in ("π", "e"):
            self.reset_if_calculated()
            self._insert_at_cursor(text)
            self.update_display()
            return

        if text == "xʸ":
            self.append_operator("^")
            return

        if text == "x²":
            self.append_power("2")
            return

        if text == "x³":
            self.append_power("3")
            return

        if text == "1/x":
            self.wrap_whole("1/(")
            return

        if text == "n!":
            self.wrap_whole("fact(")
            return

    def toggle_angle_mode(self, button):
        cycle = {"deg": "rad", "rad": "grad", "grad": "deg"}
        self.engine.angle_mode = cycle[self.engine.angle_mode]
        button.text = self.engine.angle_mode.upper()

    # ------------------------------------------------------------------
    # Memory popup
    # ------------------------------------------------------------------

    def show_memory(self):
        layout = BoxLayout(
            orientation="vertical",
            spacing=dp(10),
            padding=dp(10),
        )

        memory_label = Label(
            text=f"Stored Memory: {self.format_number(self.memory)}",
            size_hint_y=None,
            height=dp(40),
        )
        self.memory_label = memory_label
        layout.add_widget(memory_label)

        mc = Button(text="MC")
        mr = Button(text="MR")
        mp = Button(text="M+")
        mm = Button(text="M-")
        close = Button(
            text="Close",
            size_hint_y=None,
            height=dp(45),
        )

        layout.add_widget(mc)
        layout.add_widget(mr)
        layout.add_widget(mp)
        layout.add_widget(mm)
        layout.add_widget(close)

        popup = self.make_sheet_popup("Memory", layout, height=0.42)

        mc.bind(on_press=lambda x: self.memory_clear())
        mr.bind(on_press=lambda x: self.memory_recall())
        mp.bind(on_press=lambda x: self.memory_add())
        mm.bind(on_press=lambda x: self.memory_subtract())
        close.bind(on_press=popup.dismiss)

        popup.open()

    def update_memory_label(self):
        if self.memory_label is not None:
            self.memory_label.text = f"Stored Memory: {self.format_number(self.memory)}"

    def update_memory_indicator(self):
        self.memory_indicator.text = "M" if self.memory != 0 else ""

    def memory_clear(self):
        self.memory = 0
        self.update_memory_label()
        self.update_memory_indicator()
        self.save_state()

    def memory_recall(self):
        self.reset_if_calculated()
        self._insert_at_cursor(self.format_number(self.memory))
        self.update_display()

    def memory_add(self):
        try:
            self.memory += float(self.display.text)
        except (ValueError, TypeError):
            pass
        self.update_memory_label()
        self.update_memory_indicator()
        self.save_state()

    def memory_subtract(self):
        try:
            self.memory -= float(self.display.text)
        except (ValueError, TypeError):
            pass
        self.update_memory_label()
        self.update_memory_indicator()
        self.save_state()

    # ------------------------------------------------------------------
    # History popup (scrollable, tap to reuse, clearable)
    # ------------------------------------------------------------------

    def _make_wrapping_step_label(self, text):
        """A Label whose height grows to fit however many lines its text
        wraps to, instead of a fixed height that clips longer
        explanations. Width-wrapping needs the width known first, then
        the label's own rendered texture tells us the height it needs."""
        label = Label(
            text=text,
            size_hint_y=None,
            font_size="14sp",
            halign="left",
            valign="top",
            padding=(dp(4), dp(10)),
        )

        def update_text_width(widget, width):
            widget.text_size = (width, None)

        def update_height_from_texture(widget, texture_size):
            widget.height = texture_size[1] + dp(4)

        label.bind(width=update_text_width)
        label.bind(texture_size=update_height_from_texture)
        return label

    def show_steps_popup(self, title, lines):
        scroll = ScrollView()
        steps_grid = GridLayout(
            cols=1,
            spacing=dp(6),
            padding=dp(10),
            size_hint_y=None,
        )
        steps_grid.bind(minimum_height=steps_grid.setter("height"))

        if not lines:
            steps_grid.add_widget(Label(
                text="No steps to show for this.",
                size_hint_y=None, height=dp(40),
            ))
        else:
            for i, line in enumerate(lines, start=1):
                steps_grid.add_widget(
                    self._make_wrapping_step_label(f"{i}. {line}")
                )

        scroll.add_widget(steps_grid)

        outer = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        outer.add_widget(scroll)
        close_button = Button(text="Close", size_hint_y=None, height=dp(45))
        outer.add_widget(close_button)

        popup = self.make_sheet_popup(title, outer, height=0.6)
        close_button.bind(on_press=popup.dismiss)
        popup.open()

    def show_history(self):
        popup_layout = BoxLayout(
            orientation="vertical",
            spacing=dp(5),
        )

        scroll = ScrollView()
        history_grid = GridLayout(
            cols=1,
            spacing=dp(4),
            size_hint_y=None,
        )
        history_grid.bind(minimum_height=history_grid.setter("height"))

        def rebuild_history_grid():
            history_grid.clear_widgets()

            if not self.history:
                history_grid.add_widget(
                    Label(text="No history yet.", size_hint_y=None, height=dp(40))
                )
                return

            for expr, ans in reversed(self.history):
                entry_text = f"{expr} = {self.format_number(ans)}"

                row = BoxLayout(
                    orientation="horizontal",
                    size_hint_y=None,
                    height=dp(45),
                    spacing=dp(4),
                )

                entry_button = Button(
                    text=entry_text,
                    halign="left",
                )

                def reuse(instance, answer=ans):
                    self.reset_if_calculated()
                    self._insert_at_cursor(self.format_number(answer))
                    self.update_display()

                def view_steps(instance, expression=expr):
                    trace = []
                    try:
                        self.engine.evaluate(expression, trace=trace)
                    except Exception:
                        pass
                    self.show_steps_popup(f"How: {expression}", trace)

                steps_button = Button(
                    text="Steps",
                    size_hint_x=0.28,
                )

                entry_button.bind(on_press=reuse)
                steps_button.bind(on_press=view_steps)
                row.add_widget(entry_button)
                row.add_widget(steps_button)
                history_grid.add_widget(row)

        rebuild_history_grid()

        scroll.add_widget(history_grid)
        popup_layout.add_widget(scroll)

        clear_button = Button(
            text="Clear History",
            size_hint_y=None,
            height=dp(45),
        )
        close_button = Button(
            text="Close",
            size_hint_y=None,
            height=dp(45),
        )

        popup_layout.add_widget(clear_button)
        popup_layout.add_widget(close_button)

        popup = self.make_sheet_popup("Calculation History", popup_layout, height=0.6)

        def clear_history(instance):
            self.history = []
            self.history_label.text = "Welcome.\n\nLet's calculate something."
            rebuild_history_grid()
            self.save_state()

        clear_button.bind(on_press=clear_history)
        close_button.bind(on_press=popup.dismiss)

        popup.open()

    # ------------------------------------------------------------------
    # About popup
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Shared popup-building helpers
    # ------------------------------------------------------------------

    def _labeled_input(self, layout, hint_text):
        label = Label(
            text=hint_text,
            size_hint_y=None,
            height=dp(24),
            font_size="12sp",
            halign="left",
            valign="middle",
        )
        label.bind(size=self.update_text_size)
        layout.add_widget(label)

        field = TextInput(
            multiline=False,
            size_hint_y=None,
            height=dp(40),
        )
        layout.add_widget(field)
        return field

    def _result_label(self, layout, height=dp(60)):
        result = Label(
            text="",
            size_hint_y=None,
            height=height,
            font_size="14sp",
            halign="left",
            valign="middle",
        )
        result.bind(size=self.update_text_size)
        layout.add_widget(result)
        return result

    def _action_row(self, layout, specs):
        """specs: list of (label, callback) tuples, rendered as a row of buttons."""
        row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(45),
            spacing=dp(5),
        )
        for label, callback in specs:
            button = Button(text=label)
            button.bind(on_press=callback)
            row.add_widget(button)
        layout.add_widget(row)

    # ------------------------------------------------------------------
    # Number Theory popup (Phase 3)
    # ------------------------------------------------------------------

    def show_number_theory(self):
        scroll = ScrollView()
        layout = BoxLayout(
            orientation="vertical",
            spacing=dp(8),
            padding=dp(10),
            size_hint_y=None,
        )
        layout.bind(minimum_height=layout.setter("height"))

        last_steps = {"prime": [], "gcd_lcm": [], "fraction": []}

        layout.add_widget(Label(
            text="Prime check & factorization",
            size_hint_y=None, height=dp(24), font_size="13sp", bold=True,
        ))
        n_field = self._labeled_input(layout, "Whole number")
        n_result = self._result_label(layout)

        def check_prime(instance):
            try:
                n = int(float(n_field.text))
                verdict, steps = is_prime_steps(n)
                n_result.text = f"{n} is {'prime' if verdict else 'not prime'}"
                last_steps["prime"] = steps
                self.add_to_history(f"is {n} prime?", n_result.text)
            except Exception as exc:
                n_result.text = f"Error: {exc}"
                last_steps["prime"] = []

        def factorize(instance):
            try:
                n = int(float(n_field.text))
                factors, steps = prime_factorize_steps(n)
                n_result.text = format_prime_factors(factors)
                last_steps["prime"] = steps
                self.add_to_history(f"prime factors of {n}", n_result.text)
            except Exception as exc:
                n_result.text = f"Error: {exc}"
                last_steps["prime"] = []

        def view_prime_steps(instance):
            self.show_steps_popup("How this was worked out", last_steps["prime"])

        self._action_row(layout, [
            ("Is Prime?", check_prime),
            ("Prime Factors", factorize),
        ])
        self._action_row(layout, [("View Steps", view_prime_steps)])

        layout.add_widget(Label(
            text="GCD & LCM",
            size_hint_y=None, height=dp(24), font_size="13sp", bold=True,
        ))
        a_field = self._labeled_input(layout, "First whole number")
        b_field = self._labeled_input(layout, "Second whole number")
        ab_result = self._result_label(layout, height=dp(40))

        def compute_gcd(instance):
            try:
                a, b = int(float(a_field.text)), int(float(b_field.text))
                result, steps = gcd_steps(a, b)
                ab_result.text = f"GCD = {result}"
                last_steps["gcd_lcm"] = steps
                self.add_to_history(f"GCD({a}, {b})", result)
            except Exception as exc:
                ab_result.text = f"Error: {exc}"
                last_steps["gcd_lcm"] = []

        def compute_lcm(instance):
            try:
                a, b = int(float(a_field.text)), int(float(b_field.text))
                result, steps = lcm_steps(a, b)
                ab_result.text = f"LCM = {result}"
                last_steps["gcd_lcm"] = steps
                self.add_to_history(f"LCM({a}, {b})", result)
            except Exception as exc:
                ab_result.text = f"Error: {exc}"
                last_steps["gcd_lcm"] = []

        def view_gcd_lcm_steps(instance):
            self.show_steps_popup("How this was worked out", last_steps["gcd_lcm"])

        self._action_row(layout, [
            ("GCD", compute_gcd),
            ("LCM", compute_lcm),
        ])
        self._action_row(layout, [("View Steps", view_gcd_lcm_steps)])

        layout.add_widget(Label(
            text="Simplify a fraction",
            size_hint_y=None, height=dp(24), font_size="13sp", bold=True,
        ))
        num_field = self._labeled_input(layout, "Numerator")
        den_field = self._labeled_input(layout, "Denominator")
        frac_result = self._result_label(layout, height=dp(40))

        def simplify(instance):
            try:
                num, den = int(float(num_field.text)), int(float(den_field.text))
                (n, d), steps = simplify_fraction_steps(num, den)
                frac_result.text = f"= {n}/{d}"
                last_steps["fraction"] = steps
                self.add_to_history(f"simplify {num}/{den}", f"{n}/{d}")
            except Exception as exc:
                frac_result.text = f"Error: {exc}"
                last_steps["fraction"] = []

        def to_mixed(instance):
            try:
                num, den = int(float(num_field.text)), int(float(den_field.text))
                whole, rem_num, rem_den = to_mixed_number(num, den)
                mixed_text = format_mixed_number(whole, rem_num, rem_den)
                frac_result.text = f"= {mixed_text}"
                if rem_num == 0:
                    last_steps["fraction"] = [f"{num}/{den} is exactly {whole} - no remainder"]
                else:
                    last_steps["fraction"] = [
                        f"Whole part: {whole}",
                        f"Remaining fraction: {rem_num}/{rem_den}",
                        f"So {num}/{den} = {mixed_text}",
                    ]
                self.add_to_history(f"{num}/{den} as mixed number", mixed_text)
            except Exception as exc:
                frac_result.text = f"Error: {exc}"
                last_steps["fraction"] = []

        def view_fraction_steps(instance):
            self.show_steps_popup("How this was worked out", last_steps["fraction"])

        self._action_row(layout, [
            ("Simplify", simplify),
            ("Mixed Number", to_mixed),
        ])
        self._action_row(layout, [("View Steps", view_fraction_steps)])

        scroll.add_widget(layout)
        popup = self.make_sheet_popup("Number Theory", scroll, height=0.85)
        popup.open()

    # ------------------------------------------------------------------
    # Algebra popup (Phase 3)
    # ------------------------------------------------------------------

    def show_algebra(self):
        scroll = ScrollView()
        layout = BoxLayout(
            orientation="vertical",
            spacing=dp(8),
            padding=dp(10),
            size_hint_y=None,
        )
        layout.bind(minimum_height=layout.setter("height"))

        layout.add_widget(Label(
            text="Equation in x, e.g. 2*x+3=7  or  x^2-5*x+6=0",
            size_hint_y=None, height=dp(36), font_size="12sp",
        ))
        eq_field = self._labeled_input(layout, "Equation")
        eq_result = self._result_label(layout, height=dp(50))
        eq_last_steps = {"lines": []}

        def do_linear(instance):
            try:
                steps = []
                x = solve_linear(self.engine, eq_field.text, steps=steps)
                eq_result.text = f"x = {format_plain_number(x)}"
                eq_last_steps["lines"] = steps
                self.add_to_history(eq_field.text, eq_result.text)
            except Exception as exc:
                eq_result.text = f"Error: {exc}"
                eq_last_steps["lines"] = []

        def do_quadratic(instance):
            try:
                steps = []
                roots = solve_quadratic(self.engine, eq_field.text, steps=steps)
                eq_result.text = "x = " + ", ".join(format_plain_number(r) for r in roots)
                eq_last_steps["lines"] = steps
                self.add_to_history(eq_field.text, eq_result.text)
            except Exception as exc:
                eq_result.text = f"Error: {exc}"
                eq_last_steps["lines"] = []

        layout.add_widget(Label(
            text=(
                "For an equation with two letters (e.g. 6*x+15-3*y=0), "
                "type which one to solve for below - the other is treated "
                "as a known value and appears in the answer"
            ),
            size_hint_y=None, height=dp(46), font_size="11sp",
        ))
        solve_for_field = self._labeled_input(layout, "Solve for")
        solve_for_field.text = "x"

        def do_exact_solve(instance):
            try:
                target = solve_for_field.text.strip() or "x"
                solutions = symbolic_solve(eq_field.text, solve_for=target)
                eq_result.text = f"{target} = " + ", ".join(solutions)
                eq_last_steps["lines"] = [
                    "Solved exactly using symbolic algebra (sympy) - "
                    "detailed step-by-step algebra isn't available for exact "
                    "mode, but the answer is precise, not approximated."
                ]
                self.add_to_history(eq_field.text, eq_result.text)
            except Exception as exc:
                eq_result.text = f"Error: {exc}"
                eq_last_steps["lines"] = []

        def view_eq_steps(instance):
            self.show_steps_popup("How this was solved", eq_last_steps["lines"])

        self._action_row(layout, [
            ("Solve Linear", do_linear),
            ("Solve Quadratic", do_quadratic),
        ])
        self._action_row(layout, [("Solve (Exact)", do_exact_solve)])
        self._action_row(layout, [("View Steps", view_eq_steps)])

        note = Label(
            text=(
                "'Solve (Exact)' handles ANY equation - any degree, trig, "
                "logs - and gives exact answers (fractions, exact roots, "
                "even complex solutions) instead of decimal approximations."
            ),
            size_hint_y=None, height=dp(50), font_size="11sp",
        )
        note.bind(size=self.update_text_size)
        layout.add_widget(note)

        layout.add_widget(Label(
            text="Simplify or expand an expression",
            size_hint_y=None, height=dp(24), font_size="13sp", bold=True,
        ))
        simplify_field = self._labeled_input(layout, "Expression, e.g. sin(x)^2+cos(x)^2")
        simplify_result = self._result_label(layout, height=dp(40))

        def do_simplify(instance):
            try:
                result = symbolic_simplify(simplify_field.text)
                simplify_result.text = "= " + result
                self.add_to_history(f"simplify({simplify_field.text})", result)
            except Exception as exc:
                simplify_result.text = f"Error: {exc}"

        def do_expand(instance):
            try:
                result = symbolic_expand(simplify_field.text)
                simplify_result.text = "= " + result
                self.add_to_history(f"expand({simplify_field.text})", result)
            except Exception as exc:
                simplify_result.text = f"Error: {exc}"

        self._action_row(layout, [
            ("Simplify", do_simplify),
            ("Expand", do_expand),
        ])

        layout.add_widget(Label(
            text="Simultaneous equations in x and y",
            size_hint_y=None, height=dp(24), font_size="13sp", bold=True,
        ))
        eq1_field = self._labeled_input(layout, "Equation 1, e.g. 2*x+y=5")
        eq2_field = self._labeled_input(layout, "Equation 2, e.g. x-y=1")
        sim_result = self._result_label(layout, height=dp(40))
        sim_last_steps = {"lines": []}

        def do_simultaneous(instance):
            try:
                steps = []
                x, y = solve_simultaneous(self.engine, eq1_field.text, eq2_field.text, steps=steps)
                sim_result.text = f"x = {format_plain_number(x)}, y = {format_plain_number(y)}"
                sim_last_steps["lines"] = steps
                self.add_to_history(
                    f"{eq1_field.text} & {eq2_field.text}", sim_result.text
                )
            except Exception as exc:
                sim_result.text = f"Error: {exc}"
                sim_last_steps["lines"] = []

        def view_sim_steps(instance):
            self.show_steps_popup("How this was solved", sim_last_steps["lines"])

        self._action_row(layout, [("Solve Simultaneous", do_simultaneous)])
        self._action_row(layout, [("View Steps", view_sim_steps)])

        scroll.add_widget(layout)
        popup = self.make_sheet_popup("Algebra", scroll, height=0.75)
        popup.open()

    # ------------------------------------------------------------------
    # Calculus popup (Phase 4) - numerical methods, radians internally
    # ------------------------------------------------------------------

    def show_calculus(self):
        scroll = ScrollView()
        layout = BoxLayout(
            orientation="vertical",
            spacing=dp(8),
            padding=dp(10),
            size_hint_y=None,
        )
        layout.bind(minimum_height=layout.setter("height"))

        layout.add_widget(Label(
            text="f(x) = , e.g. x^2, sin(x), 1/x",
            size_hint_y=None, height=dp(24), font_size="12sp",
        ))
        expr_field = self._labeled_input(layout, "f(x)")
        point_field = self._labeled_input(layout, "x =")
        calc_result = self._result_label(layout, height=dp(60))
        calc_last_steps = {"lines": []}

        def with_radians(func):
            previous_mode = self.engine.angle_mode
            self.engine.angle_mode = "rad"
            try:
                return func()
            finally:
                self.engine.angle_mode = previous_mode

        def do_derivative(instance):
            try:
                x0 = float(point_field.text)
                h = 1e-5
                f_plus, f_minus, value = with_radians(
                    lambda: (
                        self.engine.evaluate(expr_field.text, variables={"x": x0 + h}),
                        self.engine.evaluate(expr_field.text, variables={"x": x0 - h}),
                        numerical_derivative(self.engine, expr_field.text, x0),
                    )
                )
                calc_result.text = f"f'({format_plain_number(x0)}) \u2248 {format_plain_number(value)}"
                calc_last_steps["lines"] = [
                    f"Uses a tiny step h = {h}",
                    f"f({format_plain_number(x0)}+h) = {format_plain_number(f_plus)}",
                    f"f({format_plain_number(x0)}-h) = {format_plain_number(f_minus)}",
                    f"slope \u2248 (f(x+h) - f(x-h)) \u00f7 (2h) = "
                    f"({format_plain_number(f_plus)} - {format_plain_number(f_minus)}) \u00f7 {2*h} "
                    f"= {format_plain_number(value)}",
                ]
                self.add_to_history(
                    f"d/dx[{expr_field.text}] at x={format_plain_number(x0)}", calc_result.text
                )
            except Exception as exc:
                calc_result.text = f"Error: {exc}"
                calc_last_steps["lines"] = []

        def do_second_derivative(instance):
            try:
                x0 = float(point_field.text)
                value = with_radians(
                    lambda: numerical_second_derivative(self.engine, expr_field.text, x0)
                )
                calc_result.text = f"f''({format_plain_number(x0)}) \u2248 {format_plain_number(value)}"
                calc_last_steps["lines"] = [
                    "Uses the same finite-difference idea, applied twice",
                    "f''(x) \u2248 (f(x+h) - 2f(x) + f(x-h)) \u00f7 h\u00b2",
                    f"Result: {format_plain_number(value)}",
                ]
                self.add_to_history(
                    f"d\u00b2/dx\u00b2[{expr_field.text}] at x={format_plain_number(x0)}",
                    calc_result.text,
                )
            except Exception as exc:
                calc_result.text = f"Error: {exc}"
                calc_last_steps["lines"] = []

        def do_limit(instance):
            try:
                x0 = float(point_field.text)
                value = with_radians(
                    lambda: numerical_limit(self.engine, expr_field.text, x0)
                )
                calc_result.text = f"limit at x={format_plain_number(x0)} \u2248 {format_plain_number(value)}"
                calc_last_steps["lines"] = [
                    f"Evaluated f(x) just below and just above x={format_plain_number(x0)}",
                    "If both sides agree closely, that shared value is the limit",
                    f"Result: {format_plain_number(value)}",
                ]
                self.add_to_history(
                    f"limit of {expr_field.text} as x->{format_plain_number(x0)}",
                    calc_result.text,
                )
            except Exception as exc:
                calc_result.text = f"Error: {exc}"
                calc_last_steps["lines"] = []

        order_field = self._labeled_input(layout, "Derivative order (for Exact, e.g. 1, 2, 3)")
        order_field.text = "1"

        def do_exact_derivative(instance):
            try:
                order_text = order_field.text.strip()
                order = int(order_text) if order_text else 1
                if order < 1:
                    raise ValueError("Order must be 1 or higher")
                result = symbolic_derivative(expr_field.text, order=order)
                label = "f'(x)" if order == 1 else f"f^({order})(x)"
                calc_result.text = f"{label} = {result}"
                calc_last_steps["lines"] = [
                    f"Computed the {order}{'st' if order==1 else 'nd' if order==2 else 'rd' if order==3 else 'th'} "
                    "derivative using symbolic algebra (sympy) - an exact "
                    "formula, not a numerical estimate. Detailed rule-by-rule "
                    "working (power rule, chain rule, etc.) isn't shown."
                ]
                self.add_to_history(f"{label} of {expr_field.text}", result)
            except Exception as exc:
                calc_result.text = f"Error: {exc}"
                calc_last_steps["lines"] = []

        def view_calc_steps(instance):
            self.show_steps_popup("How this was worked out", calc_last_steps["lines"])

        self._action_row(layout, [
            ("f'(x)", do_derivative),
            ("f''(x)", do_second_derivative),
            ("limit", do_limit),
        ])

        self._action_row(layout, [("Exact f\u207f(x)", do_exact_derivative)])
        self._action_row(layout, [("View Steps", view_calc_steps)])

        layout.add_widget(Label(
            text="Definite integral, from a to b",
            size_hint_y=None, height=dp(24), font_size="13sp", bold=True,
        ))
        a_field = self._labeled_input(layout, "a =")
        b_field = self._labeled_input(layout, "b =")
        integral_result = self._result_label(layout, height=dp(40))
        integral_last_steps = {"lines": []}

        def do_integral(instance):
            try:
                a, b = float(a_field.text), float(b_field.text)
                value = with_radians(
                    lambda: numerical_integral(self.engine, expr_field.text, a, b)
                )
                integral_result.text = f"\u222b f(x) dx \u2248 {format_plain_number(value)}"
                integral_last_steps["lines"] = [
                    f"Split [{format_plain_number(a)}, {format_plain_number(b)}] into 1000 "
                    "thin slices",
                    "Used Simpson's rule to add up the area of each slice",
                    f"Total \u2248 {format_plain_number(value)}",
                ]
                self.add_to_history(
                    f"\u222b[{format_plain_number(a)},{format_plain_number(b)}] "
                    f"{expr_field.text} dx",
                    integral_result.text,
                )
            except Exception as exc:
                integral_result.text = f"Error: {exc}"
                integral_last_steps["lines"] = []

        def do_exact_integral(instance):
            try:
                a_text, b_text = a_field.text.strip(), b_field.text.strip()
                if a_text and b_text:
                    result = symbolic_integral(expr_field.text, a_text, b_text)
                    integral_result.text = f"\u222b f(x) dx = {result}"
                else:
                    result = symbolic_integral(expr_field.text)
                    integral_result.text = f"\u222b f(x) dx = {result} + C"
                integral_last_steps["lines"] = [
                    "Computed using symbolic algebra (sympy) - an exact "
                    "closed-form answer, not an approximation."
                ]
                self.add_to_history(f"\u222b {expr_field.text} dx", integral_result.text)
            except Exception as exc:
                integral_result.text = f"Error: {exc}"
                integral_last_steps["lines"] = []

        def view_integral_steps(instance):
            self.show_steps_popup("How this was worked out", integral_last_steps["lines"])

        self._action_row(layout, [
            ("Integrate", do_integral),
            ("Exact Integral", do_exact_integral),
        ])
        self._action_row(layout, [("View Steps", view_integral_steps)])

        note = Label(
            text=(
                "Note: the plain buttons give close numerical "
                "approximations. 'Exact' buttons give exact symbolic "
                "formulas instead (leave a/b blank for an indefinite "
                "exact integral). Trig here always uses radians, "
                "regardless of the Scientific DEG/RAD setting."
            ),
            size_hint_y=None, height=dp(64), font_size="11sp",
        )
        note.bind(size=self.update_text_size)
        layout.add_widget(note)

        scroll.add_widget(layout)
        popup = self.make_sheet_popup("Calculus", scroll, height=0.8)
        popup.open()

    # ------------------------------------------------------------------
    # Matrices & Vectors popup (Phase 5)
    # ------------------------------------------------------------------

    def show_matrices_vectors(self):
        scroll = ScrollView()
        layout = BoxLayout(
            orientation="vertical",
            spacing=dp(8),
            padding=dp(10),
            size_hint_y=None,
        )
        layout.bind(minimum_height=layout.setter("height"))

        layout.add_widget(Label(
            text="Matrices - rows separated by ; , values by ,  e.g. 1,2;3,4",
            size_hint_y=None, height=dp(36), font_size="12sp",
        ))
        matrix_a_field = self._labeled_input(layout, "Matrix A")
        matrix_b_field = self._labeled_input(layout, "Matrix B (for +, -, x)")
        matrix_result = self._result_label(layout, height=dp(90))

        def matrix_op(op):
            def handler(instance):
                try:
                    a = parse_matrix(matrix_a_field.text)
                    label = None
                    if op in ("add", "sub", "mul"):
                        b = parse_matrix(matrix_b_field.text)
                        if op == "add":
                            result = matrix_add(a, b)
                            label = f"[{matrix_a_field.text}] + [{matrix_b_field.text}]"
                        elif op == "sub":
                            result = matrix_add(a, b, sign=-1)
                            label = f"[{matrix_a_field.text}] - [{matrix_b_field.text}]"
                        else:
                            result = matrix_multiply(a, b)
                            label = f"[{matrix_a_field.text}] x [{matrix_b_field.text}]"
                        matrix_result.text = format_matrix(result)
                    elif op == "det":
                        matrix_result.text = f"det(A) = {format_plain_number(matrix_determinant(a))}"
                        label = f"det([{matrix_a_field.text}])"
                    elif op == "inv":
                        matrix_result.text = format_matrix(matrix_inverse(a))
                        label = f"inverse([{matrix_a_field.text}])"
                    elif op == "transpose":
                        matrix_result.text = format_matrix(matrix_transpose(a))
                        label = f"transpose([{matrix_a_field.text}])"
                    elif op == "rank":
                        matrix_result.text = f"rank(A) = {matrix_rank(a)}"
                        label = f"rank([{matrix_a_field.text}])"
                    if label is not None:
                        self.add_to_history(label, matrix_result.text)
                except Exception as exc:
                    matrix_result.text = f"Error: {exc}"
            return handler

        self._action_row(layout, [
            ("A+B", matrix_op("add")),
            ("A-B", matrix_op("sub")),
            ("A\u00d7B", matrix_op("mul")),
        ])
        self._action_row(layout, [
            ("det(A)", matrix_op("det")),
            ("inverse(A)", matrix_op("inv")),
        ])
        self._action_row(layout, [
            ("transpose(A)", matrix_op("transpose")),
            ("rank(A)", matrix_op("rank")),
        ])

        layout.add_widget(Label(
            text="Vectors - comma separated, e.g. 1,2,3",
            size_hint_y=None, height=dp(24), font_size="13sp", bold=True,
        ))
        vec_a_field = self._labeled_input(layout, "Vector A")
        vec_b_field = self._labeled_input(layout, "Vector B (for +, dot, cross)")
        vector_result = self._result_label(layout, height=dp(50))

        def vector_op(op):
            def handler(instance):
                try:
                    a = parse_vector(vec_a_field.text)
                    label = None
                    if op in ("add", "dot", "cross"):
                        b = parse_vector(vec_b_field.text)
                        if op == "add":
                            vector_result.text = format_vector(vector_add(a, b))
                            label = f"({vec_a_field.text}) + ({vec_b_field.text})"
                        elif op == "dot":
                            vector_result.text = f"A\u00b7B = {format_plain_number(vector_dot(a, b))}"
                            label = f"({vec_a_field.text}) \u00b7 ({vec_b_field.text})"
                        else:
                            vector_result.text = format_vector(vector_cross(a, b))
                            label = f"({vec_a_field.text}) \u00d7 ({vec_b_field.text})"
                    elif op == "magnitude":
                        vector_result.text = f"|A| = {format_plain_number(vector_magnitude(a))}"
                        label = f"|({vec_a_field.text})|"
                    elif op == "unit":
                        vector_result.text = format_vector(vector_unit(a))
                        label = f"unit({vec_a_field.text})"
                    if label is not None:
                        self.add_to_history(label, vector_result.text)
                except Exception as exc:
                    vector_result.text = f"Error: {exc}"
            return handler

        self._action_row(layout, [
            ("A+B", vector_op("add")),
            ("A\u00b7B dot", vector_op("dot")),
        ])
        self._action_row(layout, [
            ("A\u00d7B cross", vector_op("cross")),
            ("|A|", vector_op("magnitude")),
            ("unit(A)", vector_op("unit")),
        ])

        scroll.add_widget(layout)
        popup = self.make_sheet_popup("Matrices & Vectors", scroll, height=0.85)
        popup.open()

    # ------------------------------------------------------------------
    # Conversions popup (Phase 7)
    # ------------------------------------------------------------------

    def show_conversions(self):
        outer = BoxLayout(
            orientation="vertical",
            spacing=dp(6),
            padding=dp(10),
        )

        category_grid = GridLayout(
            cols=4,
            size_hint_y=None,
            height=dp(90),
            spacing=dp(4),
        )
        for category in CONVERSION_CATEGORIES:
            button = Button(text=category, font_size="12sp")
            button.bind(on_press=lambda inst, c=category: select_category(c))
            category_grid.add_widget(button)
        outer.add_widget(category_grid)

        units_area = BoxLayout(orientation="vertical", spacing=dp(6))
        outer.add_widget(units_area)

        state = {"category": None, "from_unit": None, "to_unit": None}

        def select_category(category):
            state["category"] = category
            state["from_unit"] = None
            state["to_unit"] = None
            rebuild_units_area()

        def rebuild_units_area():
            units_area.clear_widgets()
            category = state["category"]
            if category is None:
                units_area.add_widget(Label(text="Pick a category above"))
                return

            unit_names = (
                TEMPERATURE_UNITS if category == "Temperature"
                else list(CONVERSION_CATEGORIES[category].keys())
            )
            state["from_unit"] = unit_names[0]
            state["to_unit"] = unit_names[1] if len(unit_names) > 1 else unit_names[0]

            units_area.add_widget(Label(
                text=f"{category}: from",
                size_hint_y=None, height=dp(22), font_size="12sp",
            ))
            from_grid = GridLayout(
                cols=4, size_hint_y=None, height=dp(40 * ((len(unit_names) + 3) // 4)),
                spacing=dp(3),
            )
            from_buttons = {}

            def pick_from(unit):
                state["from_unit"] = unit
                for name, btn in from_buttons.items():
                    btn.background_color = (0.1, 0.55, 0.9, 1) if name == unit else (0.15, 0.15, 0.18, 1)

            for unit in unit_names:
                b = Button(
                    text=unit, font_size="12sp",
                    background_normal="",
                    background_color=(0.1, 0.55, 0.9, 1) if unit == state["from_unit"] else (0.15, 0.15, 0.18, 1),
                )
                b.bind(on_press=lambda inst, u=unit: pick_from(u))
                from_buttons[unit] = b
                from_grid.add_widget(b)
            units_area.add_widget(from_grid)

            units_area.add_widget(Label(
                text="to",
                size_hint_y=None, height=dp(22), font_size="12sp",
            ))
            to_grid = GridLayout(
                cols=4, size_hint_y=None, height=dp(40 * ((len(unit_names) + 3) // 4)),
                spacing=dp(3),
            )
            to_buttons = {}

            def pick_to(unit):
                state["to_unit"] = unit
                for name, btn in to_buttons.items():
                    btn.background_color = (0.1, 0.55, 0.9, 1) if name == unit else (0.15, 0.15, 0.18, 1)

            for unit in unit_names:
                b = Button(
                    text=unit, font_size="12sp",
                    background_normal="",
                    background_color=(0.1, 0.55, 0.9, 1) if unit == state["to_unit"] else (0.15, 0.15, 0.18, 1),
                )
                b.bind(on_press=lambda inst, u=unit: pick_to(u))
                to_buttons[unit] = b
                to_grid.add_widget(b)
            units_area.add_widget(to_grid)

            value_field = TextInput(
                multiline=False, size_hint_y=None, height=dp(40),
                hint_text="Value to convert",
            )
            units_area.add_widget(value_field)

            result_label = Label(text="", size_hint_y=None, height=dp(40))
            result_label.bind(size=self.update_text_size)

            def do_convert(instance):
                try:
                    value = float(value_field.text)
                    converted = convert_units(category, value, state["from_unit"], state["to_unit"])
                    result_label.text = (
                        f"{format_plain_number(value)} {state['from_unit']} = "
                        f"{format_plain_number(converted)} {state['to_unit']}"
                    )
                    if category == "Temperature":
                        state["last_steps"] = [
                            f"Temperature uses a formula, not a simple factor, "
                            f"since {state['from_unit']} and {state['to_unit']} "
                            f"don't share a common zero point",
                            f"Result: {format_plain_number(converted)} {state['to_unit']}",
                        ]
                    else:
                        units = CONVERSION_CATEGORIES[category]
                        from_factor = units[state["from_unit"]]
                        to_factor = units[state["to_unit"]]
                        state["last_steps"] = [
                            f"1 {state['from_unit']} = {format_plain_number(from_factor)} base units",
                            f"1 {state['to_unit']} = {format_plain_number(to_factor)} base units",
                            f"{format_plain_number(value)} \u00d7 {format_plain_number(from_factor)} "
                            f"\u00f7 {format_plain_number(to_factor)} = {format_plain_number(converted)}",
                        ]
                    self.add_to_history(
                        f"{format_plain_number(value)} {state['from_unit']} to {state['to_unit']}",
                        result_label.text,
                    )
                except Exception as exc:
                    result_label.text = f"Error: {exc}"
                    state["last_steps"] = []

            def view_conversion_steps(instance):
                self.show_steps_popup("How this was worked out", state.get("last_steps", []))

            convert_button = Button(text="Convert", size_hint_y=None, height=dp(40))
            convert_button.bind(on_press=do_convert)
            units_area.add_widget(convert_button)
            units_area.add_widget(result_label)

            steps_button = Button(text="View Steps", size_hint_y=None, height=dp(40))
            steps_button.bind(on_press=view_conversion_steps)
            units_area.add_widget(steps_button)

        rebuild_units_area()

        popup = self.make_sheet_popup("Conversions", outer, height=0.85)
        popup.open()

        return popup, state, select_category

    # ------------------------------------------------------------------
    # Graphing popup (Phase 6 - basic function plotting)
    # ------------------------------------------------------------------

    def show_graph(self):
        layout = BoxLayout(
            orientation="vertical",
            spacing=dp(6),
            padding=dp(10),
        )

        expr_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(40),
            spacing=dp(5),
        )
        expr_field = TextInput(multiline=False, hint_text="f(x) = e.g. sin(x)")
        expr_row.add_widget(expr_field)
        layout.add_widget(expr_row)

        expr2_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(40),
            spacing=dp(5),
        )
        expr2_field = TextInput(multiline=False, hint_text="g(x) = optional, e.g. x+2")
        expr2_row.add_widget(expr2_field)
        layout.add_widget(expr2_row)

        range_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(40),
            spacing=dp(5),
        )
        x_min_field = TextInput(multiline=False, text="-10")
        x_max_field = TextInput(multiline=False, text="10")
        range_row.add_widget(Label(text="x min", size_hint_x=0.3))
        range_row.add_widget(x_min_field)
        range_row.add_widget(Label(text="x max", size_hint_x=0.3))
        range_row.add_widget(x_max_field)
        layout.add_widget(range_row)

        plot_area = BoxLayout(size_hint_y=1)
        layout.add_widget(plot_area)

        result_label = Label(text="", size_hint_y=None, height=dp(50))
        result_label.bind(size=self.update_text_size)
        layout.add_widget(result_label)

        state = {"graph": None}

        def with_radians(func):
            previous_mode = self.engine.angle_mode
            self.engine.angle_mode = "rad"
            try:
                return func()
            finally:
                self.engine.angle_mode = previous_mode

        def plot(instance=None):
            plot_area.clear_widgets()
            result_label.text = ""
            try:
                x_min = float(x_min_field.text)
                x_max = float(x_max_field.text)
                if x_min >= x_max:
                    raise ValueError("x min must be less than x max")

                expr2 = expr2_field.text.strip() or None

                graph = with_radians(
                    lambda: GraphCanvas(
                        self.engine, expr_field.text, expression2=expr2,
                        x_min=x_min, x_max=x_max,
                    )
                )

                plot_area.add_widget(graph)
                state["graph"] = graph
                if graph.error:
                    result_label.text = graph.error
            except Exception as exc:
                result_label.text = f"Error: {exc}"

        def zoom(factor):
            def handler(instance):
                try:
                    x_min, x_max = float(x_min_field.text), float(x_max_field.text)
                    center = (x_min + x_max) / 2
                    half_range = (x_max - x_min) / 2 * factor
                    x_min_field.text = format_plain_number(center - half_range)
                    x_max_field.text = format_plain_number(center + half_range)
                    plot()
                except Exception as exc:
                    result_label.text = f"Error: {exc}"
            return handler

        def pan(direction):
            def handler(instance):
                try:
                    x_min, x_max = float(x_min_field.text), float(x_max_field.text)
                    shift = (x_max - x_min) * 0.25 * direction
                    x_min_field.text = format_plain_number(x_min + shift)
                    x_max_field.text = format_plain_number(x_max + shift)
                    plot()
                except Exception as exc:
                    result_label.text = f"Error: {exc}"
            return handler

        def find_roots_pressed(instance):
            try:
                x_min, x_max = float(x_min_field.text), float(x_max_field.text)
                roots = with_radians(
                    lambda: find_roots(self.engine, expr_field.text, x_min, x_max)
                )
                if roots:
                    result_label.text = "Roots: " + ", ".join(
                        format_plain_number(r) for r in sorted(roots)
                    )
                else:
                    result_label.text = "No roots found in this range"
            except Exception as exc:
                result_label.text = f"Error: {exc}"

        def find_intersections_pressed(instance):
            try:
                if not expr2_field.text.strip():
                    result_label.text = "Enter a g(x) to find intersections with"
                    return
                x_min, x_max = float(x_min_field.text), float(x_max_field.text)
                points = with_radians(
                    lambda: find_intersections(
                        self.engine, expr_field.text, expr2_field.text, x_min, x_max
                    )
                )
                if points:
                    result_label.text = "Intersections: " + ", ".join(
                        f"({format_plain_number(x)}, {format_plain_number(y)})"
                        for x, y in sorted(points, key=lambda p: p[0])
                    )
                else:
                    result_label.text = "No intersections found in this range"
            except Exception as exc:
                result_label.text = f"Error: {exc}"

        def overlay_derivative(instance):
            try:
                derivative_expr = symbolic_derivative(expr_field.text)
                expr2_field.text = derivative_expr
                plot()
                result_label.text = f"Overlaid f'(x) = {derivative_expr}"
            except Exception as exc:
                result_label.text = f"Error: {exc}"

        def overlay_integral(instance):
            try:
                integral_expr = symbolic_integral(expr_field.text)
                expr2_field.text = integral_expr
                plot()
                result_label.text = f"Overlaid \u222bf(x)dx = {integral_expr} (with C=0)"
            except Exception as exc:
                result_label.text = f"Error: {exc}"

        self._action_row(layout, [
            ("Plot", plot),
            ("Roots", find_roots_pressed),
            ("Intersect", find_intersections_pressed),
        ])
        self._action_row(layout, [
            ("Zoom In", zoom(0.5)),
            ("Zoom Out", zoom(2)),
            ("\u25c0 Pan", pan(-1)),
            ("Pan \u25b6", pan(1)),
        ])
        self._action_row(layout, [
            ("Overlay f'(x)", overlay_derivative),
            ("Overlay \u222bf(x)", overlay_integral),
        ])

        note = Label(
            text=(
                "Overlay buttons fill g(x) with the exact derivative or "
                "indefinite integral (constant of integration set to 0 for "
                "plotting) and re-plot automatically - uses symbolic math, "
                "so it needs sympy available."
            ),
            size_hint_y=None, height=dp(46), font_size="11sp",
        )
        note.bind(size=self.update_text_size)
        layout.add_widget(note)

        popup = self.make_sheet_popup("Graph", layout, height=0.9)
        popup.open()

        return popup, plot

    def show_scan(self):
        layout = BoxLayout(
            orientation="vertical",
            spacing=dp(10),
            padding=dp(10),
        )

        if not is_scan_available():
            layout.add_widget(Label(
                text=(
                    "Camera scanning needs an actual Android device with "
                    "Google Play Services - it isn't available here.\n\n"
                    "Workflow: take a photo of a single line of printed "
                    "math with your camera app, then come back here and "
                    "choose that photo to read it."
                ),
                halign="center", valign="middle",
            ))
            close_button = Button(text="Close", size_hint_y=None, height=dp(45))
            layout.add_widget(close_button)
            popup = self.make_sheet_popup("Scan", layout, height=0.4)
            close_button.bind(on_press=popup.dismiss)
            popup.open()
            return popup

        status_label = Label(
            text="Choose a photo of a single line of printed math.",
            size_hint_y=None, height=dp(50),
        )
        status_label.bind(size=self.update_text_size)
        layout.add_widget(status_label)

        choose_button = Button(text="Choose Photo", size_hint_y=None, height=dp(45))
        layout.add_widget(choose_button)

        review_field = TextInput(
            multiline=False,
            hint_text="Recognized text will appear here for you to check",
            size_hint_y=None, height=dp(45),
        )
        layout.add_widget(review_field)

        insert_button = Button(
            text="Insert Into Calculator", size_hint_y=None, height=dp(45),
        )
        layout.add_widget(insert_button)

        close_button = Button(text="Close", size_hint_y=None, height=dp(45))
        layout.add_widget(close_button)

        def on_image_chosen(path):
            if not path:
                status_label.text = "Cancelled - no photo chosen."
                return
            status_label.text = "Reading text from photo..."
            try:
                raw_text = recognize_text_from_image(path)
                cleaned = clean_scanned_text(raw_text)
                review_field.text = cleaned
                status_label.text = (
                    "Check the text below before inserting - OCR isn't "
                    "always perfect, fix anything that looks wrong."
                )
            except ScanUnavailable as exc:
                status_label.text = f"Error: {exc}"

        def do_choose(instance):
            status_label.text = "Opening photo picker..."
            try:
                pick_image_from_gallery(on_image_chosen)
            except ScanUnavailable as exc:
                status_label.text = f"Error: {exc}"

        def do_insert(instance):
            if not review_field.text.strip():
                status_label.text = "Nothing to insert yet."
                return
            self.reset_if_calculated()
            self._insert_at_cursor(review_field.text.strip())
            self.update_display()
            status_label.text = "Inserted into the calculator."

        choose_button.bind(on_press=do_choose)
        insert_button.bind(on_press=do_insert)

        popup = self.make_sheet_popup("Scan", layout, height=0.6)
        close_button.bind(on_press=popup.dismiss)
        popup.open()
        return popup

    def show_settings(self):
        layout = BoxLayout(
            orientation="vertical",
            spacing=dp(10),
            padding=dp(10),
        )

        layout.add_widget(Label(
            text="Appearance",
            size_hint_y=None, height=dp(24), font_size="13sp", bold=True,
        ))

        theme_button = Button(
            text="Switch to Light Mode" if self.dark_mode else "Switch to Dark Mode",
            size_hint_y=None, height=dp(45),
        )

        def do_toggle_theme(instance):
            self.toggle_theme()
            theme_button.text = "Switch to Light Mode" if self.dark_mode else "Switch to Dark Mode"

        theme_button.bind(on_press=do_toggle_theme)
        layout.add_widget(theme_button)

        layout.add_widget(Label(
            text="Data",
            size_hint_y=None, height=dp(24), font_size="13sp", bold=True,
        ))

        clear_data_button = Button(
            text="Clear All Saved Data (memory & history)",
            size_hint_y=None, height=dp(45),
        )
        clear_status = Label(text="", size_hint_y=None, height=dp(30))
        clear_status.bind(size=self.update_text_size)

        def do_clear_data(instance):
            self.memory = 0
            self.history = []
            self.update_memory_indicator()
            self.history_label.text = "Welcome.\n\nLet's calculate something."
            self.save_state()
            clear_status.text = "All saved data cleared."

        clear_data_button.bind(on_press=do_clear_data)
        layout.add_widget(clear_data_button)
        layout.add_widget(clear_status)

        close_button = Button(text="Close", size_hint_y=None, height=dp(45))
        layout.add_widget(close_button)

        popup = self.make_sheet_popup("Settings", layout, height=0.45)
        close_button.bind(on_press=popup.dismiss)
        popup.open()

    def show_about(self, instance):
        layout = BoxLayout(
            orientation="vertical",
            spacing=dp(10),
            padding=dp(10),
        )

        about_label = Label(
            text=(
                "MATHEMATICAL CALCULATOR\n\n"
                f"Version {APP_VERSION}\n\n"
                "Created by Quareeb\n\n"
                "Thank you for using this calculator!"
            ),
            halign="center",
            valign="middle",
        )
        about_label.bind(size=self.update_text_size)

        close_button = Button(
            text="Close",
            size_hint_y=None,
            height=dp(45),
        )

        layout.add_widget(about_label)
        layout.add_widget(close_button)

        popup = self.make_sheet_popup("About", layout, height=0.35)

        close_button.bind(on_press=popup.dismiss)
        popup.open()


class MathematicalCalculatorApp(App):
    def build(self):
        self.title = "Mathematical Calculator"
        return Calculator()


if __name__ == "__main__":
    MathematicalCalculatorApp().run()
