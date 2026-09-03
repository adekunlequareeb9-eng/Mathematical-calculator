import ast
import math
import operator

from kivy.app import App
from kivy.core.clipboard import Clipboard
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput


Window.clearcolor = (0.04, 0.04, 0.06, 1)


VERSION = "1.8"


class MathEngine:
    """Safe calculator engine using Python's AST instead of eval()."""

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

    functions = {
        "sqrt": math.sqrt,
        "log": math.log10,
        "ln": math.log,
        "sin": lambda x: math.sin(math.radians(x)),
        "cos": lambda x: math.cos(math.radians(x)),
        "tan": lambda x: math.tan(math.radians(x)),
        "fact": math.factorial,
        "abs": abs,
    }

    constants = {
        "pi": math.pi,
        "e": math.e,
    }

    def evaluate(self, expression):
        expression = self.normalise(expression)
        if not expression:
            raise ValueError("Empty expression")

        tree = ast.parse(expression, mode="eval")
        return self._solve(tree.body)

    @staticmethod
    def normalise(expression):
        return (
            expression.replace("×", "*")
            .replace("÷", "/")
            .replace("^", "**")
            .replace("π", "pi")
            .replace("√", "sqrt")
        )

    def _solve(self, node):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                return node.value
            raise ValueError("Invalid value")

        if isinstance(node, ast.BinOp):
            operation = self.operators.get(type(node.op))
            if operation is None:
                raise ValueError("Unsupported operation")

            left = self._solve(node.left)
            right = self._solve(node.right)

            if isinstance(node.op, ast.Pow):
                if abs(right) > 1000:
                    raise ValueError("Power too large")
                if left == 0 and right < 0:
                    raise ZeroDivisionError

            return operation(left, right)

        if isinstance(node, ast.UnaryOp):
            operation = self.operators.get(type(node.op))
            if operation is None:
                raise ValueError("Unsupported operation")
            return operation(self._solve(node.operand))

        if isinstance(node, ast.Name):
            if node.id in self.constants:
                return self.constants[node.id]
            raise ValueError("Unknown constant")

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Invalid function")

            function = self.functions.get(node.func.id)
            if function is None:
                raise ValueError("Unknown function")
            if len(node.args) != 1:
                raise ValueError("Function needs one argument")

            argument = self._solve(node.args[0])

            if node.func.id == "fact":
                if not isinstance(argument, int) or argument < 0:
                    raise ValueError("Factorial needs a non-negative integer")

            return function(argument)

        raise ValueError("Invalid expression")


class PolynomialError(ValueError):
    pass


class AlgebraEngine:
    """Small dependency-free solver for linear/quadratic equations in x."""

    @staticmethod
    def _poly(node):
        # Coefficients are [constant, x, x^2].
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                return [float(node.value), 0.0, 0.0]
            raise PolynomialError("Invalid number")

        if isinstance(node, ast.Name):
            if node.id == "x":
                return [0.0, 1.0, 0.0]
            raise PolynomialError("Only x is allowed")

        if isinstance(node, ast.UnaryOp):
            values = AlgebraEngine._poly(node.operand)
            if isinstance(node.op, ast.USub):
                return [-v for v in values]
            if isinstance(node.op, ast.UAdd):
                return values
            raise PolynomialError("Unsupported sign")

        if isinstance(node, ast.BinOp):
            left = AlgebraEngine._poly(node.left)
            right = AlgebraEngine._poly(node.right)

            if isinstance(node.op, (ast.Add, ast.Sub)):
                sign = 1 if isinstance(node.op, ast.Add) else -1
                return [left[i] + sign * right[i] for i in range(3)]

            if isinstance(node.op, ast.Mult):
                result = [0.0, 0.0, 0.0]
                for i in range(3):
                    for j in range(3):
                        if abs(left[i]) < 1e-12 or abs(right[j]) < 1e-12:
                            continue
                        if i + j > 2:
                            raise PolynomialError("Degree greater than 2")
                        result[i + j] += left[i] * right[j]
                return result

            if isinstance(node.op, ast.Div):
                if abs(right[1]) > 1e-12 or abs(right[2]) > 1e-12:
                    raise PolynomialError("Division by x is not supported")
                if abs(right[0]) < 1e-12:
                    raise ZeroDivisionError
                return [v / right[0] for v in left]

            if isinstance(node.op, ast.Pow):
                if any(abs(v) > 1e-12 for v in right[1:]):
                    raise PolynomialError("Exponent must be a number")
                exponent = right[0]
                if exponent < 0 or not exponent.is_integer() or exponent > 2:
                    raise PolynomialError("Only powers 0, 1 and 2 are supported")
                result = [1.0, 0.0, 0.0]
                for _ in range(int(exponent)):
                    result = AlgebraEngine._multiply(result, left)
                return result

            raise PolynomialError("Unsupported operator")

        raise PolynomialError("Invalid algebra expression")

    @staticmethod
    def _multiply(a, b):
        result = [0.0, 0.0, 0.0]
        for i in range(3):
            for j in range(3):
                if abs(a[i]) < 1e-12 or abs(b[j]) < 1e-12:
                    continue
                if i + j > 2:
                    raise PolynomialError("Degree greater than 2")
                result[i + j] += a[i] * b[j]
        return result

    def coefficients(self, equation):
        if "=" not in equation:
            raise PolynomialError("Use = between the two sides")

        left_text, right_text = equation.split("=", 1)
        if not left_text.strip() or not right_text.strip():
            raise PolynomialError("Both sides of the equation are required")

        left = self._poly(ast.parse(MathEngine.normalise(left_text), mode="eval").body)
        right = self._poly(ast.parse(MathEngine.normalise(right_text), mode="eval").body)
        return [left[i] - right[i] for i in range(3)]

    @staticmethod
    def clean(value):
        if abs(value) < 1e-10:
            return 0.0
        return value

    def solve_linear(self, equation):
        c, b, a = self.coefficients(equation)
        a, b, c = self.clean(a), self.clean(b), self.clean(c)

        if a != 0:
            raise PolynomialError("This is not a linear equation")
        if b == 0:
            if c == 0:
                return "Infinitely many solutions."
            return "No solution."

        x = -c / b
        return f"x = {self.format_number(x)}"

    def solve_quadratic(self, equation):
        c, b, a = self.coefficients(equation)
        a, b, c = self.clean(a), self.clean(b), self.clean(c)

        if a == 0:
            if b == 0:
                return "No quadratic solution."
            return f"Linear equation: x = {self.format_number(-c / b)}"

        discriminant = b * b - 4 * a * c

        if discriminant > 0:
            root = math.sqrt(discriminant)
            x1 = (-b + root) / (2 * a)
            x2 = (-b - root) / (2 * a)
            return (
                f"x₁ = {self.format_number(x1)}\n"
                f"x₂ = {self.format_number(x2)}"
            )

        if abs(discriminant) < 1e-10:
            x = -b / (2 * a)
            return f"x = {self.format_number(x)}"

        real = -b / (2 * a)
        imaginary = math.sqrt(-discriminant) / abs(2 * a)
        return (
            f"x₁ = {self.format_number(real)} + "
            f"{self.format_number(imaginary)}i\n"
            f"x₂ = {self.format_number(real)} - "
            f"{self.format_number(imaginary)}i"
        )

    @staticmethod
    def format_number(number):
        if abs(number - round(number)) < 1e-10:
            return str(int(round(number)))
        return str(round(number, 10)).rstrip("0").rstrip(".")


class SimultaneousEngine:
    """Dependency-free solver for two linear equations in x and y."""

    @staticmethod
    def _linear(node):
        # (x coefficient, y coefficient, constant)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                return 0.0, 0.0, float(node.value)
            raise PolynomialError("Invalid number")

        if isinstance(node, ast.Name):
            if node.id == "x":
                return 1.0, 0.0, 0.0
            if node.id == "y":
                return 0.0, 1.0, 0.0
            raise PolynomialError("Only x and y are allowed")

        if isinstance(node, ast.UnaryOp):
            x, y, c = SimultaneousEngine._linear(node.operand)
            if isinstance(node.op, ast.USub):
                return -x, -y, -c
            if isinstance(node.op, ast.UAdd):
                return x, y, c
            raise PolynomialError("Unsupported sign")

        if isinstance(node, ast.BinOp):
            lx, ly, lc = SimultaneousEngine._linear(node.left)
            rx, ry, rc = SimultaneousEngine._linear(node.right)

            if isinstance(node.op, ast.Add):
                return lx + rx, ly + ry, lc + rc
            if isinstance(node.op, ast.Sub):
                return lx - rx, ly - ry, lc - rc

            if isinstance(node.op, ast.Mult):
                left_vars = abs(lx) > 1e-12 or abs(ly) > 1e-12
                right_vars = abs(rx) > 1e-12 or abs(ry) > 1e-12
                if left_vars and right_vars:
                    raise PolynomialError("Products of x and y are not supported")
                if left_vars:
                    return lx * rc, ly * rc, lc * rc
                return rx * lc, ry * lc, rc * lc

            if isinstance(node.op, ast.Div):
                if abs(rx) > 1e-12 or abs(ry) > 1e-12:
                    raise PolynomialError("Division by x or y is not supported")
                if abs(rc) < 1e-12:
                    raise ZeroDivisionError
                return lx / rc, ly / rc, lc / rc

            raise PolynomialError("Only linear operations are supported")

        raise PolynomialError("Invalid simultaneous equation")

    def coefficients(self, equation):
        if "=" not in equation:
            raise PolynomialError("Use = between the two sides")

        left_text, right_text = equation.split("=", 1)
        left = self._linear(ast.parse(MathEngine.normalise(left_text), mode="eval").body)
        right = self._linear(ast.parse(MathEngine.normalise(right_text), mode="eval").body)

        # ax + by + c = 0
        return left[0] - right[0], left[1] - right[1], left[2] - right[2]

    @staticmethod
    def format_number(number):
        if abs(number - round(number)) < 1e-10:
            return str(int(round(number)))
        return str(round(number, 10)).rstrip("0").rstrip(".")

    def solve(self, equation1, equation2):
        a1, b1, c1 = self.coefficients(equation1)
        a2, b2, c2 = self.coefficients(equation2)

        determinant = a1 * b2 - a2 * b1

        if abs(determinant) < 1e-12:
            if abs(a1 * c2 - a2 * c1) < 1e-12 and abs(b1 * c2 - b2 * c1) < 1e-12:
                return "Infinitely many solutions."
            return "No unique solution."

        x = (b1 * c2 - b2 * c1) / determinant
        y = (c1 * a2 - c2 * a1) / determinant

        return f"x = {self.format_number(x)}\ny = {self.format_number(y)}"


class Calculator(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.orientation = "vertical"
        self.padding = dp(8)
        self.spacing = dp(6)

        self.expression = ""
        self.memory = 0
        self.engine = MathEngine()
        self.algebra = AlgebraEngine()
        self.simultaneous = SimultaneousEngine()
        self.history = []
        self.just_calculated = False

        title = Label(
            text="MATHEMATICAL CALCULATOR",
            size_hint_y=0.07,
            font_size="22sp",
            bold=True,
        )
        self.add_widget(title)

        version_bar = BoxLayout(
            orientation="horizontal",
            size_hint_y=0.04,
            spacing=dp(5),
        )

        version = Label(
            text=f"Version {VERSION}",
            font_size="12sp",
            halign="left",
            valign="middle",
        )
        version.bind(size=self.update_text_size)

        info_button = Button(
            text="i",
            size_hint=(None, 1),
            width=dp(35),
        )
        info_button.bind(on_press=self.show_about)

        version_bar.add_widget(version)
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

    def update_text_size(self, widget, size):
        widget.text_size = size

    def button_color(self, text):
        if text == "=":
            return (0.1, 0.55, 0.9, 1)
        if text in ["C", "⌫"]:
            return (0.7, 0.15, 0.18, 1)
        if text in ["+", "-", "×", "÷", "^", "%"]:
            return (0.25, 0.25, 0.55, 1)
        if text in [
            "sin", "cos", "tan", "√",
            "log", "ln", "π", "e", "!",
        ]:
            return (0.18, 0.35, 0.35, 1)
        return (0.15, 0.15, 0.18, 1)

    def reset_error(self, value):
        if self.display.text in ("Math Error", "Cannot divide by zero"):
            if value not in ("C", "⌫"):
                self.expression = ""
                self.display.text = "0"

    def button_pressed(self, button):
        value = button.text
        self.reset_error(value)

        if value == "C":
            self.expression = ""
            self.display.text = "0"
            self.just_calculated = False
            return

        if value == "⌫":
            self.expression = self.expression[:-1]
            self.just_calculated = False
            self.update_display()
            return

        if value == "=":
            self.calculate()
            return

        if value == "HIST":
            self.show_history(button)
            return

        if value == "More":
            self.show_more_menu(button)
            return

        if value == "±":
            if self.expression:
                self.expression = f"-({self.expression})"
            self.just_calculated = False
            self.update_display()
            return

        if self.just_calculated and (value.isdigit() or value == "."):
            self.expression = value
            self.just_calculated = False
        else:
            self.append_input(value)

        self.update_display()

    def append_input(self, value):
        replacements = {
            "×": "*",
            "÷": "/",
        }
        self.expression += replacements.get(value, value)

    def insert_scientific(self, value):
        if value == "!":
            if self.expression:
                self.expression = f"fact({self.expression})"
            return

        replacements = {
            "sin": "sin(",
            "cos": "cos(",
            "tan": "tan(",
            "√": "sqrt(",
            "log": "log(",
            "ln": "ln(",
            "^": "^",
            "%": "%",
            "π": "π",
            "e": "e",
            "()": "()",
        }

        insertion = replacements.get(value, value)

        if self.just_calculated and value not in ("^", "%"):
            self.just_calculated = False

        if value == "()":
            self.expression += "()"
        else:
            self.expression += insertion

        self.update_display()

    def show_about(self, instance):
        layout = BoxLayout(
            orientation="vertical",
            spacing=dp(10),
            padding=dp(10),
        )

        about_label = Label(
            text=(
                "MATHEMATICAL CALCULATOR\n\n"
                f"Version {VERSION}\n\n"
                "Created by Quareeb\n\n"
                "Basic, scientific and algebra tools."
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

        popup = Popup(
            title="About",
            content=layout,
            size_hint=(0.8, 0.5),
        )

        close_button.bind(on_press=popup.dismiss)
        popup.open()

    def show_scientific(self, instance=None):
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
            "log", "ln", "√",
            "^", "!", "%",
            "π", "e", "()",
        ]

        for text in buttons:
            button = Button(
                text=text,
                font_size="18sp",
                background_normal="",
                background_color=self.button_color(text),
            )
            button.bind(on_press=lambda btn: self.insert_scientific(btn.text))
            grid.add_widget(button)

        layout.add_widget(grid)

        close_button = Button(
            text="Close",
            size_hint_y=None,
            height=dp(45),
        )
        layout.add_widget(close_button)

        popup = Popup(
            title="Scientific",
            content=layout,
            size_hint=(0.9, 0.7),
        )

        close_button.bind(on_press=popup.dismiss)
        popup.open()

    def show_memory(self, instance=None):
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

        for widget in (mc, mr, mp, mm):
            layout.add_widget(widget)
        layout.add_widget(close)

        popup = Popup(
            title="Memory",
            content=layout,
            size_hint=(0.7, 0.6),
        )

        mc.bind(on_press=lambda x: self.memory_clear())
        mr.bind(on_press=lambda x: self.memory_recall())
        mp.bind(on_press=lambda x: self.memory_add())
        mm.bind(on_press=lambda x: self.memory_subtract())
        close.bind(on_press=popup.dismiss)

        popup.open()

    def show_more_menu(self, instance=None):
        layout = BoxLayout(
            orientation="vertical",
            spacing=dp(10),
            padding=dp(10),
        )

        scientific = Button(text="🧮 Scientific")
        memory = Button(text="💾 Memory")
        algebra = Button(text="Algebra")
        history = Button(text="📜 History")
        close = Button(
            text="Close",
            size_hint_y=None,
            height=dp(45),
        )

        layout.add_widget(scientific)
        layout.add_widget(memory)
        layout.add_widget(algebra)
        layout.add_widget(history)
        layout.add_widget(close)

        popup = Popup(
            title="More",
            content=layout,
            size_hint=(0.8, 0.65),
        )

        scientific.bind(on_press=lambda x: self.open_child_popup(self.show_scientific, popup))
        memory.bind(on_press=lambda x: self.open_child_popup(self.show_memory, popup))
        algebra.bind(on_press=lambda x: self.open_child_popup(self.show_algebra, popup))
        history.bind(on_press=lambda x: self.open_child_popup(self.show_history, popup))
        close.bind(on_press=popup.dismiss)

        popup.open()

    def open_child_popup(self, method, parent_popup):
        parent_popup.dismiss()
        method()

    def show_history(self, instance=None):
        history_text = "\n".join(
            f"{expression} = {answer}"
            for expression, answer in self.history
        )

        if not history_text:
            history_text = "No history yet."

        history_box = TextInput(
            text=history_text,
            readonly=True,
            multiline=True,
        )

        scroll = ScrollView()
        scroll.add_widget(history_box)

        popup_layout = BoxLayout(
            orientation="vertical",
            spacing=dp(5),
        )
        popup_layout.add_widget(scroll)

        copy_button = Button(
            text="Copy History",
            size_hint_y=None,
            height=dp(45),
        )
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

        popup_layout.add_widget(copy_button)
        popup_layout.add_widget(clear_button)
        popup_layout.add_widget(close_button)

        popup = Popup(
            title="Calculation History",
            content=popup_layout,
            size_hint=(0.9, 0.8),
        )

        def clear_history(_):
            self.history = []
            self.history_label.text = "Welcome.\n\nLet's calculate something."
            history_box.text = "No history yet."

        def copy_history(_):
            if self.history:
                Clipboard.copy(history_box.text)

        copy_button.bind(on_press=copy_history)
        clear_button.bind(on_press=clear_history)
        close_button.bind(on_press=popup.dismiss)

        popup.open()

    def show_algebra(self, instance=None):
        layout = BoxLayout(
            orientation="vertical",
            spacing=dp(10),
            padding=dp(10),
        )

        scroll = ScrollView()
        form = BoxLayout(
            orientation="vertical",
            spacing=dp(10),
            size_hint_y=None,
            padding=dp(5),
        )
        form.bind(minimum_height=form.setter("height"))

        title = Label(
            text="Algebra",
            font_size="20sp",
            size_hint_y=None,
            height=dp(45),
            halign="left",
            valign="middle",
        )
        title.bind(size=self.update_text_size)
        form.add_widget(title)

        hint = Label(
            text="Equation in x, e.g. 2*x+3=7 or x^2-5*x+6=0",
            size_hint_y=None,
            height=dp(55),
            halign="center",
            valign="middle",
        )
        hint.bind(size=self.update_text_size)
        form.add_widget(hint)

        equation_label = Label(
            text="Equation",
            size_hint_y=None,
            height=dp(30),
            halign="left",
        )
        form.add_widget(equation_label)

        equation = TextInput(
            text="",
            multiline=False,
            size_hint_y=None,
            height=dp(50),
        )
        form.add_widget(equation)

        result = Label(
            text="",
            size_hint_y=None,
            height=dp(70),
            halign="left",
            valign="middle",
        )
        result.bind(size=self.update_text_size)
        form.add_widget(result)

        linear_button = Button(
            text="Solve Linear",
            size_hint_y=None,
            height=dp(50),
        )
        quadratic_button = Button(
            text="Solve Quadratic",
            size_hint_y=None,
            height=dp(50),
        )
        form.add_widget(linear_button)
        form.add_widget(quadratic_button)

        sub_title = Label(
            text="Simultaneous equations in x and y",
            font_size="18sp",
            bold=True,
            size_hint_y=None,
            height=dp(45),
            halign="center",
            valign="middle",
        )
        sub_title.bind(size=self.update_text_size)
        form.add_widget(sub_title)

        eq1_label = Label(
            text="Equation 1, e.g. 2*x+y=5",
            size_hint_y=None,
            height=dp(35),
            halign="left",
        )
        form.add_widget(eq1_label)

        eq1 = TextInput(
            text="",
            multiline=False,
            size_hint_y=None,
            height=dp(50),
        )
        form.add_widget(eq1)

        eq2_label = Label(
            text="Equation 2, e.g. x-y=1",
            size_hint_y=None,
            height=dp(35),
            halign="left",
        )
        form.add_widget(eq2_label)

        eq2 = TextInput(
            text="",
            multiline=False,
            size_hint_y=None,
            height=dp(50),
        )
        form.add_widget(eq2)

        simultaneous_result = Label(
            text="",
            size_hint_y=None,
            height=dp(70),
            halign="left",
            valign="middle",
        )
        simultaneous_result.bind(size=self.update_text_size)
        form.add_widget(simultaneous_result)

        simultaneous_button = Button(
            text="Solve Simultaneous",
            size_hint_y=None,
            height=dp(50),
        )
        form.add_widget(simultaneous_button)

        scroll.add_widget(form)
        layout.add_widget(scroll)

        close = Button(
            text="Close",
            size_hint_y=None,
            height=dp(45),
        )
        layout.add_widget(close)

        popup = Popup(
            title="Algebra",
            content=layout,
            size_hint=(0.98, 0.96),
        )

        def solve_linear(_):
            try:
                result.text = self.algebra.solve_linear(equation.text)
            except ZeroDivisionError:
                result.text = "Cannot divide by zero"
            except Exception as exc:
                result.text = f"Error: {exc}"

        def solve_quadratic(_):
            try:
                result.text = self.algebra.solve_quadratic(equation.text)
            except ZeroDivisionError:
                result.text = "Cannot divide by zero"
            except Exception as exc:
                result.text = f"Error: {exc}"

        def solve_simultaneous(_):
            try:
                simultaneous_result.text = self.simultaneous.solve(
                    eq1.text,
                    eq2.text,
                )
            except ZeroDivisionError:
                simultaneous_result.text = "Cannot divide by zero"
            except Exception as exc:
                simultaneous_result.text = f"Error: {exc}"

        linear_button.bind(on_press=solve_linear)
        quadratic_button.bind(on_press=solve_quadratic)
        simultaneous_button.bind(on_press=solve_simultaneous)
        close.bind(on_press=popup.dismiss)

        popup.open()

    def update_display(self):
        self.display.text = self.expression or "0"

    def update_memory_label(self):
        if hasattr(self, "memory_label"):
            self.memory_label.text = (
                f"Stored Memory: {self.format_number(self.memory)}"
            )

    def update_memory_indicator(self):
        self.memory_indicator.text = "M" if self.memory != 0 else ""

    def memory_clear(self):
        self.memory = 0
        self.update_memory_label()
        self.update_memory_indicator()

    def memory_recall(self):
        self.expression += self.format_number(self.memory)
        self.just_calculated = False
        self.update_display()

    def memory_add(self):
        try:
            value = self.engine.evaluate(self.expression or "0")
            self.memory += value
            self.update_memory_label()
        except Exception:
            pass
        self.update_memory_indicator()

    def memory_subtract(self):
        try:
            value = self.engine.evaluate(self.expression or "0")
            self.memory -= value
            self.update_memory_label()
        except Exception:
            pass
        self.update_memory_indicator()

    @staticmethod
    def format_number(number):
        if isinstance(number, float) and number.is_integer():
            return str(int(number))
        return str(number)

    def calculate(self):
        if not self.expression:
            return

        try:
            original = self.expression
            result = self.engine.evaluate(self.expression)

            if isinstance(result, float) and result.is_integer():
                result = int(result)
            elif isinstance(result, float):
                result = round(result, 10)

            answer = self.format_number(result)

            self.history.append((original, answer))
            self.history = self.history[-50:]

            self.expression = answer
            self.display.text = answer
            self.just_calculated = True

            self.history_label.text = "\n".join(
                f"{expression} = {answer}"
                for expression, answer in self.history[-5:]
            )

        except ZeroDivisionError:
            self.display.text = "Cannot divide by zero"
            self.just_calculated = False

        except (ValueError, TypeError, SyntaxError, OverflowError):
            self.display.text = "Math Error"
            self.just_calculated = False


class MathematicalCalculatorApp(App):
    def build(self):
        self.title = "Mathematical Calculator"
        return Calculator()


if __name__ == "__main__":
    MathematicalCalculatorApp().run()
