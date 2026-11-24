"""LLM-Based Multi-Agent System for Software Engineering (SDLC pipeline).
Implements the roles from Tang & Runkler (2026): requirements -> code generation ->
static code checking -> testing -> debugging (iterative refinement) -> documentation."""
import json, os, re, subprocess, sys, tempfile
from dotenv import load_dotenv
from flask import Flask, Response, request, send_from_directory, stream_with_context
from openai import OpenAI

load_dotenv()                                   # reads .env  -> OPENAI_API_KEY lives there
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
MAX_ROUNDS = int(os.getenv("MAX_ROUNDS", "3"))
app = Flask(__name__, static_folder="static")

PROMPTS = {
 "requirements": "You are a Requirements Engineering agent. From the project description produce concise markdown: "
   "1) **User stories** (3-5), 2) **Acceptance criteria**, 3) **Function signatures** to implement in Python, 4) **Edge cases**.",
 "programmer": "You are a senior Python Programmer agent. Implement the requirements as a single module with docstrings and type hints. "
   "Only standard library. Reply with ONE ```python code block and nothing else.",
 "reviewer": "You are a Static Code Review agent (like a critic auditor). Without running the code, inspect it for bugs, vulnerabilities, "
   "code smells and mismatches with the requirements. Give a markdown list with severity (High/Medium/Low) per finding, "
   "then a last line exactly 'VERDICT: PASS' or 'VERDICT: FAIL'.",
 "tester": "You are a Test Engineer agent. Write a Python `unittest` test file for the module saved as solution.py. "
   "Start with `import unittest` and `from solution import *`. Cover normal, edge and error cases. "
   "End with `if __name__ == '__main__': unittest.main()`. Reply with ONE ```python block only.",
 "debugger": "You are a Debugging agent doing program repair. You get the code, tests, review notes and the failing test output. "
   "Find the root cause, fix the SOLUTION (not the tests unless a test clearly contradicts the requirements). "
   "Reply with one short line of root cause, then ONE ```python block containing the full corrected solution.py.",
 "demo": "You are a Run-Guide agent. Write a short runnable `demo.py` that does `from solution import *` and demonstrates the main features "
   "of the module with print() statements and realistic sample data. Reply with ONE ```python block, then one line: 'Expected output: ...' describing what the user will see.",
 "docs": "You are a Documentation agent. Write short markdown docs for the final code: Overview, Usage example, Functions table, Known limitations.",
}

GUIDE = """### How to run the generated code
1. Create a new folder, for example `my_project`, and open a terminal inside it.
2. Download **Code** as `solution.py`, **Tests** as `test_solution.py` and **Demo** as `demo.py` (buttons below). Keep all three in the same folder.
3. Check Python is installed: `python --version` (3.9 or newer; no extra packages needed).
4. Run the demo: `python demo.py`
5. Run the unit tests: `python -m unittest -v test_solution`
6. On Linux/Mac use `python3` instead of `python`.

The demo script is below. Save it as `demo.py`, or open `solution.py` and import from it in your own code.
"""

def llm(agent, user):
    client = OpenAI()                            # picks OPENAI_API_KEY from environment
    r = client.chat.completions.create(model=MODEL, temperature=0.2,
        messages=[{"role": "system", "content": PROMPTS[agent]}, {"role": "user", "content": user}])
    return r.choices[0].message.content.strip()

def code_of(text):
    m = re.search(r"```(?:python)?\n(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip()

def run_tests(code, tests):
    """Tool feedback: execute generated tests in an isolated temp dir with timeout."""
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "solution.py"), "w", encoding="utf-8").write(code)
        open(os.path.join(d, "test_solution.py"), "w", encoding="utf-8").write(tests)
        try:
            p = subprocess.run([sys.executable, "-m", "unittest", "-v", "test_solution"],
                               cwd=d, capture_output=True, text=True, timeout=20)
            return p.returncode == 0, (p.stdout + p.stderr).strip()
        except subprocess.TimeoutExpired:
            return False, "Timeout: tests ran longer than 20 seconds."

def pipeline(task):
    def ev(agent, status, content="", **kw):
        return json.dumps({"agent": agent, "status": status, "content": content, **kw}) + "\n"
    try:
        yield ev("requirements", "running")
        req = llm("requirements", task)
        yield ev("requirements", "done", req)

        yield ev("programmer", "running")
        code = code_of(llm("programmer", f"Project:\n{task}\n\nRequirements:\n{req}"))
        yield ev("programmer", "done", f"```python\n{code}\n```")

        yield ev("reviewer", "running")
        review = llm("reviewer", f"Requirements:\n{req}\n\nCode:\n```python\n{code}\n```")
        yield ev("reviewer", "done", review)

        yield ev("tester", "running")
        tests = code_of(llm("tester", f"Requirements:\n{req}\n\nCode:\n```python\n{code}\n```"))
        yield ev("tester", "done", f"```python\n{tests}\n```")

        passed = False
        for rnd in range(1, MAX_ROUNDS + 1):
            yield ev("executor", "running")
            passed, out = run_tests(code, tests)
            yield ev("executor", "done" if passed else "fail",
                     f"**Round {rnd}: {'all tests passed' if passed else 'tests failed'}**\n```\n{out[-1800:]}\n```", append=True)
            if passed or rnd == MAX_ROUNDS:
                break
            yield ev("debugger", "running")
            fix = llm("debugger", f"Code:\n```python\n{code}\n```\n\nTests:\n```python\n{tests}\n```\n\n"
                                  f"Review:\n{review}\n\nFailing output:\n{out[-2500:]}")
            code = code_of(fix)
            yield ev("debugger", "done", f"**Round {rnd} fix**\n{fix}", append=True)

        yield ev("docs", "running")
        docs = llm("docs", f"Requirements:\n{req}\n\nFinal code:\n```python\n{code}\n```")
        yield ev("docs", "done", docs)

        yield ev("demo", "running")
        demo_raw = llm("demo", f"Requirements:\n{req}\n\nFinal code:\n```python\n{code}\n```")
        demo = code_of(demo_raw)
        tail = demo_raw.split("```")[-1].strip()
        guide = GUIDE + f"\n#### demo.py\n```python\n{demo}\n```\n{tail}\n"
        yield ev("demo", "done", guide)
        yield ev("final", "done", passed=passed, code=code, tests=tests, docs=docs, demo=demo, guide=guide)
    except Exception as e:                      # e.g. bad API key, no internet, quota
        yield ev("error", "error", f"{type(e).__name__}: {e}")

@app.post("/api/run")
def run():
    task = (request.get_json(silent=True) or {}).get("task", "").strip()
    if not task:
        return {"error": "Project description is empty"}, 400
    if not os.getenv("OPENAI_API_KEY"):
        return {"error": "OPENAI_API_KEY missing. Add it to the .env file and restart."}, 500
    return Response(stream_with_context(pipeline(task)), mimetype="application/x-ndjson",
                    headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})

@app.get("/")
def index():
    return send_from_directory("static", "index.html")

if __name__ == "__main__":
    print(f"Open http://127.0.0.1:5000  (model: {MODEL})")
    app.run(debug=False, threaded=True, port=5000)
