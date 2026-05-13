"""Quick test script to verify GUI module can be imported and DGA runtime works."""
import sys
import os

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

print(f"Project root: {PROJECT_ROOT}")

# Test 1: Syntax check
print("\n--- Test 1: Syntax check ---")
import py_compile
try:
    py_compile.compile(os.path.join(os.path.dirname(__file__), 'dga_gui.py'), doraise=True)
    print("dga_gui.py syntax: OK")
except py_compile.PyCompileError as e:
    print(f"dga_gui.py syntax ERROR: {e}")

# Test 2: DGA runtime import
print("\n--- Test 2: DGA runtime import ---")
try:
    from model_training import dga_runtime
    print("dga_runtime imported successfully")
except Exception as e:
    print(f"dga_runtime import FAILED: {e}")

# Test 3: DGA predict
print("\n--- Test 3: DGA predict ---")
try:
    is_dga, score = dga_runtime.predict("example.com", threshold=0.7)
    print(f"example.com -> is_dga={is_dga}, score={score:.4f}")
    is_dga2, score2 = dga_runtime.predict("asdfghjk12345.xyz", threshold=0.7)
    print(f"asdfghjk12345.xyz -> is_dga={is_dga2}, score={score2:.4f}")
except Exception as e:
    print(f"DGA predict FAILED: {e}")

# Test 4: tkinter availability
print("\n--- Test 4: tkinter availability ---")
try:
    import tkinter
    print("tkinter available")
except ImportError:
    print("tkinter NOT available")

# Test 5: DNS client availability
print("\n--- Test 5: DNS client ---")
try:
    import dns.message
    import dns.query
    print("dnspython available")
except ImportError:
    print("dnspython NOT available")

# Test 6: JSON loading
print("\n--- Test 6: JSON domain loading ---")
import json, tempfile
test_data = {"domains": ["example.com", "test.xyz"]}
with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
    json.dump(test_data, f)
    tmp_path = f.name

sys.path.insert(0, os.path.dirname(__file__))
from dga_gui import load_domains_from_json
domains = load_domains_from_json(tmp_path)
os.unlink(tmp_path)
print(f"Loaded domains: {domains}")

print("\n=== All tests completed ===")
