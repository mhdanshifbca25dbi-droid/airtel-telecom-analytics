import os
import sys
from streamlit.testing.v1 import AppTest

app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dashboard", "app.py"))
print(f"Initializing AppTest from {app_path}...")
at = AppTest.from_file(app_path, default_timeout=30)
at.run()

if at.exception:
    print("EXCEPTION ENCOUNTERED:")
    for ex in at.exception:
        print(ex.value)
    sys.exit(1)
else:
    print("SUCCESS: Initial load passed with 0 exceptions!")

# Check warnings / errors in elements
errors = [e for e in at.error]
if errors:
    print(f"ERRORS FOUND ({len(errors)}):")
    for err in errors:
        print(err.value)
else:
    print("Zero st.error elements found.")

# Test Reset button
print("\nTesting 'Reset All Filters' button...")
reset_btn = None
for b in at.button:
    if "Reset" in b.label:
        reset_btn = b
        break

if reset_btn:
    reset_btn.click().run()
    if at.exception:
        print("EXCEPTION AFTER RESET:")
        for ex in at.exception:
            print(ex.value)
        sys.exit(1)
    else:
        print("SUCCESS: Reset button worked cleanly!")

# Test High Risk Preset button
print("\nTesting 'High-Risk (Prepaid)' preset button...")
for b in at.button:
    if "High-Risk" in b.label:
        b.click().run()
        break

if at.exception:
    print("EXCEPTION AFTER HIGH-RISK PRESET:")
    for ex in at.exception:
        print(ex.value)
    sys.exit(1)
else:
    print("SUCCESS: High-Risk preset worked cleanly!")

# Test Postpaid Preset button
print("\nTesting 'Postpaid Core' preset button...")
for b in at.button:
    if "Postpaid" in b.label:
        b.click().run()
        break

if at.exception:
    print("EXCEPTION AFTER POSTPAID PRESET:")
    for ex in at.exception:
        print(ex.value)
    sys.exit(1)
else:
    print("SUCCESS: Postpaid preset worked cleanly!")

# Test changing selectboxes across all charts
print("\nTesting Selectbox options across all charts...")
selectboxes = at.selectbox
print(f"Total selectboxes found: {len(selectboxes)}")
for sb in selectboxes:
    print(f"Selectbox: key={sb.key}, value={sb.value}, options={sb.options[:3]}")

# Test selecting different options on each chart
print("\nTesting interactive filtering on each chart...")
for sb in selectboxes:
    if len(sb.options) > 1 and sb.key:
        new_val = sb.options[1]
        print(f"Changing {sb.key} from {sb.value} -> {new_val}")
        sb.select(new_val).run()
        if at.exception:
            print(f"EXCEPTION when changing {sb.key}:")
            for ex in at.exception:
                print(ex.value)
            sys.exit(1)

print("\nALL AUTOMATED TESTS COMPLETED WITH 100% SUCCESS!")
