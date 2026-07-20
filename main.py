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


class MathEngine:
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
        expression = expression.replace("×", "*")
        expression = expression.replace("÷", "/")
        expression = expression.replace("^", "**")
        expression = expression.replace("π", "pi")

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
            text="Version 1.4",
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

    def show_about(self, instance):
        layout = BoxLayout(
        orientation="vertical",
        spacing=dp(10),
        padding=dp(10),
        )

        about_label = Label(
            text=(
                "MATHEMATICAL CALCULATOR\n\n"
                "Version 1.4\n\n"
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

    def show_scientific(self, instance):
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
            size_hint=(0.9, 0.7),
        )

        close_button.bind(on_press=popup.dismiss)

        popup.open()

    def scientific_button_pressed(self, button):
        text = button.text

    def show_memory(self, instance):
        layout = BoxLayout(
            orientation="vertical",
            spacing=dp(10),
            padding=dp(10),
        )

        memory_label = Label(
            text=f"Stored Memory: {self.memory}",
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

    def button_pressed(self, button):
        value = button.text

        replacements = {
            "sin": "sin(",
            "cos": "cos(",
            "tan": "tan(",
            "log": "log(",
            "ln": "ln(",
            "√": "sqrt(",
            "^": "^",
            "!": "!",
            "%": "%",
            "π": "π",
            "e": "e",
            "()": "()",
        }

    self.expression += replacements.get(text, text)
    self.update_display()

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
            "log", "ln", "π", "e", "!"
        ]:
            return (0.18, 0.35, 0.35, 1)

        return (0.15, 0.15, 0.18, 1)

    def button_pressed(self, button):
        value = button.text

        if self.display.text in ("Math Error", "Cannot divide by zero"):
            if value not in ("C", "⌫"):
                self.expression = ""
                self.display.text = "0"

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

        if value == "MC":
            self.memory_clear()
            return

        if value == "MR":
            self.memory_recall()
            return

        if value == "M+":
            self.memory_add()
            return

        if value == "M-":
            self.memory_subtract()
            return

        if value == "HIST":
            self.show_history(instance)
            return

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

            close_button = Button(
                text="Close",
                size_hint_y=None,
                height=dp(45),
            )

            clear_button = Button(
                text="Clear History",
                size_hint_y=None,
                height=dp(45),
            )

            popup = Popup(
                title="Calculation History",
                content=popup_layout,
                size_hint=(0.9, 0.8),
            )

    def show_history(self, instance):
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

        close_button = Button(
            text="Close",
            size_hint_y=None,
            height=dp(45),
        )

        clear_button = Button(
            text="Clear History",
            size_hint_y=None,
            height=dp(45),
        )

        popup = Popup(
            title="Calculation History",
            content=popup_layout,
            size_hint=(0.9, 0.8),
        )

        def clear_history(instance):
            self.history = []
            history_box.text = "No history yet."

        clear_button.bind(on_press=clear_history)
        close_button.bind(on_press=popup.dismiss)

        popup_layout.add_widget(clear_button)
        popup_layout.add_widget(close_button)

        popup.open()

    def show_more_menu(self, value):
        if value == "More":
            layout = BoxLayout(
                orientation="vertical",
                spacing=dp(10),
                padding=dp(10),
            )

            scientific = Button(text="🧮 Scientific")
            memory = Button(text="💾 Memory")
            memory.bind(on_press=self.show_memory)
            history = Button(text="📜 History")
            history.bind(on_press=self.show_history)
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

            close.bind(on_press=popup.dismiss)

            popup.open()
            return

        if value == "ANS":
            if self.history:
                self.expression += str(self.history[-1][1])
                self.update_display()
            return

        if value == "±":
            self.expression = f"-({self.expression})"
            self.update_display()
            return

        replacements = {
            "sin": "sin(",
            "cos": "cos(",
            "tan": "tan(",
            "√": "sqrt(",
            "log": "log(",
            "ln": "ln(",
            "π": "π",
            "e": "e",
            "!": "",
        }

        if value == "!":
            self.expression = f"fact({self.expression})"
        elif value in replacements:
            self.expression += replacements[value]
        else:
            if getattr(self, "just_calculated", False) and (value.isdigit() or value == "."):
                self.expression = value
                self.just_calculated = False
            else:
                self.expression += value

        self.update_display()

    def update_display(self):
        self.display.text = self.expression or "0"

    def update_memory_label(self):
        if hasattr(self, "memory_label"):
            self.memory_label.text=f"Stored Memory: {self.format_number(self.memory)}",

    def update_memory_indicator(self):
        if self.memory != 0:
            self.memory_indicator.text = "M"
        else:
            self.memory_indicator.text = ""

    def memory_clear(self):
        self.memory = 0
        self.update_memory_label()
        self.update_memory_indicator()

    def memory_recall(self):
        self.expression += str(self.memory)
        self.update_display()

    def memory_add(self):
        try:
            self.memory += float(self.display.text)
            self.update_memory_label()
        except:
            pass
        self.update_memory_indicator()

    def memory_subtract(self):
        try:
            self.memory -= float(self.display.text)
            self.update_memory_label()
        except:
            pass
        self.update_memory_indicator()

    def format_number(self, number):
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

            if isinstance(result, float):
                result = round(result, 10)

            self.history.append((original, result))
            self.history = self.history[-50:]

            self.expression = str(result)
            self.display.text = str(result)
            self.just_calculated = True

            history_text = "\n".join(
                f"{expression} = {answer}"
                for expression, answer in self.history
            )

            self.history_label.text = history_text

        except ZeroDivisionError:
            self.display.text = "Cannot divide by zero"

        except Exception:
            self.display.text = "Math Error"


class MathematicalCalculatorApp(App):
    def build(self):
        self.title = "Mathematical Calculator"
        return Calculator()


if __name__ == "__main__":
    MathematicalCalculatorApp().run()
