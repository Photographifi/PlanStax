import os

import pytest

# The tests check French texts, whatever the language of the system or the one chosen in the menu.
os.environ["PLANSTAX_LANG"] = "fr"


@pytest.fixture(autouse=True)
def french():
    from planstax import i18n
    i18n.set_language("fr")
    yield
    i18n.set_language("fr")
