import ast
import math
import operator
import re

from kivy.app import App
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView


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

    def _factorial(self, x):
        if x < 0 or int(x) != x:
            raise ValueError("Factorial requires a non-negative whole number")
        if x > 170:
            raise ValueError("Number too large for factorial")
        return math.factorial(int(x))

    def evaluate(self, expression):
        expression = expression.strip()
        expression = expression.replace("×", "*")
        expression = expression.replace("÷", "/")
        expression = expression.replace("^", "**")
        expression = expression.replace("π", "pi")

        if not expression:
            raise ValueError("Empty expression")

        tree = ast.parse(expression, mode="eval")
        return self._solve(tree.body)

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


OPERATOR_CHARS = {"+", "-", "×", "÷", "^", "%"}

SCIENTIFIC_COLOR_LABELS = {
    "sin", "cos", "tan", "asin", "acos", "atan",
    "√", "log", "ln", "π", "e", "n!",
    "x²", "x³", "xʸ", "1/x",
}


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
            text=f"Version {APP_VERSION}",
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

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------

    def update_text_size(self, widget, size):
        widget.text_size = size

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
            self.just_calculated = True

            self.history_label.text = "\n".join(
                f"{expr} = {self.format_number(ans)}"
                for expr, ans in self.history[-3:]
            )

        except ZeroDivisionError:
            self.display.text = "Cannot divide by zero"
            self.expression = ""
            self.just_calculated = False

        except (ValueError, SyntaxError, TypeError, OverflowError):
            self.display.text = "Math Error"
            self.expression = ""
            self.just_calculated = False

        except Exception:
            self.display.text = "Math Error"
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
        layout = BoxLayout(
            orientation="vertical",
            spacing=dp(10),
            padding=dp(10),
        )

        scientific = Button(text="\U0001F9EE Scientific")
        memory = Button(text="\U0001F4BE Memory")
        history = Button(text="\U0001F4DC History")
        close = Button(
            text="Close",
            size_hint_y=None,
            height=dp(45),
        )

        layout.add_widget(scientific)
        layout.add_widget(memory)
        layout.add_widget(history)
        layout.add_widget(close)

        popup = Popup(
            title="More",
            content=layout,
            size_hint=(0.8, 0.6),
        )

        def open_scientific(instance):
            popup.dismiss()
            self.show_scientific()

        def open_memory(instance):
            popup.dismiss()
            self.show_memory()

        def open_history(instance):
            popup.dismiss()
            self.show_history()

        scientific.bind(on_press=open_scientific)
        memory.bind(on_press=open_memory)
        history.bind(on_press=open_history)
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

        popup = Popup(
            title="Scientific",
            content=layout,
            size_hint=(0.9, 0.8),
        )

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

    def update_memory_label(self):
        if self.memory_label is not None:
            self.memory_label.text = f"Stored Memory: {self.format_number(self.memory)}"

    def update_memory_indicator(self):
        self.memory_indicator.text = "M" if self.memory != 0 else ""

    def memory_clear(self):
        self.memory = 0
        self.update_memory_label()
        self.update_memory_indicator()

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

    def memory_subtract(self):
        try:
            self.memory -= float(self.display.text)
        except (ValueError, TypeError):
            pass
        self.update_memory_label()
        self.update_memory_indicator()

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

        popup = Popup(
            title="Calculation History",
            content=popup_layout,
            size_hint=(0.9, 0.8),
        )

        def clear_history(instance):
            self.history = []
            self.history_label.text = "Welcome.\n\nLet's calculate something."
            rebuild_history_grid()

        clear_button.bind(on_press=clear_history)
        close_button.bind(on_press=popup.dismiss)

        popup.open()

    # ------------------------------------------------------------------
    # About popup
    # ------------------------------------------------------------------

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

        popup = Popup(
            title="About",
            content=layout,
            size_hint=(0.8, 0.5),
        )

        close_button.bind(on_press=popup.dismiss)
        popup.open()


class MathematicalCalculatorApp(App):
    def build(self):
        self.title = "Mathematical Calculator"
        return Calculator()


if __name__ == "__main__":
    MathematicalCalculatorApp().run()
