# AgentForge: LLM-Based Multi-Agent System for Software Engineering

Implementation of the concept paper **"LLM-Based Agentic Systems for Software Engineering: Challenges and Opportunities"** (Tang & Runkler, arXiv:2601.09822, 2026).

The user describes a small software project in plain English. A team of specialised LLM agents then runs the SDLC stages the paper reviews and shows each step live in a web UI.

## 1. Mapping: paper -> project

| Paper section | Agent in this project | What it does |
|---|---|---|
| 3.1 Requirements Engineering (MARE, user-story agents) | Requirements agent | User stories, acceptance criteria, signatures, edge cases |
| 3.2 Code Generation (role specialisation, PairCoder) | Programmer agent | Generates Python module from requirements |
| 3.3 Static Code Checking (GPTLENS, CodeAgent reviewer) | Static review agent | Critic audits code, severity list, PASS/FAIL verdict |
| 3.4 Testing and QA (CoverUp, unit test agents) | Test agent + Test runner | Writes `unittest` file, executes it as tool feedback |
| 3.5 Debugging / Program repair (ChatRepair, AutoSD) | Debug agent | Gets failing output + review, returns fixed code; loop up to `MAX_ROUNDS` |
| Run guide (added feature) | Run-guide agent | Writes `demo.py` and step-by-step instructions to run the generated code |
| 2.2 / 5: documentation agent, modularity | Documentation agent | Writes usage docs for final code |

Paper concepts used: role specialisation, modular agents (each has its own prompt in `PROMPTS`), **iterative refinement with tool feedback** (code is really executed), peer review between agents, orchestrator (`pipeline()`), cost control (low-cost model + bounded rounds), human-in-the-loop (user can edit the description and rerun).

## 2. Architecture

```
Browser (static/index.html)
   | POST /api/run  (streamed NDJSON events)
Flask orchestrator (app.py: pipeline())
   |--> Requirements -> Programmer -> Reviewer -> Tester
   |--> loop (<= MAX_ROUNDS): Executor(unittest in temp dir) --fail--> Debugger --> code'
   |--> Documentation -> final result
   `--> OpenAI Chat Completions API (key from .env)
```
Each agent = one system prompt + one OpenAI call. The orchestrator passes outputs between them and streams every event to the UI.

## 3. Where to put the OpenAI API key

1. Copy `.env.example` to `.env`
2. Open `.env` and set `OPENAI_API_KEY=sk-...` (your key). Optional: `OPENAI_MODEL` (default `gpt-4o-mini`, cheap and fast; use `gpt-4o` for better quality), `MAX_ROUNDS`.

The key is read in `app.py` through `load_dotenv()` and `OpenAI()`. Never hardcode it or upload `.env` to GitHub.

## 4. How to run

Requirement: Python 3.9+ and internet.

**Windows**
```
cd agentic-se
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env        (then edit .env and add your key)
python app.py
```
**Linux / Mac**
```
cd agentic-se
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # edit .env and add your key
python3 app.py
```
Open **http://127.0.0.1:5000** in the browser.

## 5. Demo flow (for presentation)
1. Click a sample chip (e.g. "Library system") -> **Build with agents**.
2. Show the cards turning blue (working) -> green (done) one by one.
3. After the build, the **How to run** tab shows exact steps (save files, run `demo.py`, run unit tests) and the Download buttons give `solution.py`, `test_solution.py`, `demo.py`.
4. Open the Test runner card: show real test output. If a round fails, show the Debug agent fixing it.
4. Final panel: Code / Tests / Docs tabs, Copy and Download buttons. Toggle dark mode.

## 6. Project structure
```
agentic-se/
  app.py              backend, agents, orchestrator, test runner
  static/index.html   frontend (HTML+CSS+JS, no build step)
  requirements.txt    flask, openai, python-dotenv
  .env.example        template for API key and settings
  README.md           this documentation
```

## 7. Troubleshooting
- **OPENAI_API_KEY missing**: `.env` not created or app not restarted.
- **AuthenticationError / 401**: wrong key. **RateLimit / quota**: billing or credits missing in the OpenAI account.
- **Model not found**: change `OPENAI_MODEL` to one your account can use.
- Page blank / no streaming: use Chrome or Edge, and open via `http://127.0.0.1:5000`, not by double-clicking the HTML.
- Fonts need internet; without it the UI falls back to system fonts and still works.

## 8. Limitations and future work (from paper, Section 5)
- Targets single-module Python projects, not full repositories.
- Generated code runs locally in a temp folder with a 20 s timeout. It is **not sandboxed**, so use only in a trusted/demo environment (Docker sandbox is the next step).
- Future: domain-specific agents (security auditor), RAG over project data, human approval checkpoints, model distillation for lower cost, benchmark evaluation (HumanEval, Tests4Py), MCP/A2A protocols, frameworks such as LangGraph or AutoGen.

## 9. Likely viva questions
- *Why multi-agent over a single LLM?* Specialisation, modularity, parallelism, tool use (paper Sec 2.2).
- *How is correctness verified?* Tests are executed; failures drive the repair loop (feedback-driven repair, Sec 3.5).
- *How is cost controlled?* Small model by default, max rounds, short prompts (Sec 5).
- *Privacy?* Code goes to the OpenAI API; the paper suggests open-source local LLMs (LLaMA, DeepSeek) for sensitive code. Only `llm()` needs changing for that.

## 10. Reference
Tang, Y. and Runkler, T.: *LLM-Based Agentic Systems for Software Engineering: Challenges and Opportunities*, arXiv:2601.09822v2, 2026.
