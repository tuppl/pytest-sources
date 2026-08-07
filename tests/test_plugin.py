from pytest_sources import plugin


def test_plugin_is_registered(pytestconfig):
    assert pytestconfig.pluginmanager.hasplugin("sources")
    assert pytestconfig.pluginmanager.get_plugin("sources") is plugin
