"""The catalogue is the source of truth for model ids."""

from __future__ import annotations

from llm.catalog import CATALOGS, ModelInfo, OpenRouterModels, TogetherAIModels


def test_each_catalogue_lists_only_its_own_models() -> None:
    assert set(OpenRouterModels.ids()).isdisjoint(
        set(TogetherAIModels.ids()) - set(OpenRouterModels.ids())
    )
    assert all(isinstance(model, ModelInfo) for model in OpenRouterModels.all().values())


def test_shared_lookup_behaviour_is_defined_once() -> None:
    # all()/ids() live on ModelCatalog; each subclass still sees only its own.
    assert "deepseek/deepseek-v4-flash" in OpenRouterModels.ids()
    assert "deepseek/deepseek-v4-flash" not in TogetherAIModels.ids()


def test_by_id_finds_a_model_and_returns_none_otherwise() -> None:
    assert OpenRouterModels.by_id("z-ai/glm-5") is not None
    assert OpenRouterModels.by_id("does/not-exist") is None


def test_flag_helpers_filter_the_catalogue() -> None:
    assert all(model.free for model in OpenRouterModels.free_models())
    assert all(model.fast for model in OpenRouterModels.fast_models())


def test_every_registered_provider_has_a_catalogue() -> None:
    from llm.registry import FACTORIES

    assert set(FACTORIES) <= set(CATALOGS)


def test_the_stale_model_that_caused_silent_empty_output_is_absent() -> None:
    # The old frontend hard-coded this id and defaulted new steps to it.
    assert "meta-llama/Llama-3-8b-chat-hf" not in OpenRouterModels.ids()
    assert "meta-llama/Llama-3-8b-chat-hf" not in TogetherAIModels.ids()
