[app]

title = Mathematical Calculator
package.name = mathematicalcalculator
package.domain = com.quareeb

source.dir = .
source.include_exts = py,png,jpg,kv

version = 1.0

requirements = python3,kivy,charset-normalizer==3.4.3

orientation = portrait
fullscreen = 0

android.archs = armeabi-v7a,arm64-v8a
android.minapi = 24
android.python = 3.12
p4a.branch = master

[buildozer]

log_level = 2
warn_on_root = 1
