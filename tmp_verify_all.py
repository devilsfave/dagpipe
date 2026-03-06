"""Batch verify all test zips and delete the pre-fix faulty one."""
import zipfile
import ast
from pathlib import Path

# Delete the faulty pre-fix zip
faulty = Path("outputs/test1.zip")
if faulty.exists():
    faulty.unlink()
    print("Deleted: test1.zip (generated before the fix — broken)\n")

zips = sorted(Path("outputs").glob("test*.zip"), key=lambda p: p.name)
print(f"Verifying {len(zips)} zip(s)...\n")

all_pass = True
for z_path in zips:
    with zipfile.ZipFile(z_path) as z:
        content = z.read("runner.py").decode()
    no_fences = not content.strip().startswith("```")
    try:
        ast.parse(content)
        valid_py = True
    except SyntaxError:
        valid_py = False
    ok = no_fences and valid_py
    if not ok:
        all_pass = False
    icon = "PASS" if ok else "FAIL"
    detail = "" if ok else f" [fences={not no_fences}, syntax_ok={valid_py}]"
    print(f"  {icon}  {z_path.name}{detail}")

print()
if all_pass:
    print(f"ALL {len(zips)}/10 PASS ✓  — READY FOR STEP 3 (Apify actor)")
else:
    print("FAILURES DETECTED — do not proceed to Step 3")
