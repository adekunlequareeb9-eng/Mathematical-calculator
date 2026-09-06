[app]

title = Mathematical Calculator
package.name = mathematicalcalculator
package.domain = com.quareeb

source.dir = .
source.include_exts = py,png,jpg,kv

version = 1.0

requirements = python3,kivy,sympy,mpmath,pyjnius,android

orientation = portrait
fullscreen = 0

android.archs = armeabi-v7a,arm64-v8a
android.minapi = 24

# Needed for camera scanning (Google ML Kit on-device text recognition).
# NOTE: android.gradle_dependencies is documented as only working with the
# sdl2_gradle bootstrap. Modern Buildozer/python-for-android versions
# generally use a Gradle-based build by default already, so this is
# usually fine as-is - but if the build log shows this dependency being
# silently ignored, that bootstrap setting is the first thing to check.
android.gradle_dependencies = com.google.mlkit:text-recognition:16.0.0

# Google's Maven repository - this is what actually hosts the
# com.google.mlkit artifact above. Without this, Gradle won't know where
# to download it from.
android.gradle_repositories = "maven { url 'https://maven.google.com' }"

[buildozer]

log_level = 2
warn_on_root = 1
