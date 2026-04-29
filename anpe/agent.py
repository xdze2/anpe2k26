from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from anpe.config import settings
from anpe.profile import profile_system_prompt, read_profile, write_profile
from anpe.tools.naf import register_naf_tools

_model = OpenAIChatModel(
    settings.openrouter_model,
    provider=OpenAIProvider(
        base_url=settings.openrouter_base_url,
        api_key=settings.openrouter_api_key,
    ),
)

agent = Agent(
    _model,
    system_prompt=(
        "Tu es l'Assistant Numérique Pour l'Emploi (ANPE). "
        "Tu aides l'utilisateur à identifier des entreprises, projets ou personnes "
        "qui correspondent à ce qu'il recherche. "
        "Réponds en français sauf si l'utilisateur s'adresse à toi dans une autre langue. "
        "Garde le profil de recherche concis (moins de 400 mots) : synthétise, ne cumule pas. "
        f"\n\n{profile_system_prompt()}"
    ),
)


@agent.tool_plain
def read_search_profile() -> str:
    """Return the user's current search profile."""
    content = read_profile()
    return content if content else "No profile yet."


@agent.tool_plain
def update_search_profile(new_content: str) -> str:
    """Rewrite the user's search profile with new_content.

    new_content should be the complete new profile in markdown.
    Keep it under 400 words — synthesize, don't accumulate.
    Returns a warning if the content is too long.
    """
    warning = write_profile(new_content)
    return warning if warning else "Profile updated."


register_naf_tools(agent)
