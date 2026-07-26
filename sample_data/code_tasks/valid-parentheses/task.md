## Valid Parentheses

Given a string `s` containing only the characters `(`, `)`, `{`, `}`,
`[`, and `]`, determine if the input string is valid.

A string is valid if:
1. Open brackets are closed by the same type of bracket.
2. Open brackets are closed in the correct order.
3. Every closing bracket has a corresponding opening bracket of the same type.

**Function signature:**
```python
def is_valid(s: str) -> bool:
```

Return `True` if the string is valid, `False` otherwise.

**Examples:**
```
Input: s = "()"        → True
Input: s = "()[]{}"    → True
Input: s = "(]"        → False
Input: s = "([)]"      → False
Input: s = "{[]}"      → True
```
