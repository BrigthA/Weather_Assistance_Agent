"""AutoGen weather report agent with a Streamlit frontend."""
import asyncio
import os
import re
from datetime import datetime
from typing import Any

import streamlit as st
from autogen_agentchat.agents import AssistantAgent
from autogen_core.tools import FunctionTool
from autogen_ext.models.openai import OpenAIChatCompletionClient
from ddgs import DDGS
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()


class WeatherReport(BaseModel):
    """Three fields displayed as exactly three short weather lines."""
    weather: str = Field(description="City and current weather conditions, short.")
    temperature: str = Field(description="Temperature and rain forecast, short.")
    advice: str = Field(description="Practical weather advice, short.")


def search_weather(city: str) -> str:
    """Search the web for current weather, temperature, rain forecast, and advice for a city."""
    today = datetime.now().strftime("%Y-%m-%d")
    query = f"{city} weather now temperature rain forecast {today}"
    try:
        results: list[dict[str, Any]] = list(DDGS().text(query, max_results=5))
    except Exception as exc:
        return f"Weather search failed: {exc}"
    if not results:
        return f"No weather search results found for {city}."
    return "\n".join(
        f"Title: {item.get('title', '')}\n"
        f"Details: {item.get('body', '')}\n"
        f"Source: {item.get('href', '')}"
        for item in results
    )


def one_line(value: str) -> str:
    """Remove embedded newlines and excessive whitespace."""
    return re.sub(r"\s+", " ", value).strip()


async def generate_weather_report(city: str) -> WeatherReport:
    """Run the AutoGen agent and always close the model client."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing. Add it to your .env file.")

    model_client = OpenAIChatCompletionClient(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        api_key=api_key,
    )
    try:
        agent = AssistantAgent(
            name="weather_reporter",
            model_client=model_client,
            tools=[FunctionTool(search_weather, description=search_weather.__doc__.strip(), strict=True)],
            reflect_on_tool_use=True,
            output_content_type=WeatherReport,
            max_tool_iterations=2,
            system_message=(
                "You are a professional weather reporting assistant. "
                "Always call search_weather to look up the requested city. "
                "Use only information supported by search results; never invent "
                "a temperature, condition, or rain forecast. "
                "Return three short fields: weather (city and conditions), "
                "temperature (temperature and rain forecast), and advice. "
                "If the search fails or information is missing, explicitly say "
                "that the information is unavailable in the relevant field. "
                "Keep each field to one short sentence with no line breaks."
            ),
        )
        result = await agent.run(task=f"Report current weather for {city}.")
        content = result.messages[-1].content
        if isinstance(content, WeatherReport):
            return content
        if isinstance(content, dict):
            return WeatherReport.model_validate(content)
        if isinstance(content, str):
            return WeatherReport.model_validate_json(content)
        raise ValueError("Unexpected agent response format.")
    finally:
        await model_client.close()


def main() -> None:
    """Render the Streamlit weather frontend."""
    st.set_page_config(page_title="Weather AI Agent", page_icon="🌤️", layout="centered")
    st.markdown(
        """
        <style>
        .block-container {max-width: 780px; padding-top: 3rem;}
        .report-row {
            padding: 14px 18px;
            border: 1px solid rgba(120, 140, 160, .25);
            border-radius: 12px;
            margin-bottom: 10px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.title("🌤️ Weather AI Agent")
    st.caption("Powered by Microsoft AutoGen + OpenAI + DuckDuckGo")

    with st.form("weather_form"):
        city = st.text_input("Enter City", placeholder="Chennai, London, Dubai...")
        submitted = st.form_submit_button("🔎 Get Weather Report", use_container_width=True)

    if submitted:
        city = city.strip()
        if not city:
            st.warning("Please enter a city.")
        else:
            with st.spinner(f"Searching weather for {city}..."):
                try:
                    st.session_state["weather_report"] = asyncio.run(
                        generate_weather_report(city)
                    )
                    st.session_state["weather_city"] = city.title()
                    st.session_state.pop("weather_error", None)
                except Exception as exc:
                    st.session_state.pop("weather_report", None)
                    st.session_state["weather_error"] = str(exc)

    if st.session_state.get("weather_error"):
        st.error(st.session_state["weather_error"])

    report = st.session_state.get("weather_report")
    if report is not None:
        st.subheader(f"Weather in {st.session_state['weather_city']}")
        lines = [
            f"Weather: {one_line(report.weather)}",
            f"Temperature: {one_line(report.temperature)}",
            f"Advice: {one_line(report.advice)}",
        ]
        for icon, line in zip(("🌤️", "🌡️", "💡"), lines):
            st.markdown(f"{icon} {line}")
        st.caption("Based on web search results; may not be real-time.")


if __name__ == "__main__":
    main()
