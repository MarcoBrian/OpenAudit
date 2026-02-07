# ⚠️ CRITICAL: LangChain Prompt Template Syntax

## The Problem

LangChain's `ChatPromptTemplate` uses **curly braces `{}` as template variables**. This means:

- `{variable}` = Template variable (will be replaced)
- `{}` = **ERROR!** Treated as a variable with empty name → KeyError
- `{{}}` = Literal curly braces (escaped)

## Common Mistakes

❌ **WRONG:**
```python
prompt = "Action Input: {}"  # This will cause KeyError!
```

✅ **CORRECT:**
```python
prompt = "Action Input: {{}}"  # This is literal {}
```

## Rules

1. **Template variables**: Use single braces `{variable_name}`
   - Example: `{input}`, `{tools}`, `{agent_scratchpad}`

2. **Literal braces**: Use double braces `{{}}` or `{{variable}}`
   - Example: `{{}}` for empty JSON object
   - Example: `{{"key": "value"}}` for JSON (but better to use variables)

3. **NEVER use single `{}` for literal braces** - it will cause:
   ```
   KeyError: "Input to ChatPromptTemplate is missing variables {''}"
   ```

## How to Check

Before committing code with ChatPromptTemplate:

1. Search for `ChatPromptTemplate` in your code
2. Check all string literals passed to it
3. Verify any `{}` are escaped as `{{}}`
4. Verify template variables use single `{variable}`

## Example

```python
# ✅ CORRECT
examples = (
    "Action Input: {{}}\n"  # Literal {}
    "User said: {input}\n"  # Template variable
)

# ❌ WRONG
examples = (
    "Action Input: {}\n"  # Will cause KeyError!
    "User said: {input}\n"
)
```

## Prevention

- Always use `{{}}` when you want literal curly braces
- Test prompt templates immediately after writing them
- If you see KeyError about missing variables with empty name `{''}`, check for unescaped `{}`
