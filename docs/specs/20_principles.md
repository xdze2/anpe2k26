

user data vault

user_profile: description of what the user is actually looking for

companies/Node: directory storing collected data and analyses done

aka informations about candidates (or nodes)


Each information fetch is followed by an "eval" call done by a LLM, to asses the quality, worthisness and novelty of the information obtained, Maintain a summary of all gathered information
identify next source of interesting information to collect

3 layers eval: Data quality, Content value, Novelty and Match delta

(the summarized informations are in point of view of the user profile) - it is not "objectif" information summarization,


The pipeline is oriented toward positive matches: few companies will be strong
positives among many negatives.

raw data are also stored, as a cache, and a way to re-run analyses
every data input is append only, use last timestamp


An IA agent is used to glue the tools togetheers, and take user inputs

Tools
- write/read user profile
- append/read/search to "companies_data"
- Gather information + eval information

Agent autonomous mode: 
for example: gather next 10 pending enrichmentent  


## Information source
  * API: siren cost1
  * web search: cost1, cost2, cost3 
  * web capture: cost1, cost2, cost3 


each source have a level of "cost", and should be prioritized,



### `enrich_company` dispatcher

one entry_point `enrich_company(seed)`, which from current state of the nodes, decided next target for information (decide_next_step)


## Triage rank

not relevant
not interested
not clear enough to decide
interesting
very_interesting

either input from user, or infered from the agent (user_progile, node_summary)