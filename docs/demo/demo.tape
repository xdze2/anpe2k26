# vhs script for the ANPE demo gif.
# Regenerate with:  vhs docs/demo/demo.tape
#
# Uses a fake ./anpe script (docs/demo/anpe) that prints canned output,
# including simulated user replies (via sleep + echo) — so vhs never needs
# to type into a fake prompt.

Output docs/demo/demo.gif

Set FontSize 14
Set Width 960
Set Height 720
Set TypingSpeed 60ms
Set PlaybackSpeed 1.0

# ── Setup ─────────────────────────────────────────────────────────
Hide
Type "export PS1='$ ' && cd docs/demo"
Enter
Sleep 400ms
Show

# ── Frame 1: cold start ───────────────────────────────────────────
Type "cat user_profile.md"
Enter
Sleep 2000ms

Type "./anpe loop --budget mistral=20 --budget ddg=200"
Enter
Sleep 3500ms

# ── Frame 3: funnel ───────────────────────────────────────────────
Type "./anpe jobs status"
Enter
Sleep 2500ms

# ── Frame 4: review ───────────────────────────────────────────────
Type "./anpe prospect review --score=good --score=maybe"
Enter
Sleep 4000ms

# ── Frame 5: profile sharpens ────────────────────────────────────
Type "./anpe profile update"
Enter
Sleep 4000ms

# ── Frame 6: second pass ─────────────────────────────────────────
Type "./anpe loop --budget mistral=20"
Enter
Sleep 3500ms
