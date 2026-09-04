import ast
import json
import math
import operator
import os
import re
from fractions import Fraction

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
        self.angle_mode = "deg"  # "deg" or "rad"

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

    def _trig(self, func, x):
        if self.angle_mode == "deg":
            x = math.radians(x)
        return func(x)

    def _inverse_trig(self, func, x):
        result = func(x)
        if self.angle_mode == "deg":
            result = math.degrees(result)
        return result

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

    def evaluate(self, expression, variables=None):
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
        return self._solve(tree.body)

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

    def _solve(self, node):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError("Invalid value")

        if isinstance(node, ast.BinOp):
            operation = self.operators.get(type(node.op))
            if operation is None:
                raise ValueError("Unsupported operation")

            left = self._solve(node.left)
            right = self._solve(node.right)

            if isinstance(node.op, (ast.Div, ast.Mod)) and right == 0:
                raise ZeroDivisionError("Cannot divide by zero")

            if isinstance(node.op, ast.Pow) and abs(right) > 1000:
                raise ValueError("Power too large")

            return operation(left, right)

        if isinstance(node, ast.UnaryOp):
            operation = self.operators.get(type(node.op))
            if operation is None:
                raise ValueError("Unsupported operation")
            return operation(self._solve(node.operand))

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

            arguments = [self._solve(arg) for arg in node.args]
            return function(*arguments)

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


def solve_linear(engine, equation):
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

    return -y0 / a


def solve_quadratic(engine, equation):
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
        return [-coeff_c / coeff_b]

    discriminant = coeff_b * coeff_b - 4 * coeff_a * coeff_c
    if discriminant < 0:
        raise ValueError("No real roots")

    sqrt_d = math.sqrt(discriminant)
    x1 = (-coeff_b + sqrt_d) / (2 * coeff_a)
    x2 = (-coeff_b - sqrt_d) / (2 * coeff_a)
    return sorted({round(x1, 10), round(x2, 10)})


def solve_simultaneous(engine, equation1, equation2):
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
        raise ValueError("No unique solution (equations are parallel or identical)")

    x = (c1 * b2 - c2 * b1) / det
    y = (a1 * c2 - a2 * c1) / det
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
        self.add_widget(self.preview_label)

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

        if self.history:
            self.history_label.text = "\n".join(
                f"{expr} = {self.format_number(ans)}"
                for expr, ans in self.history[-3:]
            )

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------

    def update_text_size(self, widget, size):
        widget.text_size = size

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

        if text in ("DEG", "RAD"):
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
            self.expression += value
            self.update_display()
            return

        if value.isdigit():
            self.reset_if_calculated()
            self.expression += value
            self.update_display()
            return

        # Fallback for any unexpected label - just append it as typed.
        self.reset_if_calculated()
        self.expression += value
        self.update_display()

    # ------------------------------------------------------------------
    # Expression editing helpers (Phase 1 reliability)
    # ------------------------------------------------------------------

    def reset_if_calculated(self):
        if self.just_calculated:
            self.expression = ""
            self.just_calculated = False

    def clear_all(self):
        self.expression = ""
        self.display.text = "0"
        self.preview_label.text = ""
        self.just_calculated = False

    def backspace(self):
        self.expression = self.expression[:-1]
        self.just_calculated = False
        self.update_display()

    def append_decimal(self):
        self.reset_if_calculated()

        segment = re.split(r"[+\-×÷^%(]", self.expression)[-1] if self.expression else ""
        if "." in segment:
            return

        self.expression += "0." if not segment else "."
        self.update_display()

    def append_operator(self, op):
        if not self.expression:
            if op == "-":
                self.expression = "-"
                self.update_display()
            return

        last = self.expression[-1]

        if last in OPERATOR_CHARS:
            if op == "-" and last != "-":
                # allow forming a negative number, e.g. 5x-3
                self.expression += op
            else:
                self.expression = self.expression[:-1] + op
        else:
            self.expression += op

        self.just_calculated = False
        self.update_display()

    def toggle_sign(self):
        self.reset_if_calculated()

        match = re.search(r"(-?\d*\.?\d+)$", self.expression)
        if not match:
            if not self.expression:
                self.expression = "-"
                self.update_display()
            return

        number = match.group(1)
        start = match.start(1)

        if number.startswith("-"):
            new_number = number[1:]
        else:
            new_number = "-" + number

        self.expression = self.expression[:start] + new_number + self.expression[match.end(1):]
        self.update_display()

    def wrap_whole(self, prefix, suffix=")"):
        if self.expression:
            self.expression = f"{prefix}{self.expression}{suffix}"
        else:
            self.expression = prefix
        self.just_calculated = False
        self.update_display()

    def append_power(self, digit):
        self.append_operator("^")
        self.expression += digit
        self.update_display()

    def update_display(self):
        self.display.text = self.expression or "0"
        self.update_preview()

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
            self.just_calculated = False

        except (ValueError, SyntaxError, TypeError, OverflowError):
            self.display.text = "Math Error"
            self.preview_label.text = ""
            self.expression = ""
            self.just_calculated = False

        except Exception:
            self.display.text = "Math Error"
            self.preview_label.text = ""
            self.expression = ""
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

        if text in ("DEG", "RAD"):
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
            self.expression += function_tokens[text]
            self.update_display()
            return

        if text in ("π", "e"):
            self.reset_if_calculated()
            self.expression += text
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
        if self.engine.angle_mode == "deg":
            self.engine.angle_mode = "rad"
        else:
            self.engine.angle_mode = "deg"

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
        self.expression += self.format_number(self.memory)
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
                entry_button = Button(
                    text=entry_text,
                    size_hint_y=None,
                    height=dp(45),
                    halign="left",
                )

                def reuse(instance, answer=ans):
                    self.reset_if_calculated()
                    self.expression += self.format_number(answer)
                    self.update_display()

                entry_button.bind(on_press=reuse)
                history_grid.add_widget(entry_button)

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

        layout.add_widget(Label(
            text="Prime check & factorization",
            size_hint_y=None, height=dp(24), font_size="13sp", bold=True,
        ))
        n_field = self._labeled_input(layout, "Whole number")
        n_result = self._result_label(layout)

        def check_prime(instance):
            try:
                n = int(float(n_field.text))
                verdict = "prime" if is_prime(n) else "not prime"
                n_result.text = f"{n} is {verdict}"
            except Exception as exc:
                n_result.text = f"Error: {exc}"

        def factorize(instance):
            try:
                n = int(float(n_field.text))
                factors = prime_factorize(n)
                n_result.text = format_prime_factors(factors)
            except Exception as exc:
                n_result.text = f"Error: {exc}"

        self._action_row(layout, [
            ("Is Prime?", check_prime),
            ("Prime Factors", factorize),
        ])

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
                ab_result.text = f"GCD = {gcd_of(a, b)}"
            except Exception as exc:
                ab_result.text = f"Error: {exc}"

        def compute_lcm(instance):
            try:
                a, b = int(float(a_field.text)), int(float(b_field.text))
                ab_result.text = f"LCM = {lcm_of(a, b)}"
            except Exception as exc:
                ab_result.text = f"Error: {exc}"

        self._action_row(layout, [
            ("GCD", compute_gcd),
            ("LCM", compute_lcm),
        ])

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
                n, d = simplify_fraction(num, den)
                frac_result.text = f"= {n}/{d}"
            except Exception as exc:
                frac_result.text = f"Error: {exc}"

        self._action_row(layout, [("Simplify", simplify)])

        scroll.add_widget(layout)
        popup = self.make_sheet_popup("Number Theory", scroll, height=0.75)
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

        def do_linear(instance):
            try:
                x = solve_linear(self.engine, eq_field.text)
                eq_result.text = f"x = {format_plain_number(x)}"
            except Exception as exc:
                eq_result.text = f"Error: {exc}"

        def do_quadratic(instance):
            try:
                roots = solve_quadratic(self.engine, eq_field.text)
                eq_result.text = "x = " + ", ".join(format_plain_number(r) for r in roots)
            except Exception as exc:
                eq_result.text = f"Error: {exc}"

        self._action_row(layout, [
            ("Solve Linear", do_linear),
            ("Solve Quadratic", do_quadratic),
        ])

        layout.add_widget(Label(
            text="Simultaneous equations in x and y",
            size_hint_y=None, height=dp(24), font_size="13sp", bold=True,
        ))
        eq1_field = self._labeled_input(layout, "Equation 1, e.g. 2*x+y=5")
        eq2_field = self._labeled_input(layout, "Equation 2, e.g. x-y=1")
        sim_result = self._result_label(layout, height=dp(40))

        def do_simultaneous(instance):
            try:
                x, y = solve_simultaneous(self.engine, eq1_field.text, eq2_field.text)
                sim_result.text = f"x = {format_plain_number(x)}, y = {format_plain_number(y)}"
            except Exception as exc:
                sim_result.text = f"Error: {exc}"

        self._action_row(layout, [("Solve Simultaneous", do_simultaneous)])

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
                value = with_radians(
                    lambda: numerical_derivative(self.engine, expr_field.text, x0)
                )
                calc_result.text = f"f'({format_plain_number(x0)}) \u2248 {format_plain_number(value)}"
            except Exception as exc:
                calc_result.text = f"Error: {exc}"

        def do_second_derivative(instance):
            try:
                x0 = float(point_field.text)
                value = with_radians(
                    lambda: numerical_second_derivative(self.engine, expr_field.text, x0)
                )
                calc_result.text = f"f''({format_plain_number(x0)}) \u2248 {format_plain_number(value)}"
            except Exception as exc:
                calc_result.text = f"Error: {exc}"

        def do_limit(instance):
            try:
                x0 = float(point_field.text)
                value = with_radians(
                    lambda: numerical_limit(self.engine, expr_field.text, x0)
                )
                calc_result.text = f"limit at x={format_plain_number(x0)} \u2248 {format_plain_number(value)}"
            except Exception as exc:
                calc_result.text = f"Error: {exc}"

        self._action_row(layout, [
            ("f'(x)", do_derivative),
            ("f''(x)", do_second_derivative),
            ("limit", do_limit),
        ])

        layout.add_widget(Label(
            text="Definite integral, from a to b",
            size_hint_y=None, height=dp(24), font_size="13sp", bold=True,
        ))
        a_field = self._labeled_input(layout, "a =")
        b_field = self._labeled_input(layout, "b =")
        integral_result = self._result_label(layout, height=dp(40))

        def do_integral(instance):
            try:
                a, b = float(a_field.text), float(b_field.text)
                value = with_radians(
                    lambda: numerical_integral(self.engine, expr_field.text, a, b)
                )
                integral_result.text = f"\u222b f(x) dx \u2248 {format_plain_number(value)}"
            except Exception as exc:
                integral_result.text = f"Error: {exc}"

        self._action_row(layout, [("Integrate", do_integral)])

        note = Label(
            text=(
                "Note: results are close numerical approximations, "
                "not exact symbolic answers. Trig functions here always "
                "use radians, regardless of the Scientific DEG/RAD setting."
            ),
            size_hint_y=None, height=dp(50), font_size="11sp",
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
                    if op in ("add", "sub", "mul"):
                        b = parse_matrix(matrix_b_field.text)
                        if op == "add":
                            result = matrix_add(a, b)
                        elif op == "sub":
                            result = matrix_add(a, b, sign=-1)
                        else:
                            result = matrix_multiply(a, b)
                        matrix_result.text = format_matrix(result)
                    elif op == "det":
                        matrix_result.text = f"det(A) = {format_plain_number(matrix_determinant(a))}"
                    elif op == "inv":
                        matrix_result.text = format_matrix(matrix_inverse(a))
                    elif op == "transpose":
                        matrix_result.text = format_matrix(matrix_transpose(a))
                    elif op == "rank":
                        matrix_result.text = f"rank(A) = {matrix_rank(a)}"
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
                    if op in ("add", "dot", "cross"):
                        b = parse_vector(vec_b_field.text)
                        if op == "add":
                            vector_result.text = format_vector(vector_add(a, b))
                        elif op == "dot":
                            vector_result.text = f"A\u00b7B = {format_plain_number(vector_dot(a, b))}"
                        else:
                            vector_result.text = format_vector(vector_cross(a, b))
                    elif op == "magnitude":
                        vector_result.text = f"|A| = {format_plain_number(vector_magnitude(a))}"
                    elif op == "unit":
                        vector_result.text = format_vector(vector_unit(a))
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
                except Exception as exc:
                    result_label.text = f"Error: {exc}"

            convert_button = Button(text="Convert", size_hint_y=None, height=dp(40))
            convert_button.bind(on_press=do_convert)
            units_area.add_widget(convert_button)
            units_area.add_widget(result_label)

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

        popup = self.make_sheet_popup("Graph", layout, height=0.9)
        popup.open()

        return popup, plot

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
