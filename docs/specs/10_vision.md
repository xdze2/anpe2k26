ANPE2k26 is a personal job-search IA assistant. Its primary goal is to help the user scan companies (or projects, people) and identify which ones match what he is looking for. The agent accumulates knowledge over time: it learns the user's preferences, gathers data on companies from the web, and records the user's reactions to each one.

It is also a side project aimed to learn and explore working with IA agents.



Possible UI/UX routes:
- terminal base chat app
- browser extension


Key ideas:
brute force search, Active learning, Importance sampling (monte carlo)

Data is accumulated as the user explore and gives feedback. The tools could do automous search session. 


Information source:
- Siren data base (France)
- Web searches and surfs


Key design approach:
- File base storage, local




Tech stack:

Python 3.12, uv, pydantic-ai. LLM calls go through OpenRouter (OpenAI-compatible API).
