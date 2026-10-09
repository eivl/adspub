# Demo for the README. Render with:  vhs demo/demo.tape
# Requires vhs, ttyd and ffmpeg (https://github.com/charmbracelet/vhs).

Output demo/demo.gif

Set Shell "bash"
Set FontSize 15
Set Width 1000
Set Height 620
Set Padding 20
Set Theme "Catppuccin Mocha"
Set TypingSpeed 40ms
Set Framerate 30

# Put the project CLI on PATH and warm a private cache so output is quick (not shown).
Hide
Type "export PATH=$PWD/.venv/bin:$PATH ADSPUB_CACHE_DIR=$(mktemp -d) PS1='$ ' && adspub latest >/dev/null && clear"
Enter
Sleep 4s
Show

Type "adspub latest"
Sleep 500ms
Enter
Sleep 2s

Type "adspub list"
Sleep 500ms
Enter
Sleep 3s

Type "adspub check v202511 v202602 v202608 v202405"
Sleep 500ms
Enter
Sleep 3s

Type "echo exit code: $?"
Sleep 300ms
Enter
Sleep 2s

Type "clear"
Enter
Type "adspub --json check v202511"
Sleep 500ms
Enter
Sleep 5s
