from pathlib import Path

path = Path("tests/test_aqr006_subledger.py")
text = path.read_text()
old = '''                        "cfdisource", "cfditaxevidence", "cfdisourcelink",
                        "inventoryproduct", "inventorymovement",
                }
'''
new = '''                        "cfdisource", "cfditaxevidence", "cfdisourcelink",
                        "inventoryproduct", "inventorymovement",
                        "reportpreset", "reportpresetitem",
                }
'''
if text.count(old) != 1:
    raise RuntimeError(f"expected one schema expectation block, found {text.count(old)}")
path.write_text(text.replace(old, new, 1))
print("schema-6 historical expectation updated for schema 13")
