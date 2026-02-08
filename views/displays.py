import logging
from game.arenas import Arena
from game.players import Player
import streamlit as st
from views.headers import display_headers
from views.sidebars import display_sidebar
from interfaces.llms import LLM, is_gateway_connected


class Display:
    """
    The User Interface for an Arena using streamlit
    """

    arena: Arena

    def __init__(self, arena: Arena):
        self.arena = arena
        self.progress_container = None

    @staticmethod
    def display_record(rec) -> None:
        """
        Describe the most recent Turn Record on the UI
        """
        if rec.is_invalid_move:
            text = "Illegal last move"
        else:
            text = f"Strategy: {rec.move.strategy}  \n\n"
            text += f"- Gave to {rec.move.give}\n"
            text += f"- Took from {rec.move.take}\n"
        if len(rec.alliances_with) > 0:
            alliances = ", ".join(rec.alliances_with)
            text += f"- :green[In an alliance with {alliances}]\n"
        if len(rec.alliances_against) > 0:
            alliances = ", ".join(rec.alliances_against)
            text += f"- :red[Being ganged up on by {alliances}]"
        st.write(text)

    @staticmethod
    def display_player_title(each) -> None:
        """
        Show the player's title in the heading, colored for winner / loser
        """
        if each.is_dead:
            st.header(f":red[{each.name}]")
        elif each.is_winner:
            st.header(f":green[{each.name}]")
        else:
            st.header(f":blue[{each.name}]")

    def display_model_selector(self, player: Player, index: int) -> None:
        """
        Show two dropdowns: Provider then Model.
        - First dropdown: Select provider (built-in + gateway providers with "Proxy - " prefix)
        - Second dropdown: Select model for that provider
        
        Model selection is locked after the game starts (turn > 1) to ensure
        leaderboard data accurately reflects the models used throughout the game.
        """
        import streamlit as st
        
        # Check if game has started (turn > 1 means at least one turn completed)
        game_started = self.arena.turn > 1
        
        # Build provider list: built-in + gateway providers
        builtin_providers = self._get_builtin_providers()
        gateway_providers = self._get_gateway_providers()
        
        all_providers = builtin_providers.copy()
        for gw_provider in gateway_providers:
            all_providers[f"Proxy - {gw_provider}"] = gateway_providers[gw_provider]
        
        provider_names = list(all_providers.keys())
        
        # Determine current provider from player's model
        current_model = player.llm.model_name if player.llm else None
        current_provider = self._get_provider_for_model(current_model, all_providers)
        
        try:
            provider_idx = provider_names.index(current_provider) if current_provider else 0
        except ValueError:
            provider_idx = 0
        
        # First dropdown: Provider
        col1, col2 = st.columns(2)
        
        with col1:
            selected_provider = st.selectbox(
                "Provider",
                options=provider_names,
                index=provider_idx,
                key=f"provider_select_{index}",
                help="Select LLM provider" if not game_started else "Locked - game in progress",
                disabled=game_started
            )
        
        # Get models for selected provider
        if selected_provider in all_providers:
            available_models = all_providers[selected_provider]
        else:
            available_models = []
        
        # Find current model index in provider's models
        if current_model in available_models:
            model_idx = available_models.index(current_model)
        else:
            model_idx = 0
        
        with col2:
            if available_models:
                selected_model = st.selectbox(
                    "Model",
                    options=available_models,
                    index=model_idx,
                    key=f"model_select_{index}",
                    help="Select model" if not game_started else "Locked - game in progress",
                    disabled=game_started
                )
            else:
                st.selectbox("Model", options=["No models available"], key=f"model_select_{index}", disabled=True)
                selected_model = None
        
        # Update player if model changed (only if game hasn't started)
        if not game_started and selected_model and selected_model != current_model:
            try:
                # Check if this is a gateway model
                is_proxy = selected_provider.startswith("Proxy - ")
                new_llm = LLM.for_model_name(selected_model, player.llm.temperature if player.llm else 0.7)
                player.llm = new_llm
                if hasattr(new_llm, '_setup_error') and new_llm._setup_error:
                    st.warning(f"⚠️ {new_llm._setup_error[:50]}...")
            except Exception as e:
                st.error(f"Failed to load model: {e}")
        
        # Show warning if current model has setup error
        if player.llm and hasattr(player.llm, '_setup_error') and player.llm._setup_error:
            st.warning(f"⚠️ API key missing - select another model")
    
    def _get_builtin_providers(self) -> dict:
        """
        Get built-in providers with allowed models.
        
        Only these 4 models can be used with API keys:
        - openai/gpt-oss-120b (Groq)
        - gpt-5-nano (OpenAI)
        - grok-4-fast (xAI)
        - claude-haiku-4-5 (Anthropic)
        
        Gateway models are unrestricted.
        """
        import os
        
        providers = {}
        
        # Groq - openai/gpt-oss-120b
        if os.getenv("GROQ_API_KEY"):
            providers["Groq"] = ["openai/gpt-oss-120b"]
        
        # OpenAI - gpt-5-nano
        if os.getenv("OPENAI_API_KEY"):
            providers["OpenAI"] = ["gpt-5-nano"]
        
        # Grok / xAI - grok-4-fast
        if os.getenv("XAI_API_KEY") or os.getenv("GROK_API_KEY"):
            providers["Grok"] = ["grok-4-fast"]
        
        # Anthropic - claude-haiku-4-5
        if os.getenv("ANTHROPIC_API_KEY"):
            providers["Anthropic"] = ["claude-haiku-4-5"]
        
        # Gemini - gemini-2.5-flash-lite
        if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
            providers["Gemini"] = ["gemini-2.5-flash-lite"]
        
        return providers
    
    def _get_gateway_providers(self) -> dict:
        """Get providers from connected gateway."""
        session = st.session_state.get("gateway_session")
        if not session or session.is_expired():
            return {}
        
        providers = {}
        for resource in session.get_resources_by_type("llm"):
            provider_name = resource.provider.capitalize()
            # Use actual models from the gateway, or default if none
            if resource.models:
                providers[provider_name] = resource.models
            else:
                # Fallback: use a default model name based on provider
                providers[provider_name] = [f"{resource.provider}/default"]
        
        return providers
    
    def _get_provider_for_model(self, model_name: str, providers: dict) -> str:
        """Find which provider owns a given model."""
        if not model_name:
            return list(providers.keys())[0] if providers else ""
        
        for provider, models in providers.items():
            if model_name in models:
                return provider
        
        # Fallback: try to guess from model name prefix
        return list(providers.keys())[0] if providers else ""

    def display_player(self, each: Player, index: int) -> None:
        """
        Show the player, including title, model selector, coins, expander and latest turn
        """
        self.display_player_title(each)
        
        # Model selector dropdown
        self.display_model_selector(each, index)
        
        records = each.records
        st.metric("Coins", each.coins, each.coins - each.prior_coins)
        with st.expander("Inner thoughts", expanded=False):
            st.markdown(
                f'<p class="small-font">{each.report()}</p>', unsafe_allow_html=True
            )
        if len(records) > 0:
            record = records[-1]
            self.display_record(record)

    def do_turn(self) -> None:
        """
        Callback to run a turn, either triggered from the Run Turn button, or automatically if a game is on auto
        """
        logging.info("Kicking off turn")
        progress_text = "Kicking off turn"
        with self.progress_container.container():
            bar = st.progress(0.0, text=progress_text)
        self.arena.do_turn(bar.progress)
        bar.empty()

    def do_auto_turn(self) -> None:
        """
        Callback to run a turn on automatic mode, after the Run Game button has been pressed
        """
        st.session_state.auto_move = False
        self.do_turn()
        if not self.arena.is_game_over:
            st.session_state.auto_move = True

    def display_page(self) -> None:
        """
        Show the full UI, including columns for each player, and handle auto run if the Run Game button was pressed
        """
        display_sidebar()
        display_headers(self.arena, self.do_turn, self.do_auto_turn)
        self.progress_container = st.empty()
        player_columns = st.columns(len(self.arena.players))

        for index, player_column in enumerate(player_columns):
            player = self.arena.players[index]
            with player_column:
                inner = st.empty()
                with inner.container():
                    self.display_player(player, index)

        if st.session_state.auto_move:
            self.do_auto_turn()
            st.rerun()

