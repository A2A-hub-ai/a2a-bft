import re

def extract_code(raw):
    if not raw:
        return ''
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", raw, re.DOTALL)
    if blocks:
        return blocks[-1].strip()
    m = re.search(r"^(\s*(?:def |class |import |from |@).*)", raw, re.DOTALL | re.MULTILINE)
    if m:
        return m.group(1).strip()
    return raw.strip()

# case1: markdown 块带 import
raw1 = "Here is my solution:\n```python\nfrom collections import deque\ndef f(x):\n    return x\n```\nHope this helps!"
c1 = extract_code(raw1)
assert c1.startswith('from collections'), c1
assert extract_code(c1) == c1, 'not idempotent'

# case2: 无 markdown，prose + import + def
raw2 = "Sure!\nimport math\ndef g(a):\n    return math.sqrt(a)\nDone."
c2 = extract_code(raw2)
assert c2.startswith('import math'), c2
assert extract_code(c2) == c2

# case3: 纯 def 开头
c3 = extract_code("def h():\n    pass")
assert c3.startswith('def') and extract_code(c3) == c3

print('IDEMPOTENT_OK')
